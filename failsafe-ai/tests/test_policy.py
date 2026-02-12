"""Tests for policy engine and finance pack."""

import pytest

from failsafe.core.models import HandoffPayload
from failsafe.core.policy import Policy, PolicyEngine, PolicyPack
from failsafe.policies.finance import finance_pack


def make_payload(data=None, metadata=None) -> HandoffPayload:
    return HandoffPayload(
        source="agent_a",
        target="agent_b",
        data=data or {},
        metadata=metadata or {},
    )


class TestPolicyEngine:
    def setup_method(self):
        self.engine = PolicyEngine()

    def test_no_packs_no_violations(self):
        payload = make_payload(data={"x": 1})
        assert self.engine.evaluate(payload) == []

    def test_load_and_evaluate(self):
        pack = PolicyPack(
            name="test",
            policies=[
                Policy(
                    name="test_policy",
                    description="Always fails",
                    condition=lambda p: True,
                    check=lambda p: __import__("failsafe.core.models", fromlist=["Violation"]).Violation(
                        rule="test", message="Always fails", source_agent=p.source, target_agent=p.target
                    ),
                )
            ],
        )
        self.engine.load_pack(pack)
        violations = self.engine.evaluate(make_payload())
        assert len(violations) == 1

    def test_condition_not_met(self):
        pack = PolicyPack(
            name="test",
            policies=[
                Policy(
                    name="never_applies",
                    description="Condition never met",
                    condition=lambda p: False,
                    check=lambda p: __import__("failsafe.core.models", fromlist=["Violation"]).Violation(
                        rule="test", message="Should not fire", source_agent=p.source, target_agent=p.target
                    ),
                )
            ],
        )
        self.engine.load_pack(pack)
        violations = self.engine.evaluate(make_payload())
        assert len(violations) == 0


class TestFinancePack:
    def setup_method(self):
        self.engine = PolicyEngine()
        self.engine.load_pack(finance_pack)

    def test_large_transaction_no_approval(self):
        payload = make_payload(
            data={"amount": 50000, "human_approved": False},
            metadata={"transaction_limit": 10000},
        )
        violations = self.engine.evaluate(payload)
        assert any(v.rule == "large_transaction_approval" for v in violations)

    def test_large_transaction_with_approval(self):
        payload = make_payload(
            data={"amount": 50000, "human_approved": True},
            metadata={"transaction_limit": 10000},
        )
        violations = self.engine.evaluate(payload)
        assert not any(v.rule == "large_transaction_approval" for v in violations)

    def test_small_transaction_passes(self):
        payload = make_payload(data={"amount": 500})
        violations = self.engine.evaluate(payload)
        assert not any(v.rule == "large_transaction_approval" for v in violations)

    def test_pii_leakage_ssn_field(self):
        payload = make_payload(data={"name": "Alice", "ssn": "123-45-6789"})
        violations = self.engine.evaluate(payload)
        assert any(v.rule == "pii_isolation" for v in violations)

    def test_pii_leakage_in_text(self):
        payload = make_payload(data={"notes": "SSN: 123-45-6789"})
        violations = self.engine.evaluate(payload)
        assert any(v.rule == "pii_isolation" for v in violations)

    def test_no_pii_passes(self):
        payload = make_payload(data={"name": "Alice", "status": "verified"})
        violations = self.engine.evaluate(payload)
        assert not any(v.rule == "pii_isolation" for v in violations)

    def test_gdpr_eu_data_no_tag(self):
        payload = make_payload(data={"name": "Hans", "country": "DE"})
        violations = self.engine.evaluate(payload)
        assert any(v.rule == "gdpr_tagging" for v in violations)

    def test_gdpr_eu_data_with_tag(self):
        payload = make_payload(
            data={"name": "Hans", "country": "DE", "gdpr_tag": "consent_obtained"}
        )
        violations = self.engine.evaluate(payload)
        assert not any(v.rule == "gdpr_tagging" for v in violations)

    def test_non_eu_data_no_gdpr_needed(self):
        payload = make_payload(data={"name": "John", "country": "US"})
        violations = self.engine.evaluate(payload)
        assert not any(v.rule == "gdpr_tagging" for v in violations)
