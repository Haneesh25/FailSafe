"""Dashboard server — python dashboard/app.py → http://localhost:8420"""

from __future__ import annotations

import sys
import os
import json
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from agentpact.core.models import (
    AgentIdentity,
    AuthorityLevel,
    ContractRegistry,
    FieldContract,
    HandoffContract,
    HandoffValidationResult,
)
from agentpact.policies.finance import FinancePolicyPack
from agentpact.interceptor.middleware import HandoffInterceptor, HandoffBlockedError
from agentpact.audit.logger import AuditLogger



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

registry.register_contract(HandoffContract(
    contract_id="CTR-001", name="Customer Request to Research",
    consumer_agent="customer_service", provider_agent="research_agent",
    request_schema=[
        FieldContract(name="customer_id", field_type="string", required=True,
                      pattern=r"^CUST-\d{6}$", pii=True),
        FieldContract(name="request_type", field_type="string", required=True,
                      enum_values=["portfolio_review", "rebalance_request", "risk_assessment"]),
        FieldContract(name="account_id", field_type="string", required=True,
                      pattern=r"^(ACCT-\d{8}|\*{4}\d{4})$"),
    ],
    required_authority=AuthorityLevel.READ_ONLY,
    allowed_actions=["query", "analyze"],
    prohibited_actions=["trade", "modify", "delete"],
    required_compliance_scopes=["SOX", "SEC"],
))
registry.register_contract(HandoffContract(
    contract_id="CTR-002", name="Research Recommendations to Trading",
    consumer_agent="research_agent", provider_agent="trading_agent",
    request_schema=[
        FieldContract(name="symbol", field_type="string", required=True, pattern=r"^[A-Z]{1,5}$"),
        FieldContract(name="action", field_type="string", required=True,
                      enum_values=["buy", "sell", "hold"]),
        FieldContract(name="amount", field_type="number", required=True,
                      min_value=0, max_value=500000, financial_data=True),
        FieldContract(name="rationale", field_type="string", required=True, max_length=1000),
    ],
    required_authority=AuthorityLevel.READ_WRITE,
    allowed_actions=["recommend", "trade"],
    required_compliance_scopes=["SOX", "SEC", "FINRA"],
    require_audit_trail=True,
))
registry.register_contract(HandoffContract(
    contract_id="CTR-003", name="Trade Execution to Compliance Review",
    consumer_agent="trading_agent", provider_agent="compliance_agent",
    request_schema=[
        FieldContract(name="trade_id", field_type="string", required=True),
        FieldContract(name="symbol", field_type="string", required=True),
        FieldContract(name="action", field_type="string", required=True, enum_values=["buy", "sell"]),
        FieldContract(name="amount", field_type="number", required=True, financial_data=True),
        FieldContract(name="execution_price", field_type="number", required=True, financial_data=True),
    ],
    required_authority=AuthorityLevel.EXECUTE,
    allowed_actions=["compliance_review", "audit"],
    required_compliance_scopes=["SOX", "SEC", "FINRA"],
    require_audit_trail=True,
))

audit = AuditLogger()
interceptor = HandoffInterceptor(registry, audit)
interceptor.register_policy_pack(FinancePolicyPack())



def seed_data():

    interceptor.validate_outgoing("customer_service", "research_agent", {
        "customer_id": "CUST-123456", "request_type": "rebalance_request",
        "account_id": "ACCT-00112233",
    }, {"action": "query", "request_id": "REQ-001", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "customer_portal"})

    interceptor.validate_outgoing("research_agent", "trading_agent", {
        "symbol": "AAPL", "action": "buy", "amount": 5000.0,
        "rationale": "Portfolio underweight in tech.",
    }, {"action": "recommend", "request_id": "REQ-001", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "research_agent"})

    interceptor.validate_outgoing("trading_agent", "compliance_agent", {
        "trade_id": "TRD-001", "symbol": "AAPL", "action": "buy",
        "amount": 5000.0, "execution_price": 182.50,
    }, {"action": "compliance_review", "request_id": "REQ-001", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "trading_agent"})

    interceptor.validate_outgoing("customer_service", "research_agent", {
        "customer_id": "CUST-789012", "request_type": "risk_assessment",
        "account_id": "ACCT-44556677",
    }, {"action": "query", "request_id": "REQ-002", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "customer_portal"})

    interceptor.validate_outgoing("research_agent", "trading_agent", {
        "symbol": "MSFT", "action": "buy", "amount": 8000.0,
        "rationale": "Diversify into cloud sector.",
    }, {"action": "recommend", "request_id": "REQ-002", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "research_agent"})

    interceptor.validate_outgoing("trading_agent", "compliance_agent", {
        "trade_id": "TRD-002", "symbol": "MSFT", "action": "buy",
        "amount": 8000.0, "execution_price": 412.30,
    }, {"action": "compliance_review", "request_id": "REQ-002", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "trading_agent"})

    # SSN leak
    interceptor.validate_outgoing("research_agent", "trading_agent", {
        "symbol": "TSLA", "action": "buy", "amount": 3000.0,
        "rationale": "Client (SSN: 456-78-9012) wants EV exposure",
    }, {"action": "recommend", "request_id": "REQ-003", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "research_agent"})

    # Large tx, no approval
    interceptor.validate_outgoing("research_agent", "trading_agent", {
        "symbol": "GOOGL", "action": "buy", "amount": 75000.0,
        "rationale": "Major rebalancing",
    }, {"action": "recommend", "request_id": "REQ-004", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "research_agent"})

    # Schema violation
    interceptor.validate_outgoing("customer_service", "research_agent", {
        "customer_id": "BAD-FORMAT", "request_type": "rebalance_request",
        "account_id": "ACCT-00112233",
    }, {"action": "query", "request_id": "REQ-005", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "customer_portal"})

    # MNPI
    interceptor.validate_outgoing("research_agent", "trading_agent", {
        "symbol": "NVDA", "action": "buy", "amount": 8000.0,
        "rationale": "Pre-release earnings suggest strong Q4. Insider sources confirm.",
    }, {"action": "recommend", "request_id": "REQ-006", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "research_agent"})

    # No contract
    interceptor.validate_outgoing("customer_service", "trading_agent", {
        "symbol": "HACK", "action": "buy", "amount": 50000.0,
        "rationale": "Direct trade attempt",
    }, {"action": "trade", "request_id": "REQ-007", "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "customer_service"})


seed_data()



app = FastAPI(title="Failsafe Dashboard")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text())


@app.get("/api/summary")
async def api_summary():
    report = audit.generate_summary_report()
    return JSONResponse(report)


@app.get("/api/handoffs")
async def api_handoffs():
    all_records = audit.get_all()
    return JSONResponse([r.to_dict() for r in all_records])


@app.get("/api/agents")
async def api_agents():
    return JSONResponse({
        name: agent.to_dict() for name, agent in registry.agents.items()
    })


@app.get("/api/contracts")
async def api_contracts():
    return JSONResponse({
        cid: c.to_dict() for cid, c in registry.contracts.items()
    })


@app.post("/api/validate")
async def api_validate(request: dict):
    try:
        from_agent = request.get("from_agent", "")
        to_agent = request.get("to_agent", "")
        data = request.get("data", {})
        metadata = request.get("metadata", {})
        r = interceptor.validate_outgoing(from_agent, to_agent, data, metadata)
        return JSONResponse(r.to_dict())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/simulate/{scenario}")
async def api_simulate(scenario: str):
    try:
        if scenario == "happy":
            r = interceptor.validate_outgoing("customer_service", "research_agent", {
                "customer_id": "CUST-999999", "request_type": "portfolio_review",
                "account_id": "ACCT-88888888",
            }, {"action": "query", "request_id": f"SIM-{datetime.now(timezone.utc).timestamp():.0f}",
                "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "dashboard"})
            return JSONResponse(r.to_dict())
        elif scenario == "ssn_leak":
            r = interceptor.validate_outgoing("research_agent", "trading_agent", {
                "symbol": "AAPL", "action": "buy", "amount": 5000.0,
                "rationale": "Client SSN: 111-22-3333 wants AAPL",
            }, {"action": "recommend", "request_id": f"SIM-{datetime.now(timezone.utc).timestamp():.0f}",
                "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "dashboard"})
            return JSONResponse(r.to_dict())
        elif scenario == "large_tx":
            r = interceptor.validate_outgoing("research_agent", "trading_agent", {
                "symbol": "AMZN", "action": "buy", "amount": 80000.0,
                "rationale": "Large position change",
            }, {"action": "recommend", "request_id": f"SIM-{datetime.now(timezone.utc).timestamp():.0f}",
                "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "dashboard"})
            return JSONResponse(r.to_dict())
        elif scenario == "authority_escalation":
            r = interceptor.validate_outgoing("customer_service", "trading_agent", {
                "symbol": "TSLA", "action": "buy", "amount": 10000.0,
                "rationale": "Direct bypass",
            }, {"action": "trade", "request_id": f"SIM-{datetime.now(timezone.utc).timestamp():.0f}",
                "timestamp": datetime.now(timezone.utc).isoformat(), "initiator": "dashboard"})
            return JSONResponse(r.to_dict())
        else:
            return JSONResponse({"error": f"Unknown scenario: {scenario}"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    print("\n  Failsafe Dashboard")
    print("  http://localhost:8420\n")
    uvicorn.run(app, host="0.0.0.0", port=8420, log_level="warning")
