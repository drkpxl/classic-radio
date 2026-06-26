"""The daemon's current state as a plain dict — the single shape both the web UI
and the on-device TFT render from.

Lifted out of the web app so non-web consumers (the TFT renderer) can derive the
same snapshot without importing Starlette. Every state-change event just means
"rebuild this", giving every surface one render path.
"""

from __future__ import annotations


def build_state(tuner, metadata) -> dict:
    snap = tuner.snapshot()
    np = metadata.now_playing()
    return {
        "preset": {
            "index": snap["index"],
            "label": snap["label"],
            "mode": snap["mode"],
            "freq": snap["freq"],
            "hd_program": snap["hd_program"],
        },
        "status": snap["status"],
        "now_playing": {
            "title": np["title"],
            "artist": np["artist"],
            "label": np["label"],
            "art": np["art"],
        },
        "ring": [
            {"index": i, "label": p.label, "mode": p.mode, "freq": p.freq, "hd_program": p.hd_program}
            for i, p in enumerate(tuner.ring.items)
        ],
    }
