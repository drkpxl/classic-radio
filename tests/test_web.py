import asyncio
import json
import time

from starlette.testclient import TestClient


async def asgi_response_start(app, path):
    """Drive the ASGI app directly: capture response headers, then disconnect.

    Avoids client-side body buffering, so it works on infinite streaming
    endpoints (stream.mp3 / SSE) that block on their body forever.
    """
    scope = {
        "type": "http", "method": "GET", "path": path,
        "raw_path": path.encode(), "query_string": b"", "headers": [],
    }
    captured = {}
    started = asyncio.Event()

    async def receive():
        await started.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = {k.decode(): v.decode() for k, v in message["headers"]}
            started.set()

    task = asyncio.ensure_future(app(scope, receive, send))
    await asyncio.wait_for(started.wait(), 5)
    try:
        await asyncio.wait_for(task, 5)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        task.cancel()
    return captured["status"], captured["headers"]

from fmradiod.audio import FanOut
from fmradiod.backends.analog import AnalogBackend
from fmradiod.backends.hd import HdBackend
from fmradiod.backends.weather import WeatherBackend
from fmradiod.config import AudioConfig, Preset, SdrConfig
from fmradiod.events import EventBus
from fmradiod.metadata import Metadata
from fmradiod.presets import Ring
from fmradiod.state import StateStore
from fmradiod.tuner import Tuner
from fmradiod.web.app import build_state, create_app, format_sse

PRESETS = [Preset("KBCO", "hd", 97.3, 0), Preset("WX", "weather", 162.55), Preset("KTCL", "analog", 93.3)]
BACKENDS = {"analog": AnalogBackend(), "hd": HdBackend(), "weather": WeatherBackend()}


class FakeReader:
    async def read(self, n):
        return b""

    async def readline(self):
        return b""


class FakeGroup:
    def __init__(self):
        self.stdout = FakeReader()
        self.source_stderr = FakeReader()
        self.stopped = False

    async def wait(self):
        await asyncio.Event().wait()  # never exits on its own

    async def stop(self):
        self.stopped = True


async def fake_spawn(pipeline):
    return FakeGroup()


def build(tmp_path):
    bus = EventBus()
    fanout = FanOut()
    metadata = Metadata(bus)
    tuner = Tuner(
        Ring(list(PRESETS)), AudioConfig("256k", 48000, 2), SdrConfig("auto", 0),
        fanout, bus, StateStore(tmp_path / "state.json"),
        backends=BACKENDS, spawn=fake_spawn, metadata=metadata, aas_root=str(tmp_path),
    )
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>radio</html>")
    app = create_app(tuner, fanout, metadata, bus, str(static))
    return app, tuner, metadata


def build_bt(tmp_path, seed=None, discoverable=None):
    from fmradiod.bluetooth.controller import FakeBluetoothController
    bus = EventBus()
    fanout = FanOut()
    metadata = Metadata(bus)
    tuner = Tuner(
        Ring(list(PRESETS)), AudioConfig("256k", 48000, 2), SdrConfig("auto", 0),
        fanout, bus, StateStore(tmp_path / "state.json"),
        backends=BACKENDS, spawn=fake_spawn, metadata=metadata, aas_root=str(tmp_path),
    )
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>radio</html>")
    ctrl = FakeBluetoothController(seed=seed, discoverable=discoverable)
    app = create_app(tuner, fanout, metadata, bus, str(static), bluetooth=ctrl)
    return app, tuner, ctrl


BT_SEED = [{"mac": "AA:1", "name": "Echo", "paired": True, "connected": False}]


def test_bt_disabled_state_and_endpoints(tmp_path):
    app, _, _ = build(tmp_path)  # no controller
    with TestClient(app) as c:
        assert c.get("/api/state").json()["bluetooth"]["enabled"] is False
        assert c.get("/api/state").json()["output"] == "web"
        assert c.post("/api/bt/scan/on").status_code == 409


def test_bt_scan_surfaces_devices(tmp_path):
    app, _, _ = build_bt(tmp_path, discoverable=[{"mac": "BB:2", "name": "JBL", "paired": False, "connected": False}])
    with TestClient(app) as c:
        c.post("/api/bt/scan/on")
        s = c.get("/api/state").json()
        assert s["bluetooth"]["scanning"] is True
        assert any(d["mac"] == "BB:2" for d in s["bluetooth"]["devices"])


def test_bt_connect_switches_output_and_back(tmp_path):
    app, tuner, ctrl = build_bt(tmp_path, seed=BT_SEED)
    with TestClient(app) as c:
        s = c.get("/api/state").json()
        assert s["bluetooth"]["enabled"] is True
        assert [d["mac"] for d in s["bluetooth"]["devices"]] == ["AA:1"]
        r = c.post("/api/bt/connect/AA:1").json()
        assert r["bluetooth"]["connected"] == "AA:1"
        assert r["output"] == "bluetooth"
        r2 = c.post("/api/bt/disconnect/AA:1").json()
        assert r2["output"] == "web"
        assert r2["bluetooth"]["connected"] is None


def test_output_bluetooth_without_device_conflicts(tmp_path):
    app, _, _ = build_bt(tmp_path)  # no devices connected
    with TestClient(app) as c:
        assert c.post("/api/output/bluetooth").status_code == 409


def test_bluetooth_output_restored_on_startup(tmp_path):
    # Persisted output=bluetooth + last_device + a connected speaker → the lifespan
    # restores bluetooth output on boot.
    from fmradiod.bluetooth.controller import FakeBluetoothController
    st = StateStore(tmp_path / "state.json")
    st.save_output("bluetooth")
    st.save_device("AA:1")
    bus = EventBus()
    fanout = FanOut()
    metadata = Metadata(bus)
    tuner = Tuner(
        Ring(list(PRESETS)), AudioConfig("256k", 48000, 2), SdrConfig("auto", 0),
        fanout, bus, st, backends=BACKENDS, spawn=fake_spawn, metadata=metadata,
        aas_root=str(tmp_path),
    )
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>radio</html>")
    ctrl = FakeBluetoothController(seed=[{"mac": "AA:1", "name": "Echo", "paired": True, "connected": True}])
    app = create_app(tuner, fanout, metadata, bus, str(static), bluetooth=ctrl)
    with TestClient(app) as c:
        s = c.get("/api/state").json()
        assert s["output"] == "bluetooth"
        assert s["bluetooth"]["connected"] == "AA:1"


def test_bluetooth_start_failure_is_failsoft(tmp_path):
    # If the controller can't start (bus down), the lifespan must log + continue;
    # the daemon serves web normally and tuning still works.
    from fmradiod.bluetooth.controller import FakeBluetoothController

    class BoomController(FakeBluetoothController):
        async def start(self):
            raise RuntimeError("bus down")

    bus = EventBus()
    fanout = FanOut()
    metadata = Metadata(bus)
    tuner = Tuner(
        Ring(list(PRESETS)), AudioConfig("256k", 48000, 2), SdrConfig("auto", 0),
        fanout, bus, StateStore(tmp_path / "state.json"),
        backends=BACKENDS, spawn=fake_spawn, metadata=metadata, aas_root=str(tmp_path),
    )
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>radio</html>")
    app = create_app(tuner, fanout, metadata, bus, str(static), bluetooth=BoomController())
    with TestClient(app) as c:
        assert c.get("/api/state").status_code == 200
        assert c.post("/api/tune/2").json()["preset"]["index"] == 2  # daemon still works


def test_state_shape(tmp_path):
    app, tuner, md = build(tmp_path)
    with TestClient(app) as c:
        s = c.get("/api/state").json()
    assert s["preset"]["index"] == 0
    assert s["preset"]["label"] == "KBCO"
    assert s["status"] in ("acquiring", "playing", "no_signal")
    assert len(s["ring"]) == 3
    assert s["ring"][2]["label"] == "KTCL"
    assert "now_playing" in s


def test_tune_endpoint(tmp_path):
    app, tuner, md = build(tmp_path)
    with TestClient(app) as c:
        r = c.post("/api/tune/2")
        assert r.status_code == 200
        assert r.json()["preset"]["index"] == 2
        assert tuner.index == 2


def test_next_and_prev_endpoints(tmp_path):
    app, tuner, md = build(tmp_path)
    with TestClient(app) as c:
        c.post("/api/tune/0")
        assert c.post("/api/next").json()["preset"]["index"] == 1
        assert c.post("/api/prev").json()["preset"]["index"] == 0


def test_tune_bad_index_404(tmp_path):
    app, _, _ = build(tmp_path)
    with TestClient(app) as c:
        assert c.post("/api/tune/99").status_code == 404


async def test_stream_headers(tmp_path):
    app, _, _ = build(tmp_path)
    status, headers = await asgi_response_start(app, "/stream.mp3")
    assert status == 200
    assert headers["content-type"].startswith("audio/mpeg")


async def test_events_headers(tmp_path):
    app, _, _ = build(tmp_path)
    status, headers = await asgi_response_start(app, "/api/events")
    assert status == 200
    assert headers["content-type"].startswith("text/event-stream")


def test_art_404_when_none(tmp_path):
    app, _, md = build(tmp_path)
    with TestClient(app) as c:
        assert c.get("/art/current").status_code == 404


def test_art_served_when_present(tmp_path):
    app, _, md = build(tmp_path)
    art = tmp_path / "art.jpg"
    art.write_bytes(b"\xff\xd8\xff\xffjpgdata")
    with TestClient(app) as c:
        md.art_path = str(art)  # set after startup (switch() resets it during start)
        r = c.get("/art/current")
        assert r.status_code == 200
        assert r.content.startswith(b"\xff\xd8")


def test_index_served(tmp_path):
    app, _, _ = build(tmp_path)
    with TestClient(app) as c:
        r = c.get("/")
    assert r.status_code == 200
    assert "radio" in r.text


def test_format_sse():
    out = format_sse({"type": "state", "index": 1})
    assert out.startswith("data: ")
    assert out.endswith("\n\n")
    assert json.loads(out[6:].strip()) == {"type": "state", "index": 1}


def test_build_state_lifted_to_viewstate():
    # web.app re-exports the lifted build_state; both names are the same object so
    # the web UI and the TFT renderer can never derive different state.
    from fmradiod import viewstate
    from fmradiod.web import app as webapp
    assert webapp.build_state is viewstate.build_state


def test_button_press_advances_preset_and_lifespan_cleans_up(tmp_path):
    # End-to-end through the real lifespan (fake-spawn tuner, fake GPIO source):
    # the lifespan starts the button task, a scripted press advances the ring,
    # and shutdown stops the task + releases the GPIO source.
    from fmradiod.buttons.debounce import Debouncer
    from fmradiod.buttons.input import ButtonInput
    from fmradiod.buttons.source import FakeButtonSource

    bus = EventBus()
    fanout = FanOut()
    metadata = Metadata(bus)
    tuner = Tuner(
        Ring(list(PRESETS)), AudioConfig("256k", 48000, 2), SdrConfig("auto", 0),
        fanout, bus, StateStore(tmp_path / "state.json"),
        backends=BACKENDS, spawn=fake_spawn, metadata=metadata, aas_root=str(tmp_path),
    )
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>radio</html>")

    source = FakeButtonSource([(True, False)])  # one "next" press, then released
    button_input = ButtonInput(tuner, source, debouncer=Debouncer(stable_samples=1), poll_ms=5)
    app = create_app(tuner, fanout, metadata, bus, str(static), button_input=button_input)

    with TestClient(app) as c:
        # The lifespan started at index 0; the scripted press should advance once.
        deadline = time.time() + 2.0
        while tuner.index == 0 and time.time() < deadline:
            time.sleep(0.02)
        assert tuner.index == 1
    # Lifespan shutdown must have stopped the task and released the GPIO source.
    assert source.closed is True
