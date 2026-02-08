"""External agent that communicates via HTTP."""

import httpx
from typing import Any

from ..traces.schema import Observation, AgentAction, ActionType
from .agent import BaseAgent, AgentContext
from .tools import ToolRegistry


class ExternalAgent(BaseAgent):
    """Agent that communicates with an external HTTP endpoint.

    Expects OpenAI-like interface:
    POST /act
    Request: {observation, tools, history, goal}
    Response: {action, args, reasoning?}
    """

    def __init__(self, agent_url: str, timeout: float = 30.0):
        self.agent_url = agent_url.rstrip("/")
        self.timeout = timeout
        self.tool_registry = ToolRegistry()
        self._client: httpx.AsyncClient | None = None

    async def reset(self) -> None:
        """Reset agent state."""
        if self._client:
            await self._client.aclose()
        self._client = httpx.AsyncClient(timeout=self.timeout)

        # Optionally notify the external agent of reset
        try:
            await self._client.post(
                f"{self.agent_url}/reset",
                json={}
            )
        except Exception:
            # Reset endpoint is optional
            pass

    async def decide(
        self,
        observation: Observation,
        context: AgentContext
    ) -> AgentAction:
        """Get next action from external agent."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)

        request_body = {
            "observation": {
                "url": observation.url,
                "title": observation.title,
                "dom_summary": observation.dom_summary,
                "visible_text": observation.visible_text[:5000],  # Truncate for API
                "elements": observation.elements[:50],  # Limit elements
                "error": observation.error,
            },
            "tools": self.tool_registry.get_tools_schema(),
            "history": context.history[-10:],  # Last 10 actions
            "goal": context.goal,
            "step": context.current_step,
            "max_steps": context.max_steps,
        }

        try:
            response = await self._client.post(
                f"{self.agent_url}/act",
                json=request_body
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            raise RuntimeError(f"External agent timed out after {self.timeout}s")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"External agent returned error: {e.response.status_code}")
        except Exception as e:
            raise RuntimeError(f"Failed to communicate with external agent: {str(e)}")

        # Parse response
        action_name = data.get("action")
        args = data.get("args", {})
        reasoning = data.get("reasoning")

        # Validate action
        is_valid, error = self.tool_registry.validate_action(action_name, args)
        if not is_valid:
            raise ValueError(f"Invalid action from external agent: {error}")

        # Map to ActionType
        try:
            action_type = ActionType(action_name)
        except ValueError:
            raise ValueError(f"Unknown action type: {action_name}")

        return AgentAction(
            action=action_type,
            selector=args.get("selector"),
            text=args.get("text") or args.get("value"),
            url=args.get("url"),
            wait_ms=args.get("ms"),
            reasoning=reasoning,
        )

    async def __aenter__(self):
        await self.reset()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
