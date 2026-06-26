"""Persist a little runtime state so the daemon resumes on boot.

A tiny JSON file holding the last selected preset, the audio output mode, and the
last connected Bluetooth speaker. Any problem reading it (missing, corrupt, out
of range) falls back to the caller's default rather than failing startup. Writes
merge into the existing file so the keys don't clobber each other.
"""

from __future__ import annotations

import json
from pathlib import Path

_OUTPUTS = ("web", "bluetooth")


class StateStore:
    def __init__(self, path: str | Path):
        self._path = Path(path)

    # ----- low-level merge -----
    def _read(self) -> dict:
        try:
            data = json.loads(self._path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _merge(self, **kv) -> None:
        data = self._read()
        data.update(kv)
        self._path.write_text(json.dumps(data))

    # ----- preset index -----
    def save_index(self, index: int) -> None:
        self._merge(last_preset_index=index)

    def load_index(self, default: int = 0, count: int | None = None) -> int:
        try:
            index = int(self._read()["last_preset_index"])
        except (ValueError, KeyError, TypeError):
            return default
        if index < 0 or (count is not None and index >= count):
            return default
        return index

    # ----- output mode -----
    def save_output(self, mode: str) -> None:
        self._merge(output=mode)

    def load_output(self, default: str = "web") -> str:
        mode = self._read().get("output")
        return mode if mode in _OUTPUTS else default

    # ----- last Bluetooth device -----
    def save_device(self, mac: str | None) -> None:
        self._merge(last_device=mac)

    def load_device(self) -> str | None:
        mac = self._read().get("last_device")
        return mac if isinstance(mac, str) and mac else None
