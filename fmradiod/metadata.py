"""Now-playing + album art for the current station, parsed from nrsc5 stderr.

For HD, nrsc5 prints `Title:`/`Artist:` lines, `LOT file:` lines (the images/files
it receives), and `XHDR:` lines — all on its stderr — so a single line reader
yields everything. For analog/weather there's no metadata: we hold the preset
label, no art, and just drain the source's stderr so the process never blocks on
a full pipe.

Art→program association: nrsc5 dumps `LOT file:` images for *every* program/port
on the station (e.g. tuned to KBCO HD1 we still receive HD3's art and promo tiles),
so picking "any image" shows the wrong art. The `XHDR:` line is the tie-breaker: its
last field is the LOT id of the *current tuned program's* cover art (`-1` = none, a
station-ID screen). So we map `lot -> filename` from `LOT file:` lines and only show
the image whose lot matches the latest `XHDR`, clearing art when it's -1.
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
        self._cur_lot = None     # LOT id of the current program's art (from XHDR), or None
        self._lots: dict[int, str] = {}   # lot -> image filename, from LOT file lines

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
        elif line.startswith("XHDR:"):
            # "XHDR: <param> <mime> <lot>" — the last field is the LOT id of the
            # current tuned program's cover art (-1 = none / station-ID screen).
            self._cur_lot = self._parse_xhdr_lot(line)
            changed = self._recompute_art() or changed
        elif line.startswith("LOT file:"):
            # Record images as they arrive; the XHDR decides which is current.
            self._record_lot(line)
            changed = self._recompute_art() or changed
        if changed:
            self.bus.publish(self.now_playing())

    @staticmethod
    def _parse_xhdr_lot(line: str) -> int | None:
        try:
            lot = int(line.split()[-1])
        except (IndexError, ValueError):
            return None
        return lot if lot >= 0 else None

    def _record_lot(self, line: str) -> None:
        name = _token(line, "name=")
        lot = _token(line, "lot=")
        if not name or not lot or not name.lower().endswith(_IMAGE_EXTS):
            return
        try:
            self._lots[int(lot)] = name
        except ValueError:
            pass

    def _recompute_art(self) -> bool:
        """Set art_path to the image matching the current XHDR lot (or None when the
        lot is -1 or its file hasn't arrived). Returns whether the path changed."""
        if self._cur_lot is not None and self._aas_dir and self._cur_lot in self._lots:
            new_path = str(Path(self._aas_dir) / f"{self._cur_lot}_{self._lots[self._cur_lot]}")
        else:
            new_path = None
        if new_path != self.art_path:
            self.art_path = new_path
            self.art_token += 1
            return True
        return False

    @staticmethod
    async def _drain(reader) -> None:
        if reader is None:
            return
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
