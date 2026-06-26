import textwrap

import pytest

from fmradiod.config import ConfigError, load_config


def _write(tmp_path, body):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(body))
    return p


_HEAD = """
    server: { host: "0.0.0.0", port: 8000 }
    sdr: { gain: "auto", ppm: 0 }
    audio: { bitrate: "256k", sample_rate: 48000, channels: 2 }
    defaults: { start_preset: 0 }
"""


def test_loads_valid_config(tmp_path):
    cfg = load_config(_write(tmp_path, _HEAD + """
    presets:
      - { label: "KBCO", mode: hd, freq: 97.3, hd_program: 0 }
      - { label: "Weather", mode: weather, freq: 162.550 }
      - { label: "KTCL", mode: analog, freq: 93.3 }
    """))
    assert cfg.server.host == "0.0.0.0"
    assert cfg.server.port == 8000
    assert cfg.sdr.gain == "auto"
    assert cfg.audio.sample_rate == 48000
    assert cfg.audio.channels == 2
    assert cfg.defaults.start_preset == 0
    assert len(cfg.presets) == 3
    assert cfg.presets[0].label == "KBCO"
    assert cfg.presets[0].mode == "hd"
    assert cfg.presets[0].freq == 97.3
    assert cfg.presets[0].hd_program == 0


def test_hd_without_program_defaults_to_zero(tmp_path):
    cfg = load_config(_write(tmp_path, _HEAD + """
    presets:
      - { label: "KBCO", mode: hd, freq: 97.3 }
    """))
    assert cfg.presets[0].hd_program == 0


def test_weather_without_program_ok(tmp_path):
    cfg = load_config(_write(tmp_path, _HEAD + """
    presets:
      - { label: "Weather", mode: weather, freq: 162.550 }
    """))
    assert cfg.presets[0].mode == "weather"
    assert cfg.presets[0].hd_program is None


def test_analog_program_is_none(tmp_path):
    cfg = load_config(_write(tmp_path, _HEAD + """
    presets:
      - { label: "KTCL", mode: analog, freq: 93.3 }
    """))
    assert cfg.presets[0].hd_program is None


def test_bad_mode_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + """
    presets:
      - { label: "Bad", mode: shortwave, freq: 100.0 }
    """))


def test_missing_preset_freq_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + """
    presets:
      - { label: "NoFreq", mode: analog }
    """))


def test_missing_preset_label_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + """
    presets:
      - { mode: analog, freq: 93.3 }
    """))


def test_empty_presets_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + """
    presets: []
    """))


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does-not-exist.yaml")


_PRESETS = """
    presets:
      - { label: "KBCO", mode: hd, freq: 97.3, hd_program: 0 }
"""


def test_display_defaults_when_block_absent(tmp_path):
    cfg = load_config(_write(tmp_path, _HEAD + _PRESETS))
    assert cfg.display.enabled is False
    assert cfg.display.rotation == 90
    assert cfg.display.brightness == 1.0


def test_display_block_parsed(tmp_path):
    cfg = load_config(_write(tmp_path, _HEAD + _PRESETS + """
    display: { enabled: true, rotation: 270, brightness: 0.5 }
    """))
    assert cfg.display.enabled is True
    assert cfg.display.rotation == 270
    assert cfg.display.brightness == 0.5


def test_display_bad_rotation_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + _PRESETS + """
    display: { enabled: true, rotation: 45 }
    """))


def test_display_bad_brightness_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + _PRESETS + """
    display: { enabled: true, brightness: 2.0 }
    """))


def test_display_not_a_mapping_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + _PRESETS + """
    display: "on"
    """))


def test_buttons_defaults_when_block_absent(tmp_path):
    cfg = load_config(_write(tmp_path, _HEAD + _PRESETS))
    assert cfg.buttons.enabled is False
    assert cfg.buttons.next_pin == 23
    assert cfg.buttons.prev_pin == 24
    assert cfg.buttons.debounce_ms == 25
    assert cfg.buttons.poll_ms == 20


def test_buttons_block_parsed(tmp_path):
    cfg = load_config(_write(tmp_path, _HEAD + _PRESETS + """
    buttons: { enabled: true, next_pin: 5, prev_pin: 6, debounce_ms: 40, poll_ms: 10 }
    """))
    assert cfg.buttons.enabled is True
    assert cfg.buttons.next_pin == 5
    assert cfg.buttons.prev_pin == 6
    assert cfg.buttons.debounce_ms == 40
    assert cfg.buttons.poll_ms == 10


def test_buttons_bad_pin_type_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + _PRESETS + """
    buttons: { enabled: true, next_pin: "top" }
    """))


def test_buttons_same_pin_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + _PRESETS + """
    buttons: { next_pin: 23, prev_pin: 23 }
    """))


def test_buttons_nonpositive_interval_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + _PRESETS + """
    buttons: { poll_ms: 0 }
    """))


def test_buttons_not_a_mapping_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _HEAD + _PRESETS + """
    buttons: "on"
    """))
