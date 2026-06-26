import asyncio

import pytest

from fmradiod.audio import FanOut
from fmradiod.backends.analog import AnalogBackend
from fmradiod.backends.hd import HdBackend
from fmradiod.backends.weather import WeatherBackend
from fmradiod.config import AudioConfig, Preset, SdrConfig
from fmradiod.events import EventBus
from fmradiod.presets import Ring
from fmradiod.state import StateStore
from fmradiod.tuner import Tuner

AUDIO = AudioConfig("256k", 48000, 2)
SDR = SdrConfig("auto", 0)
BACKENDS = {"analog": AnalogBackend(), "hd": HdBackend(), "weather": WeatherBackend()}
PRESETS = [
    Preset("KBCO", "hd", 97.3, 0),
    Preset("WX", "weather", 162.55),
    Preset("KTCL", "analog", 93.3),
]


class FakeReader:
    async def read(self, n):
        return b""

    async def readline(self):
        return b""


class DataReader:
    """Yields chunks, then blocks (simulates a live stream with no EOF)."""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._blocked = asyncio.Event()

    async def read(self, n):
        if self._chunks:
            return self._chunks.pop(0)
        await self._blocked.wait()
        return b""


class FakeGroup:
    def __init__(self, pipeline, tracker, stdout=None):
        self.pipeline = pipeline
        self.tracker = tracker
        self.stopped = False
        self.stdout = stdout if stdout is not None else FakeReader()
        self.source_stderr = FakeReader()
        self._exit = asyncio.Event()
        self._code = 0

    async def wait(self):
        await self._exit.wait()
        return self._code

    def crash(self, code=1):
        self._code = code
        self._exit.set()

    async def stop(self):
        if not self.stopped:
            self.stopped = True
            self.tracker.active -= 1
            self._exit.set()


class SpawnTracker:
    def __init__(self, make_stdout=None):
        self.groups = []
        self.active = 0
        self.max_concurrent = 0
        self._make_stdout = make_stdout or (lambda: FakeReader())

    async def spawn(self, pipeline):
        self.active += 1
        self.max_concurrent = max(self.max_concurrent, self.active)
        g = FakeGroup(pipeline, self, self._make_stdout())
        self.groups.append(g)
        return g


class FakeMeta:
    def __init__(self):
        self.switches = []
        self.stops = 0

    async def switch(self, preset, group, aas_dir):
        self.switches.append((preset.mode, aas_dir))

    async def stop(self):
        self.stops += 1


def make_tuner(tmp_path, tracker, meta=None, backoff=0.0, signal_timeout=5.0):
    return Tuner(
        Ring(list(PRESETS)), AUDIO, SDR, FanOut(), EventBus(),
        StateStore(tmp_path / "state.json"),
        backends=BACKENDS, spawn=tracker.spawn, metadata=meta or FakeMeta(),
        aas_root=str(tmp_path), default_index=0, retry_backoff=backoff,
        signal_timeout=signal_timeout,
    )


async def test_tune_starts_one_backend(tmp_path):
    t = SpawnTracker()
    tuner = make_tuner(tmp_path, t)
    await tuner.tune(2)  # analog
    assert len(t.groups) == 1
    assert t.groups[0].pipeline[0][0] == "rtl_fm"
    assert tuner.index == 2
    assert tuner.current.label == "KTCL"
    await tuner.stop()


async def test_switch_stops_previous_before_starting(tmp_path):
    t = SpawnTracker()
    tuner = make_tuner(tmp_path, t)
    await tuner.tune(0)
    g0 = t.groups[0]
    await tuner.tune(2)
    assert g0.stopped is True
    assert t.max_concurrent == 1
    await tuner.stop()


async def test_rapid_concurrent_switches_serialized(tmp_path):
    t = SpawnTracker()
    tuner = make_tuner(tmp_path, t)
    await asyncio.gather(*(tuner.tune(i % 3) for i in range(5)))
    assert t.max_concurrent == 1
    assert len(t.groups) == 5
    assert sum(1 for g in t.groups if not g.stopped) == 1  # exactly one live
    await tuner.stop()


async def test_state_persisted_on_tune(tmp_path):
    t = SpawnTracker()
    tuner = make_tuner(tmp_path, t)
    await tuner.tune(2)
    assert StateStore(tmp_path / "state.json").load_index() == 2
    await tuner.stop()


async def test_resume_last_on_start(tmp_path):
    StateStore(tmp_path / "state.json").save_index(1)
    t = SpawnTracker()
    tuner = make_tuner(tmp_path, t)
    await tuner.start()
    assert tuner.index == 1
    assert len(t.groups) == 1
    await tuner.stop()


async def test_start_uses_default_when_no_state(tmp_path):
    t = SpawnTracker()
    tuner = make_tuner(tmp_path, t)
    await tuner.start()
    assert tuner.index == 0
    await tuner.stop()


async def test_next_and_prev_wrap(tmp_path):
    t = SpawnTracker()
    tuner = make_tuner(tmp_path, t)
    await tuner.tune(0)
    await tuner.prev()
    assert tuner.index == 2  # wrapped backward
    await tuner.next()
    assert tuner.index == 0  # wrapped forward
    await tuner.stop()


async def test_stop_tears_down(tmp_path):
    t = SpawnTracker()
    tuner = make_tuner(tmp_path, t)
    await tuner.tune(0)
    g0 = t.groups[0]
    await tuner.stop()
    assert g0.stopped is True
    assert t.active == 0


async def test_hd_passes_aas_dir_nonhd_passes_none(tmp_path):
    t = SpawnTracker()
    meta = FakeMeta()
    tuner = make_tuner(tmp_path, t, meta=meta)
    await tuner.tune(0)  # hd
    await tuner.tune(2)  # analog
    modes = dict(meta.switches)
    assert modes["hd"] is not None       # aas dir provided for HD
    assert modes["analog"] is None       # none for analog
    await tuner.stop()


async def test_status_acquiring_then_playing_on_first_data(tmp_path):
    t = SpawnTracker(make_stdout=lambda: DataReader([b"audio"]))
    tuner = make_tuner(tmp_path, t, signal_timeout=5.0)
    await tuner.tune(0)
    await asyncio.sleep(0.05)  # let the pump deliver the first chunk
    assert tuner.status == "playing"
    await tuner.stop()


async def test_no_signal_when_no_data_within_timeout(tmp_path):
    # default FakeReader hits EOF immediately => no audio ever flows
    t = SpawnTracker()
    tuner = make_tuner(tmp_path, t, signal_timeout=0.05)
    q = tuner.bus.subscribe()
    await tuner.tune(0)
    await asyncio.sleep(0.15)  # past the signal timeout
    assert tuner.status == "no_signal"
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    assert any(e.get("status") == "no_signal" for e in events)
    await tuner.stop()


async def test_unexpected_exit_publishes_error_and_retries(tmp_path):
    t = SpawnTracker()
    tuner = make_tuner(tmp_path, t, backoff=0.0)
    await tuner.tune(0)
    q = tuner.bus.subscribe()
    t.groups[0].crash()
    await asyncio.sleep(0.05)  # let the supervisor publish + retry
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    assert any(e.get("status") == "error" for e in events)
    assert len(t.groups) == 2          # retried with a fresh pipeline
    assert t.max_concurrent == 1
    await tuner.stop()
