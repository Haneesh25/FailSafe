"""
AgentPact A2A Interceptor

Middleware that sits between A2A agents and validates handoffs in real-time.
Can operate as:
1. Inline proxy (intercepts and validates before forwarding)
2. Side-car (receives copies of messages for async validation)
3. SDK wrapper (wraps A2A client/server calls)

For MVP, implements the SDK wrapper pattern which is easiest to integrate.
"""

from __future__ import annotations
import json
from typing import Any, Callable, Optional
from datetime import datetime

from ..core.models import (
    ContractRegistry,
    HandoffDirection,
    HandoffPayload,
    HandoffValidationResult,
    ValidationResult,
)
from ..core.engine import ValidationEngine
from ..audit.logger import AuditLogger


class HandoffInterceptor:
    """
    Intercepts and validates agent-to-agent handoffs.
    
    Usage:
        interceptor = HandoffInterceptor(registry, audit_logger)
        interceptor.register_policy_pack(FinancePolicyPack())
        
        # Validate before sending
        result = interceptor.validate_outgoing(
            from_agent="research_agent",
            to_agent="trading_agent",
            data={"symbol": "AAPL", "action": "buy", "amount": 50000},
            metadata={"action": "trade"}
        )
        
        if result.is_blocked:
            print("BLOCKED:", result.summary())
        else:
            # Proceed with handoff
            send_to_agent(data)
    """
    
    def __init__(
        self,
        registry: ContractRegistry,
        audit_logger: Optional[AuditLogger] = None,
        block_on_failure: bool = True,
    ):
        self.engine = ValidationEngine(registry)
        self.audit = audit_logger or AuditLogger()
        self.block_on_failure = block_on_failure
        self._callbacks: list[Callable] = []
    
    def register_policy_pack(self, policy_pack) -> None:
        """Add a domain-specific policy pack."""
        self.engine.register_policy_pack(policy_pack)
    
    def on_violation(self, callback: Callable[[HandoffValidationResult], None]) -> None:
        """Register a callback for when violations are detected."""
        self._callbacks.append(callback)
    
    def validate_outgoing(
        self,
        from_agent: str,
        to_agent: str,
        data: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> HandoffValidationResult:
        """
        Validate an outgoing handoff (consumer → provider).
        Call this before sending data to another agent.
        """
        payload = HandoffPayload(
            data=data,
            metadata=metadata or {},
        )
        
        result = self.engine.validate_handoff(
            consumer_name=from_agent,
            provider_name=to_agent,
            payload=payload,
            direction=HandoffDirection.REQUEST,
        )
        
        self.audit.log(result)
        
        # Notify callbacks
        if result.total_violations > 0:
            for cb in self._callbacks:
                cb(result)
        
        return result
    
    def validate_incoming(
        self,
        from_agent: str,
        to_agent: str,
        data: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> HandoffValidationResult:
        """
        Validate an incoming handoff (provider → consumer response).
        Call this when receiving data from another agent.
        """
        payload = HandoffPayload(
            data=data,
            metadata=metadata or {},
        )
        
        result = self.engine.validate_handoff(
            consumer_name=from_agent,
            provider_name=to_agent,
            payload=payload,
            direction=HandoffDirection.RESPONSE,
        )
        
        self.audit.log(result)
        
        if result.total_violations > 0:
            for cb in self._callbacks:
                cb(result)
        
        return result
    
    def wrap_a2a_message(
        self,
        from_agent: str,
        to_agent: str,
        a2a_message: dict,
    ) -> tuple[HandoffValidationResult, dict]:
        """
        Wrap an A2A protocol message with validation.
        Extracts data from A2A message format, validates, and returns
        the original message with validation metadata attached.
        
        Returns:
            (validation_result, annotated_message)
        """
        # Extract data from A2A message parts
        data = {}
        parts = a2a_message.get("message", {}).get("parts", [])
        for part in parts:
            if part.get("type") == "text":
                # Try to parse as JSON, fall back to text
                try:
                    data = json.loads(part["text"])
                except (json.JSONDecodeError, KeyError):
                    data = {"text": part.get("text", "")}
            elif part.get("type") == "data":
                data.update(part.get("data", {}))
        
        metadata = a2a_message.get("message", {}).get("metadata", {})
        
        result = self.validate_outgoing(from_agent, to_agent, data, metadata)
        
        # Annotate the message with validation results
        annotated = dict(a2a_message)
        if "message" not in annotated:
            annotated["message"] = {}
        if "metadata" not in annotated["message"]:
            annotated["message"]["metadata"] = {}
        
        annotated["message"]["metadata"]["agentpact"] = {
            "validated": True,
            "result": result.overall_result.value,
            "handoff_id": result.handoff_id,
            "violations": result.total_violations,
            "blocked": result.is_blocked,
            "timestamp": result.timestamp.isoformat(),
        }
        
        return result, annotated


class AgentPactGuard:
    """
    High-level decorator/context manager for protecting agent handoffs.
    
    Usage as context manager:
        with AgentPactGuard(interceptor, "agent_a", "agent_b") as guard:
            guard.send({"key": "value"})
    
    Usage as decorator:
        @agentpact_guard(interceptor, "agent_a", "agent_b")
        def process_handoff(data):
            return transformed_data
    """
    
    def __init__(
        self,
        interceptor: HandoffInterceptor,
        from_agent: str,
        to_agent: str,
        raise_on_block: bool = True,
    ):
        self.interceptor = interceptor
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.raise_on_block = raise_on_block
        self.last_result: Optional[HandoffValidationResult] = None
    
    def send(
        self, data: dict, metadata: Optional[dict] = None
    ) -> HandoffValidationResult:
        """Validate and return result. Raises if blocked and raise_on_block=True."""
        result = self.interceptor.validate_outgoing(
            self.from_agent, self.to_agent, data, metadata
        )
        self.last_result = result
        
        if result.is_blocked and self.raise_on_block:
            raise HandoffBlockedError(result)
        
        return result
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class HandoffBlockedError(Exception):
    """Raised when a handoff is blocked by validation."""
    
    def __init__(self, result: HandoffValidationResult):
        self.result = result
        violations = result.schema_violations + result.policy_violations + result.authority_violations
        critical = [v for v in violations if v.severity.value in ("critical", "high")]
        messages = [v.message for v in critical[:3]]
        super().__init__(
            f"Handoff blocked: {result.consumer_agent} → {result.provider_agent}. "
            f"Violations: {'; '.join(messages)}"
        )
