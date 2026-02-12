"""FailSafeCallbackHandler — zero-code observability for LangChain."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from failsafe.core.models import Violation

if TYPE_CHECKING:
    from failsafe.core.engine import FailSafe

try:
    from langchain_core.callbacks import AsyncCallbackHandler
except ImportError:
    # Provide a base class when langchain is not installed
    class AsyncCallbackHandler:  # type: ignore[no-redef]
        pass


class FailSafeCallbackHandler(AsyncCallbackHandler):
    """Drop-in callback handler for LangChain.

    Monitors all agent actions, tool calls, and chain handoffs.
    No contracts needed — just observability.
    Add contracts to start enforcing.

    Usage:
        handler = FailSafeCallbackHandler(failsafe=fs, mode="warn")
        result = await agent.invoke(input, config={"callbacks": [handler]})
    """

    name = "failsafe"

    def __init__(self, failsafe: "FailSafe", mode: str = "warn"):
        self.fs = failsafe
        self.mode = mode
        self.violations: list[Violation] = []
        self.audit_log: list[dict[str, Any]] = []
        self._chain_stack: list[str] = []
        self._trace_id = str(uuid4())

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        chain_name = serialized.get("name", serialized.get("id", ["unknown"])[-1])
        self._chain_stack.append(chain_name)
        self.audit_log.append(
            {
                "event": "chain_start",
                "chain": chain_name,
                "inputs_keys": list(inputs.keys()) if isinstance(inputs, dict) else [],
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": self._trace_id,
            }
        )

    async def on_chain_end(
        self,
        outputs: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        chain_name = self._chain_stack.pop() if self._chain_stack else "unknown"

        # If there's a previous chain in the stack, validate the handoff
        if self._chain_stack:
            source = self._chain_stack[-1]
            target = chain_name
            payload = outputs if isinstance(outputs, dict) else {"output": str(outputs)}

            result = await self.fs.handoff(
                source=source,
                target=target,
                payload=payload,
                trace_id=self._trace_id,
            )
            self.violations.extend(result.violations)

        self.audit_log.append(
            {
                "event": "chain_end",
                "chain": chain_name,
                "output_keys": list(outputs.keys()) if isinstance(outputs, dict) else [],
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": self._trace_id,
            }
        )

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        agent_name = self._chain_stack[-1] if self._chain_stack else "unknown"

        self.audit_log.append(
            {
                "event": "tool_start",
                "tool": tool_name,
                "agent": agent_name,
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": self._trace_id,
            }
        )

        # Validate tool call against agent authority
        if not self.fs.registry.has_authority(agent_name, f"tool:{tool_name}"):
            violation = Violation(
                rule="authority",
                severity="high",
                message=f"Agent '{agent_name}' lacks authority for tool '{tool_name}'",
                evidence={"tool": tool_name, "agent": agent_name},
                source_agent=agent_name,
                target_agent=f"tool:{tool_name}",
            )
            self.violations.append(violation)

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        self.audit_log.append(
            {
                "event": "tool_end",
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": self._trace_id,
            }
        )

    async def on_agent_action(self, action: Any, **kwargs: Any) -> None:
        agent_name = self._chain_stack[-1] if self._chain_stack else "unknown"
        tool = getattr(action, "tool", "unknown")

        self.audit_log.append(
            {
                "event": "agent_action",
                "agent": agent_name,
                "tool": tool,
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": self._trace_id,
            }
        )
