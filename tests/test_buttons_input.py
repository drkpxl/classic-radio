import asyncio

from fmradiod.buttons.debounce import Debouncer
from fmradiod.buttons.input import ButtonInput, create_button_input
from fmradiod.buttons.source import FakeButtonSource
from fmradiod.config import ButtonsConfig


class RecordingTuner:
    def __init__(self):
        self.calls = []

    async def next(self):
        self.calls.append("next")

    async def prev(self):
        self.calls.append("prev")


def _input(samples, tuner=None):
    tuner = tuner or RecordingTuner()
    source = FakeButtonSource(samples)
    # stable_samples=1 so a single scripted sample commits immediately.
    bi = ButtonInput(tuner, source, debouncer=Debouncer(stable_samples=1), poll_ms=1)
    return bi, tuner, source


async def _wait_until(pred, timeout=1.0):
    loop = asyncio.get_event_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if pred():
            return True
        await asyncio.sleep(0.002)
    return pred()


def test_fake_source_exhausts_to_released():
    src = FakeButtonSource([(True, False)])
    assert src.read() == (True, False)
    assert src.read() == (False, False)   # past the script -> released forever
    assert src.read() == (False, False)


async def test_next_press_calls_tuner_next():
    bi, tuner, source = _input([(True, False)])
    bi.start()
    assert await _wait_until(lambda: tuner.calls == ["next"])
    await bi.stop()
    assert source.closed is True


async def test_prev_press_calls_tuner_prev():
    bi, tuner, source = _input([(False, True)])
    bi.start()
    assert await _wait_until(lambda: tuner.calls == ["prev"])
    await bi.stop()


async def test_held_button_calls_once():
    # Button held down across many polls -> exactly one navigation.
    bi, tuner, source = _input([(True, False)] * 20)
    bi.start()
    assert await _wait_until(lambda: tuner.calls == ["next"])
    await asyncio.sleep(0.05)               # prove it does not repeat while held
    assert tuner.calls == ["next"]
    await bi.stop()


async def test_cancellation_closes_source():
    bi, tuner, source = _input([(False, False)])
    bi.start()
    assert await _wait_until(lambda: source.read_count >= 1)
    await bi.stop()
    assert source.closed is True


async def test_stop_without_start_closes_source():
    tuner = RecordingTuner()
    source = FakeButtonSource([])
    bi = ButtonInput(tuner, source)
    await bi.stop()                          # never started; must still release GPIO
    assert source.closed is True


def test_create_button_input_disabled_returns_none():
    assert create_button_input(ButtonsConfig(enabled=False), RecordingTuner()) is None


def test_create_button_input_failsoft_when_source_init_raises(monkeypatch):
    import fmradiod.buttons.source as source_mod

    def boom(**kw):
        raise RuntimeError("no GPIO")

    monkeypatch.setattr(source_mod, "create_source", boom)
    bi = create_button_input(ButtonsConfig(enabled=True), RecordingTuner())
    assert bi is None
