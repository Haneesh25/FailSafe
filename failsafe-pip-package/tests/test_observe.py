"""Tests for observe() factory and FailSafeObserver."""

import asyncio

import pytest

from failsafe.core.engine import FailSafe
from failsafe.core.models import ValidationResult
from failsafe.integrations.langchain.callback import FailSafeCallbackHandler
from failsafe.observe import FailSafeObserver, observe


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def observer():
    return observe(dashboard=False, print_url=False)


@pytest.fixture
def fs():
    return FailSafe(mode="warn", audit_db=":memory:")


# ---------------------------------------------------------------------------
# FailSafeObserver tests
# ---------------------------------------------------------------------------

class TestObserverTrace:
    def test_observe_returns_observer_by_default(self):
        obs = observe(dashboard=False, print_url=False)
        assert isinstance(obs, FailSafeObserver)

    def test_observe_returns_callback_handler_for_langchain(self):
        handler = observe(framework="langchain", dashboard=False, print_url=False)
        assert isinstance(handler, FailSafeCallbackHandler)

    def test_observe_returns_callback_handler_for_langgraph(self):
        handler = observe(framework="langgraph", dashboard=False, print_url=False)
        assert isinstance(handler, FailSafeCallbackHandler)

    def test_observer_has_fs_instance(self, observer):
        assert isinstance(observer.fs, FailSafe)

    def test_trace_logs_handoff_without_contracts(self, observer):
        result = observer.trace("a", "b", {"key": "val"})
        assert isinstance(result, ValidationResult)
        assert result.passed is True

    def test_trace_logs_handoff_with_contract_violation(self, observer):
        observer.fs.contract(
            name="a-to-b",
            source="a",
            target="b",
            deny=["secret"],
        )
        result = observer.trace("a", "b", {"secret": "x", "ok": "y"})
        assert result.passed is False
        assert len(result.violations) > 0

    def test_atrace_async(self, observer):
        async def _run():
            return await observer.atrace("a", "b", {"key": "val"})
        result = asyncio.run(_run())
        assert isinstance(result, ValidationResult)
        assert result.passed is True

    def test_trace_pushes_to_event_bus(self, observer):
        observer.trace("a", "b", {"key": "val"})
        history = observer.fs.event_bus._history
        assert len(history) >= 1
        assert history[-1]["type"] == "validation"

    def test_violations_property_accumulates(self, observer):
        observer.fs.contract(
            name="a-to-b",
            source="a",
            target="b",
            deny=["secret"],
        )
        observer.trace("a", "b", {"secret": "x"})
        observer.trace("a", "b", {"secret": "y"})
        assert len(observer.violations) >= 2

    def test_audit_log_property(self, observer):
        observer.trace("a", "b", {"key": "val"})
        log = observer.audit_log
        assert len(log) >= 1
        assert log[-1]["type"] == "validation"


# ---------------------------------------------------------------------------
# watch() decorator tests
# ---------------------------------------------------------------------------

class TestWatchDecorator:
    def test_watch_decorator_sync(self, observer):
        @observer.watch("agent_a")
        def step_a(data: dict) -> dict:
            return {"result": "from_a"}

        @observer.watch("agent_b")
        def step_b(data: dict) -> dict:
            return {"result": "from_b"}

        step_a({})
        step_b({})

        # After step_b, a trace from agent_a -> agent_b should exist
        history = observer.fs.event_bus._history
        assert len(history) >= 1
        last = history[-1]
        assert last["data"]["source"] == "agent_a"
        assert last["data"]["target"] == "agent_b"

    def test_watch_decorator_async(self, observer):
        @observer.watch("async_a")
        async def step_a(data: dict) -> dict:
            return {"result": "from_a"}

        @observer.watch("async_b")
        async def step_b(data: dict) -> dict:
            return {"result": "from_b"}

        async def _run():
            await step_a({})
            await step_b({})

        asyncio.run(_run())

        history = observer.fs.event_bus._history
        assert len(history) >= 1
        last = history[-1]
        assert last["data"]["source"] == "async_a"
        assert last["data"]["target"] == "async_b"

    def test_watch_auto_registers_agents(self, observer):
        @observer.watch("new_agent")
        def my_func(data: dict) -> dict:
            return {}

        assert observer.fs.registry.get("new_agent") is not None

    def test_watch_with_contract_enforcement(self, observer):
        observer.fs.contract(
            name="a-to-b",
            source="writer",
            target="reader",
            deny=["password"],
        )

        @observer.watch("writer")
        def write_step(data: dict) -> dict:
            return {"password": "secret123", "name": "alice"}

        @observer.watch("reader")
        def read_step(data: dict) -> dict:
            return data

        write_step({})
        read_step({})

        assert len(observer.violations) > 0

    def test_watch_first_call_no_source(self, observer):
        @observer.watch("first_agent")
        def first(data: dict) -> dict:
            return {"x": 1}

        first({})

        # First call has no previous agent, so no trace should be emitted
        assert len(observer.fs.event_bus._history) == 0
        # But _last_agent should be set
        assert observer._last_agent == "first_agent"


# ---------------------------------------------------------------------------
# observe() factory tests
# ---------------------------------------------------------------------------

class TestObserveFactory:
    def test_observe_default_mode_is_warn(self):
        obs = observe(dashboard=False, print_url=False)
        assert obs.fs.mode == "warn"

    def test_observe_custom_mode(self):
        obs = observe(mode="block", dashboard=False, print_url=False)
        assert obs.fs.mode == "block"

    def test_observe_dashboard_false_no_server(self):
        obs = observe(dashboard=False, print_url=False)
        assert obs.fs._dashboard_server is None

    def test_observe_print_url_to_stderr(self, capsys):
        obs = observe(dashboard=False, print_url=True)
        captured = capsys.readouterr()
        # dashboard=False means no URL printed even if print_url=True
        assert "FailSafe observing" not in captured.err

    def test_observe_print_url_to_stderr_when_dashboard(self, monkeypatch):
        # Prevent actual dashboard server from starting
        monkeypatch.setattr(FailSafe, "_start_dashboard", lambda self, port: None)
        import io
        import sys
        captured = io.StringIO()
        monkeypatch.setattr(sys, "stderr", captured)
        observe(dashboard=True, print_url=True, dashboard_port=9999)
        output = captured.getvalue()
        assert "FailSafe observing" in output
        assert "9999" in output

    def test_observe_invalid_framework_raises(self):
        with pytest.raises(ValueError, match="Unknown framework"):
            observe(framework="invalid_thing", dashboard=False)


# ---------------------------------------------------------------------------
# fs.trace() method tests
# ---------------------------------------------------------------------------

class TestFsTraceMethod:
    def test_fs_trace_alias_works(self, fs):
        result = fs.trace("a", "b", {"x": 1})
        assert isinstance(result, ValidationResult)

    def test_fs_trace_same_as_handoff_sync(self, fs):
        fs.contract(
            name="a-to-b",
            source="a",
            target="b",
            deny=["secret"],
        )
        result_trace = fs.trace("a", "b", {"secret": "x", "ok": "y"})
        result_handoff = fs.handoff_sync("a", "b", {"secret": "x", "ok": "y"})
        assert result_trace.passed == result_handoff.passed
        assert len(result_trace.violations) == len(result_handoff.violations)
