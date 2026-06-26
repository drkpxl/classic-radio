"""Pure rendering of daemon state to a TFT frame.

`build_view(state)` decides *what* to show (a small, deterministic view-model);
`render(state, size)` paints it to a PIL image. Keeping the content decisions in
`build_view` makes them unit-testable without inspecting pixels, and keeps the
panel a tuner readout — no album art is ever drawn.

Fonts come from Pillow's bundled scalable default (`load_default(size=...)`,
Pillow >= 10.1) so rendering is deterministic across the Mac and the Pi with no
system-font dependency and no binary asset to ship.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_FONT_DIR = Path(__file__).resolve().parent / "fonts"
_FONT_FILES = {False: _FONT_DIR / "DejaVuSans.ttf", True: _FONT_DIR / "DejaVuSans-Bold.ttf"}

SIZE = (240, 135)  # Mini PiTFT 1.14" in landscape

# Retro-radio palette: near-black panel, warm off-white text, mode/status accents.
BG = (10, 12, 16)
FG = (235, 232, 222)
DIM = (150, 150, 140)
DIVIDER = (40, 44, 52)

_MODE_BADGE = {"analog": "FM", "hd": "HD", "weather": "WX"}
_MODE_COLOR = {"analog": (255, 176, 0), "hd": (0, 200, 220), "weather": (120, 220, 120)}

# status key -> (label, color)
_STATUS = {
    "acquiring": ("ACQUIRING", (255, 176, 0)),
    "playing": ("PLAYING", (120, 220, 120)),
    "no_signal": ("NO SIGNAL", (240, 80, 80)),
    "error": ("ERROR", (240, 80, 80)),
    "stopped": ("STOPPED", DIM),
}

# now-playing is meaningless / stale when there's no lock.
_NO_METADATA_STATUSES = ("no_signal", "error", "stopped")


@dataclass(frozen=True)
class ReadoutView:
    freq_text: str          # e.g. "97.3"
    unit_text: str          # "MHz"
    mode_badge: str         # "FM" | "HD" | "WX"
    mode_color: tuple
    hd_chip: str | None     # "HD1" / "HD2" ... for HD, else None
    label: str              # preset label (always shown)
    status_key: str
    status_text: str
    status_color: tuple
    title: str | None       # now-playing extras; None when not shown
    artist: str | None


def build_view(state: dict) -> ReadoutView:
    preset = state.get("preset") or {}
    mode = preset.get("mode", "")
    freq = preset.get("freq")
    hd = preset.get("hd_program")
    status_key = state.get("status", "stopped")

    freq_text = f"{freq:g}" if isinstance(freq, (int, float)) else "--"
    badge = _MODE_BADGE.get(mode, mode.upper() or "??")
    color = _MODE_COLOR.get(mode, DIM)
    # Consumer HD numbering: program 0 -> HD1, program 1 -> HD2, ...
    hd_chip = f"HD{hd + 1}" if mode == "hd" and isinstance(hd, int) else None

    label = preset.get("label") or (state.get("now_playing") or {}).get("label") or ""
    status_text, status_color = _STATUS.get(status_key, (status_key.upper(), DIM))

    title = artist = None
    if status_key not in _NO_METADATA_STATUSES:
        np = state.get("now_playing") or {}
        title = np.get("title") or None
        artist = np.get("artist") or None

    return ReadoutView(
        freq_text=freq_text, unit_text="MHz", mode_badge=badge, mode_color=color,
        hd_chip=hd_chip, label=label, status_key=status_key,
        status_text=status_text, status_color=status_color, title=title, artist=artist,
    )


_FONT_CACHE: dict[tuple, ImageFont.FreeTypeFont] = {}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    f = _FONT_CACHE.get(key)
    if f is None:
        path = _FONT_FILES[bold]
        # Vendored DejaVu (broad Latin coverage: dashes, accents, curly quotes);
        # fall back to Pillow's bundled font only if the asset went missing.
        try:
            f = ImageFont.truetype(str(path), size)
        except OSError:
            f = ImageFont.load_default(size=size)
        _FONT_CACHE[key] = f
    return f


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    """Trim `text` to fit `max_width` px, appending an ellipsis when shortened."""
    if not text:
        return ""
    if draw.textlength(text, font=font) <= max_width:
        return text
    ell = "…"
    for i in range(len(text), 0, -1):
        cand = text[:i].rstrip() + ell
        if draw.textlength(cand, font=font) <= max_width:
            return cand
    return ell


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list:
    """Word-wrap `text` to at most `max_lines` lines within `max_width` px. If it
    still overflows, the last line is ellipsized to signal the cut."""
    if not text:
        return []
    words = text.split()
    lines, cur, idx = [], "", 0
    while idx < len(words) and len(lines) < max_lines:
        trial = f"{cur} {words[idx]}".strip()
        if cur and draw.textlength(trial, font=font) > max_width:
            lines.append(cur)
            cur = ""
        else:
            cur = trial
            idx += 1
    if cur and len(lines) < max_lines:
        lines.append(cur)
        cur = ""
    if (idx < len(words) or cur) and lines:   # leftover text didn't fit
        last = lines[-1]
        # Force a trailing ellipsis, trimming characters until "last…" fits.
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1].rstrip()
        lines[-1] = (last + "…") if last else "…"
    return lines


def render(state: dict, size: tuple = SIZE) -> Image.Image:
    w, h = size
    view = build_view(state)
    img = Image.new("RGB", size, BG)
    d = ImageDraw.Draw(img)
    m = 8

    # --- Header: big frequency (left) + mode badge / HD chip (right) ---
    freq_font = _font(40, bold=True)
    unit_font = _font(13)
    d.text((m, 2), view.freq_text, font=freq_font, fill=FG)
    fx = m + d.textlength(view.freq_text, font=freq_font) + 4
    d.text((fx, 26), view.unit_text, font=unit_font, fill=DIM)

    badge_font = _font(15, bold=True)
    bw = d.textlength(view.mode_badge, font=badge_font)
    bx1, by1 = w - m, 6
    bx0, by0 = bx1 - bw - 12, by1 + 20
    d.rounded_rectangle((bx0, by1, bx1, by0), radius=4, fill=view.mode_color)
    d.text((bx0 + 6, by1 + 2), view.mode_badge, font=badge_font, fill=BG)
    if view.hd_chip:
        chip_font = _font(13, bold=True)
        cw = d.textlength(view.hd_chip, font=chip_font)
        d.text((bx1 - cw, by0 + 4), view.hd_chip, font=chip_font, fill=view.mode_color)

    # Status as a color-coded dot just left of the mode badge (green=playing,
    # amber=acquiring, red=no signal) — no word, leaving the body for the song.
    dot_d = 12
    dot_x1 = bx0 - 6
    d.ellipse((dot_x1 - dot_d, 10, dot_x1, 10 + dot_d), fill=view.status_color)

    d.line((m, 46, w - m, 46), fill=DIVIDER, width=1)

    # --- Preset label (always shown) ---
    label_font = _font(14, bold=True)
    d.text((m, 48), _ellipsize(d, view.label, label_font, w - 2 * m), font=label_font, fill=FG)

    # --- Body: the song gets the space. Show now-playing big (wrapping up to two
    # lines); only when there's no song do we spell out a non-playing status. ---
    if view.title:
        title_font = _font(20)
        ty = 64
        for line in _wrap(d, view.title, title_font, w - 2 * m, max_lines=2):
            d.text((m, ty), line, font=title_font, fill=FG)
            ty += 24
        if view.artist:
            artist_font = _font(14)
            d.text((m, ty + 1), _ellipsize(d, view.artist, artist_font, w - 2 * m),
                   font=artist_font, fill=DIM)
    elif view.status_key in ("no_signal", "acquiring", "error", "stopped"):
        status_font = _font(18, bold=True)
        d.text((m, 70), view.status_text, font=status_font, fill=view.status_color)

    return img
