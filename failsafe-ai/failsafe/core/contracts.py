"""Contract registry and definitions."""

from __future__ import annotations

from failsafe.core.models import Contract


class ContractRegistry:
    """Central registry for all contracts. Single source of truth."""

    def __init__(self) -> None:
        self._contracts: dict[str, Contract] = {}
        self._by_pair: dict[tuple[str, str], Contract] = {}

    def register(self, contract: Contract) -> None:
        self._contracts[contract.name] = contract
        self._by_pair[(contract.source, contract.target)] = contract

    def get(self, source: str, target: str) -> Contract | None:
        return self._by_pair.get((source, target))

    def get_by_name(self, name: str) -> Contract | None:
        return self._contracts.get(name)

    def list_all(self) -> list[Contract]:
        return list(self._contracts.values())

    def coverage_matrix(self) -> dict[str, dict[str, str]]:
        """Returns which agent pairs have contracts and which don't.

        Returns a nested dict: {source: {target: status}}
        where status is 'covered' or 'uncovered'.
        """
        agents: set[str] = set()
        for contract in self._contracts.values():
            agents.add(contract.source)
            agents.add(contract.target)

        matrix: dict[str, dict[str, str]] = {}
        for source in sorted(agents):
            matrix[source] = {}
            for target in sorted(agents):
                if source == target:
                    matrix[source][target] = "self"
                elif (source, target) in self._by_pair:
                    matrix[source][target] = "covered"
                else:
                    matrix[source][target] = "uncovered"
        return matrix
