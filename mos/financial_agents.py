#!/usr/bin/env python3
"""
Failsafe Example: Financial Multi-Agent System

Demonstrates a realistic scenario where multiple AI agents collaborate
on financial tasks. Failsafe validates every handoff between them.

Scenario:
  A financial services firm has 4 agents:
  1. Customer Service Agent - handles customer inquiries
  2. Research Agent - analyzes market data
  3. Trading Agent - executes trades
  4. Compliance Agent - reviews transactions

  The system processes a customer request to rebalance their portfolio.
  Failsafe validates every agent-to-agent handoff.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentpact.core.models import (
    AgentIdentity,
    AuthorityLevel,
    ContractRegistry,
    FieldContract,
    HandoffContract,
    HandoffPayload,
)
from agentpact.core.engine import ValidationEngine
from agentpact.policies.finance import FinancePolicyPack
from agentpact.interceptor.middleware import HandoffInterceptor, HandoffBlockedError
from agentpact.audit.logger import AuditLogger


def setup_agents(registry: ContractRegistry):
    """Register all agents with their identities and permissions."""
    
    # Customer Service Agent - can read customer data, no financial authority
    registry.register_agent(AgentIdentity(
        name="customer_service",
        description="Handles customer inquiries and routes requests",
        version="1.0.0",
        skills=["customer_inquiry", "account_lookup", "route_request"],
        authority_level=AuthorityLevel.READ_ONLY,
        allowed_data_domains=["customer_data", "pii"],
        compliance_scopes=["SOX", "SEC"],
        max_data_classification="confidential",
    ))
    
    # Research Agent - can read market data and write recommendations
    registry.register_agent(AgentIdentity(
        name="research_agent",
        description="Analyzes market data and generates investment recommendations",
        version="1.0.0",
        skills=["market_analysis", "portfolio_analysis", "risk_assessment"],
        authority_level=AuthorityLevel.READ_WRITE,
        allowed_data_domains=["financial_records", "market_data"],
        compliance_scopes=["SOX", "SEC", "FINRA"],
        max_data_classification="restricted",
    ))
    
    # Trading Agent - can execute trades (execute authority)
    registry.register_agent(AgentIdentity(
        name="trading_agent",
        description="Executes approved trades and portfolio rebalancing",
        version="1.0.0",
        skills=["execute_trade", "portfolio_rebalance", "order_management"],
        authority_level=AuthorityLevel.EXECUTE,
        allowed_data_domains=["financial_records", "market_data", "max_amount:100000"],
        compliance_scopes=["SOX", "SEC", "FINRA"],
        max_data_classification="restricted",
    ))
    
    # Compliance Agent - admin level, reviews everything
    registry.register_agent(AgentIdentity(
        name="compliance_agent",
        description="Reviews transactions for regulatory compliance",
        version="1.0.0",
        skills=["compliance_review", "risk_check", "audit_report"],
        authority_level=AuthorityLevel.ADMIN,
        allowed_data_domains=["financial_records", "pii", "market_data", "customer_data"],
        compliance_scopes=["SOX", "SEC", "FINRA", "PCI-DSS"],
        max_data_classification="restricted",
    ))


def setup_contracts(registry: ContractRegistry):
    """Define contracts for each agent-to-agent handoff."""
    
    # Contract 1: Customer Service → Research Agent
    registry.register_contract(HandoffContract(
        contract_id="CTR-001",
        name="Customer Request to Research",
        description="Customer service passes portfolio analysis request to research",
        consumer_agent="customer_service",
        provider_agent="research_agent",
        request_schema=[
            FieldContract(
                name="customer_id", field_type="string", required=True,
                pattern=r"^CUST-\d{6}$", pii=True,
            ),
            FieldContract(
                name="request_type", field_type="string", required=True,
                enum_values=["portfolio_review", "rebalance_request", "risk_assessment"],
            ),
            FieldContract(
                name="account_id", field_type="string", required=True,
                pattern=r"^(ACCT-\d{8}|\*{4}\d{4})$",  # Masked or full format
            ),
            FieldContract(
                name="risk_tolerance", field_type="string", required=False,
                enum_values=["conservative", "moderate", "aggressive"],
            ),
        ],
        response_schema=[
            FieldContract(
                name="analysis", field_type="object", required=True,
            ),
            FieldContract(
                name="recommendations", field_type="array", required=True,
            ),
        ],
        required_authority=AuthorityLevel.READ_ONLY,
        allowed_actions=["query", "analyze"],
        prohibited_actions=["trade", "modify", "delete"],
        required_compliance_scopes=["SOX", "SEC"],
        max_data_classification="confidential",
    ))
    
    # Contract 2: Research Agent → Trading Agent
    registry.register_contract(HandoffContract(
        contract_id="CTR-002",
        name="Research Recommendations to Trading",
        description="Research passes trade recommendations to trading for execution",
        consumer_agent="research_agent",
        provider_agent="trading_agent",
        request_schema=[
            FieldContract(
                name="account_id", field_type="string", required=True,
                pattern=r"^ACCT-\d{8}$",
            ),
            FieldContract(
                name="symbol", field_type="string", required=True,
                pattern=r"^[A-Z]{1,5}$",
            ),
            FieldContract(
                name="action", field_type="string", required=True,
                enum_values=["buy", "sell", "hold"],
            ),
            FieldContract(
                name="amount", field_type="number", required=True,
                min_value=0, max_value=500000, financial_data=True,
            ),
            FieldContract(
                name="rationale", field_type="string", required=True,
                max_length=1000,
            ),
        ],
        required_authority=AuthorityLevel.READ_WRITE,
        allowed_actions=["recommend", "trade", "execute_order"],
        prohibited_actions=["delete_account", "modify_compliance_rules"],
        required_compliance_scopes=["SOX", "SEC", "FINRA"],
        max_data_classification="restricted",
        require_audit_trail=True,
    ))
    
    # Contract 3: Trading Agent → Compliance Agent
    registry.register_contract(HandoffContract(
        contract_id="CTR-003",
        name="Trade Execution to Compliance Review",
        description="Trading sends executed trade details to compliance for review",
        consumer_agent="trading_agent",
        provider_agent="compliance_agent",
        request_schema=[
            FieldContract(
                name="trade_id", field_type="string", required=True,
            ),
            FieldContract(
                name="account_id", field_type="string", required=True,
            ),
            FieldContract(
                name="symbol", field_type="string", required=True,
            ),
            FieldContract(
                name="action", field_type="string", required=True,
                enum_values=["buy", "sell"],
            ),
            FieldContract(
                name="amount", field_type="number", required=True,
                financial_data=True,
            ),
            FieldContract(
                name="execution_price", field_type="number", required=True,
                financial_data=True,
            ),
            FieldContract(
                name="timestamp", field_type="string", required=True,
            ),
        ],
        required_authority=AuthorityLevel.EXECUTE,
        allowed_actions=["compliance_review", "audit"],
        required_compliance_scopes=["SOX", "SEC", "FINRA"],
        max_data_classification="restricted",
        require_audit_trail=True,
    ))


def run_scenario():
    """Run the full multi-agent financial scenario."""
    
    print("\n" + "=" * 70)
    print("  Failsafe Demo: Financial Multi-Agent System")
    print("=" * 70)
    print()

    registry = ContractRegistry()
    setup_agents(registry)
    setup_contracts(registry)
    
    audit = AuditLogger(db_path="agentpact_audit.db")
    interceptor = HandoffInterceptor(registry, audit)
    interceptor.register_policy_pack(FinancePolicyPack())
    
    # Register a callback for violations
    def on_violation(result):
        if result.is_blocked:
            print(f"  🚨 ALERT: Handoff blocked! {result.consumer_agent} → {result.provider_agent}")
    
    interceptor.on_violation(on_violation)
    
    print("  📋 Registered 4 agents, 3 contracts, 1 policy pack (Finance)")
    print()

    print("─" * 70)
    print("  SCENARIO 1: Valid Portfolio Rebalance Request")
    print("─" * 70)
    print()
    
    # Step 1: Customer Service → Research Agent
    print("  Step 1: Customer Service → Research Agent")
    result1 = interceptor.validate_outgoing(
        from_agent="customer_service",
        to_agent="research_agent",
        data={
            "customer_id": "CUST-123456",
            "request_type": "rebalance_request",
            "account_id": "ACCT-00112233",
            "risk_tolerance": "moderate",
        },
        metadata={
            "action": "query",
            "request_id": "REQ-2025-001",
            "timestamp": "2025-02-09T10:00:00Z",
            "initiator": "customer_portal",
        }
    )
    print(f"  {result1.summary()}")
    print()
    
    # Step 2: Research Agent → Trading Agent (recommendation, not execution)
    print("  Step 2: Research Agent → Trading Agent")
    result2 = interceptor.validate_outgoing(
        from_agent="research_agent",
        to_agent="trading_agent",
        data={
            "account_id": "ACCT-00112233",
            "symbol": "AAPL",
            "action": "buy",
            "amount": 5000.00,
            "rationale": "Portfolio underweight in tech sector. AAPL shows strong fundamentals.",
        },
        metadata={
            "action": "recommend",  # Research recommends, doesn't execute
            "request_id": "REQ-2025-001",
            "timestamp": "2025-02-09T10:01:00Z",
            "initiator": "research_agent",
        }
    )
    print(f"  {result2.summary()}")
    print()
    
    # Step 3: Trading Agent → Compliance Agent
    print("  Step 3: Trading Agent → Compliance Agent")
    result3 = interceptor.validate_outgoing(
        from_agent="trading_agent",
        to_agent="compliance_agent",
        data={
            "trade_id": "TRD-2025-00001",
            "account_id": "ACCT-00112233",
            "symbol": "AAPL",
            "action": "buy",
            "amount": 5000.00,
            "execution_price": 182.50,
            "timestamp": "2025-02-09T10:02:00Z",
        },
        metadata={
            "action": "compliance_review",
            "request_id": "REQ-2025-001",
            "timestamp": "2025-02-09T10:02:00Z",
            "initiator": "trading_agent",
        }
    )
    print(f"  {result3.summary()}")
    print()

    print("─" * 70)
    print("  SCENARIO 2: Authority Escalation (Customer Agent tries to trade)")
    print("─" * 70)
    print()
    
    print("  Customer Service Agent attempts direct trade...")
    result4 = interceptor.validate_outgoing(
        from_agent="customer_service",
        to_agent="trading_agent",
        data={
            "account_id": "ACCT-00112233",
            "symbol": "TSLA",
            "action": "buy",
            "amount": 50000.00,
            "rationale": "Customer wants TSLA",
        },
        metadata={
            "action": "trade",
            "request_id": "REQ-2025-002",
            "timestamp": "2025-02-09T10:05:00Z",
            "initiator": "customer_service",
        }
    )
    print(f"  {result4.summary()}")
    if result4.total_violations > 0:
        print("  Violations detected:")
        for v in (result4.schema_violations + result4.policy_violations + result4.authority_violations):
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}[v.severity.value]
            print(f"    {icon} [{v.rule_id}] {v.message}")
    print()

    print("─" * 70)
    print("  SCENARIO 3: PII Leak (SSN in handoff payload)")
    print("─" * 70)
    print()
    
    print("  Research Agent sends data with embedded SSN...")
    result5 = interceptor.validate_outgoing(
        from_agent="research_agent",
        to_agent="trading_agent",
        data={
            "account_id": "ACCT-00112233",
            "symbol": "MSFT",
            "action": "buy",
            "amount": 3000.00,
            "rationale": "Client John Doe (SSN: 123-45-6789) requested tech exposure",
        },
        metadata={
            "action": "trade",
            "request_id": "REQ-2025-003",
            "timestamp": "2025-02-09T10:10:00Z",
            "initiator": "research_agent",
        }
    )
    print(f"  {result5.summary()}")
    if result5.total_violations > 0:
        print("  Violations detected:")
        for v in (result5.schema_violations + result5.policy_violations + result5.authority_violations):
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}[v.severity.value]
            print(f"    {icon} [{v.rule_id}] {v.message}")
    print()

    print("─" * 70)
    print("  SCENARIO 4: Schema Violation (malformed data)")
    print("─" * 70)
    print()
    
    print("  Customer Service sends malformed request...")
    result6 = interceptor.validate_outgoing(
        from_agent="customer_service",
        to_agent="research_agent",
        data={
            "customer_id": "BAD-FORMAT",          # Wrong pattern
            "request_type": "hack_the_system",     # Invalid enum
            "account_id": "12345678901234",        # Unmasked account number
            # Missing risk_tolerance is OK (optional)
        },
        metadata={
            "action": "query",
            "request_id": "REQ-2025-004",
            "timestamp": "2025-02-09T10:15:00Z",
            "initiator": "customer_portal",
        }
    )
    print(f"  {result6.summary()}")
    if result6.total_violations > 0:
        print("  Violations detected:")
        for v in (result6.schema_violations + result6.policy_violations + result6.authority_violations):
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}[v.severity.value]
            print(f"    {icon} [{v.rule_id}] {v.message}")
    print()

    print("─" * 70)
    print("  SCENARIO 5: Large Transaction Without Human Approval")
    print("─" * 70)
    print()
    
    print("  Research Agent sends $75K trade without human approval...")
    result7 = interceptor.validate_outgoing(
        from_agent="research_agent",
        to_agent="trading_agent",
        data={
            "account_id": "ACCT-00112233",
            "symbol": "GOOGL",
            "action": "buy",
            "amount": 75000.00,
            "rationale": "Major rebalancing towards large-cap tech",
        },
        metadata={
            "action": "trade",
            "request_id": "REQ-2025-005",
            "timestamp": "2025-02-09T10:20:00Z",
            "initiator": "research_agent",
            # Note: no "human_approved" flag!
        }
    )
    print(f"  {result7.summary()}")
    if result7.total_violations > 0:
        print("  Violations detected:")
        for v in (result7.schema_violations + result7.policy_violations + result7.authority_violations):
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}[v.severity.value]
            print(f"    {icon} [{v.rule_id}] {v.message}")
    print()

    print("─" * 70)
    print("  SCENARIO 6: Material Non-Public Information Detection")
    print("─" * 70)
    print()
    
    print("  Research Agent mentions unreleased earnings data...")
    result8 = interceptor.validate_outgoing(
        from_agent="research_agent",
        to_agent="trading_agent",
        data={
            "account_id": "ACCT-00112233",
            "symbol": "NVDA",
            "action": "buy",
            "amount": 8000.00,
            "rationale": "Pre-release earnings data suggests NVDA will beat guidance. Insider sources confirm strong Q4.",
        },
        metadata={
            "action": "trade",
            "request_id": "REQ-2025-006",
            "timestamp": "2025-02-09T10:25:00Z",
            "initiator": "research_agent",
        }
    )
    print(f"  {result8.summary()}")
    if result8.total_violations > 0:
        print("  Violations detected:")
        for v in (result8.schema_violations + result8.policy_violations + result8.authority_violations):
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}[v.severity.value]
            print(f"    {icon} [{v.rule_id}] {v.message}")
    print()

    print("─" * 70)
    print("  COMPLIANCE REPORT")
    print("─" * 70)
    print()
    print(audit.print_report())
    print()
    
    # Export JSON report
    report = audit.generate_summary_report()
    with open("compliance_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("  📄 Full JSON report saved to compliance_report.json")
    
    # Export contract definitions
    with open("contracts.json", "w") as f:
        json.dump(registry.to_dict(), f, indent=2)
    print("  📄 Contract definitions saved to contracts.json")
    print()


if __name__ == "__main__":
    run_scenario()
