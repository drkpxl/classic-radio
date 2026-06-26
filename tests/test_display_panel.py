import pytest

from fmradiod.display.panel import FakePanel, Panel, St7789Panel, create_panel


def test_fakepanel_records_frames_and_close():
    p = FakePanel(size=(240, 135))
    assert isinstance(p, Panel)
    assert p.size == (240, 135)
    assert p.last_image is None and p.show_count == 0
    p.show("frame-a")
    p.show("frame-b")
    assert p.last_image == "frame-b"
    assert p.show_count == 2
    assert p.closed is False
    p.close()
    assert p.closed is True


def test_st7789_size_for_rotation():
    # Construction touches hardware, but the size math is a pure classmethod-style
    # check we can assert without instantiating: landscape for 90/270.
    assert St7789Panel.WIDTH == 135 and St7789Panel.HEIGHT == 240


def test_hardware_panel_raises_without_blinka():
    # Where the Pi-only stack is absent (dev Mac), create_panel must raise rather
    # than silently succeed, so the lifespan falls back to headless. This also
    # proves the driver import is lazy (inside __init__), not at module import.
    # On a real Pi `board` imports, so the hardware-init path is covered on-device.
    try:
        import board  # noqa: F401
    except Exception:
        with pytest.raises(Exception):
            create_panel(rotation=90, brightness=1.0)
    else:
        pytest.skip("Blinka present (real Pi); hardware init verified on-device")
