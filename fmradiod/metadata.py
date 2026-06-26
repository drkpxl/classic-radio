"""Now-playing + album art for the current station, parsed from nrsc5 stderr.

For HD, nrsc5 prints `Title:`/`Artist:` lines and `LOT file:` lines (album art /
station logos) — both on its stderr — so a single line reader yields everything.
For analog/weather there's no metadata: we hold the preset label, no art, and
just drain the source's stderr so the process never blocks on a full pipe.

Limitation (v1): nrsc5 dumps LOT files for every program/port it sees, so the
"newest image" heuristic can occasionally show another subchannel's art. Refining
the art→program association is a later improvement.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

_TS = re.compile(r"^\d\d:\d\d:\d\d\s+")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def _token(line: str, key: str) -> str | None:
    i = line.find(key)
    if i < 0:
        return None
    rest = line[i + len(key):].split()
    return rest[0] if rest else None


class Metadata:
    def __init__(self, bus, art_route: str = "/art/current"):
        self.bus = bus
        self._art_route = art_route
        self._task = None
        self._aas_dir = None
        self._reset_to(None)

    def _reset_to(self, label: str | None) -> None:
        self.title = None
        self.artist = None
        self.label = label
        self.art_path = None
        self.art_token = 0

    def now_playing(self) -> dict:
        art = f"{self._art_route}?v={self.art_token}" if self.art_path else None
        return {
            "type": "now_playing",
            "title": self.title,
            "artist": self.artist,
            "label": self.label,
            "art": art,
        }

    async def switch(self, preset, group, aas_dir) -> None:
        await self.stop()
        self._reset_to(preset.label)
        self._aas_dir = aas_dir
        if preset.mode == "hd":
            self._task = asyncio.ensure_future(self._read(group.source_stderr))
        else:
            self._task = asyncio.ensure_future(self._drain(group.source_stderr))
        self.bus.publish(self.now_playing())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _read(self, reader) -> None:
        if reader is None:
            return
        while True:
            raw = await reader.readline()
            if not raw:
                break
            self._handle_line(raw.decode("utf-8", "replace").rstrip("\r\n"))

    def _handle_line(self, line: str) -> None:
        line = _TS.sub("", line)
        changed = False
        if line.startswith("Title: "):
            self.title = line[len("Title: "):].strip() or None
            changed = True
        elif line.startswith("Artist: "):
            self.artist = line[len("Artist: "):].strip() or None
            changed = True
        elif line.startswith("LOT file:"):
            path = self._art_from_lot(line)
            if path:
                self.art_path = path
                self.art_token += 1
                changed = True
        if changed:
            self.bus.publish(self.now_playing())

    def _art_from_lot(self, line: str) -> str | None:
        name = _token(line, "name=")
        lot = _token(line, "lot=")
        if not name or not lot or not self._aas_dir:
            return None
        if not name.lower().endswith(_IMAGE_EXTS):
            return None
        return str(Path(self._aas_dir) / f"{lot}_{name}")

    @staticmethod
    async def _drain(reader) -> None:
        if reader is None:
            return
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
