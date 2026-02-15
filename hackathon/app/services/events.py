"""
Server-Sent Events (SSE) manager for real-time dashboard updates.

When a new triage report is created (from phone call, text, or voice),
an event is broadcast to all connected dashboard clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from app.models.triage import TriageReport

logger = logging.getLogger(__name__)


class EventManager:
    """Manages SSE connections and broadcasts events to all listeners."""

    def __init__(self) -> None:
        self._queues: list[asyncio.Queue] = []

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Subscribe to events. Yields SSE-formatted strings."""
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.append(queue)
        logger.info("SSE client connected. Total: %d", len(self._queues))
        try:
            while True:
                data = await queue.get()
                yield data
        except asyncio.CancelledError:
            pass
        finally:
            self._queues.remove(queue)
            logger.info("SSE client disconnected. Total: %d", len(self._queues))

    async def broadcast(self, event_type: str, report: TriageReport) -> None:
        """Broadcast a triage report event to all connected clients."""
        data = json.dumps({
            "type": event_type,
            "report": report.model_dump(mode="json"),
        })
        sse_msg = f"event: {event_type}\ndata: {data}\n\n"
        for queue in list(self._queues):
            try:
                queue.put_nowait(sse_msg)
            except asyncio.QueueFull:
                logger.warning("SSE queue full, dropping event for a client.")

    async def broadcast_raw(self, event_type: str, payload: dict) -> None:
        """Broadcast a raw dict payload as SSE event."""
        data = json.dumps(payload)
        sse_msg = f"event: {event_type}\ndata: {data}\n\n"
        for queue in list(self._queues):
            try:
                queue.put_nowait(sse_msg)
            except asyncio.QueueFull:
                logger.warning("SSE queue full, dropping event for a client.")

    @property
    def client_count(self) -> int:
        return len(self._queues)


# Module-level singleton
event_manager = EventManager()
