"""Finance compliance rules for SOX, SEC, FINRA, and PCI-DSS."""

from __future__ import annotations
from typing import Optional

from models import (
    AgentIdentity,
    HandoffContract,
    HandoffPayload,
    PolicySeverity,
    PolicyViolation,
)


class FinancePolicyPack:
    PACK_NAME = "finance_v1"
    
    def evaluate(
        self,
        contract: HandoffContract,
        payload: HandoffPayload,
        consumer: Optional[AgentIdentity],
        provider: Optional[AgentIdentity],
    ) -> list[PolicyViolation]:
        violations = []

        finance_scopes = {"SOX", "SEC", "FINRA", "PCI-DSS"}
        contract_scopes = set(contract.required_compliance_scopes)
        
        if not contract_scopes.intersection(finance_scopes):
            return violations

        rules = [
            self._check_pii_exposure,
            self._check_financial_amount_limits,
            self._check_account_number_masking,
            self._check_trade_authorization,
            self._check_segregation_of_duties,
            self._check_audit_trail_metadata,
            self._check_ssn_exposure,
            self._check_cross_boundary_data_leak,
            self._check_material_nonpublic_info,
            self._check_transaction_approval_threshold,
        ]
        
        for rule in rules:
            result = rule(contract, payload, consumer, provider)
            if result:
                if isinstance(result, list):
                    violations.extend(result)
                else:
                    violations.append(result)
        
        return violations

    # PII / sensitive data

    def _check_pii_exposure(
        self, contract, payload, consumer, provider
    ) -> Optional[PolicyViolation]:
        if not consumer:
            return None

        pii_fields = [f for f in contract.request_schema if f.pii]
        if not pii_fields:
            return None

        for field in pii_fields:
            if payload.data.get(field.name):
                if "pii" not in consumer.allowed_data_domains:
                    return PolicyViolation(
                        rule_id="FIN-PII-001",
                        rule_name="pii_exposure_to_unauthorized_agent",
                        severity=PolicySeverity.CRITICAL,
                        message=(
                            f"PII field '{field.name}' is being passed to agent '{consumer.name}' "
                            f"which is not authorized for PII data"
                        ),
                        field_path=field.name,
                        policy_pack=self.PACK_NAME,
                    )
        return None
    
    def _check_ssn_exposure(
        self, contract, payload, consumer, provider
    ) -> Optional[PolicyViolation]:
        import re
        ssn_pattern = r'\b\d{3}-?\d{2}-?\d{4}\b'
        
        def check_value(value, path=""):
            if isinstance(value, str):
                if re.search(ssn_pattern, value):
                    return PolicyViolation(
                        rule_id="FIN-PII-002",
                        rule_name="ssn_in_payload",
                        severity=PolicySeverity.CRITICAL,
                        message=f"SSN pattern detected in field '{path}'",
                        field_path=path,
                        policy_pack=self.PACK_NAME,
                    )
            elif isinstance(value, dict):
                for k, v in value.items():
                    result = check_value(v, f"{path}.{k}" if path else k)
                    if result:
                        return result
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    result = check_value(v, f"{path}[{i}]")
                    if result:
                        return result
            return None
        
        return check_value(payload.data)
    
    def _check_account_number_masking(
        self, contract, payload, consumer, provider
    ) -> Optional[PolicyViolation]:
        import re

        for key, value in payload.data.items():
            if "account" in key.lower() and isinstance(value, str):
                if re.match(r'^\d{8,}$', value):  # unmasked
                    return PolicyViolation(
                        rule_id="FIN-PII-003",
                        rule_name="unmasked_account_number",
                        severity=PolicySeverity.HIGH,
                        message=f"Account number in field '{key}' appears unmasked. Must show only last 4 digits.",
                        field_path=key,
                        policy_pack=self.PACK_NAME,
                    )
        return None

    # Authorization

    def _check_financial_amount_limits(
        self, contract, payload, consumer, provider
    ) -> Optional[PolicyViolation]:
        amount = payload.data.get("amount") or payload.data.get("transaction_amount")
        if amount is None:
            return None
        
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return PolicyViolation(
                rule_id="FIN-AUTH-001",
                rule_name="invalid_amount_format",
                severity=PolicySeverity.HIGH,
                message="Financial amount is not a valid number",
                field_path="amount",
                policy_pack=self.PACK_NAME,
            )

        agent_limit = None
        if consumer:
            agent_limit = next(
                (float(d.split(":")[1]) for d in consumer.allowed_data_domains 
                 if d.startswith("max_amount:")),
                None
            )
        
        if agent_limit and amount > agent_limit:
            return PolicyViolation(
                rule_id="FIN-AUTH-001",
                rule_name="amount_exceeds_agent_limit",
                severity=PolicySeverity.CRITICAL,
                message=f"Amount ${amount:,.2f} exceeds agent's authorized limit of ${agent_limit:,.2f}",
                field_path="amount",
                expected=f"<= {agent_limit}",
                actual=amount,
                policy_pack=self.PACK_NAME,
            )
        return None
    
    def _check_trade_authorization(
        self, contract, payload, consumer, provider
    ) -> Optional[PolicyViolation]:
        action = payload.metadata.get("action", "")
        trade_actions = {"buy", "sell", "trade", "execute_order", "place_order", "transfer"}
        
        if action.lower() in trade_actions:
            if consumer and consumer.authority_level.value not in ("execute", "admin"):
                return PolicyViolation(
                    rule_id="FIN-AUTH-002",
                    rule_name="trade_without_execute_authority",
                    severity=PolicySeverity.CRITICAL,
                    message=f"Trade action '{action}' requires execute-level authority",
                    expected="execute or admin",
                    actual=consumer.authority_level.value if consumer else "unknown",
                    policy_pack=self.PACK_NAME,
                )
        return None
    
    def _check_transaction_approval_threshold(
        self, contract, payload, consumer, provider
    ) -> Optional[PolicyViolation]:
        amount = payload.data.get("amount") or payload.data.get("transaction_amount")
        if amount is None:
            return None
        
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return None
        
        APPROVAL_THRESHOLD = 10000.0
        
        if amount > APPROVAL_THRESHOLD:
            has_approval = payload.metadata.get("human_approved", False)
            if not has_approval:
                return PolicyViolation(
                    rule_id="FIN-AUTH-003",
                    rule_name="large_transaction_no_approval",
                    severity=PolicySeverity.HIGH,
                    message=f"Transaction amount ${amount:,.2f} exceeds ${APPROVAL_THRESHOLD:,.2f} threshold and requires human approval",
                    field_path="amount",
                    policy_pack=self.PACK_NAME,
                )
        return None

    # SOX audit

    def _check_audit_trail_metadata(
        self, contract, payload, consumer, provider
    ) -> list[PolicyViolation]:
        violations = []
        
        if "SOX" not in contract.required_compliance_scopes:
            return violations
        
        required_metadata = ["request_id", "timestamp", "initiator"]
        
        for field in required_metadata:
            if field not in payload.metadata:
                violations.append(PolicyViolation(
                    rule_id="FIN-AUDIT-001",
                    rule_name="missing_audit_metadata",
                    severity=PolicySeverity.HIGH,
                    message=f"SOX requires '{field}' in handoff metadata for audit trail",
                    field_path=f"metadata.{field}",
                    policy_pack=self.PACK_NAME,
                ))
        
        return violations
    
    def _check_segregation_of_duties(
        self, contract, payload, consumer, provider
    ) -> Optional[PolicyViolation]:
        if "SOX" not in contract.required_compliance_scopes:
            return None
        
        approver = payload.metadata.get("approved_by", "")
        executor = consumer.name if consumer else ""
        
        if approver and executor and approver == executor:
            return PolicyViolation(
                rule_id="FIN-AUDIT-002",
                rule_name="segregation_of_duties_violation",
                severity=PolicySeverity.CRITICAL,
                message=f"SOX violation: Agent '{executor}' cannot both approve and execute the same transaction",
                policy_pack=self.PACK_NAME,
            )
        return None

    # SEC / data boundaries

    def _check_cross_boundary_data_leak(
        self, contract, payload, consumer, provider
    ) -> Optional[PolicyViolation]:
        if not consumer or not provider:
            return None

        financial_fields = [f for f in contract.request_schema if f.financial_data]
        if not financial_fields:
            return None
        
        if "financial_records" not in consumer.allowed_data_domains:
            for field in financial_fields:
                if payload.data.get(field.name):
                    return PolicyViolation(
                        rule_id="FIN-DATA-001",
                        rule_name="financial_data_boundary_violation",
                        severity=PolicySeverity.CRITICAL,
                        message=(
                            f"Financial data field '{field.name}' is being passed to agent "
                            f"'{consumer.name}' which is not authorized for financial records"
                        ),
                        field_path=field.name,
                        policy_pack=self.PACK_NAME,
                    )
        return None
    
    def _check_material_nonpublic_info(
        self, contract, payload, consumer, provider
    ) -> Optional[PolicyViolation]:
        if "SEC" not in contract.required_compliance_scopes:
            return None
        
        mnpi_indicators = [
            "earnings", "merger", "acquisition", "insider", "material",
            "non-public", "nonpublic", "pre-release", "guidance",
        ]
        
        data_str = str(payload.data).lower()
        found_indicators = [ind for ind in mnpi_indicators if ind in data_str]
        
        if found_indicators:
            has_mnpi_flag = payload.metadata.get("mnpi_reviewed", False)
            if not has_mnpi_flag:
                return PolicyViolation(
                    rule_id="FIN-SEC-001",
                    rule_name="potential_mnpi_unflagged",
                    severity=PolicySeverity.HIGH,
                    message=(
                        f"Payload may contain material non-public information "
                        f"(indicators: {found_indicators}). Must be flagged with 'mnpi_reviewed' metadata."
                    ),
                    policy_pack=self.PACK_NAME,
                )
        return None
