import asyncio

from fmradiod.config import Preset
from fmradiod.display.panel import FakePanel
from fmradiod.display.renderer import TftRenderer
from fmradiod.events import EventBus

PRESETS = [Preset("KBCO", "hd", 97.3, 0), Preset("WX", "weather", 162.55), Preset("KTCL", "analog", 93.3)]


class FakeRing:
    def __init__(self, items):
        self.items = items


class FakeTuner:
    def __init__(self):
        self.ring = FakeRing(list(PRESETS))
        self.status = "acquiring"

    def snapshot(self):
        p = self.ring.items[0]
        return {"index": 0, "label": p.label, "mode": p.mode, "freq": p.freq,
                "hd_program": p.hd_program, "status": self.status}


class FakeMetadata:
    def now_playing(self):
        return {"title": None, "artist": None, "label": "KBCO", "art": None}


def _renderer(panel):
    bus = EventBus()
    # Stub render so the test never depends on real font/pixel work.
    r = TftRenderer(FakeTuner(), FakeMetadata(), bus, panel, render=lambda state, size: state)
    return r, bus


async def _wait_until(pred, timeout=1.0):
    loop = asyncio.get_event_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if pred():
            return True
        await asyncio.sleep(0.005)
    return pred()


async def test_initial_render_on_start():
    panel = FakePanel()
    r, bus = _renderer(panel)
    r.start()
    assert await _wait_until(lambda: panel.show_count == 1)
    await r.stop()
    assert panel.closed is True


async def test_event_triggers_rerender():
    panel = FakePanel()
    r, bus = _renderer(panel)
    r.start()
    assert await _wait_until(lambda: panel.show_count == 1)
    bus.publish({"type": "state"})
    assert await _wait_until(lambda: panel.show_count == 2)
    await r.stop()


async def test_burst_coalesces_to_one_render():
    panel = FakePanel()
    r, bus = _renderer(panel)
    r.start()
    assert await _wait_until(lambda: panel.show_count == 1)
    # Let the loop settle back to blocking on q.get(), then publish a burst with
    # no awaits between, so all events queue before the renderer resumes.
    await asyncio.sleep(0.02)
    before = panel.show_count
    for i in range(5):
        bus.publish({"type": "state", "n": i})
    assert await _wait_until(lambda: panel.show_count == before + 1)
    # Give it a moment to prove it does NOT render the other four.
    await asyncio.sleep(0.05)
    assert panel.show_count == before + 1
    await r.stop()


class RaisingPanel(FakePanel):
    def show(self, image):
        super().show(image)
        raise RuntimeError("SPI glitch")


async def test_blit_error_does_not_crash_renderer_or_shutdown():
    panel = RaisingPanel()
    r, bus = _renderer(panel)
    r.start()
    # show() raises every time, but run() must survive and keep consuming events.
    assert await _wait_until(lambda: panel.show_count >= 1)
    bus.publish({"type": "state"})
    assert await _wait_until(lambda: panel.show_count >= 2)
    await r.stop()  # must not re-raise the blit error during teardown
    assert panel.closed is True


async def test_stop_is_idempotent_and_closes_panel():
    panel = FakePanel()
    r, bus = _renderer(panel)
    r.start()
    assert await _wait_until(lambda: panel.show_count >= 1)
    await r.stop()
    await r.stop()  # second stop must not raise
    assert panel.closed is True
