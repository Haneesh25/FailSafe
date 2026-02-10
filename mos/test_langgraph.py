"""
AgentPact LangGraph Integration Tests

Tests for ValidatedGraph — the LangGraph integration that validates
handoffs at graph edges. Covers happy path, violation detection,
blocking behavior, monitor mode, and audit logging.

Run with:
    python test_langgraph.py
    python -m pytest test_langgraph.py -v
"""

import sys
import os
import operator
from datetime import datetime, timezone
from typing import Annotated

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentpact.core.models import (
    AgentIdentity,
    AuthorityLevel,
    ContractRegistry,
    FieldContract,
    HandoffContract,
    HandoffPayload,
    ValidationResult,
)
from agentpact.core.engine import ValidationEngine
from agentpact.policies.finance import FinancePolicyPack
from agentpact.interceptor.middleware import HandoffBlockedError
from agentpact.audit.logger import AuditLogger
from agentpact.integrations.langgraph import (
    ValidatedGraph,
    AGENTPACT_STATE_KEY,
    AGENTPACT_RESULTS_KEY,
    AGENTPACT_METADATA_KEY,
)

from langgraph.graph import START, END

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


# ──────────────────────────────────────────────────────────
# Shared State Schema
# ──────────────────────────────────────────────────────────

class TestState(TypedDict):
    symbol: str
    amount: float
    note: str
    action: str
    _agentpact_metadata: dict
    _agentpact_last_node: str
    _agentpact_results: Annotated[list, operator.add]


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

def make_registry():
    """Two-agent registry with one contract for research → trading."""
    registry = ContractRegistry()

    registry.register_agent(AgentIdentity(
        name="research",
        description="Research agent",
        authority_level=AuthorityLevel.READ_WRITE,
        allowed_data_domains=["financial_records"],
        compliance_scopes=["SOX", "SEC"],
        max_data_classification="confidential",
    ))

    registry.register_agent(AgentIdentity(
        name="trading",
        description="Trading agent",
        authority_level=AuthorityLevel.EXECUTE,
        allowed_data_domains=["financial_records"],
        compliance_scopes=["SOX", "SEC", "FINRA"],
        max_data_classification="restricted",
    ))

    registry.register_contract(HandoffContract(
        contract_id="TEST-LG-001",
        name="Research to Trading",
        consumer_agent="research",
        provider_agent="trading",
        request_schema=[
            FieldContract(name="symbol", field_type="string", required=True,
                          pattern=r"^[A-Z]{1,5}$"),
            FieldContract(name="amount", field_type="number", required=True,
                          min_value=0, max_value=100000, financial_data=True),
            FieldContract(name="note", field_type="string", required=False,
                          max_length=500),
        ],
        required_authority=AuthorityLevel.READ_WRITE,
        allowed_actions=["recommend", "query"],
        prohibited_actions=["delete"],
        required_compliance_scopes=["SOX"],
        max_data_classification="confidential",
    ))

    return registry


def make_initial_state(**overrides):
    state = {
        "symbol": "",
        "amount": 0.0,
        "note": "",
        "action": "",
        AGENTPACT_METADATA_KEY: {},
        AGENTPACT_STATE_KEY: "",
        AGENTPACT_RESULTS_KEY: [],
    }
    state.update(overrides)
    return state


def build_two_node_graph(registry, audit, research_fn, trading_fn,
                         block=True, policy_pack=None):
    """Build a simple research → trading graph."""
    vg = ValidatedGraph(registry, audit, block_on_violation=block)
    if policy_pack:
        vg.register_policy_pack(policy_pack)

    graph = vg.build(TestState)
    graph.add_node("research", research_fn)
    graph.add_node("trading", trading_fn)
    graph.add_edge(START, "research")
    graph.add_edge("research", "trading")
    graph.add_edge("trading", END)

    return graph.compile()


# ──────────────────────────────────────────────────────────
# Tests: Happy Path
# ──────────────────────────────────────────────────────────

def test_valid_handoff_passes_through_graph():
    """A clean handoff should pass validation and complete the pipeline."""
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {
            "symbol": "AAPL", "amount": 5000.0,
            AGENTPACT_METADATA_KEY: {
                "action": "recommend",
                "request_id": "R1",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "initiator": "research",
            },
        }

    def trading(state):
        return {"note": "executed"}

    app = build_two_node_graph(registry, audit, research, trading)
    result = app.invoke(make_initial_state())

    validations = result[AGENTPACT_RESULTS_KEY]
    assert len(validations) == 1, f"Expected 1 validation, got {len(validations)}"
    assert validations[0]["result"] == "pass"
    assert validations[0]["consumer"] == "research"
    assert validations[0]["provider"] == "trading"
    assert validations[0]["total_violations"] == 0
    assert result["symbol"] == "AAPL"
    print("PASS test_valid_handoff_passes_through_graph")


def test_entry_node_skips_validation():
    """The first node (from START) should not be validated — there's no source agent."""
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "MSFT", "amount": 1000.0,
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading)
    result = app.invoke(make_initial_state())

    # Only 1 validation: research → trading. No validation for START → research.
    assert len(result[AGENTPACT_RESULTS_KEY]) == 1
    assert result[AGENTPACT_RESULTS_KEY][0]["consumer"] == "research"
    print("PASS test_entry_node_skips_validation")


# ──────────────────────────────────────────────────────────
# Tests: Schema Violations
# ──────────────────────────────────────────────────────────

def test_bad_pattern_blocks_in_graph():
    """Invalid symbol pattern should block the handoff."""
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "bad_symbol", "amount": 5000.0,
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading, block=True)

    try:
        app.invoke(make_initial_state())
        assert False, "Should have raised HandoffBlockedError"
    except HandoffBlockedError as e:
        assert "research" in str(e) and "trading" in str(e)
    print("PASS test_bad_pattern_blocks_in_graph")


def test_missing_required_field_blocks():
    """Missing required 'symbol' field should block."""
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"amount": 5000.0,  # Missing symbol
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading, block=True)

    try:
        app.invoke(make_initial_state())
        assert False, "Should have raised HandoffBlockedError"
    except HandoffBlockedError:
        pass
    print("PASS test_missing_required_field_blocks")


def test_amount_over_max_blocks():
    """Amount exceeding max_value should block."""
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "TSLA", "amount": 999999.0,
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading, block=True)

    try:
        app.invoke(make_initial_state())
        assert False, "Should have raised HandoffBlockedError"
    except HandoffBlockedError:
        pass
    print("PASS test_amount_over_max_blocks")


# ──────────────────────────────────────────────────────────
# Tests: Policy Violations (Finance Pack)
# ──────────────────────────────────────────────────────────

def test_ssn_detected_and_blocked():
    """SSN pattern in note field should trigger FIN-PII-002."""
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "AAPL", "amount": 5000.0,
                "note": "Client SSN 123-45-6789",
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading,
                               block=True, policy_pack=FinancePolicyPack())

    try:
        app.invoke(make_initial_state())
        assert False, "Should have blocked on SSN"
    except HandoffBlockedError as e:
        blocked = audit.get_blocked()
        assert len(blocked) == 1
        violations = blocked[0].policy_violations
        assert any(v.rule_id == "FIN-PII-002" for v in violations)
    print("PASS test_ssn_detected_and_blocked")


def test_large_transaction_without_approval_blocks():
    """Amount >$10K without human_approved should trigger FIN-AUTH-003."""
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "GOOGL", "amount": 50000.0,
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading,
                               block=True, policy_pack=FinancePolicyPack())

    try:
        app.invoke(make_initial_state())
        assert False, "Should have blocked on large transaction"
    except HandoffBlockedError:
        blocked = audit.get_blocked()
        assert len(blocked) == 1
        violations = blocked[0].policy_violations
        assert any(v.rule_id == "FIN-AUTH-003" for v in violations)
    print("PASS test_large_transaction_without_approval_blocks")


def test_large_transaction_with_approval_passes():
    """Amount >$10K with human_approved=True should pass."""
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "GOOGL", "amount": 50000.0,
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r", "human_approved": True}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading,
                               block=True, policy_pack=FinancePolicyPack())

    result = app.invoke(make_initial_state())
    validations = result[AGENTPACT_RESULTS_KEY]
    assert len(validations) == 1
    # Should not have FIN-AUTH-003
    policy_violations = validations[0]["violations"]["policy"]
    assert not any(v["rule_id"] == "FIN-AUTH-003" for v in policy_violations)
    print("PASS test_large_transaction_with_approval_passes")


def test_mnpi_detection_in_graph():
    """MNPI keywords in note should trigger FIN-SEC-001."""
    registry = make_registry()
    # Add SEC scope to the contract
    contract = registry.get_contract_for_handoff("research", "trading")
    contract.required_compliance_scopes = ["SOX", "SEC"]

    audit = AuditLogger()

    def research(state):
        return {"symbol": "NVDA", "amount": 5000.0,
                "note": "Pre-release earnings data suggests strong Q4",
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading,
                               block=True, policy_pack=FinancePolicyPack())

    try:
        app.invoke(make_initial_state())
        assert False, "Should have blocked on MNPI"
    except HandoffBlockedError:
        blocked = audit.get_blocked()
        assert len(blocked) == 1
        violations = blocked[0].policy_violations
        assert any(v.rule_id == "FIN-SEC-001" for v in violations)
    print("PASS test_mnpi_detection_in_graph")


# ──────────────────────────────────────────────────────────
# Tests: Monitor Mode (non-blocking)
# ──────────────────────────────────────────────────────────

def test_monitor_mode_logs_but_does_not_block():
    """With block_on_violation=False, violations are logged but the pipeline completes."""
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "bad", "amount": 5000.0,  # bad pattern
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {"note": "still executed"}

    app = build_two_node_graph(registry, audit, research, trading, block=False)
    result = app.invoke(make_initial_state())

    # Pipeline completed despite violation
    assert result["note"] == "still executed"

    validations = result[AGENTPACT_RESULTS_KEY]
    assert len(validations) == 1
    assert validations[0]["result"] == "fail"
    assert validations[0]["total_violations"] > 0

    # Audit should have the failure logged
    failures = audit.get_failures()
    assert len(failures) == 1
    print("PASS test_monitor_mode_logs_but_does_not_block")


# ──────────────────────────────────────────────────────────
# Tests: Audit Trail
# ──────────────────────────────────────────────────────────

def test_audit_logger_records_all_validations():
    """Every edge validation should be recorded in the audit log."""
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "AAPL", "amount": 5000.0,
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading)
    app.invoke(make_initial_state())

    all_records = audit.get_all()
    assert len(all_records) == 1
    assert all_records[0].consumer_agent == "research"
    assert all_records[0].provider_agent == "trading"
    print("PASS test_audit_logger_records_all_validations")


def test_violation_callback_fires_in_graph():
    """on_violation callbacks should fire when violations are detected."""
    registry = make_registry()
    audit = AuditLogger()

    callback_results = []

    vg = ValidatedGraph(registry, audit, block_on_violation=False)
    vg.on_violation(lambda r: callback_results.append(r))

    graph = vg.build(TestState)

    def research(state):
        return {"symbol": "bad", "amount": 5000.0,
                AGENTPACT_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {}

    graph.add_node("research", research)
    graph.add_node("trading", trading)
    graph.add_edge(START, "research")
    graph.add_edge("research", "trading")
    graph.add_edge("trading", END)
    app = graph.compile()

    app.invoke(make_initial_state())

    assert len(callback_results) == 1
    assert callback_results[0].total_violations > 0
    print("PASS test_violation_callback_fires_in_graph")


# ──────────────────────────────────────────────────────────
# Tests: No Contract
# ──────────────────────────────────────────────────────────

def test_no_contract_blocks_handoff():
    """A handoff between agents with no contract should be blocked."""
    registry = make_registry()
    audit = AuditLogger()

    # Register a third agent with no contract to "trading"
    registry.register_agent(AgentIdentity(
        name="rogue",
        description="Rogue agent",
        authority_level=AuthorityLevel.READ_ONLY,
        compliance_scopes=["SOX"],
        max_data_classification="public",
    ))

    vg = ValidatedGraph(registry, audit, block_on_violation=True)
    graph = vg.build(TestState)

    def rogue(state):
        return {"symbol": "HACK", "amount": 1.0,
                AGENTPACT_METADATA_KEY: {"action": "query"}}

    def trading(state):
        return {}

    graph.add_node("rogue", rogue)
    graph.add_node("trading", trading)
    graph.add_edge(START, "rogue")
    graph.add_edge("rogue", "trading")
    graph.add_edge("trading", END)
    app = graph.compile()

    try:
        app.invoke(make_initial_state())
        assert False, "Should have blocked — no contract"
    except HandoffBlockedError:
        pass
    print("PASS test_no_contract_blocks_handoff")


# ──────────────────────────────────────────────────────────
# Tests: Metadata Separation
# ──────────────────────────────────────────────────────────

def test_metadata_separated_from_data():
    """
    Domain 'action' field (buy/sell) should not collide with
    handoff metadata 'action' (recommend/query).
    """
    registry = make_registry()
    # Add 'action' to contract schema as a data field
    contract = registry.get_contract_for_handoff("research", "trading")
    contract.request_schema.append(
        FieldContract(name="action", field_type="string", required=False,
                      enum_values=["buy", "sell", "hold"])
    )

    audit = AuditLogger()

    def research(state):
        return {
            "symbol": "AAPL", "amount": 5000.0, "action": "buy",
            AGENTPACT_METADATA_KEY: {
                "action": "recommend",  # handoff action, not trade action
                "request_id": "R1",
                "timestamp": "t",
                "initiator": "r",
            },
        }

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading)
    result = app.invoke(make_initial_state())

    validations = result[AGENTPACT_RESULTS_KEY]
    assert validations[0]["result"] == "pass"
    # Verify the data action is "buy" but the handoff wasn't flagged
    assert result["action"] == "buy"
    print("PASS test_metadata_separated_from_data")


# ──────────────────────────────────────────────────────────
# Run All Tests
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        # Happy path
        test_valid_handoff_passes_through_graph,
        test_entry_node_skips_validation,
        # Schema violations
        test_bad_pattern_blocks_in_graph,
        test_missing_required_field_blocks,
        test_amount_over_max_blocks,
        # Finance policy
        test_ssn_detected_and_blocked,
        test_large_transaction_without_approval_blocks,
        test_large_transaction_with_approval_passes,
        test_mnpi_detection_in_graph,
        # Monitor mode
        test_monitor_mode_logs_but_does_not_block,
        # Audit
        test_audit_logger_records_all_validations,
        test_violation_callback_fires_in_graph,
        # No contract
        test_no_contract_blocks_handoff,
        # Metadata separation
        test_metadata_separated_from_data,
    ]

    passed = 0
    failed = 0

    print("\n" + "=" * 50)
    print("  AgentPact LangGraph Integration Tests")
    print("=" * 50 + "\n")

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL {test.__name__}: {e}")

    print(f"\n{'=' * 50}")
    print(f"  Results: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'=' * 50}\n")

    sys.exit(0 if failed == 0 else 1)
