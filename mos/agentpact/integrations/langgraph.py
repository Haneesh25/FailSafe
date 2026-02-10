"""LangGraph integration — validates handoffs at state graph edges."""

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
    """Wraps StateGraph to inject validation at every edge."""

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
        return _PatchedStateGraph(state_schema, self)

    @staticmethod
    def _default_field_extractor(state: dict) -> dict:
        # Skip internal keys and empty defaults that LangGraph initializes
        return {
            k: v for k, v in state.items()
            if not k.startswith("_agentpact_")
            and v not in ("", 0, 0.0, None, [], {}, False)
        }

    @staticmethod
    def _default_metadata_extractor(state: dict) -> dict:
        return dict(state.get(AGENTPACT_METADATA_KEY) or {})

    def _validate_transition(
        self, from_node: str, to_node: str, state: dict
    ) -> HandoffValidationResult:
        data = self._field_extractor(state)
        metadata = self._metadata_extractor(state)

        # Narrow to contract-scoped fields (LangGraph state accumulates across nodes)
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

            if last_node:  # skip entry point
                result = vg._validate_transition(last_node, node_name, state)
                new_results.append(result.to_dict())

                if result.is_blocked and vg.block_on_violation:
                    raise HandoffBlockedError(result)

            output = fn(state)

            # Only emit new results; the reducer handles accumulation
            if isinstance(output, dict):
                output[AGENTPACT_STATE_KEY] = node_name
                output[AGENTPACT_RESULTS_KEY] = new_results
            return output

        wrapper.__name__ = fn.__name__
        wrapper.__qualname__ = fn.__qualname__
        return wrapper
