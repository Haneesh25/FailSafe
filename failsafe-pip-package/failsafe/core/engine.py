"""Main FailSafe engine — orchestrator that ties everything together."""

from __future__ import annotations

import asyncio
from datetime import datetime
from functools import wraps
from typing import Any, Literal
from uuid import uuid4

from failsafe.core.audit import AuditLog
from failsafe.core.contracts import ContractRegistry
from failsafe.core.llm_judge import LLMJudge
from failsafe.core.models import (
    AgentCard,
    Contract,
    ContractRule,
    HandoffPayload,
    ValidationResult,
    Violation,
)
from failsafe.core.policy import PolicyEngine, PolicyPack
from failsafe.core.registry import AgentRegistry
from failsafe.core.validator import DeterministicValidator
from failsafe.dashboard.events import EventBus


class FailSafe:
    """Main FailSafe engine. Entry point for all operations."""

    def __init__(
        self,
        mode: Literal["warn", "block"] = "warn",
        policy_pack: str | PolicyPack | None = None,
        cerebras_api_key: str | None = None,
        dashboard: bool = False,
        dashboard_port: int = 8765,
        audit_db: str = "failsafe_audit.db",
    ):
        self.registry = AgentRegistry()
        self.contracts = ContractRegistry()
        self.validator = DeterministicValidator()
        self.llm_judge = LLMJudge(api_key=cerebras_api_key) if cerebras_api_key else None
        self.policy_engine = PolicyEngine()
        self.audit_log = AuditLog(db_path=audit_db)
        self.event_bus = EventBus()
        self.mode = mode
        self._dashboard_server = None

        if policy_pack:
            self._load_policy_pack(policy_pack)
        if dashboard:
            self._start_dashboard(dashboard_port)

    # --- Policy Pack Loading ---

    def _load_policy_pack(self, pack: str | PolicyPack) -> None:
        if isinstance(pack, str):
            if pack == "finance":
                from failsafe.policies.finance import finance_pack
                self.policy_engine.load_pack(finance_pack)
            else:
                raise ValueError(f"Unknown policy pack: {pack}")
        else:
            self.policy_engine.load_pack(pack)

    # --- Dashboard ---

    def _start_dashboard(self, port: int) -> None:
        import threading

        import uvicorn

        from failsafe.dashboard.server import create_app

        app = create_app(self)

        def run():
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self._dashboard_server = thread

    # --- Agent Registration ---

    def agent(
        self,
        name: str,
        description: str = "",
        authority: list[str] | None = None,
        deny_authority: list[str] | None = None,
        data_access: list[str] | None = None,
        **kwargs: Any,
    ):
        """Decorator to register an agent."""

        def decorator(func):
            card = AgentCard(
                name=name,
                description=description,
                authority=authority or [],
                deny_authority=deny_authority or [],
                data_access=data_access or [],
                metadata=kwargs,
            )
            self.registry.register(card)

            @wraps(func)
            def wrapper(*args, **kw):
                return func(*args, **kw)

            wrapper._failsafe_agent = card
            return wrapper

        return decorator

    def register_agent(self, name: str, **kwargs: Any) -> AgentCard:
        """Imperatively register an agent (non-decorator form)."""
        card = AgentCard(name=name, **kwargs)
        self.registry.register(card)
        return card

    # --- Contract Definition ---

    def contract(
        self,
        name: str,
        source: str,
        target: str,
        allow: list[str] | None = None,
        deny: list[str] | None = None,
        require: list[str] | None = None,
        rules: list[dict[str, Any]] | None = None,
        nl_rules: list[str] | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> Contract:
        """Register a contract between two agents."""
        built_rules = self._build_rules(allow, deny, require, rules or [])
        c = Contract(
            name=name,
            source=source,
            target=target,
            rules=built_rules,
            nl_rules=nl_rules or [],
            mode=mode or self.mode,
            metadata=kwargs,
        )
        self.contracts.register(c)
        return c

    def _build_rules(
        self,
        allow: list[str] | None,
        deny: list[str] | None,
        require: list[str] | None,
        extra_rules: list[dict[str, Any]],
    ) -> list[ContractRule]:
        rules: list[ContractRule] = []
        if allow:
            rules.append(
                ContractRule(rule_type="allow_fields", config={"fields": allow})
            )
        if deny:
            rules.append(
                ContractRule(
                    rule_type="deny_fields",
                    config={"fields": deny, "patterns": ["ssn", "credit_card"]},
                )
            )
        if require:
            rules.append(
                ContractRule(rule_type="require_fields", config={"fields": require})
            )
        for r in extra_rules:
            rule_type = r.pop("type", r.pop("rule_type", "field_value"))
            rules.append(ContractRule(rule_type=rule_type, config=r))
        return rules

    # --- Handoff Validation ---

    async def handoff(
        self,
        source: str,
        target: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate a handoff between two agents.

        Pipeline:
        1. Look up contract for source->target
        2. Run deterministic validation
        3. If nl_rules exist, run LLM-as-judge
        4. Run policy engine
        5. Combine results
        6. Log to audit trail
        7. Push event to dashboard
        8. Return result
        """
        handoff_payload = HandoffPayload(
            source=source,
            target=target,
            data=payload,
            timestamp=datetime.utcnow(),
            trace_id=trace_id or str(uuid4()),
            metadata=metadata or {},
        )

        contract = self.contracts.get(source, target)
        all_violations: list[Violation] = []
        validation_mode: Literal["deterministic", "llm", "both"] = "deterministic"

        # Step 1: Deterministic validation
        if contract:
            det_result = self.validator.validate(handoff_payload, contract)
            all_violations.extend(det_result.violations)

        # Step 2: LLM-as-judge
        if contract and contract.nl_rules and self.llm_judge:
            try:
                llm_violations = await self.llm_judge.evaluate(
                    handoff_payload, contract.nl_rules
                )
                all_violations.extend(llm_violations)
                validation_mode = "both" if contract.rules else "llm"
            except Exception:
                pass  # LLM failure shouldn't block validation

        # Step 3: Policy engine
        policy_violations = self.policy_engine.evaluate(handoff_payload)
        all_violations.extend(policy_violations)

        # Step 4: Build result
        effective_mode = (contract.mode if contract else self.mode)
        sanitized = (
            self._sanitize(payload, all_violations) if all_violations else payload
        )

        result = ValidationResult(
            passed=len(all_violations) == 0,
            violations=all_violations,
            sanitized_payload=sanitized,
            contract_name=contract.name if contract else "",
            validation_mode=validation_mode,
        )

        # Step 5: Audit log + dashboard event
        try:
            await self.audit_log.record(handoff_payload, result)
        except Exception:
            pass

        await self.event_bus.emit(
            "validation",
            {
                "source": source,
                "target": target,
                "passed": result.passed,
                "violations": [v.model_dump() for v in result.violations],
                "contract": contract.name if contract else None,
                "trace_id": handoff_payload.trace_id,
                "timestamp": handoff_payload.timestamp.isoformat(),
                "duration_ms": result.duration_ms,
                "payload_keys": list(payload.keys()),
                "payload_size": len(str(payload)),
                "payload_preview": self._payload_preview(payload),
                "payload": self._mask_sensitive(payload),
            },
        )

        return result

    def trace(
        self,
        source: str,
        target: str,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> ValidationResult:
        """Convenience alias for handoff_sync() — logs a handoff, validates if contracts exist."""
        return self.handoff_sync(source, target, payload, **kwargs)

    def handoff_sync(
        self,
        source: str,
        target: str,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> ValidationResult:
        """Synchronous wrapper for handoff()."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self.handoff(source, target, payload, **kwargs),
                )
                return future.result()
        return asyncio.run(self.handoff(source, target, payload, **kwargs))

    def _payload_preview(self, payload: dict, max_length: int = 200) -> str:
        """Create a short string preview of the payload for display."""
        import json

        text = json.dumps(payload, default=str)
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text

    def _mask_sensitive(self, payload: dict) -> dict:
        """Deep-copy payload with sensitive-looking values masked.

        Masks values for keys matching common sensitive patterns.
        Also masks string values that match SSN/credit card regex patterns.
        Keeps structure and key names visible — only masks the VALUES.
        """
        import re

        sensitive_key_patterns = {
            "ssn", "social_security", "password", "passwd", "secret",
            "token", "api_key", "apikey", "credit_card", "card_number",
            "account_number", "bank_account", "tax_id", "private_key",
            "access_key", "secret_key",
        }

        ssn_re = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
        cc_re = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b")

        def _mask(data: Any) -> Any:
            if isinstance(data, dict):
                result = {}
                for k, v in data.items():
                    key_lower = k.lower().replace("-", "_")
                    if key_lower in sensitive_key_patterns:
                        result[k] = "***MASKED***"
                    else:
                        result[k] = _mask(v)
                return result
            elif isinstance(data, list):
                return [_mask(item) for item in data]
            elif isinstance(data, str):
                masked = ssn_re.sub("***-**-****", data)
                masked = cc_re.sub("****-****-****-****", masked)
                return masked
            return data

        return _mask(payload)

    def _sanitize(
        self, data: dict[str, Any], violations: list[Violation]
    ) -> dict[str, Any]:
        sanitized = dict(data)
        for v in violations:
            if v.field:
                for field_name in v.field.split(", "):
                    sanitized.pop(field_name, None)
        return sanitized
