"""Full finance agent pipeline with policy pack.

Demonstrates:
- 4-agent pipeline (KYC → Onboarding → Trading → Compliance)
- Finance policy pack (SOX, GDPR, PII isolation)
- Multiple contract types
- Violation detection at every layer

Usage:
    python examples/finance_pipeline.py
"""

import asyncio

from failsafe import FailSafe


async def main():
    # 1. Initialize with finance policy pack
    fs = FailSafe(mode="warn", policy_pack="finance", audit_db=":memory:")

    # 2. Register agents
    fs.register_agent(
        "kyc_agent",
        description="KYC verification agent",
        authority=["read_client_data", "verify_identity"],
    )
    fs.register_agent(
        "onboarding_agent",
        description="Client onboarding flow",
        authority=["create_account", "set_preferences"],
    )
    fs.register_agent(
        "trading_agent",
        description="Executes trades",
        authority=["read_market_data", "execute_trades"],
    )
    fs.register_agent(
        "compliance_agent",
        description="Compliance review and audit",
        authority=["read_all_data", "generate_reports"],
    )

    # 3. Define contracts
    fs.contract(
        name="kyc-to-onboarding",
        source="kyc_agent",
        target="onboarding_agent",
        allow=["name", "date_of_birth", "verification_status", "risk_tier", "country", "gdpr_tag"],
        deny=["ssn", "raw_documents", "bank_account"],
        require=["verification_status"],
        nl_rules=["EU client data must include GDPR processing tag"],
    )

    fs.contract(
        name="onboarding-to-trading",
        source="onboarding_agent",
        target="trading_agent",
        allow=["account_id", "risk_tier", "trading_limits", "approved_instruments"],
        deny=["personal_data", "name", "date_of_birth"],
        require=["account_id", "risk_tier"],
        rules=[
            {
                "type": "field_value",
                "field": "risk_tier",
                "one_of": ["conservative", "moderate", "aggressive"],
            }
        ],
    )

    fs.contract(
        name="trading-to-compliance",
        source="trading_agent",
        target="compliance_agent",
        allow=["trade_id", "amount", "instrument", "timestamp", "account_id", "human_approved"],
        require=["trade_id", "amount"],
        rules=[
            {"type": "field_value", "field": "amount", "min": 0},
        ],
    )

    print("=" * 60)
    print("FailSafe Finance Pipeline Example")
    print("=" * 60)

    # --- Scenario 1: Clean pipeline ---
    print("\n[Scenario 1] Clean pipeline — all passes")
    print("-" * 40)

    r1 = await fs.handoff(
        source="kyc_agent",
        target="onboarding_agent",
        payload={
            "name": "Alice Johnson",
            "date_of_birth": "1990-05-15",
            "verification_status": "verified",
            "risk_tier": "moderate",
            "country": "US",
        },
    )
    print(f"  KYC → Onboarding: {'PASS' if r1.passed else 'FAIL'}")

    r2 = await fs.handoff(
        source="onboarding_agent",
        target="trading_agent",
        payload={
            "account_id": "ACC-001",
            "risk_tier": "moderate",
            "trading_limits": {"daily": 100000},
            "approved_instruments": ["stocks", "bonds"],
        },
    )
    print(f"  Onboarding → Trading: {'PASS' if r2.passed else 'FAIL'}")

    r3 = await fs.handoff(
        source="trading_agent",
        target="compliance_agent",
        payload={
            "trade_id": "TRD-001",
            "amount": 5000,
            "instrument": "AAPL",
            "timestamp": "2024-01-15T10:30:00Z",
            "account_id": "ACC-001",
            "human_approved": True,
        },
    )
    print(f"  Trading → Compliance: {'PASS' if r3.passed else 'FAIL'}")

    # --- Scenario 2: PII leakage ---
    print("\n[Scenario 2] PII leakage — SSN in onboarding data")
    print("-" * 40)

    r4 = await fs.handoff(
        source="kyc_agent",
        target="onboarding_agent",
        payload={
            "name": "Bob Smith",
            "verification_status": "verified",
            "ssn": "987-65-4321",  # VIOLATION: denied field
            "country": "US",
        },
    )
    print(f"  KYC → Onboarding: {'PASS' if r4.passed else 'FAIL'}")
    for v in r4.violations:
        print(f"    [{v.severity}] {v.rule}: {v.message}")

    # --- Scenario 3: EU data without GDPR tag ---
    print("\n[Scenario 3] EU client without GDPR tag")
    print("-" * 40)

    r5 = await fs.handoff(
        source="kyc_agent",
        target="onboarding_agent",
        payload={
            "name": "Hans Mueller",
            "verification_status": "verified",
            "country": "DE",
            # Missing gdpr_tag!
        },
    )
    print(f"  KYC → Onboarding: {'PASS' if r5.passed else 'FAIL'}")
    for v in r5.violations:
        print(f"    [{v.severity}] {v.rule}: {v.message}")

    # --- Scenario 4: Large transaction without approval ---
    print("\n[Scenario 4] Large transaction without human approval")
    print("-" * 40)

    r6 = await fs.handoff(
        source="trading_agent",
        target="compliance_agent",
        payload={
            "trade_id": "TRD-002",
            "amount": 500000,  # Over default 10k limit
            "instrument": "BTC",
            "account_id": "ACC-001",
            # No human_approved field
        },
    )
    print(f"  Trading → Compliance: {'PASS' if r6.passed else 'FAIL'}")
    for v in r6.violations:
        print(f"    [{v.severity}] {v.rule}: {v.message}")

    # --- Scenario 5: Personal data leaking to trading agent ---
    print("\n[Scenario 5] Personal data leaking to trading agent")
    print("-" * 40)

    r7 = await fs.handoff(
        source="onboarding_agent",
        target="trading_agent",
        payload={
            "account_id": "ACC-002",
            "risk_tier": "aggressive",
            "name": "Alice Johnson",  # VIOLATION: denied field
            "date_of_birth": "1990-05-15",  # VIOLATION: denied field
        },
    )
    print(f"  Onboarding → Trading: {'PASS' if r7.passed else 'FAIL'}")
    for v in r7.violations:
        print(f"    [{v.severity}] {v.rule}: {v.message}")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    all_results = [r1, r2, r3, r4, r5, r6, r7]
    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)
    total_violations = sum(len(r.violations) for r in all_results)
    print(f"  Total handoffs: {len(all_results)}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Total violations: {total_violations}")


if __name__ == "__main__":
    asyncio.run(main())
