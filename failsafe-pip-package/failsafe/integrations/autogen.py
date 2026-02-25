"""AutoGen adapter for FailSafe observability."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from failsafe.core.engine import FailSafe


class FailSafeAutoGenHandler:
    """AutoGen v0.4 message handler for FailSafe observability.

    Usage:
        from failsafe import observe
        obs = observe(framework="autogen")
        # Use obs.on_message as a message handler
    """

    def __init__(self, fs: "FailSafe"):
        self.fs = fs
        self.violations: list[Any] = []

    async def on_message(
        self,
        message: Any,
        sender: Any = None,
        recipient: Any = None,
    ) -> None:
        """Handle an AutoGen message event."""
        source = str(sender) if sender else "unknown"
        target = str(recipient) if recipient else "unknown"
        payload = (
            message if isinstance(message, dict) else {"content": str(message)}
        )

        result = await self.fs.handoff(source, target, payload)
        self.violations.extend(result.violations)
