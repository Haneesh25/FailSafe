"""Tests for LangGraph integration."""

import pytest

from failsafe.core.engine import FailSafe
from failsafe.integrations.langchain.graph import FailSafeGraph


class MockStateGraph:
    """Minimal mock of LangGraph StateGraph for testing."""

    def __init__(self):
        self.nodes: dict = {}
        self.edges: list = []

    def add_node(self, name, func):
        self.nodes[name] = func

    def add_edge(self, source, target):
        self.edges.append((source, target))

    def compile(self, **kwargs):
        return self


@pytest.fixture
def fs():
    return FailSafe(mode="warn", audit_db=":memory:")


class TestFailSafeGraph:
    def test_add_validated_edge_creates_validation_node(self, fs):
        graph = MockStateGraph()
        graph.add_node("kyc", lambda s: s)
        graph.add_node("onboarding", lambda s: s)

        fs_graph = FailSafeGraph(graph, failsafe=fs)
        fs_graph.add_validated_edge("kyc", "onboarding")

        # Should have injected a validation node
        assert "__fs_validate_kyc_onboarding__" in graph.nodes
        # Should have 2 edges: kyc -> validate, validate -> onboarding
        assert ("kyc", "__fs_validate_kyc_onboarding__") in graph.edges
        assert ("__fs_validate_kyc_onboarding__", "onboarding") in graph.edges

    @pytest.mark.asyncio
    async def test_validation_node_passes_clean_data(self, fs):
        graph = MockStateGraph()
        graph.add_node("a", lambda s: s)
        graph.add_node("b", lambda s: s)

        fs.contract(name="a-to-b", source="a", target="b", allow=["name", "status"])

        fs_graph = FailSafeGraph(graph, failsafe=fs)
        fs_graph.add_validated_edge("a", "b")

        validate_fn = graph.nodes["__fs_validate_a_b__"]
        state = {"name": "Alice", "status": "ok"}
        result = await validate_fn(state)
        assert result == state  # Should pass through unchanged

    @pytest.mark.asyncio
    async def test_validation_node_catches_violations(self, fs):
        fs.mode = "block"
        graph = MockStateGraph()
        graph.add_node("a", lambda s: s)
        graph.add_node("b", lambda s: s)

        fs.contract(name="a-to-b", source="a", target="b", deny=["secret"])

        fs_graph = FailSafeGraph(graph, failsafe=fs)
        fs_graph.add_validated_edge("a", "b")

        validate_fn = graph.nodes["__fs_validate_a_b__"]
        state = {"name": "Alice", "secret": "password123"}
        result = await validate_fn(state)
        assert result.get("__failsafe_blocked__") is True

    def test_passthrough_methods(self, fs):
        graph = MockStateGraph()
        fs_graph = FailSafeGraph(graph, failsafe=fs)

        fs_graph.add_node("x", lambda s: s)
        assert "x" in graph.nodes

        fs_graph.add_edge("x", "y")
        assert ("x", "y") in graph.edges

        compiled = fs_graph.compile()
        assert compiled is graph

    def test_extract_keys(self, fs):
        graph = MockStateGraph()
        graph.add_node("a", lambda s: s)
        graph.add_node("b", lambda s: s)

        fs_graph = FailSafeGraph(graph, failsafe=fs)
        state = {"name": "Alice", "secret": "hidden", "extra": "data"}

        extracted = fs_graph._extract_handoff_data(state, "a", "b", extract_keys=["name"])
        assert extracted == {"name": "Alice"}
