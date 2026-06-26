"""The arbiter — owns the single SDR and is the source of truth for what's playing.

`tune()` is serialized behind a lock so concurrent requests can never run two
backend pipelines at once: the current pipeline is fully torn down before the new
one starts. A per-pipeline supervisor watches for unexpected exits and retries
with backoff. State is persisted on every tune so the daemon resumes on boot.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from fmradiod.process import spawn_pipeline


class Tuner:
    def __init__(
        self,
        ring,
        audio,
        sdr,
        fanout,
        bus,
        state,
        *,
        backends,
        spawn=spawn_pipeline,
        metadata=None,
        aas_root="/tmp",
        default_index=0,
        retry_backoff=2.0,
        max_retries=3,
        signal_timeout=8.0,
    ):
        self.ring = ring
        self.audio = audio
        self.sdr = sdr
        self.fanout = fanout
        self.bus = bus
        self.state = state
        self.backends = backends
        self._spawn = spawn
        self._metadata = metadata
        self._aas_root = aas_root
        self._default_index = default_index
        self._retry_backoff = retry_backoff
        self._max_retries = max_retries
        self._signal_timeout = signal_timeout

        self._lock = asyncio.Lock()
        self._group = None
        self._pump_task = None
        self._stderr_task = None
        self._supervisor = None
        self._signal_task = None
        self._aas_dir = None
        self.status = "stopped"

    # ----- read-only state -----
    @property
    def index(self) -> int:
        return self.ring.index

    @property
    def current(self):
        return self.ring.current

    def snapshot(self) -> dict:
        p = self.current
        return {
            "type": "state",
            "index": self.ring.index,
            "label": p.label,
            "mode": p.mode,
            "freq": p.freq,
            "hd_program": p.hd_program,
            "status": self.status,
        }

    # ----- control -----
    async def start(self) -> None:
        index = self.state.load_index(default=self._default_index, count=len(self.ring))
        await self.tune(index)

    async def next(self) -> None:
        await self.tune((self.ring.index + 1) % len(self.ring))

    async def prev(self) -> None:
        await self.tune((self.ring.index - 1) % len(self.ring))

    async def tune(self, index: int, _attempt: int = 0) -> None:
        async with self._lock:
            await self._teardown()
            preset = self.ring.get(index)
            backend = self.backends[preset.mode]

            aas_dir = None
            if preset.mode == "hd":
                aas_dir = tempfile.mkdtemp(prefix="aas-", dir=self._aas_root)
            self._aas_dir = aas_dir

            pipeline = backend.build_command(preset, self.audio, self.sdr, aas_dir)
            group = await self._spawn(pipeline)
            self._group = group

            first_data = asyncio.Event()
            self._pump_task = asyncio.ensure_future(
                self.fanout.pump(group.stdout, on_first=first_data.set)
            )

            if self._metadata is not None:
                await self._metadata.switch(preset, group, aas_dir)
            else:
                self._stderr_task = asyncio.ensure_future(self._drain(group.source_stderr))

            self.status = "acquiring"
            self.state.save_index(index)
            self.bus.publish(self.snapshot())
            self._supervisor = asyncio.ensure_future(self._supervise(group, index, _attempt))
            self._signal_task = asyncio.ensure_future(self._watch_signal(group, first_data))

    async def stop(self) -> None:
        async with self._lock:
            await self._teardown()
            self.status = "stopped"

    # ----- internals -----
    async def _supervise(self, group, index: int, attempt: int) -> None:
        try:
            await group.wait()
        except asyncio.CancelledError:
            return
        if group.stopped or group is not self._group:
            return  # intentional teardown / superseded
        # Unexpected exit.
        self.status = "error"
        self.bus.publish(self.snapshot())
        if attempt < self._max_retries:
            if self._retry_backoff:
                await asyncio.sleep(self._retry_backoff)
            await self.tune(index, _attempt=attempt + 1)

    async def _watch_signal(self, group, first_data) -> None:
        """If no audio arrives within the timeout, surface a no-signal status."""
        try:
            await asyncio.wait_for(first_data.wait(), timeout=self._signal_timeout)
        except asyncio.TimeoutError:
            if group is self._group and self.status == "acquiring":
                self.status = "no_signal"
                self.bus.publish(self.snapshot())
            return
        # First audio arrived — we have signal.
        if group is self._group and self.status in ("acquiring", "no_signal"):
            self.status = "playing"
            self.bus.publish(self.snapshot())

    async def _teardown(self) -> None:
        # Exclude the current task: a retrying supervisor calls tune() -> _teardown
        # and must not cancel/await itself.
        current = asyncio.current_task()
        pending = []
        for task in (self._supervisor, self._pump_task, self._stderr_task, self._signal_task):
            if task is not None and task is not current:
                task.cancel()
                pending.append(task)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._supervisor = self._pump_task = self._stderr_task = self._signal_task = None

        if self._metadata is not None:
            await self._metadata.stop()
        if self._group is not None:
            await self._group.stop()
            self._group = None
        if self._aas_dir:
            shutil.rmtree(self._aas_dir, ignore_errors=True)
            self._aas_dir = None

    @staticmethod
    async def _drain(reader) -> None:
        if reader is None:
            return
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
