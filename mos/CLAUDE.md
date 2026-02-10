# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AgentPact** — contract testing and compliance validation for multi-agent AI systems. Validates handoffs between agents for schema violations, authority escalation, PII leaks, and regulatory non-compliance.

## Build & Test

```bash
pip install -e ".[dev]"               # dev deps (pytest)
pip install -e ".[all]"               # all optional deps (fastapi, langgraph)

python3 test_core.py                  # 18 core tests
python3 test_langgraph.py             # 14 LangGraph integration tests
python3 financial_agents.py           # 4-agent demo
python3 examples/langgraph_financial_agents.py  # LangGraph demo
python3 dashboard/app.py              # Dashboard on http://localhost:8420
```

Tests use `sys.path` insertion to resolve the `agentpact` package from the repo root.

## Package Structure

```
agentpact/
  core/models.py       — AgentIdentity, FieldContract, HandoffContract, ContractRegistry
  core/engine.py       — ValidationEngine (schema → authority → policy)
  policies/finance.py  — FinancePolicyPack (10 rules: PII, SOX, SEC, FINRA)
  interceptor/middleware.py — HandoffInterceptor, AgentPactGuard, HandoffBlockedError
  audit/logger.py      — AuditLogger (in-memory + SQLite)
  integrations/langgraph.py — ValidatedGraph (wraps LangGraph StateGraph)
dashboard/
  app.py               — FastAPI server with seeded demo scenarios
  index.html           — Single-page monitoring dashboard
```

Root-level `models.py`, `engine.py`, etc. are the original flat copies (pre-package).

## Key Design

- **Fail closed** — CRITICAL/HIGH violations block handoffs
- **Three-layer validation** — schema, authority, policy (pluggable packs)
- **Zero core dependencies** — stdlib only (dataclasses, sqlite3, re, json)
- **LangGraph integration** — `_agentpact_metadata` state key separates handoff metadata from domain data; contract-scoped field filtering avoids false positives from LangGraph's cumulative state
- **Python 3.10+**
