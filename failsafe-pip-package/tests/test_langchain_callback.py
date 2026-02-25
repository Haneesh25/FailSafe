"""Tests for LangChain callback handler."""

from types import SimpleNamespace

import pytest

from failsafe.core.engine import FailSafe
from failsafe.integrations.langchain.callback import FailSafeCallbackHandler


@pytest.fixture
def fs():
    return FailSafe(mode="warn", audit_db=":memory:")


@pytest.fixture
def handler(fs):
    return FailSafeCallbackHandler(failsafe=fs, mode="warn")


# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# New tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chain_inputs_tracked(handler):
    """on_chain_start stores inputs in _chain_inputs."""
    await handler.on_chain_start({"name": "planner"}, {"goal": "buy milk", "budget": 10})
    assert "planner" in handler._chain_inputs
    assert handler._chain_inputs["planner"] == {"goal": "buy milk", "budget": 10}


@pytest.mark.asyncio
async def test_handoff_audit_entry_on_nested_chain_end(fs, handler):
    """After nested chain end, audit_log contains a handoff entry with expected keys."""
    await handler.on_chain_start({"name": "outer"}, {"x": 1})
    await handler.on_chain_start({"name": "inner"}, {"y": 2})
    await handler.on_chain_end({"result": "done"})

    handoff_entries = [e for e in handler.audit_log if e["event"] == "handoff"]
    assert len(handoff_entries) == 1
    h = handoff_entries[0]
    assert h["source"] == "outer"
    assert h["target"] == "inner"
    assert "passed" in h
    assert h["payload_keys"] == ["result"]


@pytest.mark.asyncio
async def test_llm_start_tracked(handler):
    """on_llm_start records model info in the audit log."""
    await handler.on_chain_start({"name": "agent"}, {})
    await handler.on_llm_start(
        {"kwargs": {"model_name": "gpt-4"}, "id": ["langchain", "llms", "openai"]},
        ["What is 2+2?"],
    )

    llm_entries = [e for e in handler.audit_log if e["event"] == "llm_start"]
    assert len(llm_entries) == 1
    assert llm_entries[0]["model"] == "gpt-4"
    assert llm_entries[0]["agent"] == "agent"
    assert llm_entries[0]["prompt_count"] == 1


@pytest.mark.asyncio
async def test_llm_start_fallback_model_name(handler):
    """on_llm_start falls back to serialized id when model_name is absent."""
    await handler.on_chain_start({"name": "agent"}, {})
    await handler.on_llm_start(
        {"id": ["langchain", "llms", "anthropic"]},
        ["Hello"],
    )
    llm_entries = [e for e in handler.audit_log if e["event"] == "llm_start"]
    assert llm_entries[0]["model"] == "anthropic"


@pytest.mark.asyncio
async def test_llm_end_tracked(handler):
    """on_llm_end captures token_usage from the response."""
    await handler.on_chain_start({"name": "agent"}, {})

    mock_response = SimpleNamespace(
        llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 20}}
    )
    await handler.on_llm_end(mock_response)

    llm_entries = [e for e in handler.audit_log if e["event"] == "llm_end"]
    assert len(llm_entries) == 1
    assert llm_entries[0]["token_usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 20,
    }
    assert llm_entries[0]["agent"] == "agent"


@pytest.mark.asyncio
async def test_llm_end_no_token_usage(handler):
    """on_llm_end handles missing llm_output gracefully."""
    await handler.on_chain_start({"name": "agent"}, {})
    mock_response = SimpleNamespace(llm_output=None)
    await handler.on_llm_end(mock_response)

    llm_entries = [e for e in handler.audit_log if e["event"] == "llm_end"]
    assert llm_entries[0]["token_usage"] == {}


@pytest.mark.asyncio
async def test_summary_method(handler):
    """summary() returns the correct structure after a full chain simulation."""
    # Simulate: outer chain -> inner chain with tool call
    await handler.on_chain_start({"name": "orchestrator"}, {"task": "search"})
    await handler.on_chain_start({"name": "searcher"}, {"query": "test"})
    await handler.on_tool_start({"name": "web_search"}, "test query")
    await handler.on_tool_end("search results")
    await handler.on_chain_end({"answer": "42"})
    await handler.on_chain_end({"final": "done"})

    s = handler.summary()
    assert s["trace_id"] == handler._trace_id
    assert s["total_events"] == len(handler.audit_log)
    assert set(s["chains_seen"]) == {"orchestrator", "searcher"}
    assert s["tools_called"] == ["web_search"]
    assert len(s["handoffs"]) == 1
    assert s["handoffs"][0]["source"] == "orchestrator"
    assert s["handoffs"][0]["target"] == "searcher"
    assert isinstance(s["violations"], list)
    assert s["total_violations"] == len(handler.violations)


@pytest.mark.asyncio
async def test_repr(handler):
    """__repr__ includes trace_id prefix and counts."""
    await handler.on_chain_start({"name": "a"}, {})
    await handler.on_chain_end({})

    r = repr(handler)
    assert r.startswith("<FailSafeCallbackHandler trace=")
    assert "events=2" in r
    assert "violations=0" in r


@pytest.mark.asyncio
async def test_chain_inputs_cleaned_up(handler):
    """After chain end, inputs for that chain are removed from _chain_inputs."""
    await handler.on_chain_start({"name": "step_one"}, {"data": "hello"})
    assert "step_one" in handler._chain_inputs

    await handler.on_chain_end({"result": "world"})
    assert "step_one" not in handler._chain_inputs


@pytest.mark.asyncio
async def test_handler_as_observe_integration(fs):
    """observe(framework='langchain', dashboard=False) returns a handler that works end-to-end."""
    from failsafe.observe import observe

    handler = observe(framework="langchain", dashboard=False)
    assert isinstance(handler, FailSafeCallbackHandler)

    # Run a full chain simulation through the handler
    await handler.on_chain_start({"name": "planner"}, {"goal": "test"})
    await handler.on_llm_start(
        {"kwargs": {"model_name": "gpt-4"}, "id": ["openai"]},
        ["Plan something"],
    )
    await handler.on_llm_end(SimpleNamespace(llm_output={"token_usage": {"prompt_tokens": 5}}))
    await handler.on_chain_start({"name": "executor"}, {"plan": "do it"})
    await handler.on_tool_start({"name": "run_code"}, "print('hi')")
    await handler.on_tool_end("hi")
    await handler.on_chain_end({"done": True})
    await handler.on_chain_end({"final": "complete"})

    # Verify everything was captured
    s = handler.summary()
    assert s["total_events"] > 0
    assert set(s["chains_seen"]) == {"planner", "executor"}
    assert s["tools_called"] == ["run_code"]
    assert len(s["handoffs"]) == 1
    assert repr(handler).startswith("<FailSafeCallbackHandler")
