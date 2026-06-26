"""The hardware seam: a tiny `Panel` interface so the renderer never touches the
SPI driver directly.

`FakePanel` records frames for tests (runs anywhere). `St7789Panel` drives the
real Mini PiTFT 1.14" and lazy-imports the Pi-only Blinka/`adafruit_rgb_display`
stack inside `__init__`, so importing this module on the Mac costs nothing and
never fails for want of hardware libraries.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Panel(ABC):
    @property
    @abstractmethod
    def size(self) -> tuple:
        """(width, height) of the frame `show()` expects, in pixels."""

    @abstractmethod
    def show(self, image) -> None:
        """Blit a PIL image (sized `self.size`) to the panel."""

    @abstractmethod
    def close(self) -> None:
        """Release SPI/GPIO; safe to call more than once."""


class FakePanel(Panel):
    """In-memory panel for tests: records the last frame and the show count."""

    def __init__(self, size: tuple = (240, 135)):
        self._size = size
        self.last_image = None
        self.show_count = 0
        self.closed = False

    @property
    def size(self) -> tuple:
        return self._size

    def show(self, image) -> None:
        self.last_image = image
        self.show_count += 1

    def close(self) -> None:
        self.closed = True


class St7789Panel(Panel):
    """Adafruit Mini PiTFT 1.14" — 240x135 ST7789 over hardware SPI.

    Constants below mirror Adafruit's current `rgb_display_minipitft.py` example.
    VERIFY them on the device (task 7.2) before treating them as final — the
    1.14" panel needs non-zero column/row offsets, and a wrong value shifts or
    garbles the image rather than failing loudly.
    """

    # Native (portrait) controller geometry + the 1.14" memory-window offsets.
    WIDTH, HEIGHT = 135, 240
    X_OFFSET, Y_OFFSET = 53, 40
    BAUDRATE = 64_000_000

    def __init__(self, rotation: int = 90, brightness: float = 1.0):
        # Lazy, Pi-only imports: keep them out of module import on the Mac.
        import board
        import digitalio
        from adafruit_rgb_display import st7789

        self._rotation = rotation
        self._cs = digitalio.DigitalInOut(board.CE0)
        self._dc = digitalio.DigitalInOut(board.D25)
        self._spi = board.SPI()
        self._disp = st7789.ST7789(
            self._spi, cs=self._cs, dc=self._dc, rst=None,
            baudrate=self.BAUDRATE,
            width=self.WIDTH, height=self.HEIGHT,
            x_offset=self.X_OFFSET, y_offset=self.Y_OFFSET,
        )
        # Backlight on GPIO22. On/off for now (PWM brightness is a later refinement).
        self._backlight = digitalio.DigitalInOut(board.D22)
        self._backlight.switch_to_output()
        self._backlight.value = brightness > 0

        # In landscape (90/270) the visible frame is 240x135.
        self._size = (self.HEIGHT, self.WIDTH) if rotation % 180 == 90 else (self.WIDTH, self.HEIGHT)

    @property
    def size(self) -> tuple:
        return self._size

    def show(self, image) -> None:
        self._disp.image(image, self._rotation)

    def close(self) -> None:
        # Best-effort: blank the backlight and release every handle, ignoring
        # double-close / partial-init so shutdown never raises.
        try:
            self._backlight.value = False
        except Exception:
            pass
        for io in (getattr(self, "_backlight", None), getattr(self, "_cs", None), getattr(self, "_dc", None)):
            try:
                if io is not None:
                    io.deinit()
            except Exception:
                pass
        try:
            self._spi.deinit()
        except Exception:
            pass


def create_panel(rotation: int = 90, brightness: float = 1.0) -> Panel:
    """Construct the real hardware panel. Raises if the Pi-only stack or the
    hardware is unavailable — the caller (lifespan) turns that into fail-soft
    headless operation."""
    return St7789Panel(rotation=rotation, brightness=brightness)
