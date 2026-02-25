"""EventBus — pushes live events to dashboard via SSE."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any


class EventBus:
    """Pushes events to connected SSE clients via async queues."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._history: list[dict[str, Any]] = []
        self._max_history = 5000

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Create a new subscriber queue and return it."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a subscriber queue."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    @property
    def history(self) -> list[dict[str, Any]]:
        """Return recent event history."""
        return self._history[-200:]

    async def emit(self, event_type: str, data: Any) -> None:
        """Broadcast an event to all SSE subscribers."""
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        dead: list[asyncio.Queue] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead.append(queue)

        for q in dead:
            self.unsubscribe(q)
