"""FastAPI backend — serves dashboard + WebSocket endpoint."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from failsafe.core.engine import FailSafe

FRONTEND_DIST_DIR = Path(__file__).parent / "frontend" / "dist"


def create_app(fs: "FailSafe") -> FastAPI:
    app = FastAPI(title="FailSafe Dashboard")

    # --- WebSocket ---

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await fs.event_bus.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            fs.event_bus.disconnect(websocket)

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

    if FRONTEND_DIST_DIR.exists():
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
