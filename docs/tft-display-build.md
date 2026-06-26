# Build Log — the TFT tuner readout

**Goal:** light up the Adafruit Mini PiTFT 1.14" (240×135 ST7789) as a **read-only**
tuner readout that mirrors the daemon — the on-device counterpart to the web UI.
(Physical preset buttons are the *next* change; album art stays web-only.)

**Result:** code complete and unit-tested on the Mac (render, panel seam, renderer
lifecycle, fail-soft wiring). On-device verification (SPI enable, offset/rotation
confirmation, live readout) is the remaining hands-on step — see *On the Pi* below.

## What it is

A small async task inside `fmradiod` that subscribes to the existing `EventBus` and,
on every state change, re-derives the **full** state with `build_state(tuner, metadata)`
— the same snapshot the web UI renders — and blits a fresh frame to the panel:

- **Header:** big frequency + a mode badge (`FM` / `HD` / `WX`), an `HD1`/`HD2` chip, and a
  **color-coded status dot** just left of the badge (green = playing, amber = acquiring,
  red = no signal) — no status *word*, so the body is free for the song.
- **Preset label** (small), then the **now-playing** title large (wrapping up to two lines)
  with the artist beneath. When there's no song, a non-playing status (`NO SIGNAL` /
  `ACQUIRING`) is spelled out in that space instead.
- **No album art** — the panel is a tuner readout by design.

## How it's built (the seams)

- `fmradiod/display/render.py` — a **pure** `render(state, size) -> PIL.Image`. The
  content decisions live in `build_view(state)` (a small view-model), so they're
  unit-tested without inspecting pixels. Fonts are **vendored** (`fonts/DejaVuSans*.ttf`).
- `fmradiod/display/panel.py` — a thin `Panel` interface. `FakePanel` records frames for
  tests (runs anywhere); `St7789Panel` drives the real hardware and **lazy-imports** the
  Pi-only Blinka / `adafruit_rgb_display` stack inside `__init__`.
- `fmradiod/display/renderer.py` — `TftRenderer`: subscribes to the bus, coalesces a
  tune's burst of events into one redraw, and runs every blit on a dedicated
  single-worker thread (`run_in_executor`) so the blocking SPI flush never stalls the
  audio fan-out.
- Wired in `__main__.build_app()` + `web/app.py` lifespan: started after the tuner, torn
  down before it. **Off by default** (`display.enabled: false`); enabling it imports the
  display package *only then*, and any failure (no Blinka, no panel) logs a warning and
  runs headless — the screen can never take down audio.

Config (`config.yaml`):

```yaml
display:
  enabled: false    # set true on the Pi
  rotation: 90      # Mini PiTFT landscape
  brightness: 1.0   # backlight on/off for now (PWM later)
```

## On the Pi (verification runbook)

Status as verified on `fmradio.local` (Pi 3A+, DietPi, Debian 13 / Python 3.13.5):

1. **Enable SPI** — *already done* on this Pi (`dtparam=spi=on` in
   `/boot/firmware/config.txt`; `/dev/spidev0.0`/`0.1` present, no reboot needed). On a
   fresh box: add the line and reboot. The Mini PiTFT uses hardware SPI0 + GPIO25 (DC),
   GPIO22 (backlight), CE0 (CS); reset is tied (rst=None).
2. **Install deps** — *done.* `pip install -r requirements.txt` pulls Pillow +
   `adafruit-blinka` + `adafruit-circuitpython-rgb-display`. **Gotcha:** Blinka pulls
   `RPi.GPIO`/`rpi_ws281x`, whose C extensions need the Python headers — `apt-get install
   -y python3.13-dev` first or the wheel build fails on `Python.h`.
3. **Confirm offsets/rotation** against Adafruit's current `rgb_display_minipitft.py`
   example. The 1.14" panel needs non-zero column/row offsets (currently `x_offset=53`,
   `y_offset=40`, rotation 90 in `St7789Panel`) — a wrong value *shifts or garbles* the
   image rather than erroring. Lock the constants once the frame is correctly positioned.
   (Blinka already auto-detects `RASPBERRY_PI_3A_PLUS` and `board.CE0/D25/D22` resolve, so
   no `BLINKA_FORCEBOARD` hint is needed here.)
4. **Run the suite** — *done:* `python -m pytest -q` → 100 passed, 1 skipped (the skip is
   the hardware-init guard; render/renderer/fail-soft are covered).
5. **Enable + restart:** set `display.enabled: true`, `systemctl restart fmradiod`, and
   confirm the readout tracks tunes and HD metadata, the status dot is right, long titles
   ellipsize, and `systemctl stop` leaves no orphaned SPI/GPIO handles.

## Gotchas worth remembering

- **The bundled Pillow font is too narrow.** `ImageFont.load_default(size=…)` is missing
  en/em-dashes **and** accented Latin (é, ñ, ü) — and the Denver preset labels use
  en-dashes ("KBCO – World Class Rock") while HD song metadata is full of accents. We
  vendor `DejaVuSans` Regular+Bold into the package (broad Latin coverage) and load those;
  the bundled font is only a last-resort fallback.
- **Keep the blit off the event loop.** A synchronous SPI flush (~tens of ms) on the
  asyncio loop would jitter the MP3 fan-out. The renderer uses a single-worker
  `ThreadPoolExecutor`; one worker also serializes panel access so frames can't tear.
- **Coalesce the tune burst.** A single tune emits `state` then `now_playing` events
  back-to-back; the renderer drains the queue and redraws once, not per event.
- **Pi-only deps stay out of the Mac path.** Importing `fmradiod` headless touches no
  display/PIL code (verified) — the display package is imported only inside the
  `display.enabled` branch, and the driver stack only inside `St7789Panel.__init__`.
- **If Blinka can't detect the board on DietPi**, set `BLINKA_FORCEBOARD` /
  `BLINKA_FORCECHIP`. Because init is fail-soft, a detection miss degrades to headless
  rather than crashing the daemon — check the journal for the warning.
