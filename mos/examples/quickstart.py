"""Failsafe quickstart — run with: failsafe watch examples/quickstart.py -v"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentpact import Failsafe

fs = Failsafe()

# Register agents
fs.agent("customer_service", authority="read_only",
         compliance=["SOX", "SEC"], allowed_domains=["customer_data", "pii"],
         max_classification="confidential")
fs.agent("research_agent", authority="read_write",
         compliance=["SOX", "SEC", "FINRA"], allowed_domains=["financial_records", "market_data"],
         max_classification="restricted")
fs.agent("trading_agent", authority="execute",
         compliance=["SOX", "SEC", "FINRA"], allowed_domains=["financial_records", "market_data"],
         max_classification="restricted")

# Register contracts
fs.contract("customer_service", "research_agent", fields={
    "customer_id": {"type": "string", "pattern": r"^CUST-\d{6}$", "pii": True},
    "request_type": {"type": "string", "enum": ["portfolio_review", "rebalance_request"]},
}, authority="read_only", compliance=["SOX", "SEC"])

fs.contract("research_agent", "trading_agent", fields={
    "symbol": {"type": "string", "pattern": r"^[A-Z]{1,5}$"},
    "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
    "amount": {"type": "number", "min_value": 0, "max_value": 500000, "financial_data": True},
    "rationale": {"type": "string", "max_length": 1000},
}, authority="read_write", compliance=["SOX", "SEC", "FINRA"])

meta = {"action": "query", "request_id": "REQ-001", "timestamp": "2025-01-01T00:00:00Z", "initiator": "portal"}

# 1) Valid handoff
fs.validate("customer_service", "research_agent",
            {"customer_id": "CUST-123456", "request_type": "portfolio_review"}, meta)

# 2) Valid trade
fs.validate("research_agent", "trading_agent",
            {"symbol": "AAPL", "action": "buy", "amount": 5000.0, "rationale": "Portfolio underweight in tech."},
            {"action": "recommend", "request_id": "REQ-002", "timestamp": "2025-01-01T00:00:00Z", "initiator": "research"})

# 3) SSN leak
fs.validate("research_agent", "trading_agent",
            {"symbol": "TSLA", "action": "buy", "amount": 3000.0,
             "rationale": "Client (SSN: 456-78-9012) wants EV exposure"},
            {"action": "recommend", "request_id": "REQ-003", "timestamp": "2025-01-01T00:00:00Z", "initiator": "research"})

# 4) Large transaction without approval
fs.validate("research_agent", "trading_agent",
            {"symbol": "GOOGL", "action": "buy", "amount": 75000.0, "rationale": "Major rebalancing"},
            {"action": "recommend", "request_id": "REQ-004", "timestamp": "2025-01-01T00:00:00Z", "initiator": "research"})

# Print compliance report
print("\n" + fs.report())
