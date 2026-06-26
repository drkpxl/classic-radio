"""The async task that turns button presses into preset navigation.

It polls the `ButtonSource` on a fixed interval, feeds each sample through the
pure `Debouncer`, and on a committed press edge awaits `tuner.next()` /
`tuner.prev()`. The daemon stays the single source of truth — the web UI and the
TFT mirror the change via the existing EventBus, so this task touches neither.

Reads are cheap, non-blocking GPIO reads (microseconds), so — unlike the panel's
SPI blit — they run inline on the event loop with no executor. Because a press
awaits the (lock-serialized) tune, presses arriving mid-tune simply aren't
sampled until it returns: the loop drops the firehose rather than queuing a
backlog of tunes.
"""

from __future__ import annotations

import asyncio
import logging

from fmradiod.buttons.debounce import NEXT, PREV, Debouncer, stable_samples_for

log = logging.getLogger("fmradiod.buttons")


class ButtonInput:
    def __init__(self, tuner, source, *, debounce_ms: int = 25, poll_ms: int = 20,
                 debouncer: Debouncer | None = None):
        self.tuner = tuner
        self.source = source
        self._poll = poll_ms / 1000.0
        self._debouncer = debouncer or Debouncer(stable_samples_for(debounce_ms, poll_ms))
        self._task = None

    def start(self) -> None:
        self._task = asyncio.ensure_future(self.run())

    async def run(self) -> None:
        try:
            while True:
                # A bad read or a failed tune must never kill the input loop.
                try:
                    next_pressed, prev_pressed = self.source.read()
                    for action in self._debouncer.update(next_pressed, prev_pressed):
                        await self._dispatch(action)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.warning("button poll failed", exc_info=True)
                await asyncio.sleep(self._poll)
        finally:
            self.source.close()

    async def _dispatch(self, action: str) -> None:
        if action == NEXT:
            await self.tuner.next()
        elif action == PREV:
            await self.tuner.prev()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                # Cancelled (normal) or died-with-error: we're tearing down either
                # way; the run() finally has already closed the source.
                pass
            self._task = None
        else:
            # Never started but we still own the source — release it.
            self.source.close()


def create_button_input(buttons_cfg, tuner):
    """Build a button-input task when buttons are enabled, else None. A source
    that can't initialize (no Blinka, no hardware, contended pin) is logged and
    downgraded to None so the daemon keeps running without buttons — input
    hardware never takes down audio (mirrors `create_renderer`)."""
    if not getattr(buttons_cfg, "enabled", False):
        return None
    from fmradiod.buttons.source import create_source
    try:
        source = create_source(next_pin=buttons_cfg.next_pin, prev_pin=buttons_cfg.prev_pin)
    except Exception:
        log.warning("buttons enabled but GPIO init failed; running without buttons", exc_info=True)
        return None
    return ButtonInput(tuner, source,
                       debounce_ms=buttons_cfg.debounce_ms, poll_ms=buttons_cfg.poll_ms)
