"""Deterministic trace mutation engine."""

import hashlib
import random
from dataclasses import dataclass
from typing import Callable

from .schema import Session, Step, ActionType


@dataclass
class MutationConfig:
    """Configuration for trace mutations."""
    timing_jitter_ms: tuple[int, int] = (-500, 1500)
    misclick_probability: float = 0.05
    back_navigation_probability: float = 0.03
    alternate_selector_probability: float = 0.1
    retry_on_failure_probability: float = 0.3
    abandonment_probability: float = 0.02
    extra_wait_probability: float = 0.1
    extra_wait_ms: tuple[int, int] = (500, 2000)


class TraceMutator:
    """Deterministically mutate traces based on a seed."""

    def __init__(self, seed: int, config: MutationConfig | None = None):
        self.seed = seed
        self.config = config or MutationConfig()
        self._rng: random.Random | None = None

    def _get_rng(self, session_id: str) -> random.Random:
        """Get a deterministic RNG for a specific session."""
        combined = f"{self.seed}:{session_id}"
        hash_bytes = hashlib.sha256(combined.encode()).digest()
        derived_seed = int.from_bytes(hash_bytes[:8], "big")
        return random.Random(derived_seed)

    def mutate(self, session: Session) -> Session:
        """Apply mutations to a session trace."""
        rng = self._get_rng(session.session_id)

        mutated_steps: list[Step] = []
        abandoned = False
        cumulative_jitter = 0.0

        for i, step in enumerate(session.steps):
            if abandoned:
                break

            if rng.random() < self.config.abandonment_probability:
                abandoned = True
                session_copy = session.model_copy(deep=True)
                session_copy.steps = mutated_steps
                session_copy.tags = session.tags + ["mutated", "abandoned"]
                return session_copy

            if rng.random() < self.config.extra_wait_probability:
                wait_ms = rng.randint(*self.config.extra_wait_ms)
                wait_step = Step(
                    ts=step.ts + cumulative_jitter / 1000,
                    action=ActionType.WAIT,
                    metadata={"mutation": "extra_wait", "wait_ms": wait_ms}
                )
                mutated_steps.append(wait_step)
                cumulative_jitter += wait_ms

            if rng.random() < self.config.back_navigation_probability and i > 0:
                back_step = Step(
                    ts=step.ts + cumulative_jitter / 1000,
                    action=ActionType.BACK,
                    metadata={"mutation": "back_navigation"}
                )
                mutated_steps.append(back_step)
                cumulative_jitter += 500

            jitter_ms = rng.randint(*self.config.timing_jitter_ms)
            cumulative_jitter += max(0, jitter_ms)

            mutated_step = step.model_copy(deep=True)
            mutated_step.ts = step.ts + cumulative_jitter / 1000

            if step.selector and rng.random() < self.config.alternate_selector_probability:
                mutated_step.selector = self._generate_alternate_selector(step.selector, rng)
                mutated_step.metadata = {**mutated_step.metadata, "mutation": "alternate_selector"}

            if rng.random() < self.config.misclick_probability:
                misclick_step = Step(
                    ts=mutated_step.ts,
                    action=ActionType.CLICK,
                    selector="body",
                    metadata={"mutation": "misclick"}
                )
                mutated_steps.append(misclick_step)
                mutated_step.ts += 0.3

            mutated_steps.append(mutated_step)

            if step.action in (ActionType.SUBMIT, ActionType.CLICK) and step.expect:
                if rng.random() < self.config.retry_on_failure_probability:
                    retry_step = step.model_copy(deep=True)
                    retry_step.ts = mutated_step.ts + 1.0
                    retry_step.metadata = {**retry_step.metadata, "mutation": "retry"}
                    mutated_steps.append(retry_step)

        session_copy = session.model_copy(deep=True)
        session_copy.steps = mutated_steps
        session_copy.tags = session.tags + ["mutated"]
        return session_copy

    def _generate_alternate_selector(self, selector: str, rng: random.Random) -> str:
        """Generate an alternate but equivalent selector."""
        if selector.startswith("[data-testid="):
            testid = selector.split("=")[1].rstrip("]").strip("'\"")
            alternatives = [
                f'[data-testid="{testid}"]',
                f"[data-testid='{testid}']",
                f'*[data-testid="{testid}"]',
            ]
            return rng.choice(alternatives)

        if selector.startswith("#"):
            element_id = selector[1:]
            return f'[id="{element_id}"]'

        return selector

    def get_mutation_summary(self, original: Session, mutated: Session) -> dict:
        """Get a summary of mutations applied."""
        mutations = {
            "extra_waits": 0,
            "back_navigations": 0,
            "misclicks": 0,
            "alternate_selectors": 0,
            "retries": 0,
            "abandoned": "abandoned" in mutated.tags,
            "original_steps": len(original.steps),
            "mutated_steps": len(mutated.steps),
        }

        for step in mutated.steps:
            mutation_type = step.metadata.get("mutation")
            if mutation_type == "extra_wait":
                mutations["extra_waits"] += 1
            elif mutation_type == "back_navigation":
                mutations["back_navigations"] += 1
            elif mutation_type == "misclick":
                mutations["misclicks"] += 1
            elif mutation_type == "alternate_selector":
                mutations["alternate_selectors"] += 1
            elif mutation_type == "retry":
                mutations["retries"] += 1

        return mutations
