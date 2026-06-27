"""Daemon entrypoint: wire config -> ring -> tuner -> web app, then serve.

Run with `python -m fmradiod` (from /root/fmradio on the Pi). uvicorn installs
SIGTERM/SIGINT handlers and runs the app lifespan, so systemd `stop` triggers a
clean tuner teardown (no orphaned rtl_fm/nrsc5).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import uvicorn

from fmradiod.audio import FanOut
from fmradiod.backends.analog import AnalogBackend
from fmradiod.backends.hd import HdBackend
from fmradiod.backends.weather import WeatherBackend
from fmradiod.config import load_config
from fmradiod.events import EventBus
from fmradiod.metadata import Metadata
from fmradiod.presets import Ring
from fmradiod.state import StateStore
from fmradiod.tuner import Tuner
from fmradiod.web.app import create_app

_PKG = Path(__file__).resolve().parent
_REPO = _PKG.parent


def build_app(config_path=None, state_path=None, aas_root=None):
    config_path = config_path or os.environ.get("FMRADIO_CONFIG") or (_REPO / "config.yaml")
    state_path = state_path or os.environ.get("FMRADIO_STATE") or (_REPO / "state.json")
    aas_root = aas_root or os.environ.get("FMRADIO_AAS_ROOT") or "/tmp"

    cfg = load_config(config_path)
    bus = EventBus()
    fanout = FanOut()
    metadata = Metadata(bus)
    tuner = Tuner(
        Ring(cfg.presets),
        cfg.audio,
        cfg.sdr,
        fanout,
        bus,
        StateStore(state_path),
        backends={"analog": AnalogBackend(), "hd": HdBackend(), "weather": WeatherBackend()},
        metadata=metadata,
        aas_root=aas_root,
        default_index=cfg.defaults.start_preset,
    )

    # Optional on-device TFT readout. The display package pulls in Pi-only deps
    # (Pillow, Blinka), so import it ONLY when enabled; any failure (deps absent,
    # no panel) degrades to headless rather than taking down the daemon.
    renderer = None
    if cfg.display.enabled:
        try:
            from fmradiod.display.renderer import create_renderer
            renderer = create_renderer(cfg.display, tuner, metadata, bus)
        except Exception:
            logging.getLogger("fmradiod.display").warning(
                "TFT display enabled but unavailable; running headless", exc_info=True)

    # Optional on-device GPIO buttons → preset next/prev. Reuses the Blinka stack
    # the display pulls in, so no new deps; gated + fail-soft like the display so
    # the Mac and any button-less Pi run unchanged.
    button_input = None
    if cfg.buttons.enabled:
        try:
            from fmradiod.buttons.input import create_button_input
            button_input = create_button_input(cfg.buttons, tuner)
        except Exception:
            logging.getLogger("fmradiod.buttons").warning(
                "buttons enabled but unavailable; running without buttons", exc_info=True)

    # Optional A2DP Bluetooth speaker output. The D-Bus stack is imported lazily
    # inside the controller's start() (in the lifespan), so construction here is
    # bus-free; a true failure surfaces fail-soft at start() → web output only.
    bluetooth = None
    if cfg.bluetooth.enabled:
        try:
            from fmradiod.bluetooth.dbus import create_controller
            bluetooth = create_controller()
        except Exception:
            logging.getLogger("fmradiod.bluetooth").warning(
                "bluetooth enabled but unavailable; web output only", exc_info=True)

    app = create_app(tuner, fanout, metadata, bus, str(_PKG / "web" / "static"),
                     renderer=renderer, button_input=button_input, bluetooth=bluetooth)
    return app, cfg


def main():
    app, cfg = build_app()
    # Long-lived streams (audio + SSE) would otherwise block graceful shutdown
    # forever; cap it so SIGTERM (systemd stop) force-closes them promptly and
    # the tuner teardown runs (no orphaned rtl_fm/nrsc5).
    uvicorn.run(
        app,
        host=cfg.server.host,
        port=cfg.server.port,
        log_level="info",
        timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    main()
