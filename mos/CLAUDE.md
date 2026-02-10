# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Failsafe** — contract testing and compliance validation for multi-agent AI systems. Validates handoffs between agents for schema violations, authority escalation, PII leaks, and regulatory non-compliance. Package name is `agentpact`, brand name is Failsafe.

## Build & Test

```bash
pip install -e ".[dev]"               # dev deps (pytest)
pip install -e ".[all]"               # all optional deps (fastapi, langgraph)

# Tests (all in repo root, use sys.path insertion for imports)
python3 test_core.py                  # 18 core validation tests
python3 test_api.py                   # 9 SDK API tests
python3 test_cli.py                   # 4 CLI tests
python3 test_langgraph.py             # 14 LangGraph integration tests
pytest                                # all 45 tests via pytest

# Single test
pytest test_core.py::test_ssn_detection -v

# Demos
failsafe demo -v                      # CLI demo with colored output
failsafe watch examples/quickstart.py -v  # Watch mode on any script
python3 financial_agents.py           # 4-agent financial demo
python3 dashboard/app.py              # Dashboard on http://localhost:8420
```

## Package Structure

```
agentpact/
  __init__.py            — Public API exports + __version__
  api.py                 — Failsafe high-level SDK class
  cli.py                 — CLI entry point (failsafe watch/demo/report)
  core/models.py         — AgentIdentity, FieldContract, HandoffContract, ContractRegistry, enums
  core/engine.py         — ValidationEngine (schema → authority → policy pipeline)
  policies/finance.py    — FinancePolicyPack (10 rules: PII, SOX, SEC, FINRA, PCI-DSS)
  interceptor/middleware.py — HandoffInterceptor, FailsafeGuard, HandoffBlockedError
  audit/logger.py        — AuditLogger (in-memory + SQLite)
  integrations/langgraph.py — ValidatedGraph (wraps LangGraph StateGraph)
dashboard/
  app.py                 — FastAPI server (port 8420) with seeded demo scenarios
  index.html             — Single-page dashboard UI
```

Root-level `models.py`, `engine.py`, `finance.py`, `middleware.py`, `logger.py` are legacy flat copies. Canonical code is in `agentpact/`. Keep them in sync if editing core models.

## Key Architecture

- **Two API layers**: High-level `Failsafe` class in `api.py` (5-line quickstart, method chaining, auto-registers finance policies) wraps the low-level `ContractRegistry` + `HandoffInterceptor` + `AuditLogger` wiring
- **Fail closed** — CRITICAL/HIGH severity violations block handoffs by default
- **Three-layer validation** — schema, authority, policy (pluggable packs via `evaluate()` interface)
- **Zero core dependencies** — stdlib only; FastAPI/LangGraph are optional
- **Callback system** — `on_violation()` fires on failures only; `on_validation()` fires on every validation (used by CLI watch mode via `FAILSAFE_WATCH_MODE` env var)
- **LangGraph integration** — `_failsafe_metadata` state key separates handoff metadata from domain data; contract-scoped field filtering avoids false positives from LangGraph's cumulative state
- **Dashboard** — FastAPI serves `index.html` + REST API (`/api/summary`, `/api/handoffs`, `/api/agents`, `/api/contracts`, `/api/simulate/{scenario}`, `/api/validate`)

## Policy Pack Interface

Custom policy packs implement one method:
```python
def evaluate(self, contract, payload, consumer, provider) -> list[PolicyViolation]
```
Register via `interceptor.register_policy_pack(pack)` or auto-registered when using `Failsafe` class with matching compliance scopes.
