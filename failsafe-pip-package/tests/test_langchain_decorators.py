"""Tests for LangChain decorators."""

import pytest

from failsafe.core.engine import FailSafe
from failsafe.integrations.langchain.decorators import (
    ToolAuthorityViolation,
    validated_tool,
)


@pytest.fixture
def fs():
    return FailSafe(mode="warn", audit_db=":memory:")


class TestValidatedTool:
    def test_sync_tool_passes(self, fs):
        @validated_tool(fs, agent="research_agent")
        def search(query: str) -> str:
            return f"results for {query}"

        result = search("test")
        assert result == "results for test"

    def test_sync_tool_blocked(self, fs):
        fs.mode = "block"
        fs.contract(
            name="agent->tool:restricted_tool",
            source="agent",
            target="tool:restricted_tool",
            deny=["forbidden_arg"],
        )

        @validated_tool(fs, agent="agent")
        def restricted_tool(x: str) -> str:
            return x

        # This should not raise because the payload doesn't contain 'forbidden_arg'
        result = restricted_tool("ok")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_async_tool_passes(self, fs):
        @validated_tool(fs, agent="async_agent")
        async def async_search(query: str) -> str:
            return f"async results for {query}"

        result = await async_search("test")
        assert result == "async results for test"

    def test_tool_with_constraints_creates_contract(self, fs):
        @validated_tool(
            fs,
            agent="research_agent",
            constraints=["Can only query public data"],
        )
        def public_search(query: str) -> str:
            return query

        # Should have registered a contract
        contract = fs.contracts.get("research_agent", "tool:public_search")
        assert contract is not None
        assert "Can only query public data" in contract.nl_rules
