"""FastAPI backend — serves dashboard + SSE stream endpoint."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from failsafe.core.engine import FailSafe

FRONTEND_DIST_DIR = Path(__file__).parent / "frontend" / "dist"


def create_app(fs: "FailSafe") -> FastAPI:
    app = FastAPI(title="FailSafe Dashboard")

    # --- SSE Stream ---

    @app.get("/api/stream")
    async def sse_stream(request: Request):
        queue = fs.event_bus.subscribe()

        async def event_generator():
            # Send recent history first
            for event in fs.event_bus.history:
                yield {"data": json.dumps(event)}

            # Then stream live events
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield {"data": json.dumps(event)}
                    except asyncio.TimeoutError:
                        # Send keepalive comment
                        yield {"comment": "keepalive"}
            finally:
                fs.event_bus.unsubscribe(queue)

        return EventSourceResponse(event_generator())

    # --- REST API ---

    @app.get("/api/agents")
    async def get_agents():
        agents = fs.registry.list_all()
        return [a.model_dump() for a in agents]

    @app.get("/api/contracts")
    async def get_contracts():
        contracts = fs.contracts.list_all()
        return [c.model_dump() for c in contracts]

    @app.get("/api/coverage")
    async def get_coverage():
        return fs.contracts.coverage_matrix()

    @app.get("/api/validations")
    async def get_validations(
        source: str | None = None,
        target: str | None = None,
        passed: bool | None = None,
        trace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        return await fs.audit_log.query(
            source=source,
            target=target,
            passed=passed,
            trace_id=trace_id,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/violations/{validation_id}")
    async def get_violations(validation_id: int):
        return await fs.audit_log.get_violations(validation_id)

    @app.get("/api/handoffs/recent")
    async def get_recent_handoffs(limit: int = 50):
        """Get recent handoffs with payload data from event bus history."""
        events = fs.event_bus.history[-limit:]
        return [
            {
                "source": e["data"].get("source"),
                "target": e["data"].get("target"),
                "passed": e["data"].get("passed"),
                "payload": e["data"].get("payload"),
                "payload_preview": e["data"].get("payload_preview"),
                "payload_keys": e["data"].get("payload_keys"),
                "violations": e["data"].get("violations", []),
                "timestamp": e["data"].get("timestamp"),
                "trace_id": e["data"].get("trace_id"),
            }
            for e in events
            if e.get("type") == "validation"
        ]

    @app.get("/api/handoffs/{trace_id}")
    async def get_handoff_detail(trace_id: str):
        """Get full handoff details for a specific trace ID."""
        for e in reversed(fs.event_bus._history):
            if e.get("type") == "validation" and e["data"].get("trace_id") == trace_id:
                return e["data"]
        return {"error": "Not found"}

    @app.get("/api/graph")
    async def get_graph():
        agents = fs.registry.list_all()
        contracts = fs.contracts.list_all()
        nodes = [
            {"id": a.name, "label": a.name, "data": a.model_dump()} for a in agents
        ]
        edges = [
            {
                "id": c.name,
                "source": c.source,
                "target": c.target,
                "label": c.name,
                "data": c.model_dump(),
            }
            for c in contracts
        ]
        return {"nodes": nodes, "edges": edges}

    # --- Static files (React frontend) ---

    if FRONTEND_DIST_DIR.exists() and (FRONTEND_DIST_DIR / "assets").exists():
        app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_DIST_DIR / "assets"),
            name="assets",
        )

        @app.get("/{path:path}")
        async def serve_frontend(path: str = ""):
            index = FRONTEND_DIST_DIR / "index.html"
            if index.exists():
                return FileResponse(index)
            return JSONResponse(
                {"message": "Dashboard frontend not built. Run: cd failsafe/dashboard/frontend && npm run build"},
                status_code=404,
            )
    else:

        @app.get("/")
        async def no_frontend():
            return JSONResponse(
                {"message": "Dashboard frontend not built. Run: cd failsafe/dashboard/frontend && npm run build"},
                status_code=404,
            )

    return app
