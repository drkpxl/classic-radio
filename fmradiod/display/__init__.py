"""On-device TFT readout: a read-only mirror of the daemon's now-playing state on
the Adafruit Mini PiTFT 1.14" (240x135 ST7789).

Split into three seams so the bulk is testable on a Mac with no hardware:
- `render`   — pure state -> PIL.Image (and the view-model behind it)
- `panel`    — thin hardware interface (`St7789Panel`) + `FakePanel` for tests
- `renderer` — the async task that subscribes to the EventBus and blits frames

The heavy Pi-only driver stack is imported lazily inside `panel`, so importing
this package on the Mac (or a panel-less Pi) costs nothing.
"""
