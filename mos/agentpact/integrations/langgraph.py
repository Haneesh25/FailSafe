"""
AgentPact LangGraph Integration

Validates agent-to-agent handoffs at LangGraph state graph edges.
Wraps node functions so that every state transition is checked against
the contract registry before the receiving node executes.

Usage:
    from agentpact.integrations.langgraph import ValidatedGraph

    vg = ValidatedGraph(registry, audit_logger)
    vg.register_policy_pack(FinancePolicyPack())

    graph = vg.build(State)
    graph.add_node("research", research_fn)
    graph.add_node("trading", trading_fn)
    graph.add_edge(START, "research")
    graph.add_edge("research", "trading")
    graph.add_edge("trading", END)

    app = graph.compile()
    result = app.invoke(initial_state)
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Type

from langgraph.graph import StateGraph, END

from ..core.models import (
    ContractRegistry,
    HandoffDirection,
    HandoffPayload,
    HandoffValidationResult,
    ValidationResult,
)
from ..core.engine import ValidationEngine
from ..audit.logger import AuditLogger
from ..interceptor.middleware import HandoffBlockedError


AGENTPACT_STATE_KEY = "_agentpact_last_node"
AGENTPACT_RESULTS_KEY = "_agentpact_results"
AGENTPACT_METADATA_KEY = "_agentpact_metadata"


class ValidatedGraph:
    """
    Wraps LangGraph's StateGraph to inject AgentPact validation at every edge.

    Each node function is wrapped so that before it runs, the state transition
    from the previous node is validated against the contract registry. If the
    handoff violates a contract with CRITICAL or HIGH severity, a
    HandoffBlockedError is raised (configurable).

    The graph state must include:
        _agentpact_last_node: str   — tracks the source node
        _agentpact_results: list    — accumulates validation results (dicts)
        _agentpact_metadata: dict   — handoff metadata (action, request_id, etc.)

    Agent node functions should set _agentpact_metadata in their output
    to specify the handoff action and audit fields (request_id, timestamp,
    initiator, human_approved). This keeps handoff metadata separate from
    domain data fields (e.g. trade "action" vs handoff "action").
    """

    def __init__(
        self,
        registry: ContractRegistry,
        audit_logger: Optional[AuditLogger] = None,
        block_on_violation: bool = True,
        field_extractor: Optional[Callable[[dict], dict]] = None,
        metadata_extractor: Optional[Callable[[dict], dict]] = None,
    ):
        self.registry = registry
        self.engine = ValidationEngine(registry)
        self.audit = audit_logger or AuditLogger()
        self.block_on_violation = block_on_violation
        self._field_extractor = field_extractor or self._default_field_extractor
        self._metadata_extractor = metadata_extractor or self._default_metadata_extractor
        self._callbacks: list[Callable[[HandoffValidationResult], None]] = []

    def register_policy_pack(self, policy_pack: Any) -> None:
        self.engine.register_policy_pack(policy_pack)

    def on_violation(self, callback: Callable[[HandoffValidationResult], None]) -> None:
        self._callbacks.append(callback)

    def build(self, state_schema: Type) -> _PatchedStateGraph:
        """
        Create a StateGraph with AgentPact validation wired in.

        Returns a _PatchedStateGraph that behaves like StateGraph but
        wraps node functions with validation logic.
        """
        return _PatchedStateGraph(state_schema, self)

    @staticmethod
    def _default_field_extractor(state: dict) -> dict:
        """
        Extract handoff data fields from state, excluding internal keys
        and empty/default values.

        LangGraph state always contains every declared field. Fields with
        empty-string, zero, None, or empty-list values are excluded so
        that AgentPact doesn't flag unrelated fields as "unexpected".
        """
        return {
            k: v for k, v in state.items()
            if not k.startswith("_agentpact_")
            and v not in ("", 0, 0.0, None, [], {}, False)
        }

    @staticmethod
    def _default_metadata_extractor(state: dict) -> dict:
        """
        Extract handoff metadata from the _agentpact_metadata state key.

        Agent nodes set _agentpact_metadata to specify the handoff action
        and audit trail fields. This avoids collisions between domain data
        (e.g. trade action "buy") and handoff metadata (e.g. action "recommend").
        """
        return dict(state.get(AGENTPACT_METADATA_KEY) or {})

    def _validate_transition(
        self, from_node: str, to_node: str, state: dict
    ) -> HandoffValidationResult:
        """Run AgentPact validation for a state transition."""
        data = self._field_extractor(state)
        metadata = self._metadata_extractor(state)

        # In LangGraph, state accumulates fields from all nodes. To avoid
        # false "unexpected field" warnings, narrow the data to only fields
        # defined in the contract schema for this specific edge.
        contract = self.registry.get_contract_for_handoff(from_node, to_node)
        if contract and contract.request_schema:
            contract_fields = {f.name for f in contract.request_schema}
            data = {k: v for k, v in data.items() if k in contract_fields}

        payload = HandoffPayload(data=data, metadata=metadata)

        result = self.engine.validate_handoff(
            consumer_name=from_node,
            provider_name=to_node,
            payload=payload,
            direction=HandoffDirection.REQUEST,
        )

        self.audit.log(result)

        if result.total_violations > 0:
            for cb in self._callbacks:
                cb(result)

        return result


class _PatchedStateGraph:
    """
    A thin wrapper around StateGraph that intercepts add_node to wrap
    node functions with AgentPact validation.
    """

    def __init__(self, state_schema: Type, validated_graph: ValidatedGraph):
        self._vg = validated_graph
        self._inner = StateGraph(state_schema)
        self._node_names: set[str] = set()

    def add_node(self, name: str, fn: Callable) -> _PatchedStateGraph:
        wrapped = self._wrap_node(name, fn)
        self._inner.add_node(name, wrapped)
        self._node_names.add(name)
        return self

    def add_edge(self, from_node: str, to_node: str) -> _PatchedStateGraph:
        self._inner.add_edge(from_node, to_node)
        return self

    def add_conditional_edges(
        self, source: str, path: Callable, path_map: Optional[dict] = None, **kwargs
    ) -> _PatchedStateGraph:
        if path_map is not None:
            self._inner.add_conditional_edges(source, path, path_map, **kwargs)
        else:
            self._inner.add_conditional_edges(source, path, **kwargs)
        return self

    def set_entry_point(self, node: str) -> _PatchedStateGraph:
        self._inner.set_entry_point(node)
        return self

    def set_finish_point(self, node: str) -> _PatchedStateGraph:
        self._inner.set_finish_point(node)
        return self

    def compile(self, **kwargs):
        return self._inner.compile(**kwargs)

    def _wrap_node(self, node_name: str, fn: Callable) -> Callable:
        vg = self._vg

        def wrapper(state: dict) -> dict:
            last_node = state.get(AGENTPACT_STATE_KEY, "")
            new_results: list[dict] = []

            # Validate if there is a source node (skip for entry point)
            if last_node:
                result = vg._validate_transition(last_node, node_name, state)
                new_results.append(result.to_dict())

                if result.is_blocked and vg.block_on_violation:
                    raise HandoffBlockedError(result)

            # Call the real node function
            output = fn(state)

            # Track provenance. Only emit NEW results — the Annotated[list,
            # operator.add] reducer on _agentpact_results handles accumulation.
            if isinstance(output, dict):
                output[AGENTPACT_STATE_KEY] = node_name
                output[AGENTPACT_RESULTS_KEY] = new_results
            return output

        wrapper.__name__ = fn.__name__
        wrapper.__qualname__ = fn.__qualname__
        return wrapper
