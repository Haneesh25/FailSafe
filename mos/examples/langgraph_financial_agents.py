#!/usr/bin/env python3
"""
AgentPact + LangGraph: Financial Multi-Agent System

A complete working example of 4 AI agents collaborating on portfolio
rebalancing, with AgentPact validating every handoff at the LangGraph
graph edges.

Agents:
  1. Customer Service — handles inquiries, routes requests (READ_ONLY)
  2. Research — analyzes markets, makes recommendations (READ_WRITE)
  3. Trading — executes trades (EXECUTE)
  4. Compliance — reviews transactions (ADMIN)

Key concept:
  Each agent sets `_agentpact_metadata` in its output to declare the
  handoff action and audit fields. This keeps handoff metadata separate
  from domain data (e.g. trade action "buy" vs handoff action "recommend").

Run:
  python examples/langgraph_financial_agents.py
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from typing import Annotated, Any
import operator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import START, END

from agentpact.core.models import (
    AgentIdentity,
    AuthorityLevel,
    ContractRegistry,
    FieldContract,
    HandoffContract,
)
from agentpact.policies.finance import FinancePolicyPack
from agentpact.interceptor.middleware import HandoffBlockedError
from agentpact.audit.logger import AuditLogger
from agentpact.integrations.langgraph import (
    ValidatedGraph,
    AGENTPACT_STATE_KEY,
    AGENTPACT_RESULTS_KEY,
    AGENTPACT_METADATA_KEY,
)

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class FinancialState(TypedDict):
    # Customer request fields
    customer_id: str
    request_type: str
    account_id: str
    risk_tolerance: str

    # Research output fields
    symbol: str
    action: str          # Trade action: buy/sell/hold (domain data)
    amount: float
    rationale: str

    # Trading output fields
    trade_id: str
    execution_price: float
    timestamp: str

    # Compliance output
    compliance_status: str
    review_notes: str

    # AgentPact handoff metadata (action here = handoff action: query/recommend/etc)
    _agentpact_metadata: dict
    _agentpact_last_node: str
    _agentpact_results: Annotated[list, operator.add]


def customer_service(state: FinancialState) -> dict:
    """
    Customer service processes the incoming request and routes it.
    Sets handoff action to "query" — it's only reading/routing, not trading.
    """
    return {
        "customer_id": state.get("customer_id", "CUST-123456"),
        "request_type": state.get("request_type", "rebalance_request"),
        "account_id": state.get("account_id", "ACCT-00112233"),
        "risk_tolerance": state.get("risk_tolerance", "moderate"),
        AGENTPACT_METADATA_KEY: {
            "action": "query",
            "request_id": "REQ-2025-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "initiator": "customer_portal",
        },
    }


def research_agent(state: FinancialState) -> dict:
    """
    Research analyzes the request and produces a trade recommendation.
    Sets handoff action to "recommend" — it advises, trading executes.
    """
    risk = state.get("risk_tolerance", "moderate")
    amount_map = {"conservative": 3000.0, "moderate": 5000.0, "aggressive": 15000.0}
    return {
        "symbol": "AAPL",
        "action": "buy",
        "amount": amount_map.get(risk, 5000.0),
        "rationale": "Portfolio underweight in tech. AAPL fundamentals strong.",
        AGENTPACT_METADATA_KEY: {
            "action": "recommend",
            "request_id": "REQ-2025-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "initiator": "research_agent",
        },
    }


def trading_agent(state: FinancialState) -> dict:
    """
    Trading executes the recommended trade.
    Sets handoff action to "compliance_review" for the next hop.
    """
    return {
        "trade_id": "TRD-2025-00001",
        "execution_price": 182.50,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        AGENTPACT_METADATA_KEY: {
            "action": "compliance_review",
            "request_id": "REQ-2025-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "initiator": "trading_agent",
        },
    }


def compliance_agent(state: FinancialState) -> dict:
    """Compliance reviews the completed trade."""
    return {
        "compliance_status": "approved",
        "review_notes": f"Trade {state.get('trade_id', 'N/A')} reviewed. No issues found.",
        AGENTPACT_METADATA_KEY: {
            "action": "audit",
            "request_id": "REQ-2025-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "initiator": "compliance_agent",
        },
    }


def build_registry() -> ContractRegistry:
    """
    Register all agents and the contracts governing their handoffs.

    Agent hierarchy:
      customer_service (READ_ONLY) → research_agent (READ_WRITE)
      research_agent (READ_WRITE)  → trading_agent (EXECUTE)
      trading_agent (EXECUTE)      → compliance_agent (ADMIN)
    """
    registry = ContractRegistry()

    registry.register_agent(AgentIdentity(
        name="customer_service",
        description="Handles customer inquiries and routes requests",
        skills=["customer_inquiry", "account_lookup", "route_request"],
        authority_level=AuthorityLevel.READ_ONLY,
        allowed_data_domains=["customer_data", "pii"],
        compliance_scopes=["SOX", "SEC"],
        max_data_classification="confidential",
    ))

    registry.register_agent(AgentIdentity(
        name="research_agent",
        description="Analyzes market data and generates investment recommendations",
        skills=["market_analysis", "portfolio_analysis", "risk_assessment"],
        authority_level=AuthorityLevel.READ_WRITE,
        allowed_data_domains=["financial_records", "market_data"],
        compliance_scopes=["SOX", "SEC", "FINRA"],
        max_data_classification="restricted",
    ))

    registry.register_agent(AgentIdentity(
        name="trading_agent",
        description="Executes approved trades and portfolio rebalancing",
        skills=["execute_trade", "portfolio_rebalance"],
        authority_level=AuthorityLevel.EXECUTE,
        allowed_data_domains=["financial_records", "market_data"],
        compliance_scopes=["SOX", "SEC", "FINRA"],
        max_data_classification="restricted",
    ))

    registry.register_agent(AgentIdentity(
        name="compliance_agent",
        description="Reviews transactions for regulatory compliance",
        skills=["compliance_review", "risk_check", "audit_report"],
        authority_level=AuthorityLevel.ADMIN,
        allowed_data_domains=["financial_records", "pii", "market_data", "customer_data"],
        compliance_scopes=["SOX", "SEC", "FINRA", "PCI-DSS"],
        max_data_classification="restricted",
    ))

    # Contract: customer_service → research_agent
    registry.register_contract(HandoffContract(
        contract_id="CTR-001",
        name="Customer Request to Research",
        consumer_agent="customer_service",
        provider_agent="research_agent",
        request_schema=[
            FieldContract(name="customer_id", field_type="string", required=True,
                          pattern=r"^CUST-\d{6}$", pii=True),
            FieldContract(name="request_type", field_type="string", required=True,
                          enum_values=["portfolio_review", "rebalance_request", "risk_assessment"]),
            FieldContract(name="account_id", field_type="string", required=True,
                          pattern=r"^(ACCT-\d{8}|\*{4}\d{4})$"),
            FieldContract(name="risk_tolerance", field_type="string", required=False,
                          enum_values=["conservative", "moderate", "aggressive"]),
        ],
        required_authority=AuthorityLevel.READ_ONLY,
        allowed_actions=["query", "analyze"],
        prohibited_actions=["trade", "modify", "delete"],
        required_compliance_scopes=["SOX", "SEC"],
        max_data_classification="confidential",
    ))

    # Contract: research_agent → trading_agent
    registry.register_contract(HandoffContract(
        contract_id="CTR-002",
        name="Research Recommendations to Trading",
        consumer_agent="research_agent",
        provider_agent="trading_agent",
        request_schema=[
            FieldContract(name="account_id", field_type="string", required=True,
                          pattern=r"^ACCT-\d{8}$"),
            FieldContract(name="symbol", field_type="string", required=True,
                          pattern=r"^[A-Z]{1,5}$"),
            FieldContract(name="action", field_type="string", required=True,
                          enum_values=["buy", "sell", "hold"]),
            FieldContract(name="amount", field_type="number", required=True,
                          min_value=0, max_value=500000, financial_data=True),
            FieldContract(name="rationale", field_type="string", required=True,
                          max_length=1000),
        ],
        required_authority=AuthorityLevel.READ_WRITE,
        allowed_actions=["recommend", "trade", "execute_order"],
        prohibited_actions=["delete_account", "modify_compliance_rules"],
        required_compliance_scopes=["SOX", "SEC", "FINRA"],
        max_data_classification="restricted",
        require_audit_trail=True,
    ))

    # Contract: trading_agent → compliance_agent
    registry.register_contract(HandoffContract(
        contract_id="CTR-003",
        name="Trade Execution to Compliance Review",
        consumer_agent="trading_agent",
        provider_agent="compliance_agent",
        request_schema=[
            FieldContract(name="trade_id", field_type="string", required=True),
            FieldContract(name="account_id", field_type="string", required=True),
            FieldContract(name="symbol", field_type="string", required=True),
            FieldContract(name="action", field_type="string", required=True,
                          enum_values=["buy", "sell"]),
            FieldContract(name="amount", field_type="number", required=True,
                          financial_data=True),
            FieldContract(name="execution_price", field_type="number", required=True,
                          financial_data=True),
        ],
        required_authority=AuthorityLevel.EXECUTE,
        allowed_actions=["compliance_review", "audit"],
        required_compliance_scopes=["SOX", "SEC", "FINRA"],
        max_data_classification="restricted",
        require_audit_trail=True,
    ))

    return registry


def build_graph(
    registry: ContractRegistry,
    audit: AuditLogger,
    block_on_violation: bool = True,
) -> Any:
    """Build and compile the LangGraph financial agent pipeline."""
    vg = ValidatedGraph(registry, audit, block_on_violation=block_on_violation)
    vg.register_policy_pack(FinancePolicyPack())

    graph = vg.build(FinancialState)
    graph.add_node("customer_service", customer_service)
    graph.add_node("research_agent", research_agent)
    graph.add_node("trading_agent", trading_agent)
    graph.add_node("compliance_agent", compliance_agent)

    graph.add_edge(START, "customer_service")
    graph.add_edge("customer_service", "research_agent")
    graph.add_edge("research_agent", "trading_agent")
    graph.add_edge("trading_agent", "compliance_agent")
    graph.add_edge("compliance_agent", END)

    return graph.compile()


def make_initial_state(**overrides) -> dict:
    """Create initial state with sensible defaults."""
    state: dict[str, Any] = {
        "customer_id": "CUST-123456",
        "request_type": "rebalance_request",
        "account_id": "ACCT-00112233",
        "risk_tolerance": "moderate",
        "symbol": "",
        "action": "",
        "amount": 0.0,
        "rationale": "",
        "trade_id": "",
        "execution_price": 0.0,
        "timestamp": "",
        "compliance_status": "",
        "review_notes": "",
        AGENTPACT_METADATA_KEY: {},
        AGENTPACT_STATE_KEY: "",
        AGENTPACT_RESULTS_KEY: [],
    }
    state.update(overrides)
    return state


def run_demo():
    print("\n" + "=" * 70)
    print("  AgentPact + LangGraph: Financial Multi-Agent System")
    print("=" * 70)

    print("\n" + "-" * 70)
    print("  SCENARIO 1: Valid Portfolio Rebalance (Happy Path)")
    print("-" * 70 + "\n")

    registry = build_registry()
    audit = AuditLogger()
    app = build_graph(registry, audit)

    result = app.invoke(make_initial_state())

    validations = result[AGENTPACT_RESULTS_KEY]
    print(f"  Pipeline completed. {len(validations)} handoffs validated.\n")
    for v in validations:
        icon = "PASS" if v["result"] == "pass" else "FAIL"
        print(f"    [{icon}] {v['consumer']} -> {v['provider']}  "
              f"violations={v['total_violations']}")
    print(f"\n  Final state: compliance_status={result['compliance_status']}")
    print(f"  Trade: {result['symbol']} {result['action']} "
          f"${result['amount']:.2f} @ ${result['execution_price']:.2f}")

    print("\n" + "-" * 70)
    print("  SCENARIO 2: PII Leak Detection (SSN in rationale)")
    print("-" * 70 + "\n")

    registry2 = build_registry()
    audit2 = AuditLogger()
    vg2 = ValidatedGraph(registry2, audit2, block_on_violation=True)
    vg2.register_policy_pack(FinancePolicyPack())
    graph2 = vg2.build(FinancialState)

    def bad_research(state):
        """Research agent that accidentally leaks an SSN in the rationale."""
        return {
            "symbol": "MSFT",
            "action": "buy",
            "amount": 3000.0,
            "rationale": "Client John Doe (SSN: 123-45-6789) wants tech exposure",
            AGENTPACT_METADATA_KEY: {
                "action": "recommend",
                "request_id": "REQ-2025-002",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "initiator": "research_agent",
            },
        }

    graph2.add_node("customer_service", customer_service)
    graph2.add_node("research_agent", bad_research)
    graph2.add_node("trading_agent", trading_agent)
    graph2.add_node("compliance_agent", compliance_agent)
    graph2.add_edge(START, "customer_service")
    graph2.add_edge("customer_service", "research_agent")
    graph2.add_edge("research_agent", "trading_agent")
    graph2.add_edge("trading_agent", "compliance_agent")
    graph2.add_edge("compliance_agent", END)
    app2 = graph2.compile()

    try:
        app2.invoke(make_initial_state())
        print("  ERROR: Should have been blocked!")
    except HandoffBlockedError as e:
        print(f"  BLOCKED: {e}\n")
        blocked = audit2.get_blocked()
        if blocked:
            r = blocked[0]
            all_v = r.schema_violations + r.policy_violations + r.authority_violations
            for v in all_v:
                print(f"    [{v.severity.value.upper()}] {v.rule_id}: {v.message}")

    print("\n" + "-" * 70)
    print("  SCENARIO 3: Large Transaction Without Human Approval")
    print("-" * 70 + "\n")

    registry3 = build_registry()
    audit3 = AuditLogger()
    vg3 = ValidatedGraph(registry3, audit3, block_on_violation=True)
    vg3.register_policy_pack(FinancePolicyPack())
    graph3 = vg3.build(FinancialState)

    def aggressive_research(state):
        """Research agent recommending a $75K trade without human approval."""
        return {
            "symbol": "GOOGL",
            "action": "buy",
            "amount": 75000.0,
            "rationale": "Major rebalancing towards large-cap tech",
            AGENTPACT_METADATA_KEY: {
                "action": "recommend",
                "request_id": "REQ-2025-003",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "initiator": "research_agent",
                # NOTE: no "human_approved" flag — this triggers the violation
            },
        }

    graph3.add_node("customer_service", customer_service)
    graph3.add_node("research_agent", aggressive_research)
    graph3.add_node("trading_agent", trading_agent)
    graph3.add_node("compliance_agent", compliance_agent)
    graph3.add_edge(START, "customer_service")
    graph3.add_edge("customer_service", "research_agent")
    graph3.add_edge("research_agent", "trading_agent")
    graph3.add_edge("trading_agent", "compliance_agent")
    graph3.add_edge("compliance_agent", END)
    app3 = graph3.compile()

    try:
        app3.invoke(make_initial_state())
        print("  ERROR: Should have been blocked!")
    except HandoffBlockedError as e:
        print(f"  BLOCKED: {e}")

    print("\n" + "-" * 70)
    print("  SCENARIO 4: Monitor Mode (violations logged but not blocked)")
    print("-" * 70 + "\n")

    registry4 = build_registry()
    audit4 = AuditLogger()
    app4 = build_graph(registry4, audit4, block_on_violation=False)

    result4 = app4.invoke(make_initial_state(
        customer_id="BAD-FORMAT",       # Invalid customer_id pattern
        request_type="rebalance_request",
    ))

    validations4 = result4[AGENTPACT_RESULTS_KEY]
    print(f"  Pipeline completed (monitor mode). {len(validations4)} handoffs validated.\n")
    for v in validations4:
        icon = "PASS" if v["result"] == "pass" else "FAIL"
        violations = (v["violations"]["schema"]
                      + v["violations"]["policy"]
                      + v["violations"]["authority"])
        print(f"    [{icon}] {v['consumer']} -> {v['provider']}  "
              f"violations={v['total_violations']}")
        for viol in violations:
            print(f"         [{viol['severity'].upper()}] {viol['rule_id']}: {viol['message']}")

    print("\n" + "-" * 70)
    print("  SUMMARY")
    print("-" * 70 + "\n")
    print("  Scenario 1: Happy path           — all handoffs passed")
    print("  Scenario 2: PII leak             — blocked at research -> trading")
    print("  Scenario 3: Large tx no approval  — blocked at research -> trading")
    print("  Scenario 4: Monitor mode          — violations logged, not blocked")
    print()


if __name__ == "__main__":
    run_demo()
