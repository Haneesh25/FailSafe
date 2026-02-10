"""Handoff interceptor and validation middleware."""

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
        self.engine.register_policy_pack(policy_pack)

    def on_violation(self, callback: Callable[[HandoffValidationResult], None]) -> None:
        self._callbacks.append(callback)
    
    def validate_outgoing(
        self,
        from_agent: str,
        to_agent: str,
        data: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> HandoffValidationResult:
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

        annotated = dict(a2a_message)
        if "message" not in annotated:
            annotated["message"] = {}
        if "metadata" not in annotated["message"]:
            annotated["message"]["metadata"] = {}
        
        annotated["message"]["metadata"]["failsafe"] = {
            "validated": True,
            "result": result.overall_result.value,
            "handoff_id": result.handoff_id,
            "violations": result.total_violations,
            "blocked": result.is_blocked,
            "timestamp": result.timestamp.isoformat(),
        }
        
        return result, annotated


class FailsafeGuard:
    """Context manager / decorator for protecting handoffs."""

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
    def __init__(self, result: HandoffValidationResult):
        self.result = result
        violations = result.schema_violations + result.policy_violations + result.authority_violations
        critical = [v for v in violations if v.severity.value in ("critical", "high")]
        messages = [v.message for v in critical[:3]]
        super().__init__(
            f"Handoff blocked: {result.consumer_agent} → {result.provider_agent}. "
            f"Violations: {'; '.join(messages)}"
        )
