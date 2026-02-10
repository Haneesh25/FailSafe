"""Tests for the high-level Failsafe SDK API."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentpact import Failsafe


def test_quickstart_5_lines():
    fs = Failsafe()
    fs.agent("customer_service", authority="read_only", compliance=["SOX"])
    fs.agent("research_agent", authority="read_write", compliance=["SOX", "SEC"])
    fs.contract("customer_service", "research_agent",
               fields={"customer_id": "string", "request_type": "string"})
    result = fs.validate("customer_service", "research_agent",
                        {"customer_id": "CUST-123", "request_type": "review"})
    assert result.overall_result.value == "pass"
    assert result.total_violations == 0


def test_method_chaining():
    fs = (Failsafe()
          .agent("a", authority="read_write")
          .agent("b", authority="execute")
          .contract("a", "b", fields={"amount": "number"}))
    result = fs.validate("a", "b", {"amount": 1000})
    assert result.overall_result.value == "pass"


def test_simple_field_syntax():
    fs = Failsafe()
    fs.agent("a").agent("b")
    fs.contract("a", "b", fields={"name": "string", "age": "number", "active": "boolean"})
    result = fs.validate("a", "b", {"name": "John", "age": 30, "active": True})
    assert result.overall_result.value == "pass"


def test_advanced_field_syntax():
    fs = Failsafe()
    fs.agent("a", authority="read_write")
    fs.agent("b", authority="execute")
    fs.contract("a", "b", fields={
        "customer_id": {"type": "string", "pattern": r"^CUST-\d{6}$", "pii": True},
        "amount": {"type": "number", "min_value": 0, "max_value": 10000, "financial_data": True},
    })

    r1 = fs.validate("a", "b", {"customer_id": "CUST-123456", "amount": 5000})
    assert r1.overall_result.value == "pass"

    r2 = fs.validate("a", "b", {"customer_id": "BAD", "amount": 5000})
    assert r2.total_violations > 0


def test_auto_finance_policy():
    fs = Failsafe()
    fs.agent("a", authority="read_write", compliance=["SOX", "SEC"])
    fs.agent("b", authority="execute", compliance=["SOX", "SEC", "FINRA"])
    fs.contract("a", "b", fields={"amount": "number"}, compliance=["SOX", "SEC"])

    result = fs.validate("a", "b", {"amount": 50000},
                        metadata={"action": "trade", "request_id": "R1",
                                  "timestamp": "2025-01-01T00:00:00Z", "initiator": "test"})
    assert any("FIN-" in v.rule_id for v in result.policy_violations)


def test_report_generation():
    fs = Failsafe()
    fs.agent("a").agent("b")
    fs.contract("a", "b", fields={"x": "string"})
    fs.validate("a", "b", {"x": "v1"})
    fs.validate("a", "b", {"x": "v2"})

    report = fs.report()
    assert "Failsafe Compliance Report" in report


def test_access_low_level_api():
    fs = Failsafe()
    assert fs.registry is not None
    assert fs.audit is not None
    assert fs.interceptor is not None

    from agentpact import AgentIdentity, AuthorityLevel
    fs.registry.register_agent(AgentIdentity(
        name="low_level", description="test", authority_level=AuthorityLevel.ADMIN,
    ))
    assert fs.registry.get_agent("low_level") is not None


def test_violation_callback():
    seen = []
    fs = Failsafe()
    fs.on_violation(lambda r: seen.append(r))
    fs.agent("a").agent("b")
    fs.contract("a", "b", fields={"required_field": "string"})

    result = fs.validate("a", "b", {})
    assert len(seen) == 1
    assert seen[0].handoff_id == result.handoff_id


def test_validation_callback():
    seen = []
    fs = Failsafe()
    fs.on_validation(lambda r: seen.append(r))
    fs.agent("a").agent("b")
    fs.contract("a", "b", fields={"x": "string"})

    fs.validate("a", "b", {"x": "ok"})
    fs.validate("a", "b", {})
    assert len(seen) == 2  # fires on pass AND fail


TESTS = [
    test_quickstart_5_lines,
    test_method_chaining,
    test_simple_field_syntax,
    test_advanced_field_syntax,
    test_auto_finance_policy,
    test_report_generation,
    test_access_low_level_api,
    test_violation_callback,
    test_validation_callback,
]

if __name__ == "__main__":
    passed = failed = 0
    print("=" * 50)
    print("  Failsafe SDK API Tests")
    print("=" * 50)
    print()
    for t in TESTS:
        try:
            t()
            print(f"\u2705 {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"\u274c {t.__name__}: {e}")
            failed += 1
    print()
    print("=" * 50)
    print(f"  Results: {passed} passed, {failed} failed, {len(TESTS)} total")
    print("=" * 50)
    sys.exit(1 if failed else 0)
