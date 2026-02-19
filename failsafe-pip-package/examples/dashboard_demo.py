"""Run the dashboard with live validation events.

Usage:
    python examples/dashboard_demo.py

Then open http://localhost:8765 in your browser.
"""

import asyncio
import random
import time

from failsafe import FailSafe


async def main():
    # Start FailSafe with dashboard enabled
    fs = FailSafe(mode="warn", policy_pack="finance", dashboard=True, dashboard_port=8765)

    # Register agents
    fs.register_agent("kyc_agent", description="KYC verification")
    fs.register_agent("onboarding_agent", description="Client onboarding")
    fs.register_agent("trading_agent", description="Trade execution")
    fs.register_agent("compliance_agent", description="Compliance review")

    # Define contracts
    fs.contract(
        name="kyc-to-onboarding",
        source="kyc_agent",
        target="onboarding_agent",
        allow=["name", "date_of_birth", "verification_status", "country", "gdpr_tag"],
        deny=["ssn", "raw_documents"],
        require=["verification_status"],
    )
    fs.contract(
        name="onboarding-to-trading",
        source="onboarding_agent",
        target="trading_agent",
        allow=["account_id", "risk_tier", "trading_limits"],
        deny=["name", "date_of_birth"],
        require=["account_id", "risk_tier"],
    )
    fs.contract(
        name="trading-to-compliance",
        source="trading_agent",
        target="compliance_agent",
        allow=["trade_id", "amount", "instrument", "account_id", "human_approved"],
        require=["trade_id", "amount"],
    )

    fs.contract(
        name="trading-to-compliance",
        source="onboarding_agent",
        target="compliance_agent",
        allow=["trade_id", "amount", "instrument", "account_id", "human_approved"],
        require=["trade_id", "amount"],
    )
    print("Dashboard running at http://localhost:8765")
    print("Sending validation events every 2 seconds... (Ctrl+C to stop)\n")

    # Simulate handoffs in a loop
    scenarios = [
        # Clean handoffs
        ("kyc_agent", "onboarding_agent", {"name": "Alice", "verification_status": "verified", "country": "US"}),
        ("onboarding_agent", "trading_agent", {"account_id": "ACC-001", "risk_tier": "moderate", "trading_limits": {"daily": 100000}}),
        ("trading_agent", "compliance_agent", {"trade_id": "TRD-001", "amount": 5000, "instrument": "AAPL", "human_approved": True}),
        # Violations
        ("kyc_agent", "onboarding_agent", {"name": "Bob", "verification_status": "verified", "ssn": "123-45-6789"}),
        ("kyc_agent", "onboarding_agent", {"name": "Hans", "verification_status": "verified", "country": "DE"}),
        ("onboarding_agent", "trading_agent", {"account_id": "ACC-002", "risk_tier": "aggressive", "name": "Alice"}),
        ("trading_agent", "compliance_agent", {"trade_id": "TRD-002", "amount": 500000, "instrument": "BTC"}),
        ("kyc_agent", "onboarding_agent", {"name": "Marie", "verification_status": "verified", "country": "FR", "gdpr_tag": "consent"}),
        ("trading_agent", "compliance_agent", {"trade_id": "TRD-003", "amount": 200, "instrument": "MSFT", "human_approved": True}),
    ]

    i = 0
    while True:
        source, target, payload = scenarios[i % len(scenarios)]
        result = await fs.handoff(source=source, target=target, payload=payload)
        status = "PASS" if result.passed else f"FAIL ({len(result.violations)} violations)"
        print(f"  {source} -> {target}: {status}")
        i += 1
        await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
