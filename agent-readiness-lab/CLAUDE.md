# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Start all services (API, worker, webapp, postgres, redis)
docker compose up --build

# Run the end-to-end demo
./scripts/demo.sh

# Install CLI locally for development
pip install -e ".[dev]"

# Run tests
pytest tests/
pytest tests/test_traces.py -v          # Single file
pytest tests/test_mutator.py::TestMutatorDeterminism -v  # Single class
pytest --cov=packages/arlab tests/      # With coverage

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## Architecture

This system tests AI agents by replaying user interaction traces against a sandboxed webapp and scoring their performance.

### Core Flow
1. **Traces** (JSONL files) define user sessions with goals and step sequences
2. **API** (`apps/api/`) receives traces and queues evaluation jobs via Redis/RQ
3. **Worker** (`apps/worker/`) executes jobs using Playwright against the webapp
4. **Replayer** (`packages/arlab/replayer/`) either replays traces directly OR runs an agent
5. **Agent Harness** (`packages/arlab/harness/`) provides constrained tool API to agents (no shell access)
6. **Scoring** (`packages/arlab/scoring/`) calculates metrics from execution results
7. Results stored in Postgres, accessible via API endpoints

### Key Design Decisions
- **Constrained Tool API**: Agents can only use allowed actions (click, type, goto, etc.) defined in `harness/tools.py`. Selectors and URLs are validated for safety.
- **Deterministic Mutations**: `TraceMutator` uses seed + session_id to generate reproducible perturbations (jitter, misclicks, retries, abandonment).
- **Two Agent Types**: `StubAgent` (rule-based, in-repo) and `ExternalAgent` (HTTP endpoint, OpenAI-like interface).

### Service Ports
- API: 8000
- Webapp: 3000
- Postgres: 5432
- Redis: 6379

### Toy Webapp
The webapp (`apps/webapp/`) simulates e-commerce with intentional failure modes:
- Login → Search → Product → Cart → Checkout workflow
- Configurable: `CHECKOUT_FAILURE_RATE`, `MAX_LATENCY_MS`, `WEBAPP_SEED`
- All interactive elements use `data-testid` attributes for stable selectors

### Trace Format
JSONL where first line is session metadata, subsequent lines are steps:
```jsonl
{"session_id": "...", "goal": "...", "start_url": "http://webapp:3000"}
{"ts": 0, "action": "goto", "url": "..."}
{"ts": 1, "action": "click", "selector": "[data-testid='...']"}
```

### External Agent Interface
Agents implement `POST /act` receiving `{observation, tools, history, goal}` and returning `{action, args, reasoning}`.
