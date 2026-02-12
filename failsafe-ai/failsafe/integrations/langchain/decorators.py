"""Agent and tool decorators for FailSafe validation."""

from __future__ import annotations

import asyncio
from functools import wraps
from typing import TYPE_CHECKING, Any

from failsafe.core.models import Violation

if TYPE_CHECKING:
    from failsafe.core.engine import FailSafe


class ToolAuthorityViolation(Exception):
    """Raised when a tool call violates agent authority."""

    def __init__(self, violations: list[Violation]):
        self.violations = violations
        messages = [v.message for v in violations]
        super().__init__(f"Tool authority violation: {'; '.join(messages)}")


def validated_tool(
    fs: "FailSafe",
    agent: str,
    constraints: list[str] | None = None,
):
    """Decorator that validates tool calls against agent authority.

    Usage:
        @validated_tool(fs, agent="research_agent", constraints=["Can only query public market data"])
        def market_data_tool(ticker: str) -> str:
            return api.get(ticker)
    """

    def decorator(func: Any) -> Any:
        tool_name = f"tool:{func.__name__}"

        # Register a contract for this tool if constraints are provided
        if constraints:
            fs.contract(
                name=f"{agent}->{func.__name__}",
                source=agent,
                target=tool_name,
                nl_rules=constraints,
            )

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await fs.handoff(
                source=agent,
                target=tool_name,
                payload={"args": list(args), "kwargs": kwargs},
            )
            if not result.passed and fs.mode == "block":
                raise ToolAuthorityViolation(result.violations)
            return await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            result = fs.handoff_sync(
                source=agent,
                target=tool_name,
                payload={"args": list(args), "kwargs": kwargs},
            )
            if not result.passed and fs.mode == "block":
                raise ToolAuthorityViolation(result.violations)
            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
