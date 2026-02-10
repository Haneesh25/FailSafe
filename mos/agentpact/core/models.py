"""
AgentPact Core Data Models

Extends A2A protocol concepts with contract testing and compliance validation.
Models are designed around the A2A Agent Card spec + Pact-style contract definitions.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4
import json


# ──────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────

class ValidationResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"

class PolicySeverity(Enum):
    CRITICAL = "critical"   # Blocks handoff
    HIGH = "high"           # Blocks handoff
    MEDIUM = "medium"       # Warning, logged
    LOW = "low"             # Info only
    
class HandoffDirection(Enum):
    REQUEST = "request"     # Consumer -> Provider
    RESPONSE = "response"   # Provider -> Consumer

class AuthorityLevel(Enum):
    """What an agent is authorized to do"""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    EXECUTE = "execute"
    ADMIN = "admin"


# ──────────────────────────────────────────────────────────
# A2A-Compatible Agent Identity
# ──────────────────────────────────────────────────────────

@dataclass
class AgentIdentity:
    """
    Maps to A2A Agent Card fields.
    Extended with AgentPact-specific contract metadata.
    """
    name: str
    description: str
    version: str = "1.0.0"
    url: str = ""
    skills: list[str] = field(default_factory=list)
    
    # AgentPact extensions
    authority_level: AuthorityLevel = AuthorityLevel.READ_ONLY
    allowed_data_domains: list[str] = field(default_factory=list)  # e.g. ["customer_data", "financial_records"]
    compliance_scopes: list[str] = field(default_factory=list)     # e.g. ["SOX", "SEC", "HIPAA"]
    max_data_classification: str = "public"                        # public, internal, confidential, restricted
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": self.url,
            "skills": self.skills,
            "agentpact": {
                "authority_level": self.authority_level.value,
                "allowed_data_domains": self.allowed_data_domains,
                "compliance_scopes": self.compliance_scopes,
                "max_data_classification": self.max_data_classification,
            }
        }


# ──────────────────────────────────────────────────────────
# Contract Definitions
# ──────────────────────────────────────────────────────────

@dataclass
class FieldContract:
    """
    Contract for a single field in a handoff payload.
    Inspired by Pact matchers + JSON Schema.
    """
    name: str
    field_type: str                         # "string", "number", "boolean", "object", "array"
    required: bool = True
    description: str = ""
    
    # Validation rules
    pattern: Optional[str] = None           # Regex pattern (like Pact regex matcher)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    enum_values: Optional[list] = None      # Allowed values
    max_length: Optional[int] = None
    
    # Compliance metadata
    data_classification: str = "public"     # public, internal, confidential, restricted
    pii: bool = False                       # Contains personally identifiable info
    phi: bool = False                       # Contains protected health info
    financial_data: bool = False            # Contains financial records
    
    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "type": self.field_type,
            "required": self.required,
        }
        if self.pattern:
            d["pattern"] = self.pattern
        if self.enum_values:
            d["enum"] = self.enum_values
        if self.pii:
            d["pii"] = True
        if self.phi:
            d["phi"] = True
        if self.financial_data:
            d["financial_data"] = True
        d["data_classification"] = self.data_classification
        return d


@dataclass
class HandoffContract:
    """
    Defines the contract for a single agent-to-agent handoff.
    This is the core primitive — analogous to a Pact interaction
    but for inter-agent communication.
    """
    contract_id: str = field(default_factory=lambda: str(uuid4())[:8])
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    
    # Who's involved
    consumer_agent: str = ""                # Agent receiving/requesting
    provider_agent: str = ""                # Agent sending/providing
    
    # What's being handed off
    request_schema: list[FieldContract] = field(default_factory=list)
    response_schema: list[FieldContract] = field(default_factory=list)
    
    # Authority constraints
    required_authority: AuthorityLevel = AuthorityLevel.READ_ONLY
    allowed_actions: list[str] = field(default_factory=list)    # e.g. ["query", "summarize"]
    prohibited_actions: list[str] = field(default_factory=list) # e.g. ["delete", "modify", "trade"]
    
    # Compliance requirements
    required_compliance_scopes: list[str] = field(default_factory=list)
    max_data_classification: str = "internal"
    require_audit_trail: bool = True
    require_human_approval: bool = False
    
    # SLOs
    max_latency_ms: Optional[int] = None
    timeout_ms: int = 30000
    
    def to_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "name": self.name,
            "version": self.version,
            "consumer": self.consumer_agent,
            "provider": self.provider_agent,
            "request_schema": [f.to_dict() for f in self.request_schema],
            "response_schema": [f.to_dict() for f in self.response_schema],
            "authority": {
                "required_level": self.required_authority.value,
                "allowed_actions": self.allowed_actions,
                "prohibited_actions": self.prohibited_actions,
            },
            "compliance": {
                "scopes": self.required_compliance_scopes,
                "max_data_classification": self.max_data_classification,
                "require_audit_trail": self.require_audit_trail,
                "require_human_approval": self.require_human_approval,
            }
        }


# ──────────────────────────────────────────────────────────
# Runtime Handoff Records
# ──────────────────────────────────────────────────────────

@dataclass
class HandoffPayload:
    """The actual data being passed between agents at runtime."""
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # A2A protocol fields
    task_id: str = ""
    context_id: str = ""
    message_id: str = field(default_factory=lambda: str(uuid4()))
    

@dataclass 
class PolicyViolation:
    """A single policy violation detected during handoff validation."""
    rule_id: str
    rule_name: str
    severity: PolicySeverity
    message: str
    field_path: str = ""
    expected: Any = None
    actual: Any = None
    policy_pack: str = ""
    
    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "message": self.message,
            "field_path": self.field_path,
            "policy_pack": self.policy_pack,
        }


@dataclass
class HandoffValidationResult:
    """Complete result of validating a single handoff."""
    handoff_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    contract_id: str = ""
    consumer_agent: str = ""
    provider_agent: str = ""
    direction: HandoffDirection = HandoffDirection.REQUEST
    
    # Results
    overall_result: ValidationResult = ValidationResult.PASS
    schema_violations: list[PolicyViolation] = field(default_factory=list)
    policy_violations: list[PolicyViolation] = field(default_factory=list)
    authority_violations: list[PolicyViolation] = field(default_factory=list)
    
    # Timing
    validation_duration_ms: float = 0.0
    
    # The actual payload (for audit trail)
    payload_snapshot: Optional[dict] = None
    
    @property
    def is_blocked(self) -> bool:
        """Should this handoff be blocked?"""
        all_violations = self.schema_violations + self.policy_violations + self.authority_violations
        return any(
            v.severity in (PolicySeverity.CRITICAL, PolicySeverity.HIGH) 
            for v in all_violations
        )
    
    @property
    def total_violations(self) -> int:
        return len(self.schema_violations) + len(self.policy_violations) + len(self.authority_violations)
    
    def to_dict(self) -> dict:
        return {
            "handoff_id": self.handoff_id,
            "timestamp": self.timestamp.isoformat(),
            "contract_id": self.contract_id,
            "consumer": self.consumer_agent,
            "provider": self.provider_agent,
            "direction": self.direction.value,
            "result": self.overall_result.value,
            "blocked": self.is_blocked,
            "violations": {
                "schema": [v.to_dict() for v in self.schema_violations],
                "policy": [v.to_dict() for v in self.policy_violations],
                "authority": [v.to_dict() for v in self.authority_violations],
            },
            "total_violations": self.total_violations,
            "validation_duration_ms": self.validation_duration_ms,
        }
    
    def summary(self) -> str:
        icon = "✅" if self.overall_result == ValidationResult.PASS else "❌" if self.is_blocked else "⚠️"
        return (
            f"{icon} Handoff [{self.consumer_agent} → {self.provider_agent}] "
            f"Result: {self.overall_result.value.upper()} | "
            f"Violations: {self.total_violations} | "
            f"Blocked: {self.is_blocked}"
        )


# ──────────────────────────────────────────────────────────
# Contract Registry
# ──────────────────────────────────────────────────────────

@dataclass
class ContractRegistry:
    """
    Stores all contracts and agent identities.
    In production this would be a database; for MVP it's in-memory.
    """
    agents: dict[str, AgentIdentity] = field(default_factory=dict)
    contracts: dict[str, HandoffContract] = field(default_factory=dict)
    
    def register_agent(self, agent: AgentIdentity) -> None:
        self.agents[agent.name] = agent
    
    def register_contract(self, contract: HandoffContract) -> None:
        self.contracts[contract.contract_id] = contract
    
    def get_contract_for_handoff(self, consumer: str, provider: str) -> Optional[HandoffContract]:
        """Find the contract that governs a specific agent-to-agent handoff."""
        for contract in self.contracts.values():
            if contract.consumer_agent == consumer and contract.provider_agent == provider:
                return contract
        return None
    
    def get_agent(self, name: str) -> Optional[AgentIdentity]:
        return self.agents.get(name)
    
    def to_dict(self) -> dict:
        return {
            "agents": {k: v.to_dict() for k, v in self.agents.items()},
            "contracts": {k: v.to_dict() for k, v in self.contracts.items()},
        }
