"""Finance policy pack — SOX, GDPR, data isolation rules."""

from __future__ import annotations

import re

from failsafe.core.models import HandoffPayload, Violation
from failsafe.core.policy import Policy, PolicyPack

SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
ACCOUNT_PATTERN = re.compile(r"\b\d{8,17}\b")

EU_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE",
}


def _is_eu_data(payload: HandoffPayload) -> bool:
    country = payload.data.get("country", "").upper()
    region = payload.data.get("region", "").upper()
    return country in EU_COUNTRIES or region == "EU"


def _scan_text_for_patterns(data: dict) -> list[str]:
    """Recursively scan all string values for sensitive patterns."""
    found: list[str] = []
    for value in data.values():
        if isinstance(value, str):
            if SSN_PATTERN.search(value):
                found.append("ssn")
            if ACCOUNT_PATTERN.search(value):
                found.append("account_number")
        elif isinstance(value, dict):
            found.extend(_scan_text_for_patterns(value))
    return found


def _check_pii_leakage(payload: HandoffPayload) -> Violation | None:
    pii_fields = {"ssn", "social_security", "tax_id", "bank_account", "account_number"}
    found = pii_fields & set(payload.data.keys())

    patterns_found = _scan_text_for_patterns(payload.data)

    if found or patterns_found:
        return Violation(
            rule="pii_isolation",
            severity="critical",
            message=f"PII detected crossing agent boundary: fields={sorted(found)}, patterns={patterns_found}",
            evidence={"pii_fields": sorted(found), "patterns": patterns_found},
            source_agent=payload.source,
            target_agent=payload.target,
        )
    return None


finance_pack = PolicyPack(
    name="finance",
    policies=[
        Policy(
            name="large_transaction_approval",
            description="Transactions over threshold require human approval",
            condition=lambda p: "amount" in p.data,
            check=lambda p: (
                Violation(
                    rule="large_transaction_approval",
                    severity="critical",
                    message=f"Transaction amount {p.data['amount']} exceeds limit "
                    f"{p.metadata.get('transaction_limit', 10000)} without human approval",
                    field="amount",
                    evidence={
                        "amount": p.data["amount"],
                        "limit": p.metadata.get("transaction_limit", 10000),
                        "human_approved": p.data.get("human_approved", False),
                    },
                    source_agent=p.source,
                    target_agent=p.target,
                )
                if p.data.get("amount", 0)
                > p.metadata.get("transaction_limit", 10000)
                and not p.data.get("human_approved")
                else None
            ),
            severity="critical",
        ),
        Policy(
            name="pii_isolation",
            description="PII fields must not cross agent boundaries without explicit allow",
            condition=lambda p: True,
            check=_check_pii_leakage,
            severity="critical",
        ),
        Policy(
            name="gdpr_tagging",
            description="EU client data must include GDPR processing tag",
            condition=_is_eu_data,
            check=lambda p: (
                Violation(
                    rule="gdpr_tagging",
                    severity="high",
                    message="EU client data missing GDPR processing tag",
                    field="gdpr_tag",
                    evidence={"country": p.data.get("country", ""), "region": p.data.get("region", "")},
                    source_agent=p.source,
                    target_agent=p.target,
                )
                if "gdpr_tag" not in p.data
                else None
            ),
            severity="high",
        ),
    ],
)
