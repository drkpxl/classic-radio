"""MP3 fan-out — broadcast one encoder's output to many HTTP listeners.

One encoder regardless of listener count (the proven spike pattern, made async).
Each client gets a bounded queue; a client that can't keep up has its oldest data
dropped (and is eventually disconnected by the web layer) so it never blocks the
encoder or other listeners. The fan-out is source-agnostic: `pump()` can be called
with a new source across a preset switch and registered clients keep receiving.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator


class Client:
    def __init__(self, maxsize: int):
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def put(self, chunk: bytes) -> None:
        try:
            self.queue.put_nowait(chunk)
        except asyncio.QueueFull:
            try:
                self.queue.get_nowait()  # drop oldest
                self.dropped += 1
            except asyncio.QueueEmpty:
                pass
            try:
                self.queue.put_nowait(chunk)
            except asyncio.QueueFull:
                pass


class FanOut:
    def __init__(self, maxsize: int = 256, chunk_size: int = 4096):
        self._clients: set[Client] = set()
        self._maxsize = maxsize
        self._chunk_size = chunk_size

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def register(self) -> Client:
        client = Client(self._maxsize)
        self._clients.add(client)
        return client

    def unregister(self, client: Client) -> None:
        self._clients.discard(client)

    def broadcast(self, chunk: bytes) -> None:
        for client in list(self._clients):
            client.put(chunk)

    async def stream(self) -> AsyncIterator[bytes]:
        """Async generator for one HTTP client; unregisters on close/disconnect."""
        client = self.register()
        try:
            while True:
                yield await client.queue.get()
        finally:
            self.unregister(client)

    async def pump(self, reader, on_first=None) -> None:
        """Read chunks from an async reader until EOF, broadcasting each.

        `on_first` (if given) is called once, when the first chunk arrives — used
        by the tuner to know a backend actually produced audio (signal lock).
        """
        first = True
        while True:
            chunk = await reader.read(self._chunk_size)
            if not chunk:
                break
            if first:
                if on_first is not None:
                    on_first()
                first = False
            self.broadcast(chunk)
