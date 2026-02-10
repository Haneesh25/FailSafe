"""LangGraph integration tests."""

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
    FAILSAFE_STATE_KEY,
    FAILSAFE_RESULTS_KEY,
    FAILSAFE_METADATA_KEY,
)

from langgraph.graph import START, END

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict



class HandoffState(TypedDict):
    symbol: str
    amount: float
    note: str
    action: str
    _failsafe_metadata: dict
    _failsafe_last_node: str
    _failsafe_results: Annotated[list, operator.add]



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
        FAILSAFE_METADATA_KEY: {},
        FAILSAFE_STATE_KEY: "",
        FAILSAFE_RESULTS_KEY: [],
    }
    state.update(overrides)
    return state


def build_two_node_graph(registry, audit, research_fn, trading_fn,
                         block=True, policy_pack=None):
    """Build a simple research → trading graph."""
    vg = ValidatedGraph(registry, audit, block_on_violation=block)
    if policy_pack:
        vg.register_policy_pack(policy_pack)

    graph = vg.build(HandoffState)
    graph.add_node("research", research_fn)
    graph.add_node("trading", trading_fn)
    graph.add_edge(START, "research")
    graph.add_edge("research", "trading")
    graph.add_edge("trading", END)

    return graph.compile()



def test_valid_handoff_passes_through_graph():
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {
            "symbol": "AAPL", "amount": 5000.0,
            FAILSAFE_METADATA_KEY: {
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

    validations = result[FAILSAFE_RESULTS_KEY]
    assert len(validations) == 1, f"Expected 1 validation, got {len(validations)}"
    assert validations[0]["result"] == "pass"
    assert validations[0]["consumer"] == "research"
    assert validations[0]["provider"] == "trading"
    assert validations[0]["total_violations"] == 0
    assert result["symbol"] == "AAPL"
    print("PASS test_valid_handoff_passes_through_graph")


def test_entry_node_skips_validation():
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "MSFT", "amount": 1000.0,
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading)
    result = app.invoke(make_initial_state())

    # Only research → trading; START → research skipped
    assert len(result[FAILSAFE_RESULTS_KEY]) == 1
    assert result[FAILSAFE_RESULTS_KEY][0]["consumer"] == "research"
    print("PASS test_entry_node_skips_validation")



def test_bad_pattern_blocks_in_graph():
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "bad_symbol", "amount": 5000.0,
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
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
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"amount": 5000.0,
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
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
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "TSLA", "amount": 999999.0,
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
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



def test_ssn_detected_and_blocked():
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "AAPL", "amount": 5000.0,
                "note": "Client SSN 123-45-6789",
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
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
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "GOOGL", "amount": 50000.0,
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
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
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "GOOGL", "amount": 50000.0,
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r", "human_approved": True}}

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading,
                               block=True, policy_pack=FinancePolicyPack())

    result = app.invoke(make_initial_state())
    validations = result[FAILSAFE_RESULTS_KEY]
    assert len(validations) == 1
    policy_violations = validations[0]["violations"]["policy"]
    assert not any(v["rule_id"] == "FIN-AUTH-003" for v in policy_violations)
    print("PASS test_large_transaction_with_approval_passes")


def test_mnpi_detection_in_graph():
    registry = make_registry()
    contract = registry.get_contract_for_handoff("research", "trading")
    contract.required_compliance_scopes = ["SOX", "SEC"]

    audit = AuditLogger()

    def research(state):
        return {"symbol": "NVDA", "amount": 5000.0,
                "note": "Pre-release earnings data suggests strong Q4",
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
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



def test_monitor_mode_logs_but_does_not_block():
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "bad", "amount": 5000.0,
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
                "timestamp": "t", "initiator": "r"}}

    def trading(state):
        return {"note": "still executed"}

    app = build_two_node_graph(registry, audit, research, trading, block=False)
    result = app.invoke(make_initial_state())

    assert result["note"] == "still executed"

    validations = result[FAILSAFE_RESULTS_KEY]
    assert len(validations) == 1
    assert validations[0]["result"] == "fail"
    assert validations[0]["total_violations"] > 0

    failures = audit.get_failures()
    assert len(failures) == 1
    print("PASS test_monitor_mode_logs_but_does_not_block")



def test_audit_logger_records_all_validations():
    registry = make_registry()
    audit = AuditLogger()

    def research(state):
        return {"symbol": "AAPL", "amount": 5000.0,
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
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
    registry = make_registry()
    audit = AuditLogger()

    callback_results = []

    vg = ValidatedGraph(registry, audit, block_on_violation=False)
    vg.on_violation(lambda r: callback_results.append(r))

    graph = vg.build(HandoffState)

    def research(state):
        return {"symbol": "bad", "amount": 5000.0,
                FAILSAFE_METADATA_KEY: {"action": "recommend", "request_id": "R1",
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



def test_no_contract_blocks_handoff():
    registry = make_registry()
    audit = AuditLogger()

    registry.register_agent(AgentIdentity(
        name="rogue",
        description="Rogue agent",
        authority_level=AuthorityLevel.READ_ONLY,
        compliance_scopes=["SOX"],
        max_data_classification="public",
    ))

    vg = ValidatedGraph(registry, audit, block_on_violation=True)
    graph = vg.build(HandoffState)

    def rogue(state):
        return {"symbol": "HACK", "amount": 1.0,
                FAILSAFE_METADATA_KEY: {"action": "query"}}

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



def test_metadata_separated_from_data():
    registry = make_registry()
    contract = registry.get_contract_for_handoff("research", "trading")
    contract.request_schema.append(
        FieldContract(name="action", field_type="string", required=False,
                      enum_values=["buy", "sell", "hold"])
    )

    audit = AuditLogger()

    def research(state):
        return {
            "symbol": "AAPL", "amount": 5000.0, "action": "buy",
            FAILSAFE_METADATA_KEY: {
                "action": "recommend",
                "request_id": "R1",
                "timestamp": "t",
                "initiator": "r",
            },
        }

    def trading(state):
        return {}

    app = build_two_node_graph(registry, audit, research, trading)
    result = app.invoke(make_initial_state())

    validations = result[FAILSAFE_RESULTS_KEY]
    assert validations[0]["result"] == "pass"
    assert result["action"] == "buy"
    print("PASS test_metadata_separated_from_data")



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
    print("  Failsafe LangGraph Integration Tests")
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
