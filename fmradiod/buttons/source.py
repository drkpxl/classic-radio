"""The hardware seam: a tiny `ButtonSource` so the input loop never touches the
GPIO driver directly.

`FakeButtonSource` replays scripted samples for tests (runs anywhere).
`GpioButtonSource` reads the real Mini PiTFT 1.14" buttons and lazy-imports the
Pi-only Blinka stack inside `__init__`, so importing this module on the Mac costs
nothing and never fails for want of hardware libraries (mirrors `panel.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ButtonSource(ABC):
    @abstractmethod
    def read(self) -> tuple[bool, bool]:
        """Sample both buttons now: `(next_pressed, prev_pressed)`, pressed=True."""

    @abstractmethod
    def close(self) -> None:
        """Release GPIO; safe to call more than once."""


class FakeButtonSource(ButtonSource):
    """In-memory source for tests: replays `(next, prev)` samples in order, then
    returns released `(False, False)` forever once the script is exhausted."""

    def __init__(self, samples=None):
        self._samples = list(samples or [])
        self._i = 0
        self.read_count = 0
        self.closed = False

    def read(self) -> tuple[bool, bool]:
        self.read_count += 1
        if self._i < len(self._samples):
            s = self._samples[self._i]
            self._i += 1
        else:
            s = (False, False)
        return (bool(s[0]), bool(s[1]))

    def close(self) -> None:
        self.closed = True


class GpioButtonSource(ButtonSource):
    """The two Mini PiTFT 1.14" buttons read over Blinka `digitalio`.

    The buttons are active-low: each line idles high through an internal pull-up
    and reads low while pressed, so `pressed = not value`. Pins default to
    GPIO #23 (top) and #24 (bottom) — distinct from the panel's CE0/D25/D22/SPI.
    VERIFY the pins on-device (task 7.1) before treating them as final.
    """

    def __init__(self, next_pin: int = 23, prev_pin: int = 24):
        # Lazy, Pi-only imports: keep them out of module import on the Mac.
        import board
        import digitalio

        self._next = self._make_input(board, digitalio, next_pin)
        self._prev = self._make_input(board, digitalio, prev_pin)

    @staticmethod
    def _make_input(board, digitalio, pin: int):
        io = digitalio.DigitalInOut(getattr(board, f"D{pin}"))
        io.direction = digitalio.Direction.INPUT
        io.pull = digitalio.Pull.UP
        return io

    def read(self) -> tuple[bool, bool]:
        # Active-low: a pressed button pulls its line to ground.
        return (not self._next.value, not self._prev.value)

    def close(self) -> None:
        # Best-effort: release every line, ignoring double-close / partial init
        # so shutdown never raises (consistent with St7789Panel.close()).
        for io in (getattr(self, "_next", None), getattr(self, "_prev", None)):
            try:
                if io is not None:
                    io.deinit()
            except Exception:
                pass


def create_source(next_pin: int = 23, prev_pin: int = 24) -> ButtonSource:
    """Construct the real GPIO source. Raises if the Pi-only stack or the pins
    are unavailable — the caller (lifespan) turns that into fail-soft no-buttons
    operation."""
    return GpioButtonSource(next_pin=next_pin, prev_pin=prev_pin)
