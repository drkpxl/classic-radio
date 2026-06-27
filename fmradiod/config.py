"""Load and validate the radio's YAML config into typed dataclasses.

Canonical source is the repo; the file is mirrored to the Pi. Validation is
deliberately plain (dataclasses + manual checks) to keep the dependency set to
just starlette / uvicorn / pyyaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

MODES = ("analog", "hd", "weather")


class ConfigError(Exception):
    """Raised when the config file is missing, unreadable, or invalid."""


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int


@dataclass(frozen=True)
class SdrConfig:
    gain: str | float
    ppm: int


@dataclass(frozen=True)
class AudioConfig:
    bitrate: str
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class Defaults:
    start_preset: int


@dataclass(frozen=True)
class DisplayConfig:
    # Optional on-device TFT readout. Off by default so the daemon runs headless
    # on the dev Mac and on any Pi without the panel attached.
    enabled: bool = False
    rotation: int = 90          # 0/90/180/270; 90 is the Mini PiTFT 1.14" landscape
    brightness: float = 1.0     # 0.0–1.0 backlight level


@dataclass(frozen=True)
class ButtonsConfig:
    # Optional on-device GPIO buttons (Mini PiTFT 1.14"). Off by default so the
    # dev Mac and any button-less Pi run unchanged. Defaults match Adafruit's
    # Mini PiTFT 1.14" wiring (GPIO #23 top, #24 bottom, active-low pull-ups).
    enabled: bool = False
    next_pin: int = 23          # BCM pin for the "next preset" button
    prev_pin: int = 24          # BCM pin for the "prev preset" button
    debounce_ms: int = 25       # stable interval a press must hold before it counts
    poll_ms: int = 20           # input-loop poll interval


@dataclass(frozen=True)
class BluetoothConfig:
    # Optional A2DP Bluetooth speaker output via BlueZ + bluez-alsa. Off by
    # default so the dev Mac (no system bus / no BlueZ) and any Pi without it
    # run unchanged. When on, the daemon manages pairing/connection over D-Bus
    # and can route audio to the connected speaker (exclusive with the web output).
    enabled: bool = False


@dataclass(frozen=True)
class Preset:
    label: str
    mode: str
    freq: float
    hd_program: int | None = None


@dataclass(frozen=True)
class Config:
    server: ServerConfig
    sdr: SdrConfig
    audio: AudioConfig
    defaults: Defaults
    presets: list[Preset]
    display: DisplayConfig = DisplayConfig()
    buttons: ButtonsConfig = ButtonsConfig()
    bluetooth: BluetoothConfig = BluetoothConfig()


def _require(mapping: dict, key: str, where: str):
    if not isinstance(mapping, dict) or key not in mapping:
        raise ConfigError(f"missing required field '{key}' in {where}")
    return mapping[key]


def _preset_from(raw: dict, index: int) -> Preset:
    where = f"presets[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a mapping")

    label = _require(raw, "label", where)
    mode = _require(raw, "mode", where)
    freq = _require(raw, "freq", where)

    if mode not in MODES:
        raise ConfigError(f"{where}: unknown mode '{mode}' (expected one of {MODES})")
    try:
        freq = float(freq)
    except (TypeError, ValueError):
        raise ConfigError(f"{where}: freq must be a number, got {freq!r}")

    if mode == "hd":
        hd_program = int(raw.get("hd_program", 0))
    else:
        hd_program = None

    return Preset(label=str(label), mode=mode, freq=freq, hd_program=hd_program)


def _display_from(raw) -> DisplayConfig:
    # The whole block is optional; missing/None keeps headless defaults.
    if raw is None:
        return DisplayConfig()
    if not isinstance(raw, dict):
        raise ConfigError("config: 'display' must be a mapping")
    try:
        rotation = int(raw.get("rotation", 90))
        brightness = float(raw.get("brightness", 1.0))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"display: bad field type: {exc}") from exc
    if rotation not in (0, 90, 180, 270):
        raise ConfigError(f"display.rotation must be one of 0/90/180/270, got {rotation}")
    if not (0.0 <= brightness <= 1.0):
        raise ConfigError(f"display.brightness must be between 0.0 and 1.0, got {brightness}")
    return DisplayConfig(enabled=bool(raw.get("enabled", False)),
                         rotation=rotation, brightness=brightness)


def _buttons_from(raw) -> ButtonsConfig:
    # The whole block is optional; missing/None keeps the buttons off.
    if raw is None:
        return ButtonsConfig()
    if not isinstance(raw, dict):
        raise ConfigError("config: 'buttons' must be a mapping")
    try:
        next_pin = int(raw.get("next_pin", 23))
        prev_pin = int(raw.get("prev_pin", 24))
        debounce_ms = int(raw.get("debounce_ms", 25))
        poll_ms = int(raw.get("poll_ms", 20))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"buttons: bad field type: {exc}") from exc
    for name, pin in (("next_pin", next_pin), ("prev_pin", prev_pin)):
        if pin < 0:
            raise ConfigError(f"buttons.{name} must be a non-negative GPIO number, got {pin}")
    if next_pin == prev_pin:
        raise ConfigError(f"buttons.next_pin and buttons.prev_pin must differ (both {next_pin})")
    for name, val in (("debounce_ms", debounce_ms), ("poll_ms", poll_ms)):
        if val <= 0:
            raise ConfigError(f"buttons.{name} must be positive, got {val}")
    return ButtonsConfig(enabled=bool(raw.get("enabled", False)),
                         next_pin=next_pin, prev_pin=prev_pin,
                         debounce_ms=debounce_ms, poll_ms=poll_ms)


def _bluetooth_from(raw) -> BluetoothConfig:
    # The whole block is optional; missing/None keeps Bluetooth off.
    if raw is None:
        return BluetoothConfig()
    if not isinstance(raw, dict):
        raise ConfigError("config: 'bluetooth' must be a mapping")
    return BluetoothConfig(enabled=bool(raw.get("enabled", False)))


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        text = path.read_text()
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")

    server_raw = _require(data, "server", "config")
    sdr_raw = _require(data, "sdr", "config")
    audio_raw = _require(data, "audio", "config")
    defaults_raw = _require(data, "defaults", "config")
    presets_raw = _require(data, "presets", "config")

    if not isinstance(presets_raw, list) or not presets_raw:
        raise ConfigError("config: 'presets' must be a non-empty list")

    presets = [_preset_from(p, i) for i, p in enumerate(presets_raw)]

    try:
        server = ServerConfig(host=str(_require(server_raw, "host", "server")),
                              port=int(_require(server_raw, "port", "server")))
        sdr = SdrConfig(gain=_require(sdr_raw, "gain", "sdr"),
                        ppm=int(_require(sdr_raw, "ppm", "sdr")))
        audio = AudioConfig(bitrate=str(_require(audio_raw, "bitrate", "audio")),
                            sample_rate=int(_require(audio_raw, "sample_rate", "audio")),
                            channels=int(_require(audio_raw, "channels", "audio")))
        defaults = Defaults(start_preset=int(_require(defaults_raw, "start_preset", "defaults")))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"config: bad field type: {exc}") from exc

    start = defaults.start_preset
    if not (0 <= start < len(presets)):
        raise ConfigError(
            f"defaults.start_preset {start} out of range for {len(presets)} presets"
        )

    display = _display_from(data.get("display"))
    buttons = _buttons_from(data.get("buttons"))
    bluetooth = _bluetooth_from(data.get("bluetooth"))

    return Config(server=server, sdr=sdr, audio=audio, defaults=defaults,
                  presets=presets, display=display, buttons=buttons, bluetooth=bluetooth)
