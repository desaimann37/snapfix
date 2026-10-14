"""In-process pub/sub for Server-Sent Events.

Sync code (FastAPI threadpool, APScheduler) calls `broker.publish(...)`; each connected dashboard gets the
event through its own asyncio queue. Single-process by design (one backend container for the demo).
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import threading
from typing import Any

log = logging.getLogger(__name__)


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: str, data: dict[str, Any]) -> None:
        msg = {"id": next(self._ids), "event": event, "data": data}
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        def _deliver() -> None:
            with self._lock:
                subscribers = list(self._subscribers)
            for q in subscribers:
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:  # slow client: drop rather than block the pipeline
                    log.warning("sse: dropping event for slow subscriber")

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            _deliver()
        else:
            loop.call_soon_threadsafe(_deliver)


broker = EventBroker()
