"""Agent registry — tracks all agents, their authority, and data access."""

from __future__ import annotations

from failsafe.core.models import AgentCard


class AgentRegistry:
    """Central registry for all agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentCard] = {}

    def register(self, agent: AgentCard) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> AgentCard | None:
        return self._agents.get(name)

    def list_all(self) -> list[AgentCard]:
        return list(self._agents.values())

    def has_authority(self, agent_name: str, action: str) -> bool:
        """Check if an agent has authority to perform an action."""
        agent = self._agents.get(agent_name)
        if agent is None:
            return False
        if action in agent.deny_authority:
            return False
        if agent.authority and action not in agent.authority:
            return False
        return True

    def can_access_field(self, agent_name: str, field: str) -> bool:
        """Check if an agent can access a data field."""
        agent = self._agents.get(agent_name)
        if agent is None:
            return False
        if not agent.data_access:
            return True
        return field in agent.data_access
