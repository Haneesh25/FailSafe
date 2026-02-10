"""
Failsafe Test Suite

Tests for the core validation engine, policy packs, and interceptor.
Run with: python -m pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentpact.core.models import *
from agentpact.core.engine import ValidationEngine
from agentpact.policies.finance import FinancePolicyPack
from agentpact.interceptor.middleware import HandoffInterceptor, HandoffBlockedError
from agentpact.audit.logger import AuditLogger


def make_registry():
    """Create a test registry with basic agents and contracts."""
    registry = ContractRegistry()
    
    registry.register_agent(AgentIdentity(
        name="agent_a",
        description="Test agent A",
        authority_level=AuthorityLevel.READ_WRITE,
        allowed_data_domains=["financial_records"],
        compliance_scopes=["SOX", "SEC"],
        max_data_classification="confidential",
    ))
    
    registry.register_agent(AgentIdentity(
        name="agent_b",
        description="Test agent B",
        authority_level=AuthorityLevel.EXECUTE,
        allowed_data_domains=["financial_records", "pii"],
        compliance_scopes=["SOX", "SEC", "FINRA"],
        max_data_classification="restricted",
    ))
    
    registry.register_contract(HandoffContract(
        contract_id="TEST-001",
        name="A to B",
        consumer_agent="agent_a",
        provider_agent="agent_b",
        request_schema=[
            FieldContract(name="symbol", field_type="string", required=True, pattern=r"^[A-Z]{1,5}$"),
            FieldContract(name="amount", field_type="number", required=True, min_value=0, max_value=100000),
            FieldContract(name="note", field_type="string", required=False, max_length=500),
        ],
        required_authority=AuthorityLevel.READ_WRITE,
        allowed_actions=["recommend", "query"],
        prohibited_actions=["delete"],
        required_compliance_scopes=["SOX"],
        max_data_classification="confidential",
    ))
    
    return registry


def test_valid_handoff_passes():
    registry = make_registry()
    engine = ValidationEngine(registry)
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(data={"symbol": "AAPL", "amount": 5000}),
    )
    
    assert result.overall_result == ValidationResult.PASS
    assert result.total_violations == 0
    assert not result.is_blocked
    print("✅ test_valid_handoff_passes")

def test_missing_required_field_fails():
    registry = make_registry()
    engine = ValidationEngine(registry)
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(data={"symbol": "AAPL"}),  # Missing amount
    )
    
    assert result.overall_result == ValidationResult.FAIL
    assert any(v.rule_id == "SCHEMA_001" for v in result.schema_violations)
    print("✅ test_missing_required_field_fails")

def test_pattern_mismatch_fails():
    registry = make_registry()
    engine = ValidationEngine(registry)
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(data={"symbol": "invalid_symbol", "amount": 5000}),
    )
    
    assert any(v.rule_id == "SCHEMA_003" for v in result.schema_violations)
    print("✅ test_pattern_mismatch_fails")

def test_value_out_of_range_fails():
    registry = make_registry()
    engine = ValidationEngine(registry)
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(data={"symbol": "AAPL", "amount": 999999}),  # Over max
    )
    
    assert any(v.rule_id == "SCHEMA_006" for v in result.schema_violations)
    print("✅ test_value_out_of_range_fails")

def test_type_mismatch_fails():
    registry = make_registry()
    engine = ValidationEngine(registry)
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(data={"symbol": "AAPL", "amount": "not_a_number"}),
    )
    
    assert any(v.rule_id == "SCHEMA_002" for v in result.schema_violations)
    print("✅ test_type_mismatch_fails")

def test_unexpected_field_warns():
    registry = make_registry()
    engine = ValidationEngine(registry)
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(data={"symbol": "AAPL", "amount": 5000, "secret": "hidden_data"}),
    )
    
    assert any(v.rule_id == "SCHEMA_008" for v in result.schema_violations)
    print("✅ test_unexpected_field_warns")


def test_no_contract_blocks():
    registry = make_registry()
    engine = ValidationEngine(registry)
    
    result = engine.validate_handoff(
        "agent_a", "unknown_agent",  # No contract for this pair
        HandoffPayload(data={}),
    )
    
    assert result.is_blocked
    assert any(v.rule_id == "CONTRACT_001" for v in result.schema_violations)
    print("✅ test_no_contract_blocks")

def test_prohibited_action_blocks():
    registry = make_registry()
    engine = ValidationEngine(registry)
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(
            data={"symbol": "AAPL", "amount": 5000},
            metadata={"action": "delete"},
        ),
    )
    
    assert result.is_blocked
    assert any(v.rule_id == "AUTH_004" for v in result.authority_violations)
    print("✅ test_prohibited_action_blocks")

def test_unauthorized_action_blocks():
    registry = make_registry()
    engine = ValidationEngine(registry)
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(
            data={"symbol": "AAPL", "amount": 5000},
            metadata={"action": "execute_trade"},  # Not in allowed actions
        ),
    )
    
    assert any(v.rule_id == "AUTH_005" for v in result.authority_violations)
    print("✅ test_unauthorized_action_blocks")


def test_ssn_detection():
    registry = make_registry()
    engine = ValidationEngine(registry)
    engine.register_policy_pack(FinancePolicyPack())
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(data={
            "symbol": "AAPL",
            "amount": 5000,
            "note": "Client SSN 123-45-6789 for reference",
        }),
    )
    
    assert any(v.rule_id == "FIN-PII-002" for v in result.policy_violations)
    print("✅ test_ssn_detection")

def test_large_transaction_requires_approval():
    registry = make_registry()
    engine = ValidationEngine(registry)
    engine.register_policy_pack(FinancePolicyPack())
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(
            data={"symbol": "AAPL", "amount": 50000},
            metadata={"action": "recommend"},
        ),
    )
    
    assert any(v.rule_id == "FIN-AUTH-003" for v in result.policy_violations)
    print("✅ test_large_transaction_requires_approval")

def test_large_transaction_with_approval_passes():
    registry = make_registry()
    engine = ValidationEngine(registry)
    engine.register_policy_pack(FinancePolicyPack())
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(
            data={"symbol": "AAPL", "amount": 50000},
            metadata={"action": "recommend", "human_approved": True},
        ),
    )
    
    # Should not have the approval violation
    assert not any(v.rule_id == "FIN-AUTH-003" for v in result.policy_violations)
    print("✅ test_large_transaction_with_approval_passes")

def test_mnpi_detection():
    registry = make_registry()
    engine = ValidationEngine(registry)
    engine.register_policy_pack(FinancePolicyPack())
    
    # MNPI check requires SEC scope
    contract = registry.get_contract_for_handoff("agent_a", "agent_b")
    contract.required_compliance_scopes = ["SOX", "SEC"]
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(
            data={"symbol": "NVDA", "amount": 5000, "note": "Pre-release earnings look strong"},
            metadata={"action": "recommend"},
        ),
    )
    
    assert any(v.rule_id == "FIN-SEC-001" for v in result.policy_violations)
    print("✅ test_mnpi_detection")

def test_sox_audit_metadata_required():
    registry = make_registry()
    engine = ValidationEngine(registry)
    engine.register_policy_pack(FinancePolicyPack())
    
    result = engine.validate_handoff(
        "agent_a", "agent_b",
        HandoffPayload(
            data={"symbol": "AAPL", "amount": 5000},
            metadata={"action": "recommend"},  # Missing request_id, timestamp, initiator
        ),
    )
    
    assert any(v.rule_id == "FIN-AUDIT-001" for v in result.policy_violations)
    print("✅ test_sox_audit_metadata_required")


def test_interceptor_logs_to_audit():
    registry = make_registry()
    audit = AuditLogger()
    interceptor = HandoffInterceptor(registry, audit)
    
    interceptor.validate_outgoing("agent_a", "agent_b", {"symbol": "AAPL", "amount": 5000})
    
    assert len(audit.get_all()) == 1
    print("✅ test_interceptor_logs_to_audit")

def test_guard_raises_on_block():
    from agentpact.interceptor.middleware import FailsafeGuard
    
    registry = make_registry()
    interceptor = HandoffInterceptor(registry)
    
    guard = FailsafeGuard(interceptor, "agent_a", "unknown_agent")
    
    try:
        guard.send({"data": "value"})
        assert False, "Should have raised HandoffBlockedError"
    except HandoffBlockedError as e:
        assert e.result.is_blocked
    print("✅ test_guard_raises_on_block")

def test_violation_callback_fires():
    registry = make_registry()
    interceptor = HandoffInterceptor(registry)
    
    callback_fired = [False]
    def on_violation(result):
        callback_fired[0] = True
    
    interceptor.on_violation(on_violation)
    interceptor.validate_outgoing("agent_a", "unknown_agent", {})
    
    assert callback_fired[0]
    print("✅ test_violation_callback_fires")


def test_audit_report_generation():
    registry = make_registry()
    audit = AuditLogger()
    interceptor = HandoffInterceptor(registry, audit)
    
    # Generate some test data
    interceptor.validate_outgoing("agent_a", "agent_b", {"symbol": "AAPL", "amount": 5000})
    interceptor.validate_outgoing("agent_a", "agent_b", {"symbol": "invalid", "amount": 5000})
    interceptor.validate_outgoing("agent_a", "unknown", {})
    
    report = audit.generate_summary_report()
    
    assert report["summary"]["total_handoffs"] == 3
    assert report["summary"]["passed"] >= 1
    assert report["summary"]["failed"] >= 1
    print("✅ test_audit_report_generation")


if __name__ == "__main__":
    tests = [
        # Schema
        test_valid_handoff_passes,
        test_missing_required_field_fails,
        test_pattern_mismatch_fails,
        test_value_out_of_range_fails,
        test_type_mismatch_fails,
        test_unexpected_field_warns,
        # Authority
        test_no_contract_blocks,
        test_prohibited_action_blocks,
        test_unauthorized_action_blocks,
        # Finance Policy
        test_ssn_detection,
        test_large_transaction_requires_approval,
        test_large_transaction_with_approval_passes,
        test_mnpi_detection,
        test_sox_audit_metadata_required,
        # Interceptor
        test_interceptor_logs_to_audit,
        test_guard_raises_on_block,
        test_violation_callback_fires,
        # Audit
        test_audit_report_generation,
    ]
    
    passed = 0
    failed = 0
    
    print("\n" + "=" * 50)
    print("  Failsafe Test Suite")
    print("=" * 50 + "\n")
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"❌ {test.__name__}: {e}")
    
    print(f"\n{'=' * 50}")
    print(f"  Results: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'=' * 50}\n")
    
    sys.exit(0 if failed == 0 else 1)
