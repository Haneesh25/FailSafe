"""WebSocket manager — pushes live events to dashboard."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import WebSocket


class EventBus:
    """Pushes events to connected WebSocket clients."""

    def __init__(self) -> None:
        self.connections: list[WebSocket] = []
        self._history: list[dict[str, Any]] = []
        self._max_history = 1000

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.append(websocket)
        # Send recent history on connect
        for event in self._history[-50:]:
            try:
                await websocket.send_json(event)
            except Exception:
                break

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def emit(self, event_type: str, data: Any) -> None:
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        disconnected: list[WebSocket] = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)
