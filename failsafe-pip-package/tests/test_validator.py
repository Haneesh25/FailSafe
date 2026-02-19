"""Tests for deterministic validator."""

import pytest

from failsafe.core.models import Contract, ContractRule, HandoffPayload
from failsafe.core.validator import DeterministicValidator


def make_payload(source="a", target="b", data=None) -> HandoffPayload:
    return HandoffPayload(source=source, target=target, data=data or {})


def make_contract(rules: list[ContractRule]) -> Contract:
    return Contract(name="test", source="a", target="b", rules=rules)


class TestAllowFields:
    def setup_method(self):
        self.validator = DeterministicValidator()

    def test_allowed_fields_pass(self):
        contract = make_contract(
            [ContractRule(rule_type="allow_fields", config={"fields": ["name", "age"]})]
        )
        payload = make_payload(data={"name": "Alice", "age": 30})
        result = self.validator.validate(payload, contract)
        assert result.passed

    def test_extra_fields_fail(self):
        contract = make_contract(
            [ContractRule(rule_type="allow_fields", config={"fields": ["name"]})]
        )
        payload = make_payload(data={"name": "Alice", "ssn": "123-45-6789"})
        result = self.validator.validate(payload, contract)
        assert not result.passed
        assert result.violations[0].rule == "allow_fields"
        assert "ssn" in result.violations[0].message


class TestDenyFields:
    def setup_method(self):
        self.validator = DeterministicValidator()

    def test_no_denied_fields_pass(self):
        contract = make_contract(
            [ContractRule(rule_type="deny_fields", config={"fields": ["ssn"], "scan_values": False})]
        )
        payload = make_payload(data={"name": "Alice"})
        result = self.validator.validate(payload, contract)
        assert result.passed

    def test_denied_field_present_fails(self):
        contract = make_contract(
            [ContractRule(rule_type="deny_fields", config={"fields": ["ssn"], "scan_values": False})]
        )
        payload = make_payload(data={"name": "Alice", "ssn": "123-45-6789"})
        result = self.validator.validate(payload, contract)
        assert not result.passed
        assert result.violations[0].severity == "critical"

    def test_denied_pattern_in_text(self):
        contract = make_contract(
            [
                ContractRule(
                    rule_type="deny_fields",
                    config={"fields": [], "scan_values": True, "patterns": ["ssn"]},
                )
            ]
        )
        payload = make_payload(
            data={"notes": "Client SSN is 123-45-6789 for reference"}
        )
        result = self.validator.validate(payload, contract)
        assert not result.passed
        assert "ssn" in result.violations[0].message.lower()

    def test_nested_denied_field(self):
        contract = make_contract(
            [ContractRule(rule_type="deny_fields", config={"fields": ["personal.ssn"], "scan_values": False})]
        )
        payload = make_payload(data={"personal": {"ssn": "123-45-6789"}})
        result = self.validator.validate(payload, contract)
        assert not result.passed


class TestRequireFields:
    def setup_method(self):
        self.validator = DeterministicValidator()

    def test_all_required_present(self):
        contract = make_contract(
            [ContractRule(rule_type="require_fields", config={"fields": ["name", "status"]})]
        )
        payload = make_payload(data={"name": "Alice", "status": "verified"})
        result = self.validator.validate(payload, contract)
        assert result.passed

    def test_missing_required_fails(self):
        contract = make_contract(
            [ContractRule(rule_type="require_fields", config={"fields": ["name", "status"]})]
        )
        payload = make_payload(data={"name": "Alice"})
        result = self.validator.validate(payload, contract)
        assert not result.passed
        assert "status" in result.violations[0].message


class TestFieldValue:
    def setup_method(self):
        self.validator = DeterministicValidator()

    def test_one_of_pass(self):
        contract = make_contract(
            [
                ContractRule(
                    rule_type="field_value",
                    config={"field": "status", "one_of": ["verified", "pending"]},
                )
            ]
        )
        payload = make_payload(data={"status": "verified"})
        result = self.validator.validate(payload, contract)
        assert result.passed

    def test_one_of_fail(self):
        contract = make_contract(
            [
                ContractRule(
                    rule_type="field_value",
                    config={"field": "status", "one_of": ["verified", "pending"]},
                )
            ]
        )
        payload = make_payload(data={"status": "unknown"})
        result = self.validator.validate(payload, contract)
        assert not result.passed

    def test_range_pass(self):
        contract = make_contract(
            [ContractRule(rule_type="field_value", config={"field": "age", "min": 0, "max": 150})]
        )
        payload = make_payload(data={"age": 25})
        result = self.validator.validate(payload, contract)
        assert result.passed

    def test_range_fail(self):
        contract = make_contract(
            [ContractRule(rule_type="field_value", config={"field": "age", "min": 0, "max": 150})]
        )
        payload = make_payload(data={"age": 200})
        result = self.validator.validate(payload, contract)
        assert not result.passed

    def test_regex_pass(self):
        contract = make_contract(
            [ContractRule(rule_type="field_value", config={"field": "email", "regex": r"^.+@.+\..+$"})]
        )
        payload = make_payload(data={"email": "test@example.com"})
        result = self.validator.validate(payload, contract)
        assert result.passed

    def test_regex_fail(self):
        contract = make_contract(
            [ContractRule(rule_type="field_value", config={"field": "email", "regex": r"^.+@.+\..+$"})]
        )
        payload = make_payload(data={"email": "not-an-email"})
        result = self.validator.validate(payload, contract)
        assert not result.passed

    def test_type_check(self):
        contract = make_contract(
            [ContractRule(rule_type="field_value", config={"field": "count", "type": "int"})]
        )
        payload = make_payload(data={"count": "not_a_number"})
        result = self.validator.validate(payload, contract)
        assert not result.passed

    def test_missing_field_skipped(self):
        contract = make_contract(
            [ContractRule(rule_type="field_value", config={"field": "missing", "one_of": ["a"]})]
        )
        payload = make_payload(data={"other": "value"})
        result = self.validator.validate(payload, contract)
        assert result.passed


class TestCustomRule:
    def setup_method(self):
        self.validator = DeterministicValidator()

    def test_custom_pass(self):
        contract = make_contract(
            [
                ContractRule(
                    rule_type="custom",
                    config={"func": lambda p: True},
                )
            ]
        )
        payload = make_payload(data={"x": 1})
        result = self.validator.validate(payload, contract)
        assert result.passed

    def test_custom_fail(self):
        contract = make_contract(
            [
                ContractRule(
                    rule_type="custom",
                    config={"func": lambda p: False, "message": "Custom failed"},
                )
            ]
        )
        payload = make_payload(data={"x": 1})
        result = self.validator.validate(payload, contract)
        assert not result.passed
        assert result.violations[0].message == "Custom failed"


class TestSanitization:
    def setup_method(self):
        self.validator = DeterministicValidator()

    def test_sanitized_payload_removes_violations(self):
        contract = make_contract(
            [ContractRule(rule_type="deny_fields", config={"fields": ["ssn"], "scan_values": False})]
        )
        payload = make_payload(data={"name": "Alice", "ssn": "123-45-6789"})
        result = self.validator.validate(payload, contract)
        assert "ssn" not in result.sanitized_payload
        assert "name" in result.sanitized_payload
