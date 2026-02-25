"""CrewAI adapter for FailSafe observability."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from failsafe.core.engine import FailSafe


class FailSafeCrewCallback:
    """CrewAI step_callback hook for FailSafe observability.

    Usage:
        from failsafe import observe
        obs = observe(framework="crewai")
        crew = Crew(agents=[...], tasks=[...], step_callback=obs.step_callback)
    """

    def __init__(self, fs: "FailSafe"):
        self.fs = fs
        self._last_agent: str | None = None
        self._last_payload: dict[str, Any] | None = None
        self.violations: list[Any] = []

    def step_callback(self, step_output: Any) -> None:
        """Called by CrewAI after each task step.

        Extracts agent name and output, traces the handoff from previous agent.
        """
        agent_name = getattr(step_output, "agent", None)
        if agent_name is None:
            agent_name = str(getattr(step_output, "agent_name", "unknown"))
        else:
            agent_name = str(agent_name)

        output = getattr(step_output, "output", None)
        payload = (
            output
            if isinstance(output, dict)
            else {"output": str(output) if output else ""}
        )

        if self._last_agent and self._last_agent != agent_name and self._last_payload is not None:
            result = self.fs.trace(self._last_agent, agent_name, self._last_payload)
            self.violations.extend(result.violations)

        self._last_agent = agent_name
        self._last_payload = payload
