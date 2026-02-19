"""FailSafeGraph — LangGraph integration with validated edges."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from failsafe.core.engine import FailSafe


class FailSafeGraph:
    """Wraps a LangGraph StateGraph with FailSafe validation on edges.

    Usage:
        graph = StateGraph(MyState)
        graph.add_node("kyc", kyc_agent)
        graph.add_node("onboarding", onboarding_agent)

        fs_graph = FailSafeGraph(graph, failsafe=fs)
        fs_graph.add_validated_edge("kyc", "onboarding")
        app = fs_graph.compile()
    """

    def __init__(self, graph: Any, failsafe: "FailSafe"):
        self.graph = graph
        self.fs = failsafe

    def add_validated_edge(
        self,
        source: str,
        target: str,
        extract_keys: list[str] | None = None,
    ) -> None:
        """Add an edge with FailSafe validation injected between source and target.

        Inserts a validation node between source and target:
        source -> __fs_validate_{source}_{target}__ -> target

        Args:
            source: Source node name.
            target: Target node name.
            extract_keys: Optional list of state keys to include in the handoff payload.
                         If None, all state keys are included.
        """
        validation_node_name = f"__fs_validate_{source}_{target}__"
        fs = self.fs

        async def validation_node(state: dict[str, Any]) -> dict[str, Any]:
            payload = self._extract_handoff_data(state, source, target, extract_keys)
            result = await fs.handoff(
                source=source, target=target, payload=payload
            )

            if not result.passed and fs.mode == "block":
                return {
                    **state,
                    "__failsafe_blocked__": True,
                    "__failsafe_violations__": [
                        v.model_dump() for v in result.violations
                    ],
                }

            if result.sanitized_payload and not result.passed:
                return {**state, **result.sanitized_payload}
            return state

        self.graph.add_node(validation_node_name, validation_node)
        self.graph.add_edge(source, validation_node_name)
        self.graph.add_edge(validation_node_name, target)

    def add_node(self, name: str, func: Any) -> None:
        """Pass-through to the underlying graph."""
        self.graph.add_node(name, func)

    def add_edge(self, source: str, target: str) -> None:
        """Pass-through to the underlying graph (no validation)."""
        self.graph.add_edge(source, target)

    def set_entry_point(self, name: str) -> None:
        """Pass-through to the underlying graph."""
        self.graph.set_entry_point(name)

    def set_finish_point(self, name: str) -> None:
        """Pass-through to the underlying graph."""
        self.graph.set_finish_point(name)

    def compile(self, **kwargs: Any) -> Any:
        return self.graph.compile(**kwargs)

    def _extract_handoff_data(
        self,
        state: dict[str, Any],
        source: str,
        target: str,
        extract_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        """Extract handoff data from state."""
        if extract_keys:
            return {k: state[k] for k in extract_keys if k in state}
        # Exclude internal failsafe keys
        return {
            k: v
            for k, v in state.items()
            if not k.startswith("__failsafe_")
        }
