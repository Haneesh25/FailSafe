# CLAUDE.md

This file provides guidance to Claude Code when working in the BrowserScale monorepo.

## Repository Overview

BrowserScale is a monorepo with two contributors containing multiple projects focused on AI agent testing, validation, and infrastructure.

## Projects

### `agent-readiness-lab/` — Agent Testing Sandbox

Test AI agents safely before production by replaying realistic user interaction traces in a sandboxed web environment and scoring their helpfulness + safety.

- **Stack**: FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, RQ, Playwright, Docker Compose
- **Services**: API (port 8000), Worker (Playwright runner), Toy Webapp (port 3000, e-commerce sim)
- **Key concepts**: JSONL traces, constrained tool API (no shell), deterministic mutations, StubAgent vs ExternalAgent
- **See**: `agent-readiness-lab/CLAUDE.md` for detailed build/run/architecture docs

### `failsafe-pip-package/` — Contract Validation Framework

Contract testing and compliance validation for multi-agent AI systems. Validates agent outputs against contracts and policies using deterministic checks and LLM-based judgment.

- **Stack**: Python 3.10+, Pydantic, FastAPI, SQLite (audit), React 18 + Vite + @xyflow/react (dashboard)
- **Key concepts**: Contracts, policy packs, LLM judge (Cerebras), audit trail, warn/block modes
- **Integrations**: LangChain callbacks, LangGraph, `@validated_tool` decorator
- **Run**: `pip install -e ".[dev]"`, `pytest tests/`, dashboard via `failsafe dashboard`

### `web/` — FailSafe Marketing Website (submodule)

Marketing landing page for **FailSafe by PhT Labs**. Swiss minimalist design (Anduril-inspired).

- **Stack**: React 18, Vite, TypeScript, Tailwind CSS v4, react-icons (Heroicons v2)
- **Submodule remote**: `https://github.com/andyjphu/failsafe.git`
- **Run**: `cd web && npm install && npm run dev` (localhost:5173)
- **Sections**: Navbar, Hero, Video Demo placeholder, Install/Code example, Features grid, How It Works, Footer

## Repository Structure

- **Product**: FailSafe is the product, designed by PhT Labs
- `web/` and `failsafe-pip-package/` are **separate submodules** with their own git repos
- `agent-readiness-lab/` is a regular directory in this repo

## Working in This Repo

- `web/` is a **git submodule** — commits inside it go to `andyjphu/failsafe`, not this repo. After committing in `web/`, update the submodule reference in the parent repo separately.
- Each project is self-contained with its own dependencies and tooling
- Navigate to the specific project directory before running commands
- Check each project's own CLAUDE.md or README for project-specific instructions
