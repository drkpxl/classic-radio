"""Persist the last selected preset so the daemon resumes it on boot.

A tiny JSON file. Any problem reading it (missing, corrupt, out of range) falls
back to the caller's default rather than failing startup.
"""

from __future__ import annotations

import json
from pathlib import Path


class StateStore:
    def __init__(self, path: str | Path):
        self._path = Path(path)

    def save_index(self, index: int) -> None:
        self._path.write_text(json.dumps({"last_preset_index": index}))

    def load_index(self, default: int = 0, count: int | None = None) -> int:
        try:
            data = json.loads(self._path.read_text())
            index = int(data["last_preset_index"])
        except (OSError, ValueError, KeyError, TypeError):
            return default
        if index < 0 or (count is not None and index >= count):
            return default
        return index
