"""Failsafe — contract testing and compliance validation for multi-agent AI systems."""

__version__ = "0.1.0"

from .api import Failsafe

from .core.models import (
    AgentIdentity,
    AuthorityLevel,
    ContractRegistry,
    FieldContract,
    HandoffContract,
    HandoffDirection,
    HandoffPayload,
    HandoffValidationResult,
    PolicySeverity,
    PolicyViolation,
    ValidationResult,
)
from .core.engine import ValidationEngine
from .interceptor.middleware import (
    FailsafeGuard,
    HandoffBlockedError,
    HandoffInterceptor,
)
from .audit.logger import AuditLogger
from .policies.finance import FinancePolicyPack

try:
    from .integrations.langgraph import ValidatedGraph
except ImportError:
    pass

__all__ = [
    "Failsafe",
    "AgentIdentity",
    "AuthorityLevel",
    "ContractRegistry",
    "FieldContract",
    "HandoffContract",
    "HandoffDirection",
    "HandoffPayload",
    "HandoffValidationResult",
    "PolicySeverity",
    "PolicyViolation",
    "ValidationResult",
    "ValidationEngine",
    "FailsafeGuard",
    "HandoffBlockedError",
    "HandoffInterceptor",
    "AuditLogger",
    "FinancePolicyPack",
]
