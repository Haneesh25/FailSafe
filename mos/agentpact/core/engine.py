"""Three-layer validation engine: schema, authority, and policy."""

from __future__ import annotations
import re
import time
from typing import Any, Optional

from .models import (
    AgentIdentity,
    AuthorityLevel,
    ContractRegistry,
    FieldContract,
    HandoffContract,
    HandoffDirection,
    HandoffPayload,
    HandoffValidationResult,
    PolicySeverity,
    PolicyViolation,
    ValidationResult,
)


AUTHORITY_HIERARCHY = {
    AuthorityLevel.READ_ONLY: 0,
    AuthorityLevel.READ_WRITE: 1,
    AuthorityLevel.EXECUTE: 2,
    AuthorityLevel.ADMIN: 3,
}

DATA_CLASSIFICATION_HIERARCHY = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


class ValidationEngine:
    def __init__(self, registry: ContractRegistry):
        self.registry = registry
        self._policy_packs: list = []

    def register_policy_pack(self, policy_pack) -> None:
        self._policy_packs.append(policy_pack)

    def validate_handoff(
        self,
        consumer_name: str,
        provider_name: str,
        payload: HandoffPayload,
        direction: HandoffDirection = HandoffDirection.REQUEST,
    ) -> HandoffValidationResult:
        start_time = time.time()
        
        result = HandoffValidationResult(
            consumer_agent=consumer_name,
            provider_agent=provider_name,
            direction=direction,
            payload_snapshot=payload.data.copy(),
        )
        
        contract = self.registry.get_contract_for_handoff(consumer_name, provider_name)
        if not contract:
            result.schema_violations.append(PolicyViolation(
                rule_id="CONTRACT_001",
                rule_name="missing_contract",
                severity=PolicySeverity.CRITICAL,
                message=f"No contract found for handoff: {consumer_name} → {provider_name}",
            ))
            result.overall_result = ValidationResult.FAIL
            result.validation_duration_ms = (time.time() - start_time) * 1000
            return result
        
        result.contract_id = contract.contract_id

        schema = contract.request_schema if direction == HandoffDirection.REQUEST else contract.response_schema
        result.schema_violations = self._validate_schema(payload.data, schema)

        consumer = self.registry.get_agent(consumer_name)
        provider = self.registry.get_agent(provider_name)
        result.authority_violations = self._validate_authority(
            consumer, provider, contract, payload
        )

        for policy_pack in self._policy_packs:
            violations = policy_pack.evaluate(contract, payload, consumer, provider)
            result.policy_violations.extend(violations)

        all_violations = (
            result.schema_violations + 
            result.policy_violations + 
            result.authority_violations
        )
        
        if any(v.severity in (PolicySeverity.CRITICAL, PolicySeverity.HIGH) for v in all_violations):
            result.overall_result = ValidationResult.FAIL
        elif any(v.severity == PolicySeverity.MEDIUM for v in all_violations):
            result.overall_result = ValidationResult.WARN
        else:
            result.overall_result = ValidationResult.PASS
        
        result.validation_duration_ms = (time.time() - start_time) * 1000
        return result
    
    def _validate_schema(
        self, data: dict[str, Any], schema: list[FieldContract]
    ) -> list[PolicyViolation]:
        violations = []
        
        for field_contract in schema:
            value = data.get(field_contract.name)
            
            if field_contract.required and value is None:
                violations.append(PolicyViolation(
                    rule_id="SCHEMA_001",
                    rule_name="required_field_missing",
                    severity=PolicySeverity.HIGH,
                    message=f"Required field '{field_contract.name}' is missing",
                    field_path=field_contract.name,
                    expected="present",
                    actual="missing",
                ))
                continue
            
            if value is None:
                continue

            type_violation = self._check_type(field_contract, value)
            if type_violation:
                violations.append(type_violation)
                continue

            if field_contract.pattern:
                if not re.match(field_contract.pattern, str(value)):
                    violations.append(PolicyViolation(
                        rule_id="SCHEMA_003",
                        rule_name="pattern_mismatch",
                        severity=PolicySeverity.HIGH,
                        message=f"Field '{field_contract.name}' does not match pattern '{field_contract.pattern}'",
                        field_path=field_contract.name,
                        expected=field_contract.pattern,
                        actual=str(value),
                    ))
            
            if field_contract.enum_values and value not in field_contract.enum_values:
                violations.append(PolicyViolation(
                    rule_id="SCHEMA_004",
                    rule_name="invalid_enum_value",
                    severity=PolicySeverity.HIGH,
                    message=f"Field '{field_contract.name}' has invalid value '{value}'. Allowed: {field_contract.enum_values}",
                    field_path=field_contract.name,
                    expected=field_contract.enum_values,
                    actual=value,
                ))
            
            if field_contract.min_value is not None and isinstance(value, (int, float)):
                if value < field_contract.min_value:
                    violations.append(PolicyViolation(
                        rule_id="SCHEMA_005",
                        rule_name="below_minimum",
                        severity=PolicySeverity.HIGH,
                        message=f"Field '{field_contract.name}' value {value} is below minimum {field_contract.min_value}",
                        field_path=field_contract.name,
                        expected=f">= {field_contract.min_value}",
                        actual=value,
                    ))
            
            if field_contract.max_value is not None and isinstance(value, (int, float)):
                if value > field_contract.max_value:
                    violations.append(PolicyViolation(
                        rule_id="SCHEMA_006",
                        rule_name="above_maximum",
                        severity=PolicySeverity.HIGH,
                        message=f"Field '{field_contract.name}' value {value} is above maximum {field_contract.max_value}",
                        field_path=field_contract.name,
                        expected=f"<= {field_contract.max_value}",
                        actual=value,
                    ))
            
            if field_contract.max_length is not None and isinstance(value, str):
                if len(value) > field_contract.max_length:
                    violations.append(PolicyViolation(
                        rule_id="SCHEMA_007",
                        rule_name="exceeds_max_length",
                        severity=PolicySeverity.MEDIUM,
                        message=f"Field '{field_contract.name}' length {len(value)} exceeds max {field_contract.max_length}",
                        field_path=field_contract.name,
                    ))
        
        schema_field_names = {fc.name for fc in schema}
        for key in data.keys():
            if key not in schema_field_names:
                violations.append(PolicyViolation(
                    rule_id="SCHEMA_008",
                    rule_name="unexpected_field",
                    severity=PolicySeverity.MEDIUM,
                    message=f"Unexpected field '{key}' not defined in contract",
                    field_path=key,
                ))
        
        return violations
    
    def _check_type(self, field_contract: FieldContract, value: Any) -> Optional[PolicyViolation]:
        type_map = {
            "string": str,
            "number": (int, float),
            "boolean": bool,
            "object": dict,
            "array": list,
        }
        expected_type = type_map.get(field_contract.field_type)
        if expected_type and not isinstance(value, expected_type):
            return PolicyViolation(
                rule_id="SCHEMA_002",
                rule_name="type_mismatch",
                severity=PolicySeverity.HIGH,
                message=f"Field '{field_contract.name}' expected type '{field_contract.field_type}', got '{type(value).__name__}'",
                field_path=field_contract.name,
                expected=field_contract.field_type,
                actual=type(value).__name__,
            )
        return None
    
    def _validate_authority(
        self,
        consumer: Optional[AgentIdentity],
        provider: Optional[AgentIdentity],
        contract: HandoffContract,
        payload: HandoffPayload,
    ) -> list[PolicyViolation]:
        violations = []
        
        if not consumer or not provider:
            violations.append(PolicyViolation(
                rule_id="AUTH_001",
                rule_name="unregistered_agent",
                severity=PolicySeverity.CRITICAL,
                message="One or both agents are not registered",
            ))
            return violations
        
        consumer_level = AUTHORITY_HIERARCHY.get(consumer.authority_level, 0)
        required_level = AUTHORITY_HIERARCHY.get(contract.required_authority, 0)
        
        if consumer_level < required_level:
            violations.append(PolicyViolation(
                rule_id="AUTH_002",
                rule_name="insufficient_authority",
                severity=PolicySeverity.CRITICAL,
                message=(
                    f"Agent '{consumer.name}' has authority '{consumer.authority_level.value}' "
                    f"but handoff requires '{contract.required_authority.value}'"
                ),
                expected=contract.required_authority.value,
                actual=consumer.authority_level.value,
            ))
        
        contract_classification = DATA_CLASSIFICATION_HIERARCHY.get(contract.max_data_classification, 0)
        consumer_classification = DATA_CLASSIFICATION_HIERARCHY.get(consumer.max_data_classification, 0)
        
        if contract_classification > consumer_classification:
            violations.append(PolicyViolation(
                rule_id="AUTH_003",
                rule_name="data_classification_exceeded",
                severity=PolicySeverity.CRITICAL,
                message=(
                    f"Agent '{consumer.name}' clearance is '{consumer.max_data_classification}' "
                    f"but handoff contains '{contract.max_data_classification}' data"
                ),
                expected=f"<= {consumer.max_data_classification}",
                actual=contract.max_data_classification,
            ))
        
        action = payload.metadata.get("action", "")
        if action and action in contract.prohibited_actions:
            violations.append(PolicyViolation(
                rule_id="AUTH_004",
                rule_name="prohibited_action",
                severity=PolicySeverity.CRITICAL,
                message=f"Action '{action}' is prohibited by contract",
                expected=f"Not in {contract.prohibited_actions}",
                actual=action,
            ))
        
        if action and contract.allowed_actions and action not in contract.allowed_actions:
            violations.append(PolicyViolation(
                rule_id="AUTH_005",
                rule_name="unauthorized_action",
                severity=PolicySeverity.HIGH,
                message=f"Action '{action}' is not in the allowed actions list: {contract.allowed_actions}",
                expected=contract.allowed_actions,
                actual=action,
            ))
        
        if contract.required_compliance_scopes:
            missing_scopes = set(contract.required_compliance_scopes) - set(consumer.compliance_scopes)
            if missing_scopes:
                violations.append(PolicyViolation(
                    rule_id="AUTH_006",
                    rule_name="missing_compliance_scope",
                    severity=PolicySeverity.HIGH,
                    message=f"Agent '{consumer.name}' is missing compliance scopes: {missing_scopes}",
                    expected=contract.required_compliance_scopes,
                    actual=consumer.compliance_scopes,
                ))
        
        return violations
