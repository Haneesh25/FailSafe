"""High-level SDK API for Failsafe."""

from __future__ import annotations
import os
from typing import Any, Callable, Optional

from .core.models import (
    AgentIdentity,
    AuthorityLevel,
    ContractRegistry,
    FieldContract,
    HandoffContract,
    HandoffValidationResult,
)
from .interceptor.middleware import HandoffInterceptor
from .audit.logger import AuditLogger
from .policies.finance import FinancePolicyPack


_AUTHORITY_MAP = {
    "read_only": AuthorityLevel.READ_ONLY,
    "read_write": AuthorityLevel.READ_WRITE,
    "execute": AuthorityLevel.EXECUTE,
    "admin": AuthorityLevel.ADMIN,
}

_FINANCE_SCOPES = {"SOX", "SEC", "FINRA", "PCI-DSS"}


class Failsafe:
    """Contract testing and compliance validation for multi-agent AI systems.

    Quick start::

        fs = Failsafe()
        fs.agent("customer_service", authority="read_only", compliance=["SOX"])
        fs.agent("research_agent", authority="read_write", compliance=["SOX", "SEC"])
        fs.contract("customer_service", "research_agent",
                   fields={"customer_id": "string", "request_type": "string"})
        result = fs.validate("customer_service", "research_agent",
                           {"customer_id": "CUST-123", "request_type": "review"})
    """

    def __init__(self, db_path: Optional[str] = None, block_on_failure: bool = True):
        self._registry = ContractRegistry()
        self._audit = AuditLogger(db_path=db_path)
        self._interceptor = HandoffInterceptor(
            registry=self._registry,
            audit_logger=self._audit,
            block_on_failure=block_on_failure,
        )
        self._policy_packs_registered: set[str] = set()

        if os.environ.get("FAILSAFE_WATCH_MODE") == "1":
            self._setup_watch_mode()

    def agent(
        self,
        name: str,
        description: str = "",
        authority: str = "read_only",
        compliance: Optional[list[str]] = None,
        allowed_domains: Optional[list[str]] = None,
        max_classification: str = "internal",
        skills: Optional[list[str]] = None,
    ) -> Failsafe:
        """Register an agent. Returns self for chaining."""
        authority_level = _AUTHORITY_MAP.get(authority.lower(), AuthorityLevel.READ_ONLY)

        if compliance and _FINANCE_SCOPES.intersection(compliance):
            self._ensure_finance_policy()

        self._registry.register_agent(AgentIdentity(
            name=name,
            description=description or f"Agent: {name}",
            skills=skills or [],
            authority_level=authority_level,
            allowed_data_domains=allowed_domains or [],
            compliance_scopes=compliance or [],
            max_data_classification=max_classification,
        ))
        return self

    def contract(
        self,
        consumer: str,
        provider: str,
        fields: Optional[dict[str, Any]] = None,
        response_fields: Optional[dict[str, Any]] = None,
        authority: str = "read_only",
        compliance: Optional[list[str]] = None,
        max_classification: str = "internal",
        allowed_actions: Optional[list[str]] = None,
        prohibited_actions: Optional[list[str]] = None,
        name: str = "",
    ) -> Failsafe:
        """Register a contract between two agents. Returns self for chaining.

        Fields can be simple (``{"name": "string"}``) or advanced
        (``{"name": {"type": "string", "pattern": "^...$", "pii": True}}``).
        """
        self._registry.register_contract(HandoffContract(
            name=name or f"{consumer}_to_{provider}",
            consumer_agent=consumer,
            provider_agent=provider,
            request_schema=self._parse_fields(fields or {}),
            response_schema=self._parse_fields(response_fields or {}),
            required_authority=_AUTHORITY_MAP.get(authority.lower(), AuthorityLevel.READ_ONLY),
            allowed_actions=allowed_actions or [],
            prohibited_actions=prohibited_actions or [],
            required_compliance_scopes=compliance or [],
            max_data_classification=max_classification,
        ))
        return self

    def validate(
        self,
        from_agent: str,
        to_agent: str,
        data: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> HandoffValidationResult:
        """Validate a handoff between agents."""
        return self._interceptor.validate_outgoing(from_agent, to_agent, data, metadata)

    def report(self) -> str:
        """Generate a formatted compliance report."""
        return self._audit.print_report()

    def on_violation(self, callback: Callable[[HandoffValidationResult], None]) -> Failsafe:
        """Register a callback for violations. Returns self for chaining."""
        self._interceptor.on_violation(callback)
        return self

    def on_validation(self, callback: Callable[[HandoffValidationResult], None]) -> Failsafe:
        """Register a callback for all validations (pass, warn, fail). Returns self for chaining."""
        self._interceptor.on_validation(callback)
        return self

    @property
    def registry(self) -> ContractRegistry:
        return self._registry

    @property
    def audit(self) -> AuditLogger:
        return self._audit

    @property
    def interceptor(self) -> HandoffInterceptor:
        return self._interceptor

    # -- internals --

    def _parse_fields(self, fields: dict[str, Any]) -> list[FieldContract]:
        result = []
        for name, defn in fields.items():
            if isinstance(defn, str):
                result.append(FieldContract(name=name, field_type=defn, required=True))
            elif isinstance(defn, dict):
                result.append(FieldContract(
                    name=name,
                    field_type=defn.get("type", "string"),
                    required=defn.get("required", True),
                    description=defn.get("description", ""),
                    pattern=defn.get("pattern"),
                    min_value=defn.get("min_value"),
                    max_value=defn.get("max_value"),
                    enum_values=defn.get("enum"),
                    max_length=defn.get("max_length"),
                    data_classification=defn.get("data_classification", "public"),
                    pii=defn.get("pii", False),
                    phi=defn.get("phi", False),
                    financial_data=defn.get("financial_data", False),
                ))
        return result

    def _ensure_finance_policy(self) -> None:
        if "finance_v1" not in self._policy_packs_registered:
            self._interceptor.register_policy_pack(FinancePolicyPack())
            self._policy_packs_registered.add("finance_v1")

    def _setup_watch_mode(self) -> None:
        from .cli import print_validation
        verbose = os.environ.get("FAILSAFE_VERBOSE") == "1"
        self._interceptor.on_validation(lambda r: print_validation(r, verbose=verbose))
