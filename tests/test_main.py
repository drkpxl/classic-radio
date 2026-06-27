import textwrap

from fmradiod.__main__ import build_app
from fmradiod.config import DisplayConfig
from fmradiod.display.renderer import create_renderer


def test_build_app_wires_everything(tmp_path):
    # Uses the repo config.yaml; does not start the tuner (no lifespan here),
    # so no hardware is touched.
    app, cfg = build_app(state_path=tmp_path / "state.json", aas_root=str(tmp_path))
    assert app is not None
    assert len(cfg.presets) >= 1
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/stream.mp3" in paths
    assert "/api/state" in paths
    # The appliance config enables the display; on a panel-less box build_app
    # fail-softs to headless (covered by the dedicated test below).
    assert cfg.display.enabled is True


def _write_config(tmp_path, display_block):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(textwrap.dedent("""
    server: { host: "0.0.0.0", port: 8000 }
    sdr: { gain: "auto", ppm: 0 }
    audio: { bitrate: "256k", sample_rate: 48000, channels: 2 }
    defaults: { start_preset: 0 }
    presets:
      - { label: "KBCO", mode: hd, freq: 97.3, hd_program: 0 }
    """) + display_block)
    return cfg


def test_create_renderer_disabled_short_circuits():
    # The gate returns before touching any panel/hardware import.
    assert create_renderer(DisplayConfig(enabled=False), None, None, None) is None


def test_create_renderer_failsoft_when_panel_init_raises(monkeypatch):
    # A panel that can't initialize (no Blinka, no hardware) must downgrade to
    # None, not propagate. Monkeypatched so it's deterministic on Mac and Pi.
    import fmradiod.display.panel as panel_mod

    def boom(**kw):
        raise RuntimeError("no hardware")

    monkeypatch.setattr(panel_mod, "create_panel", boom)
    assert create_renderer(DisplayConfig(enabled=True), object(), object(), object()) is None


def test_build_app_failsoft_when_display_enabled_but_panel_fails(tmp_path, monkeypatch):
    # build_app with the display enabled must still produce a working app when
    # the panel can't init — hermetic (no real SPI), so it's green on the Pi too.
    import fmradiod.display.panel as panel_mod

    def boom(**kw):
        raise RuntimeError("no hardware")

    monkeypatch.setattr(panel_mod, "create_panel", boom)
    cfg_path = _write_config(tmp_path, "display: { enabled: true }\n")
    app, cfg = build_app(config_path=cfg_path, state_path=tmp_path / "state.json",
                         aas_root=str(tmp_path))
    assert cfg.display.enabled is True
    assert app is not None


def test_build_app_buttons_disabled_touches_no_gpio(tmp_path, monkeypatch):
    # With buttons disabled, build_app must never construct a GPIO source. Make
    # create_source explode to prove it's never reached.
    import fmradiod.buttons.source as source_mod

    def boom(**kw):
        raise AssertionError("create_source must not be called when buttons disabled")

    monkeypatch.setattr(source_mod, "create_source", boom)
    cfg_path = _write_config(tmp_path, "buttons: { enabled: false }\n")
    app, cfg = build_app(config_path=cfg_path, state_path=tmp_path / "state.json",
                         aas_root=str(tmp_path))
    assert cfg.buttons.enabled is False
    assert app is not None


def test_build_app_failsoft_when_buttons_enabled_but_source_fails(tmp_path, monkeypatch):
    # Buttons enabled but GPIO unavailable must downgrade to no-buttons, not crash.
    # Hermetic (no real GPIO), so it's green on the Pi too.
    import fmradiod.buttons.source as source_mod

    def boom(**kw):
        raise RuntimeError("no GPIO")

    monkeypatch.setattr(source_mod, "create_source", boom)
    cfg_path = _write_config(tmp_path, "buttons: { enabled: true }\n")
    app, cfg = build_app(config_path=cfg_path, state_path=tmp_path / "state.json",
                         aas_root=str(tmp_path))
    assert cfg.buttons.enabled is True
    assert app is not None


def test_build_app_bluetooth_disabled_no_controller(tmp_path, monkeypatch):
    # With bluetooth disabled, build_app must never construct a controller.
    import fmradiod.bluetooth.dbus as bt_mod

    def boom(**kw):
        raise AssertionError("must not construct controller when bluetooth disabled")

    monkeypatch.setattr(bt_mod, "create_controller", boom)
    cfg_path = _write_config(tmp_path, "bluetooth: { enabled: false }\n")
    app, cfg = build_app(config_path=cfg_path, state_path=tmp_path / "state.json",
                         aas_root=str(tmp_path))
    assert cfg.bluetooth.enabled is False
    assert app is not None


def test_build_app_failsoft_when_bluetooth_enabled_but_unavailable(tmp_path, monkeypatch):
    # Bluetooth enabled but the stack/bus is unavailable must still build a working
    # app (web output only). Hermetic, so green on the Pi too.
    import fmradiod.bluetooth.dbus as bt_mod

    def boom(**kw):
        raise RuntimeError("no dbus-fast / no bus")

    monkeypatch.setattr(bt_mod, "create_controller", boom)
    cfg_path = _write_config(tmp_path, "bluetooth: { enabled: true }\n")
    app, cfg = build_app(config_path=cfg_path, state_path=tmp_path / "state.json",
                         aas_root=str(tmp_path))
    assert cfg.bluetooth.enabled is True
    assert app is not None
