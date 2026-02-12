"""Pydantic models for FailSafe AI."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentCard(BaseModel):
    """Registered agent in the system."""

    name: str
    description: str = ""
    authority: list[str] = Field(default_factory=list)
    deny_authority: list[str] = Field(default_factory=list)
    data_access: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractRule(BaseModel):
    """A single deterministic rule in a contract."""

    rule_type: Literal[
        "allow_fields", "deny_fields", "require_fields", "field_value", "custom"
    ]
    config: dict[str, Any] = Field(default_factory=dict)


class Contract(BaseModel):
    """Handoff contract between two agents."""

    name: str
    source: str
    target: str
    rules: list[ContractRule] = Field(default_factory=list)
    nl_rules: list[str] = Field(default_factory=list)
    mode: Literal["warn", "block"] = "warn"
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoffPayload(BaseModel):
    """Data being passed from one agent to another."""

    source: str
    target: str
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = Field(default_factory=dict)


class Violation(BaseModel):
    """A specific contract or policy violation."""

    rule: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    message: str
    field: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    source_agent: str = ""
    target_agent: str = ""


class ValidationResult(BaseModel):
    """Result of validating a handoff against a contract."""

    passed: bool
    violations: list[Violation] = Field(default_factory=list)
    sanitized_payload: dict[str, Any] | None = None
    contract_name: str = ""
    validation_mode: Literal["deterministic", "llm", "both"] = "deterministic"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
