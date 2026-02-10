# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AgentPact** is a contract testing and compliance validation framework for multi-agent AI systems. It validates handoffs between agents, catching schema violations, authority escalation, PII leaks, and regulatory non-compliance. Think: Pact (contract testing) meets OPA (policy engine) for agent teams.

Current status: v0.1 MVP prototype. Pure Python, zero runtime dependencies.

## Build & Development

```bash
pip install -e ".[dev]"        # Install with dev dependencies (pytest)
pip install -e ".[all]"        # Install all optional deps (fastapi, langgraph, a2a-python)
```

## Testing

```bash
python -m pytest test_core.py -v       # Run full test suite
python -m pytest test_core.py -v -k "test_name"  # Run single test
```

The test suite (test_core.py) has 17 tests covering schema validation, authority validation, finance policy rules, interceptor middleware, and audit reporting.

**Note:** Tests import from `agentpact.core.models`, `agentpact.policies.finance`, etc., but the package structure doesn't exist yet — all source files are flat in the repo root. Tests currently require a `sys.path` hack to work.

## Running the Demo

```bash
python financial_agents.py     # 4-agent financial system with 6 validation scenarios
```

## Architecture

All source files are currently flat in the repo root (future structure planned in ROADMAP.md).

### Core Components

- **models.py** — Data models using dataclasses: `AgentIdentity`, `FieldContract`, `HandoffContract`, `HandoffPayload`, `HandoffValidationResult`, `ContractRegistry`. Authority levels are hierarchical: READ_ONLY < READ_WRITE < EXECUTE < ADMIN.

- **engine.py** — `ValidationEngine` with three-layer validation:
  1. **Schema validation** — required fields, types, patterns (regex), enums, ranges, max length
  2. **Authority validation** — agent authority level, data classification clearance, allowed/prohibited actions, compliance scope overlap
  3. **Policy validation** — dispatches to registered policy packs

- **finance.py** — `FinancePolicyPack` with 10 compliance rules (PII exposure, SSN detection, unmasked accounts, transaction limits, trade authority, SOX audit metadata, segregation of duties, data boundaries, MNPI detection). Rule IDs follow `FIN-{CATEGORY}-{NUM}` pattern. Severities: CRITICAL (blocks handoff) and HIGH (blocks handoff).

- **middleware.py** — `HandoffInterceptor` wraps the validation engine for A2A JSON-RPC messages. `AgentPactGuard` provides a context manager/decorator API. Raises `HandoffBlockedError` when critical/high violations are found.

- **logger.py** — `AuditLogger` with in-memory storage and optional SQLite persistence. Provides compliance reporting: pass/fail/warn rates, violation breakdowns, per-agent stats.

### Data Flow

```
Agent A → HandoffInterceptor.validate_outgoing() → ValidationEngine → PolicyPack(s)
                                                         ↓
                                                   AuditLogger
                                                         ↓
                                               HandoffValidationResult (PASS/FAIL/WARN)
```

### Key Design Decisions

- **Fail closed**: handoffs with CRITICAL or HIGH violations are blocked, not just logged
- **Protocol-level**: targets A2A/MCP standards, framework integrations (LangGraph) are adapters
- **Policies are pluggable**: policy packs register with the engine via `engine.register_policy_pack()`
- **Zero dependencies**: core logic uses only Python stdlib (dataclasses, sqlite3, re, json)
- **Python 3.10+** required
