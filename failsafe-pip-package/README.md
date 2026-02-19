# FailSafe

Contract testing and compliance validation for multi-agent AI systems.

Built by [PhT Labs](https://github.com/pht-labs).

## Install

```bash
pip install failsafe-ai
```

## Quick Start

```python
from failsafe import FailSafe

fs = FailSafe(mode="block")

# Register agents
fs.register_agent("research_agent")
fs.register_agent("writer_agent")

# Define a contract between them
fs.contract(
    name="research-to-writer",
    source="research_agent",
    target="writer_agent",
    allow=["query", "sources", "summary"],
    deny=["api_key", "internal_config"],
    require=["query", "sources"],
)

# Validate a handoff
result = await fs.handoff(
    source="research_agent",
    target="writer_agent",
    payload={
        "query": "AI safety",
        "sources": ["arxiv.org/1234"],
        "api_key": "sk-secret-123",  # blocked
    },
)

print(result.passed)       # False
print(result.violations)   # Denied fields found in payload: ['api_key']
```

## Features

- **Validate in milliseconds** — Deterministic contract rules execute without LLM calls.
- **Prevent data leakage** — Allow/deny field lists and sensitive pattern detection block data from crossing agent boundaries.
- **Compliance policies** — Pre-built policy packs for finance regulations and GDPR.
- **LLM-as-judge** — Natural language rules evaluated by an LLM for nuanced validation.
- **Full audit trail** — Every handoff logged to SQLite with violations, timestamps, and trace IDs.
- **Warn or block modes** — Choose per-contract whether violations log warnings or actively block handoffs.

## Integrations

```bash
pip install failsafe-ai[langchain]
```

Includes LangChain callback handler, LangGraph integration, and `@validated_tool` decorator.

## Dashboard

```bash
failsafe dashboard
```

Real-time visualization of validation events via WebSocket.

## License

MIT
