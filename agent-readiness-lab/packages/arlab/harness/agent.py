"""Agent harness for running agents with observation and action cycles."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from ..traces.schema import Observation, AgentAction, ActionType


@dataclass
class AgentContext:
    """Context for an agent execution."""
    session_id: str
    goal: str
    start_url: str
    max_steps: int = 100
    timeout_ms: int = 60000
    current_step: int = 0
    history: list[dict] = field(default_factory=list)


class BaseAgent(ABC):
    """Base class for agents."""

    @abstractmethod
    async def decide(
        self,
        observation: Observation,
        context: AgentContext
    ) -> AgentAction:
        """Decide on the next action based on observation and context."""
        pass

    @abstractmethod
    async def reset(self) -> None:
        """Reset the agent state for a new session."""
        pass

    def get_name(self) -> str:
        """Get the agent name."""
        return self.__class__.__name__


class AgentHarness:
    """Harness for running agents with full auditing."""

    def __init__(
        self,
        agent: BaseAgent,
        max_steps: int = 100,
        timeout_ms: int = 60000,
    ):
        self.agent = agent
        self.max_steps = max_steps
        self.timeout_ms = timeout_ms
        self.event_log: list[dict] = []

    async def run_session(
        self,
        goal: str,
        start_url: str,
        session_id: str,
        get_observation: Any,  # Callable that returns Observation
        execute_action: Any,   # Callable that executes AgentAction
    ) -> dict:
        """Run a complete agent session.

        Args:
            goal: The goal of the session
            start_url: Starting URL
            session_id: Unique session ID
            get_observation: Async function to get current observation
            execute_action: Async function to execute an action

        Returns:
            Session result dict with success, events, metrics
        """
        await self.agent.reset()
        self.event_log = []

        context = AgentContext(
            session_id=session_id,
            goal=goal,
            start_url=start_url,
            max_steps=self.max_steps,
            timeout_ms=self.timeout_ms,
        )

        success = False
        error_message = None
        start_time = datetime.now(timezone.utc)

        try:
            for step in range(self.max_steps):
                context.current_step = step

                # Get observation
                observation = await get_observation()

                # Record observation
                event = {
                    "step": step,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "observation": observation.model_dump() if observation else None,
                    "action": None,
                    "result": None,
                    "error": None,
                }

                # Check for goal completion (simple heuristic)
                if self._check_goal_completion(observation, goal):
                    event["result"] = "goal_completed"
                    self.event_log.append(event)
                    success = True
                    break

                # Get agent decision
                try:
                    action = await self.agent.decide(observation, context)
                    event["action"] = action.model_dump()
                except Exception as e:
                    event["error"] = f"Agent decision error: {str(e)}"
                    self.event_log.append(event)
                    error_message = str(e)
                    break

                # Execute action
                try:
                    result = await execute_action(action)
                    event["result"] = result
                    context.history.append({
                        "observation": observation.model_dump() if observation else None,
                        "action": action.model_dump(),
                        "result": result,
                    })
                except Exception as e:
                    event["error"] = f"Action execution error: {str(e)}"
                    event["result"] = "failure"

                self.event_log.append(event)

                # Check for terminal states
                if event.get("error"):
                    break

        except Exception as e:
            error_message = str(e)

        end_time = datetime.now(timezone.utc)
        duration_ms = (end_time - start_time).total_seconds() * 1000

        return {
            "session_id": session_id,
            "goal": goal,
            "success": success,
            "steps": len(self.event_log),
            "duration_ms": duration_ms,
            "events": self.event_log,
            "error_message": error_message,
        }

    def _check_goal_completion(self, observation: Observation, goal: str) -> bool:
        """Check if the goal appears to be completed.

        This is a simple heuristic - real implementations would be more sophisticated.
        """
        if not observation:
            return False

        goal_lower = goal.lower()

        # Check for checkout completion
        if "checkout" in goal_lower or "purchase" in goal_lower:
            success_indicators = [
                "order confirmed",
                "thank you for your order",
                "order successful",
                "purchase complete",
                "confirmation",
            ]
            visible_text = observation.visible_text.lower()
            return any(indicator in visible_text for indicator in success_indicators)

        # Check for login completion
        if "login" in goal_lower or "sign in" in goal_lower:
            success_indicators = ["welcome", "dashboard", "logout", "sign out"]
            visible_text = observation.visible_text.lower()
            return any(indicator in visible_text for indicator in success_indicators)

        return False

    def get_event_log(self) -> list[dict]:
        """Get the full event log."""
        return self.event_log
