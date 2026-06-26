"""Minimal async pub/sub. The tuner and metadata watcher publish state-change
events; the web layer's SSE endpoint subscribes. Events are small and infrequent,
so subscriber queues are unbounded; a closed SSE connection unsubscribes via the
`events()` generator's finally block.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator


class EventBus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: Any) -> None:
        for q in list(self._subs):
            q.put_nowait(event)

    async def events(self) -> AsyncIterator[Any]:
        q = self.subscribe()
        try:
            while True:
                yield await q.get()
        finally:
            self.unsubscribe(q)
