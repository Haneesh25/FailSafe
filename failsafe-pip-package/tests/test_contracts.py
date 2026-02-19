"""Tests for contract registry."""

import pytest

from failsafe.core.contracts import ContractRegistry
from failsafe.core.models import Contract, ContractRule


def make_contract(name: str, source: str, target: str, **kwargs) -> Contract:
    return Contract(name=name, source=source, target=target, **kwargs)


class TestContractRegistry:
    def setup_method(self):
        self.registry = ContractRegistry()

    def test_register_and_get(self):
        c = make_contract("c1", "agent_a", "agent_b")
        self.registry.register(c)
        assert self.registry.get("agent_a", "agent_b") == c

    def test_get_nonexistent(self):
        assert self.registry.get("x", "y") is None

    def test_get_by_name(self):
        c = make_contract("c1", "a", "b")
        self.registry.register(c)
        assert self.registry.get_by_name("c1") == c
        assert self.registry.get_by_name("nonexistent") is None

    def test_list_all(self):
        c1 = make_contract("c1", "a", "b")
        c2 = make_contract("c2", "b", "c")
        self.registry.register(c1)
        self.registry.register(c2)
        assert len(self.registry.list_all()) == 2

    def test_coverage_matrix(self):
        self.registry.register(make_contract("c1", "a", "b"))
        self.registry.register(make_contract("c2", "b", "c"))
        matrix = self.registry.coverage_matrix()
        assert matrix["a"]["b"] == "covered"
        assert matrix["b"]["c"] == "covered"
        assert matrix["a"]["c"] == "uncovered"
        assert matrix["a"]["a"] == "self"

    def test_overwrite_contract(self):
        c1 = make_contract("c1", "a", "b", mode="warn")
        c2 = make_contract("c2", "a", "b", mode="block")
        self.registry.register(c1)
        self.registry.register(c2)
        assert self.registry.get("a", "b").mode == "block"


class TestContractModel:
    def test_default_mode(self):
        c = Contract(name="test", source="a", target="b")
        assert c.mode == "warn"

    def test_with_rules(self):
        c = Contract(
            name="test",
            source="a",
            target="b",
            rules=[
                ContractRule(rule_type="allow_fields", config={"fields": ["name"]}),
                ContractRule(rule_type="deny_fields", config={"fields": ["ssn"]}),
            ],
        )
        assert len(c.rules) == 2
        assert c.rules[0].rule_type == "allow_fields"

    def test_with_nl_rules(self):
        c = Contract(
            name="test",
            source="a",
            target="b",
            nl_rules=["Must include GDPR tag"],
        )
        assert len(c.nl_rules) == 1
