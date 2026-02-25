"""OpenAI Agents SDK adapter for FailSafe observability."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from failsafe.core.engine import FailSafe


class FailSafeTraceProcessor:
    """OpenAI Agents SDK trace processor for FailSafe observability.

    Usage:
        from failsafe import observe
        obs = observe(framework="openai_agents")
        from agents import add_trace_processor
        add_trace_processor(obs.trace_processor)
    """

    def __init__(self, fs: "FailSafe"):
        self.fs = fs
        self.violations: list[Any] = []

    def trace_processor(self, trace: Any) -> None:
        """Process a trace event from OpenAI Agents SDK."""
        if hasattr(trace, "spans"):
            for span in trace.spans:
                if hasattr(span, "data"):
                    source = getattr(span, "agent_name", "unknown")
                    target = getattr(span, "target_agent", "unknown")
                    payload = (
                        span.data
                        if isinstance(span.data, dict)
                        else {"data": str(span.data)}
                    )
                    result = self.fs.trace(source, target, payload)
                    self.violations.extend(result.violations)
