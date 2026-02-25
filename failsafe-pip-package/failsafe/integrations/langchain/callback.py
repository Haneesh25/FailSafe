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
        self._chain_inputs: dict[str, dict] = {}
        self._trace_id = str(uuid4())

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        chain_name = serialized.get("name", serialized.get("id", ["unknown"])[-1])
        self._chain_stack.append(chain_name)
        if isinstance(inputs, dict):
            self._chain_inputs[chain_name] = inputs
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

            self.audit_log.append({
                "event": "handoff",
                "source": source,
                "target": target,
                "passed": result.passed,
                "violation_count": len(result.violations),
                "payload_keys": list(payload.keys()),
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": self._trace_id,
            })

        self.audit_log.append(
            {
                "event": "chain_end",
                "chain": chain_name,
                "output_keys": list(outputs.keys()) if isinstance(outputs, dict) else [],
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": self._trace_id,
            }
        )

        # Clean up stored inputs
        self._chain_inputs.pop(chain_name, None)

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

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        agent_name = self._chain_stack[-1] if self._chain_stack else "unknown"
        model = serialized.get("kwargs", {}).get(
            "model_name", serialized.get("id", ["unknown"])[-1]
        )
        self.audit_log.append(
            {
                "event": "llm_start",
                "agent": agent_name,
                "model": model,
                "prompt_count": len(prompts) if isinstance(prompts, list) else 1,
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": self._trace_id,
            }
        )

    async def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        agent_name = self._chain_stack[-1] if self._chain_stack else "unknown"
        token_usage = {}
        if hasattr(response, "llm_output") and response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
        self.audit_log.append(
            {
                "event": "llm_end",
                "agent": agent_name,
                "token_usage": token_usage,
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

    def summary(self) -> dict:
        """Return a summary of what was observed."""
        return {
            "trace_id": self._trace_id,
            "total_events": len(self.audit_log),
            "chains_seen": list(set(
                e["chain"] for e in self.audit_log if "chain" in e
            )),
            "tools_called": list(set(
                e["tool"] for e in self.audit_log if e.get("event") == "tool_start"
            )),
            "handoffs": [
                e for e in self.audit_log if e.get("event") == "handoff"
            ],
            "violations": [
                {"rule": v.rule, "severity": v.severity, "message": v.message}
                for v in self.violations
            ],
            "total_violations": len(self.violations),
        }

    def __repr__(self) -> str:
        v = len(self.violations)
        e = len(self.audit_log)
        return f"<FailSafeCallbackHandler trace={self._trace_id[:8]}... events={e} violations={v}>"
