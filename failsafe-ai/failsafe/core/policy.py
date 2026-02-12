"""Policy engine — domain rule packs layered on contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from failsafe.core.models import HandoffPayload, Violation


@dataclass
class Policy:
    """A single policy rule."""

    name: str
    description: str
    condition: Callable[[HandoffPayload], bool]
    check: Callable[[HandoffPayload], Violation | None]
    severity: str = "medium"


@dataclass
class PolicyPack:
    """Collection of related policies."""

    name: str
    policies: list[Policy] = field(default_factory=list)


class PolicyEngine:
    """Evaluates all applicable policies against a handoff."""

    def __init__(self) -> None:
        self.packs: list[PolicyPack] = []

    def load_pack(self, pack: PolicyPack) -> None:
        self.packs.append(pack)

    def evaluate(self, payload: HandoffPayload) -> list[Violation]:
        violations: list[Violation] = []
        for pack in self.packs:
            for policy in pack.policies:
                try:
                    if policy.condition(payload):
                        result = policy.check(payload)
                        if result:
                            violations.append(result)
                except Exception:
                    pass
        return violations
