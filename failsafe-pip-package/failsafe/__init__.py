"""FailSafe — contract testing and compliance validation for multi-agent AI systems."""

from failsafe.core.engine import FailSafe
from failsafe.core.models import AgentCard, Contract, ValidationResult, Violation
from failsafe.core.policy import Policy, PolicyPack
from failsafe.observe import FailSafeObserver, observe

__all__ = [
    "FailSafe",
    "observe",
    "FailSafeObserver",
    "Contract",
    "AgentCard",
    "ValidationResult",
    "Violation",
    "Policy",
    "PolicyPack",
]

# LangChain integrations are imported separately to avoid requiring langchain as a dependency
# from failsafe.integrations.langchain.callback import FailSafeCallbackHandler
# from failsafe.integrations.langchain.graph import FailSafeGraph
# from failsafe.integrations.langchain.decorators import validated_tool
