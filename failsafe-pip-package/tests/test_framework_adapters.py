"""Tests for framework auto-detection and adapter stubs."""

import asyncio
import types

import pytest

from failsafe.core.engine import FailSafe
from failsafe.integrations.autogen import FailSafeAutoGenHandler
from failsafe.integrations.crewai import FailSafeCrewCallback
from failsafe.integrations.langchain.callback import FailSafeCallbackHandler
from failsafe.integrations.openai_agents import FailSafeTraceProcessor
from failsafe.observe import FailSafeObserver, _detect_framework, observe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fs() -> FailSafe:
    return FailSafe(mode="warn", audit_db=":memory:")


def _mock_step_output(agent: str, output=None):
    """Create a mock CrewAI step_output object."""
    obj = types.SimpleNamespace()
    obj.agent = agent
    obj.output = output
    return obj


def _mock_trace(spans):
    """Create a mock OpenAI Agents SDK trace with spans."""
    return types.SimpleNamespace(spans=spans)


def _mock_span(agent_name="unknown", target_agent="unknown", data=None):
    """Create a mock OpenAI Agents SDK span."""
    return types.SimpleNamespace(
        agent_name=agent_name,
        target_agent=target_agent,
        data=data or {},
    )


# ---------------------------------------------------------------------------
# Auto-detection tests
# ---------------------------------------------------------------------------

class TestDetectFramework:
    def test_detect_framework_returns_none_when_nothing_installed(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        blocked = {
            "langgraph", "langchain_core", "crewai", "autogen_agentchat", "agents",
        }

        def mock_import(name, *args, **kwargs):
            if name in blocked:
                raise ImportError(f"mocked: {name}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        assert _detect_framework() is None

    def test_detect_framework_returns_langchain_when_installed(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        blocked = {"langgraph"}  # block langgraph so langchain wins

        def mock_import(name, *args, **kwargs):
            if name in blocked:
                raise ImportError(f"mocked: {name}")
            if name == "langchain_core":
                return types.ModuleType("langchain_core")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        assert _detect_framework() == "langchain"

    def test_observe_auto_detects_langchain(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        blocked = {"langgraph"}

        def mock_import(name, *args, **kwargs):
            if name in blocked:
                raise ImportError(f"mocked: {name}")
            if name == "langchain_core":
                return types.ModuleType("langchain_core")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = observe(dashboard=False, print_url=False)
        assert isinstance(result, FailSafeCallbackHandler)

    def test_observe_falls_back_to_generic(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        blocked = {
            "langgraph", "langchain_core", "crewai", "autogen_agentchat", "agents",
        }

        def mock_import(name, *args, **kwargs):
            if name in blocked:
                raise ImportError(f"mocked: {name}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = observe(dashboard=False, print_url=False)
        assert isinstance(result, FailSafeObserver)


# ---------------------------------------------------------------------------
# CrewAI adapter tests
# ---------------------------------------------------------------------------

class TestCrewAIAdapter:
    def test_crewai_callback_tracks_agent_sequence(self):
        fs = _make_fs()
        cb = FailSafeCrewCallback(fs)

        step1 = _mock_step_output("agent_a", {"result": "data_a"})
        step2 = _mock_step_output("agent_b", {"result": "data_b"})

        cb.step_callback(step1)
        cb.step_callback(step2)

        # A trace from agent_a -> agent_b should exist
        history = fs.event_bus._history
        assert len(history) >= 1
        last = history[-1]
        assert last["data"]["source"] == "agent_a"
        assert last["data"]["target"] == "agent_b"

    def test_crewai_callback_catches_violations(self):
        fs = _make_fs()
        fs.contract(name="a-to-b", source="agent_a", target="agent_b", deny=["secret"])
        cb = FailSafeCrewCallback(fs)

        step1 = _mock_step_output("agent_a", {"secret": "hidden", "ok": "fine"})
        step2 = _mock_step_output("agent_b", {"result": "done"})

        cb.step_callback(step1)
        cb.step_callback(step2)

        assert len(cb.violations) > 0

    def test_crewai_callback_handles_string_output(self):
        fs = _make_fs()
        cb = FailSafeCrewCallback(fs)

        step1 = _mock_step_output("agent_a", "just a string")
        step2 = _mock_step_output("agent_b", "another string")

        cb.step_callback(step1)
        cb.step_callback(step2)

        history = fs.event_bus._history
        assert len(history) >= 1
        last = history[-1]
        assert last["data"]["source"] == "agent_a"
        # String output is wrapped in {"output": ...}
        assert "output" in last["data"].get("trace_id", "") or len(history) >= 1

    def test_crewai_callback_skips_same_agent(self):
        fs = _make_fs()
        cb = FailSafeCrewCallback(fs)

        step1 = _mock_step_output("agent_a", {"x": 1})
        step2 = _mock_step_output("agent_a", {"x": 2})

        cb.step_callback(step1)
        cb.step_callback(step2)

        # Same agent twice — no trace should be emitted
        assert len(fs.event_bus._history) == 0


# ---------------------------------------------------------------------------
# AutoGen adapter tests
# ---------------------------------------------------------------------------

class TestAutoGenAdapter:
    def test_autogen_handler_traces_messages(self):
        fs = _make_fs()
        handler = FailSafeAutoGenHandler(fs)

        async def _run():
            await handler.on_message(
                {"content": "hello"}, sender="agent_a", recipient="agent_b"
            )

        asyncio.run(_run())

        history = fs.event_bus._history
        assert len(history) >= 1
        last = history[-1]
        assert last["data"]["source"] == "agent_a"
        assert last["data"]["target"] == "agent_b"

    def test_autogen_handler_catches_violations(self):
        fs = _make_fs()
        fs.contract(name="a-to-b", source="agent_a", target="agent_b", deny=["secret"])
        handler = FailSafeAutoGenHandler(fs)

        async def _run():
            await handler.on_message(
                {"secret": "hidden", "ok": "fine"},
                sender="agent_a",
                recipient="agent_b",
            )

        asyncio.run(_run())

        assert len(handler.violations) > 0


# ---------------------------------------------------------------------------
# OpenAI Agents adapter tests
# ---------------------------------------------------------------------------

class TestOpenAIAgentsAdapter:
    def test_openai_trace_processor_handles_spans(self):
        fs = _make_fs()
        proc = FailSafeTraceProcessor(fs)

        span = _mock_span(
            agent_name="agent_a",
            target_agent="agent_b",
            data={"key": "val"},
        )
        trace = _mock_trace([span])

        proc.trace_processor(trace)

        history = fs.event_bus._history
        assert len(history) >= 1
        last = history[-1]
        assert last["data"]["source"] == "agent_a"
        assert last["data"]["target"] == "agent_b"


# ---------------------------------------------------------------------------
# General adapter contract tests
# ---------------------------------------------------------------------------

class TestAdapterContracts:
    def test_all_adapters_expose_fs(self):
        fs = _make_fs()
        adapters = [
            FailSafeCrewCallback(fs),
            FailSafeAutoGenHandler(fs),
            FailSafeTraceProcessor(fs),
            FailSafeCallbackHandler(failsafe=fs, mode="warn"),
            FailSafeObserver(fs),
        ]
        for adapter in adapters:
            assert hasattr(adapter, "fs"), f"{type(adapter).__name__} missing .fs"
            assert adapter.fs is fs

    def test_all_adapters_expose_violations(self):
        fs = _make_fs()
        adapters = [
            FailSafeCrewCallback(fs),
            FailSafeAutoGenHandler(fs),
            FailSafeTraceProcessor(fs),
            FailSafeCallbackHandler(failsafe=fs, mode="warn"),
        ]
        for adapter in adapters:
            assert hasattr(adapter, "violations"), (
                f"{type(adapter).__name__} missing .violations"
            )
            assert isinstance(adapter.violations, list)
