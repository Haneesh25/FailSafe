"""Basic LangGraph example with FailSafe validation.

Demonstrates a minimal 3-agent pipeline with 2 contracts.
Shows both a passing handoff and a violation.

Usage:
    python examples/basic_langgraph.py
"""

import asyncio

from failsafe import FailSafe


async def main():
    # 1. Initialize FailSafe
    fs = FailSafe(mode="warn", audit_db=":memory:")

    # 2. Register agents
    fs.register_agent("intake_agent", description="Collects initial client info")
    fs.register_agent("kyc_agent", description="Runs KYC verification")
    fs.register_agent("onboarding_agent", description="Handles client onboarding")

    # 3. Define contracts
    fs.contract(
        name="intake-to-kyc",
        source="intake_agent",
        target="kyc_agent",
        allow=["name", "date_of_birth", "document_type", "document_id"],
        deny=["internal_notes"],
        require=["name", "document_type"],
    )

    fs.contract(
        name="kyc-to-onboarding",
        source="kyc_agent",
        target="onboarding_agent",
        allow=["name", "date_of_birth", "verification_status"],
        deny=["ssn", "raw_documents", "bank_account"],
        require=["verification_status"],
        rules=[
            {
                "type": "field_value",
                "field": "verification_status",
                "one_of": ["verified", "pending", "rejected"],
            }
        ],
    )

    # 4. Simulate handoffs
    print("=" * 60)
    print("FailSafe Basic LangGraph Example")
    print("=" * 60)

    # --- Passing handoff ---
    print("\n--- Handoff 1: intake -> kyc (should PASS) ---")
    result1 = await fs.handoff(
        source="intake_agent",
        target="kyc_agent",
        payload={
            "name": "Alice Johnson",
            "date_of_birth": "1990-05-15",
            "document_type": "passport",
            "document_id": "AB123456",
        },
    )
    print(f"  Passed: {result1.passed}")
    print(f"  Violations: {len(result1.violations)}")

    # --- Passing handoff ---
    print("\n--- Handoff 2: kyc -> onboarding (should PASS) ---")
    result2 = await fs.handoff(
        source="kyc_agent",
        target="onboarding_agent",
        payload={
            "name": "Alice Johnson",
            "date_of_birth": "1990-05-15",
            "verification_status": "verified",
        },
    )
    print(f"  Passed: {result2.passed}")
    print(f"  Violations: {len(result2.violations)}")

    # --- Violation: leaking denied data ---
    print("\n--- Handoff 3: kyc -> onboarding (should FAIL — SSN leak) ---")
    result3 = await fs.handoff(
        source="kyc_agent",
        target="onboarding_agent",
        payload={
            "name": "Alice Johnson",
            "verification_status": "verified",
            "ssn": "123-45-6789",  # DENIED field!
        },
    )
    print(f"  Passed: {result3.passed}")
    print(f"  Violations: {len(result3.violations)}")
    for v in result3.violations:
        print(f"    [{v.severity}] {v.rule}: {v.message}")

    # --- Violation: missing required field ---
    print("\n--- Handoff 4: kyc -> onboarding (should FAIL — missing field) ---")
    result4 = await fs.handoff(
        source="kyc_agent",
        target="onboarding_agent",
        payload={
            "name": "Bob Smith",
            # Missing verification_status!
        },
    )
    print(f"  Passed: {result4.passed}")
    print(f"  Violations: {len(result4.violations)}")
    for v in result4.violations:
        print(f"    [{v.severity}] {v.rule}: {v.message}")

    # --- Coverage matrix ---
    print("\n--- Contract Coverage Matrix ---")
    matrix = fs.contracts.coverage_matrix()
    agents = sorted(matrix.keys())
    header = "".ljust(20) + "".join(a.ljust(20) for a in agents)
    print(header)
    for source in agents:
        row = source.ljust(20)
        for target in agents:
            row += matrix[source][target].ljust(20)
        print(row)

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
