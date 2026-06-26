"""The async task that keeps the TFT in sync with the daemon.

Subscribes to the EventBus and, on every change, re-derives the full state via
`build_state` (the same snapshot the web UI renders) and blits a fresh frame —
one render path, so the panel and the browser can never disagree. The blit runs
on a dedicated single-worker thread so SPI never blocks the audio fan-out, and
the worker serializes panel access so frames can't tear.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fmradiod.display.render import render as render_frame
from fmradiod.viewstate import build_state

log = logging.getLogger("fmradiod.display")


class TftRenderer:
    def __init__(self, tuner, metadata, bus, panel, *, render=render_frame):
        self.tuner = tuner
        self.metadata = metadata
        self.bus = bus
        self.panel = panel
        self._render = render
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tft")
        self._task = None

    def start(self) -> None:
        self._task = asyncio.ensure_future(self.run())

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        q = self.bus.subscribe()
        try:
            await self._safe_draw(loop)      # show current state before any event
            while True:
                await q.get()                # wake on a state change
                _drain(q)                    # collapse a burst into one redraw
                await self._safe_draw(loop)
        finally:
            self.bus.unsubscribe(q)

    async def _safe_draw(self, loop) -> None:
        # A bad blit (transient SPI glitch) must never kill the render loop or
        # escape into the lifespan; log and keep going.
        try:
            await self._draw(loop)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("TFT render failed", exc_info=True)

    async def _draw(self, loop) -> None:
        state = build_state(self.tuner, self.metadata)
        image = self._render(state, self.panel.size)
        # Blocking SPI flush off the event loop, serialized via the 1-worker pool.
        await loop.run_in_executor(self._executor, self.panel.show, image)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                # Cancelled (normal) or already-dead-with-error: either way we're
                # tearing down; don't let it escape the lifespan shutdown.
                pass
            self._task = None
        # close() is queued behind any in-flight blit in the single-worker pool,
        # so it runs only after the current frame finishes; then drain the pool.
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(self._executor, self.panel.close)
        except Exception:
            log.warning("TFT panel close failed", exc_info=True)
        self._executor.shutdown(wait=True)


def _drain(q: asyncio.Queue) -> None:
    """Discard any immediately-available events so a tune's burst of state +
    now_playing events collapses into a single redraw of the latest state."""
    try:
        while True:
            q.get_nowait()
    except asyncio.QueueEmpty:
        pass


def create_renderer(display_cfg, tuner, metadata, bus):
    """Build a renderer when the display is enabled, else None. A panel that
    can't initialize (no Blinka, no hardware) is logged and downgraded to None
    so the daemon keeps running headless — the screen never takes down audio."""
    if not getattr(display_cfg, "enabled", False):
        return None
    from fmradiod.display.panel import create_panel
    try:
        panel = create_panel(rotation=display_cfg.rotation, brightness=display_cfg.brightness)
    except Exception:
        log.warning("TFT display enabled but panel init failed; running headless", exc_info=True)
        return None
    return TftRenderer(tuner, metadata, bus, panel)
