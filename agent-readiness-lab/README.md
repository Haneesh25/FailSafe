# Agent Readiness Lab

Test AI agents safely before production by replaying realistic user interaction traces in a sandboxed web environment and scoring "helpfulness + safety".

## Features

- **Trace Replay**: Replay recorded user sessions against a toy webapp
- **Agent Testing**: Test AI agents with constrained tool API (no shell access)
- **Mutation Engine**: Deterministically perturb traces with timing jitter, misclicks, retries, etc.
- **Safety Scoring**: Track blocked harmful actions, error recovery, and success rates
- **Full Auditing**: Every agent action and system observation recorded

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) Python 3.12+ for local development

### One-Command Setup

```bash
docker compose up --build
```

This starts:
- **API**: http://localhost:8000 - FastAPI backend
- **Webapp**: http://localhost:3000 - Toy e-commerce app
- **Worker**: Background job processor with Playwright
- **Postgres**: Database for runs and traces
- **Redis**: Job queue

### Run the Demo

```bash
./scripts/demo.sh
```

Or manually:

```bash
# 1. Wait for services to be healthy
docker compose up -d
sleep 10

# 2. Ingest example traces
curl -X POST "http://localhost:8000/ingest_trace" \
  -F "file=@examples/traces/successful_checkout.jsonl"

curl -X POST "http://localhost:8000/ingest_trace" \
  -F "file=@examples/traces/search_empty_results.jsonl"

curl -X POST "http://localhost:8000/ingest_trace" \
  -F "file=@examples/traces/checkout_failure_retry.jsonl"

# 3. Run replay evaluation
curl -X POST "http://localhost:8000/run_eval" \
  -H "Content-Type: application/json" \
  -d '{"mode": "replay", "runs": 1}'

# 4. Check run status (replace RUN_ID with actual ID from step 3)
curl "http://localhost:8000/runs/RUN_ID"

# 5. View HTML report
open "http://localhost:8000/runs/RUN_ID/report"
```

## CLI Usage

Install the CLI locally:

```bash
pip install -e .
```

### Commands

```bash
# Ingest traces
arlab ingest examples/traces/*.jsonl

# List traces
arlab traces

# Run replay evaluation
arlab run --mode replay

# Run with stub agent
arlab run --mode agent

# Run with external agent
arlab run --mode agent --agent-url http://my-agent:5000

# Run with mutations
arlab run --mode replay --mutations --seed 42

# Check status
arlab status RUN_ID

# Get report
arlab report RUN_ID --format html -o report.html

# List runs
arlab runs
```

## Plugging in an External Agent

Your agent must implement a simple HTTP API:

### POST /act

Request:
```json
{
  "observation": {
    "url": "http://webapp:3000/checkout",
    "title": "Checkout",
    "dom_summary": "...",
    "visible_text": "...",
    "elements": [...],
    "error": null
  },
  "tools": [...],
  "history": [...],
  "goal": "Complete purchase of a laptop",
  "step": 5,
  "max_steps": 100
}
```

Response:
```json
{
  "action": "click",
  "args": {
    "selector": "[data-testid=\"submit-order\"]"
  },
  "reasoning": "Clicking submit to complete the order"
}
```

### Available Tools

| Tool | Parameters | Description |
|------|------------|-------------|
| `click` | `selector` | Click on an element |
| `type` | `selector`, `text` | Type text into an input |
| `goto` | `url` | Navigate to a URL |
| `wait` | `ms` | Wait (max 10000ms) |
| `read_dom` | - | Get simplified DOM structure |
| `screenshot` | - | Take a screenshot |
| `add_to_cart` | `item_id` | Domain action: add item to cart |
| `submit` | `selector` | Submit a form |
| `select` | `selector`, `value` | Select dropdown option |
| `back` | - | Go back |
| `refresh` | - | Refresh page |

**Security**: Agents cannot execute shell commands. All actions go through the constrained tool API.

## Adding New Traces

Create a JSONL file with this format:

```jsonl
{"session_id": "my_trace_001", "goal": "Complete checkout", "start_url": "http://webapp:3000", "tags": ["checkout"]}
{"ts": 0, "action": "goto", "url": "http://webapp:3000/login"}
{"ts": 1, "action": "type", "selector": "[data-testid=\"username\"]", "text": "testuser"}
{"ts": 2, "action": "click", "selector": "[data-testid=\"login-submit\"]"}
```

### Trace Format

**Session Header** (first line):
- `session_id`: Unique identifier
- `goal`: Human-readable goal
- `start_url`: Starting URL
- `expected_outcome`: (optional) Expected result
- `tags`: (optional) Array of tags

**Steps** (subsequent lines):
- `ts`: Timestamp in seconds from session start
- `action`: One of: click, type, goto, wait, submit, select, back, refresh, screenshot, read_dom, add_to_cart
- `selector`: CSS selector (for element actions)
- `text`: Text to type or select value
- `url`: URL for goto action
- `expect`: (optional) Expectations like `{"url_contains": "/success"}`
- `metadata`: (optional) Additional data like `{"wait_ms": 1000}`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ingest_trace` | POST | Upload a JSONL trace file |
| `/run_eval` | POST | Start an evaluation run |
| `/runs/{run_id}` | GET | Get run status and metrics |
| `/runs/{run_id}/report` | GET | Get HTML report |
| `/runs/{run_id}/json` | GET | Get JSON report |
| `/traces` | GET | List all traces |
| `/runs` | GET | List all runs |
| `/health` | GET | Health check |

## Metrics

| Metric | Description |
|--------|-------------|
| Success Rate | Percentage of sessions completing their goal |
| Median Time to Complete | Median duration of successful sessions |
| Error Recovery Rate | Percentage of errors that were recovered from |
| Harmful Action Blocks | Number of blocked unsafe actions |
| Tool Call Count | Total number of tool invocations |
| Abandonment Rate | Percentage of sessions abandoned (mutation-induced) |

## Toy Webapp

The included webapp simulates an e-commerce site with:

**Workflow**: Login → Search → Product → Cart → Checkout

**Failure Modes**:
- Wrong password handling
- Empty search results
- Random latency (0-500ms by default)
- Intermittent 500 errors on checkout (30% by default)
- Rate limiting after 100 requests

**Configuration** (environment variables):
- `WEBAPP_SEED`: Random seed for determinism (default: 42)
- `CHECKOUT_FAILURE_RATE`: Probability of checkout 500 (default: 0.3)
- `MAX_LATENCY_MS`: Maximum random latency (default: 500)
- `RATE_LIMIT_REQUESTS`: Requests before rate limit (default: 100)

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run specific test file
pytest tests/test_traces.py -v

# Run with coverage
pytest --cov=packages/arlab tests/
```

## Project Structure

```
agent-readiness-lab/
├── docker-compose.yml      # Service orchestration
├── apps/
│   ├── api/               # FastAPI backend
│   ├── worker/            # Playwright job runner
│   └── webapp/            # Toy e-commerce app
├── packages/
│   └── arlab/             # Shared library
│       ├── traces/        # Trace schema, parser, mutator
│       ├── harness/       # Agent harness, tools, stub agent
│       ├── replayer/      # Playwright replayer
│       ├── scoring/       # Metrics calculation
│       ├── db/            # Database models
│       └── cli/           # CLI commands
├── examples/
│   └── traces/            # Example trace files
├── migrations/            # Alembic migrations
├── tests/                 # pytest tests
└── scripts/
    └── demo.sh            # End-to-end demo
```

## License

MIT
