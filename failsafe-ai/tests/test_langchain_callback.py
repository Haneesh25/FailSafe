"""Tests for LangChain callback handler."""

import pytest

from failsafe.core.engine import FailSafe
from failsafe.integrations.langchain.callback import FailSafeCallbackHandler


@pytest.fixture
def fs():
    return FailSafe(mode="warn", audit_db=":memory:")


@pytest.fixture
def handler(fs):
    return FailSafeCallbackHandler(failsafe=fs, mode="warn")


@pytest.mark.asyncio
async def test_chain_tracking(handler):
    await handler.on_chain_start({"name": "chain_a"}, {"input": "test"})
    assert handler._chain_stack == ["chain_a"]
    await handler.on_chain_end({"output": "result"})
    assert handler._chain_stack == []


@pytest.mark.asyncio
async def test_nested_chains_validate_handoff(fs, handler):
    # Define a contract between chain_a and chain_b
    fs.contract(
        name="a-to-b",
        source="chain_a",
        target="chain_b",
        deny=["secret"],
    )

    await handler.on_chain_start({"name": "chain_a"}, {"input": "test"})
    await handler.on_chain_start({"name": "chain_b"}, {"nested": True})
    await handler.on_chain_end({"output": "ok", "secret": "hidden"})

    # Should have caught the denied field
    assert len(handler.violations) > 0


@pytest.mark.asyncio
async def test_tool_tracking(handler):
    await handler.on_chain_start({"name": "my_agent"}, {})
    await handler.on_tool_start({"name": "search_tool"}, "query")
    await handler.on_tool_end("result")

    assert any(e["event"] == "tool_start" for e in handler.audit_log)


@pytest.mark.asyncio
async def test_audit_log_populated(handler):
    await handler.on_chain_start({"name": "agent"}, {"x": 1})
    await handler.on_chain_end({"y": 2})

    assert len(handler.audit_log) == 2
    assert handler.audit_log[0]["event"] == "chain_start"
    assert handler.audit_log[1]["event"] == "chain_end"


@pytest.mark.asyncio
async def test_trace_id_consistent(handler):
    await handler.on_chain_start({"name": "a"}, {})
    await handler.on_tool_start({"name": "t"}, "")
    await handler.on_tool_end("")
    await handler.on_chain_end({})

    trace_ids = {e["trace_id"] for e in handler.audit_log}
    assert len(trace_ids) == 1  # All events share the same trace ID
