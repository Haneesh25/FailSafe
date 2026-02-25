"""FailSafe Quickstart — get visibility into your agent pipeline in 2 lines.

This example simulates a multi-agent pipeline (no LangChain required)
and shows how observe() gives you immediate visibility into what data
flows between agents.

Run:
    python examples/quickstart_observe.py
"""

from failsafe import observe

# === THE ONLY FAILSAFE CODE YOU NEED ===
obs = observe(dashboard=False)  # Set dashboard=True to see live UI at localhost:8765


# === Simulate your existing agents (these would be your real agent functions) ===


@obs.watch("research_agent")
def research(query: str) -> dict:
    """Simulates a research agent that fetches customer data."""
    return {
        "customer_name": "Alice Johnson",
        "account_id": "ACC-12345",
        "ssn": "123-45-6789",  # Oops — sensitive data!
        "credit_score": 750,
        "query": query,
    }


@obs.watch("underwriting_agent")
def underwrite(data: dict) -> dict:
    """Simulates an underwriting agent that evaluates risk."""
    return {
        "risk_level": "low",
        "approved": True,
        "customer_name": data.get("customer_name"),
        "credit_score": data.get("credit_score"),
        "internal_model_weights": [0.3, 0.7, 0.1],  # Internal data leaking
    }


@obs.watch("notification_agent")
def notify(data: dict) -> dict:
    """Simulates a notification agent that sends results to the customer."""
    return {
        "email_sent": True,
        "recipient": data.get("customer_name"),
        "message": f"Your application has been {'approved' if data.get('approved') else 'denied'}.",
    }


def main():
    print("=" * 60)
    print("FailSafe Quickstart — Zero-Config Observability")
    print("=" * 60)

    # Run the pipeline (these are just normal function calls!)
    result1 = research("loan application for Alice Johnson")
    result2 = underwrite(result1)
    result3 = notify(result2)

    # Now let's see what FailSafe observed
    print("\nWhat FailSafe saw:")
    print(f"   Events tracked: {len(obs.audit_log)}")
    print(f"   Violations: {len(obs.violations)}")

    # === NOW ADD CONTRACTS (still just a few lines) ===
    print("\n" + "=" * 60)
    print("Adding contracts to catch issues...")
    print("=" * 60)

    obs.fs.register_agent("research_agent")
    obs.fs.register_agent("underwriting_agent")
    obs.fs.register_agent("notification_agent")

    obs.fs.contract(
        name="research-to-underwriting",
        source="research_agent",
        target="underwriting_agent",
        deny=["ssn", "social_security", "tax_id"],
        require=["customer_name", "credit_score"],
    )

    obs.fs.contract(
        name="underwriting-to-notification",
        source="underwriting_agent",
        target="notification_agent",
        deny=["internal_model_weights", "raw_scores"],
        allow=["risk_level", "approved", "customer_name"],
    )

    # Run the pipeline again — now with contracts enforced
    print("\nRunning pipeline again with contracts...")
    result1 = research("loan application for Bob Smith")
    result2 = underwrite(result1)
    result3 = notify(result2)

    print(f"\nViolations caught: {len(obs.violations)}")
    for v in obs.violations:
        print(f"   [{v['severity'].upper()}] {v['rule']}: {v['message']}")

    print("\nDone! In production, set dashboard=True to see all this in a live UI.")


if __name__ == "__main__":
    main()
