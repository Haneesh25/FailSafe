"""Deterministic validation engine — fast path, no LLM calls."""

from __future__ import annotations

import re
import time
from typing import Any

from failsafe.core.models import (
    Contract,
    ContractRule,
    HandoffPayload,
    ValidationResult,
    Violation,
)

# Patterns for sensitive data detection in free-text fields
SENSITIVE_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(r"\b\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b"),
}


def _flatten_keys(data: dict[str, Any], prefix: str = "") -> set[str]:
    """Recursively extract all keys from nested dicts."""
    keys: set[str] = set()
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        keys.add(full_key)
        if isinstance(value, dict):
            keys.update(_flatten_keys(value, full_key))
    return keys


def _flatten_values(data: dict[str, Any]) -> list[str]:
    """Recursively extract all string values from nested dicts."""
    values: list[str] = []
    for value in data.values():
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, dict):
            values.extend(_flatten_values(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    values.append(item)
                elif isinstance(item, dict):
                    values.extend(_flatten_values(item))
    return values


def _get_nested(data: dict[str, Any], path: str) -> Any:
    """Get a value from a nested dict using dot notation."""
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


class DeterministicValidator:
    """Validates handoff payloads against contract rules."""

    def validate(
        self, payload: HandoffPayload, contract: Contract
    ) -> ValidationResult:
        start = time.monotonic()
        violations: list[Violation] = []

        for rule in contract.rules:
            result = self._evaluate_rule(rule, payload)
            if result:
                violations.append(result)

        duration_ms = (time.monotonic() - start) * 1000
        return ValidationResult(
            passed=len(violations) == 0,
            violations=violations,
            sanitized_payload=(
                self._sanitize(payload.data, violations) if violations else None
            ),
            contract_name=contract.name,
            validation_mode="deterministic",
            duration_ms=duration_ms,
        )

    def _evaluate_rule(
        self, rule: ContractRule, payload: HandoffPayload
    ) -> Violation | None:
        match rule.rule_type:
            case "allow_fields":
                return self._check_allow_fields(rule, payload)
            case "deny_fields":
                return self._check_deny_fields(rule, payload)
            case "require_fields":
                return self._check_require_fields(rule, payload)
            case "field_value":
                return self._check_field_value(rule, payload)
            case "custom":
                return self._check_custom(rule, payload)
        return None

    def _check_allow_fields(
        self, rule: ContractRule, payload: HandoffPayload
    ) -> Violation | None:
        allowed = set(rule.config.get("fields", []))
        actual = _flatten_keys(payload.data)
        # Only check top-level keys for allow_fields
        top_level = {k for k in actual if "." not in k}
        extra = top_level - allowed
        if extra:
            return Violation(
                rule="allow_fields",
                severity="high",
                message=f"Disallowed fields present: {sorted(extra)}",
                field=", ".join(sorted(extra)),
                evidence={"extra_fields": sorted(extra)},
                source_agent=payload.source,
                target_agent=payload.target,
            )
        return None

    def _check_deny_fields(
        self, rule: ContractRule, payload: HandoffPayload
    ) -> Violation | None:
        denied = set(rule.config.get("fields", []))
        actual = _flatten_keys(payload.data)

        found = denied & actual
        if found:
            return Violation(
                rule="deny_fields",
                severity="critical",
                message=f"Denied fields found in payload: {sorted(found)}",
                field=", ".join(sorted(found)),
                evidence={"denied_fields_found": sorted(found)},
                source_agent=payload.source,
                target_agent=payload.target,
            )

        # Also scan string values for denied field patterns
        if rule.config.get("scan_values", True):
            denied_patterns = rule.config.get("patterns", [])
            for pattern_name in denied_patterns:
                if pattern_name in SENSITIVE_PATTERNS:
                    for text in _flatten_values(payload.data):
                        if SENSITIVE_PATTERNS[pattern_name].search(text):
                            return Violation(
                                rule="deny_fields",
                                severity="critical",
                                message=f"Sensitive pattern '{pattern_name}' found in payload text",
                                evidence={"pattern": pattern_name},
                                source_agent=payload.source,
                                target_agent=payload.target,
                            )
        return None

    def _check_require_fields(
        self, rule: ContractRule, payload: HandoffPayload
    ) -> Violation | None:
        required = set(rule.config.get("fields", []))
        actual = _flatten_keys(payload.data)
        top_level = {k for k in actual if "." not in k}
        missing = required - top_level
        if missing:
            return Violation(
                rule="require_fields",
                severity="high",
                message=f"Required fields missing: {sorted(missing)}",
                field=", ".join(sorted(missing)),
                evidence={"missing_fields": sorted(missing)},
                source_agent=payload.source,
                target_agent=payload.target,
            )
        return None

    def _check_field_value(
        self, rule: ContractRule, payload: HandoffPayload
    ) -> Violation | None:
        field = rule.config.get("field", "")
        value = _get_nested(payload.data, field)

        if value is None:
            return None

        # one_of check
        one_of = rule.config.get("one_of")
        if one_of is not None and value not in one_of:
            return Violation(
                rule="field_value",
                severity="medium",
                message=f"Field '{field}' has value '{value}', expected one of {one_of}",
                field=field,
                evidence={"actual": value, "expected_one_of": one_of},
                source_agent=payload.source,
                target_agent=payload.target,
            )

        # range check
        min_val = rule.config.get("min")
        max_val = rule.config.get("max")
        if min_val is not None and value < min_val:
            return Violation(
                rule="field_value",
                severity="medium",
                message=f"Field '{field}' value {value} is below minimum {min_val}",
                field=field,
                evidence={"actual": value, "min": min_val},
                source_agent=payload.source,
                target_agent=payload.target,
            )
        if max_val is not None and value > max_val:
            return Violation(
                rule="field_value",
                severity="medium",
                message=f"Field '{field}' value {value} exceeds maximum {max_val}",
                field=field,
                evidence={"actual": value, "max": max_val},
                source_agent=payload.source,
                target_agent=payload.target,
            )

        # regex check
        pattern = rule.config.get("regex")
        if pattern is not None and isinstance(value, str):
            if not re.match(pattern, value):
                return Violation(
                    rule="field_value",
                    severity="medium",
                    message=f"Field '{field}' value '{value}' does not match pattern '{pattern}'",
                    field=field,
                    evidence={"actual": value, "pattern": pattern},
                    source_agent=payload.source,
                    target_agent=payload.target,
                )

        # type check
        expected_type = rule.config.get("type")
        if expected_type is not None:
            type_map = {
                "str": str,
                "int": int,
                "float": (int, float),
                "bool": bool,
                "list": list,
                "dict": dict,
            }
            expected = type_map.get(expected_type)
            if expected and not isinstance(value, expected):
                return Violation(
                    rule="field_value",
                    severity="medium",
                    message=f"Field '{field}' has type {type(value).__name__}, expected {expected_type}",
                    field=field,
                    evidence={
                        "actual_type": type(value).__name__,
                        "expected_type": expected_type,
                    },
                    source_agent=payload.source,
                    target_agent=payload.target,
                )

        return None

    def _check_custom(
        self, rule: ContractRule, payload: HandoffPayload
    ) -> Violation | None:
        func = rule.config.get("func")
        if func is None or not callable(func):
            return None
        try:
            result = func(payload)
            if isinstance(result, Violation):
                return result
            if result is False:
                return Violation(
                    rule="custom",
                    severity=rule.config.get("severity", "medium"),
                    message=rule.config.get("message", "Custom rule check failed"),
                    source_agent=payload.source,
                    target_agent=payload.target,
                )
        except Exception as e:
            return Violation(
                rule="custom",
                severity="high",
                message=f"Custom rule raised exception: {e}",
                source_agent=payload.source,
                target_agent=payload.target,
            )
        return None

    def _sanitize(
        self, data: dict[str, Any], violations: list[Violation]
    ) -> dict[str, Any]:
        """Remove fields that caused violations from the payload."""
        sanitized = dict(data)
        for v in violations:
            if v.field:
                for field_name in v.field.split(", "):
                    sanitized.pop(field_name, None)
        return sanitized
