"""observe() factory + FailSafeObserver — zero-friction observability for FailSafe."""

from __future__ import annotations

import asyncio
import sys
from functools import wraps
from typing import Any
from uuid import uuid4

from failsafe.core.engine import FailSafe
from failsafe.core.models import ValidationResult


class FailSafeObserver:
    """Generic (non-LangChain) observer. Wraps a FailSafe instance with lightweight tracing."""

    def __init__(self, fs: FailSafe):
        self.fs = fs
        self._trace_id = str(uuid4())
        self._last_agent: str | None = None
        self._last_output: dict[str, Any] | None = None

    def trace(self, source: str, target: str, payload: dict) -> ValidationResult:
        """Log a data handoff between two agents. Synchronous."""
        return self.fs.handoff_sync(source, target, payload, trace_id=self._trace_id)

    async def atrace(self, source: str, target: str, payload: dict) -> ValidationResult:
        """Async version of trace()."""
        return await self.fs.handoff(source, target, payload, trace_id=self._trace_id)

    def watch(self, name: str):
        """Decorator that wraps a function and auto-traces its input/output.

        Usage:
            obs = observe()

            @obs.watch("kyc_agent")
            def kyc_check(data: dict) -> dict:
                ...

            @obs.watch("trading_agent")
            def execute_trade(data: dict) -> dict:
                ...
        """
        # Auto-register the agent if not already registered
        if self.fs.registry.get(name) is None:
            self.fs.register_agent(name)

        def decorator(func):
            if asyncio.iscoroutinefunction(func):
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    # Trace from previous agent -> this agent
                    if self._last_agent is not None and self._last_output is not None:
                        await self.atrace(self._last_agent, name, self._last_output)

                    result = await func(*args, **kwargs)

                    self._last_agent = name
                    self._last_output = result if isinstance(result, dict) else {"__return__": result}
                    return result

                return async_wrapper
            else:
                @wraps(func)
                def sync_wrapper(*args, **kwargs):
                    # Trace from previous agent -> this agent
                    if self._last_agent is not None and self._last_output is not None:
                        self.trace(self._last_agent, name, self._last_output)

                    result = func(*args, **kwargs)

                    self._last_agent = name
                    self._last_output = result if isinstance(result, dict) else {"__return__": result}
                    return result

                return sync_wrapper

        return decorator

    @property
    def violations(self) -> list:
        """Return all violations seen so far across all traces."""
        violations = []
        for event in self.fs.event_bus._history:
            data = event.get("data", {})
            for v in data.get("violations", []):
                violations.append(v)
        return violations

    @property
    def audit_log(self) -> list:
        """Return the event bus history."""
        return self.fs.event_bus.history


def _detect_framework() -> str | None:
    """Detect which agent framework is installed, return its name or None."""
    # Check in priority order (most specific first)
    try:
        import langgraph  # noqa: F401
        return "langgraph"
    except ImportError:
        pass

    try:
        import langchain_core  # noqa: F401
        return "langchain"
    except ImportError:
        pass

    try:
        import crewai  # noqa: F401
        return "crewai"
    except ImportError:
        pass

    try:
        import autogen_agentchat  # noqa: F401
        return "autogen"
    except ImportError:
        pass

    try:
        import agents  # noqa: F401
        return "openai_agents"
    except ImportError:
        pass

    return None


_VALID_FRAMEWORKS = {
    None, "langchain", "langgraph", "crewai", "autogen", "openai_agents",
}


def _build_adapter(framework: str, fs: FailSafe, mode: str) -> Any:
    """Return the framework-specific adapter for the given framework name."""
    if framework in ("langchain", "langgraph"):
        from failsafe.integrations.langchain.callback import FailSafeCallbackHandler
        return FailSafeCallbackHandler(failsafe=fs, mode=mode)

    if framework == "crewai":
        from failsafe.integrations.crewai import FailSafeCrewCallback
        return FailSafeCrewCallback(fs)

    if framework == "autogen":
        from failsafe.integrations.autogen import FailSafeAutoGenHandler
        return FailSafeAutoGenHandler(fs)

    if framework == "openai_agents":
        from failsafe.integrations.openai_agents import FailSafeTraceProcessor
        return FailSafeTraceProcessor(fs)

    return None


def observe(
    framework: str | None = None,
    dashboard: bool = True,
    dashboard_port: int = 8765,
    mode: str = "warn",
    audit_db: str = ":memory:",
    print_url: bool = True,
) -> FailSafeObserver | Any:
    """Factory that returns a framework-specific adapter or a generic FailSafeObserver.

    Args:
        framework: "langchain", "langgraph", "crewai", "autogen", "openai_agents",
                   or None for auto-detect / generic fallback.
        dashboard: Auto-start dashboard on localhost.
        dashboard_port: Port for the dashboard server.
        mode: "warn" or "block".
        audit_db: Path to SQLite audit DB. Defaults to in-memory.
        print_url: Print dashboard URL to stderr on init.

    Returns:
        Framework-specific adapter if available, otherwise FailSafeObserver.
    """
    if framework is not None and framework not in _VALID_FRAMEWORKS:
        raise ValueError(
            f"Unknown framework: {framework!r}. "
            f"Supported: langchain, langgraph, crewai, autogen, openai_agents, or None."
        )

    fs = FailSafe(
        mode=mode,
        audit_db=audit_db,
        dashboard=dashboard,
        dashboard_port=dashboard_port,
    )

    if print_url and dashboard:
        print(
            f"\n\U0001f6e1\ufe0f  FailSafe observing — dashboard at http://localhost:{dashboard_port}\n",
            file=sys.stderr,
        )

    # Resolve framework: explicit or auto-detected
    resolved = framework if framework is not None else _detect_framework()

    if resolved is not None:
        adapter = _build_adapter(resolved, fs, mode)
        if adapter is not None:
            return adapter

    return FailSafeObserver(fs)
