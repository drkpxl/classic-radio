"""The preset ring — an ordered, wrapping cursor over the configured presets.

Generic over item type so it can be unit-tested without `Preset`; in the daemon
it holds `config.Preset` objects and is the model the tuner/web layer navigate.
"""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class Ring(Generic[T]):
    def __init__(self, items: list[T], start: int = 0):
        if not items:
            raise ValueError("ring must contain at least one item")
        if not (0 <= start < len(items)):
            raise IndexError(f"start index {start} out of range for {len(items)} items")
        self._items = list(items)
        self._index = start

    def __len__(self) -> int:
        return len(self._items)

    @property
    def index(self) -> int:
        return self._index

    @property
    def current(self) -> T:
        return self._items[self._index]

    @property
    def items(self) -> list[T]:
        return list(self._items)

    def next(self) -> T:
        self._index = (self._index + 1) % len(self._items)
        return self.current

    def prev(self) -> T:
        self._index = (self._index - 1) % len(self._items)
        return self.current

    def get(self, i: int) -> T:
        if not (0 <= i < len(self._items)):
            raise IndexError(f"index {i} out of range for {len(self._items)} items")
        self._index = i
        return self.current
