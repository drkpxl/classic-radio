## Why

Both demod paths are now proven on the Pi 3A+: analog FM web streaming ran with ample headroom, and the HD Radio de-risk returned a **first-class** verdict (`nrsc5` at ~1 of 4 cores, with album art and metadata for free). We have the green light to build the actual appliance.

This change builds the **headless core** — the first real feature of the product. It is a single async Python daemon that owns the SDR, tunes a curated preset ring across analog FM / HD Radio / NOAA weather, encodes everything to one uniform MP3 stream, and serves a retro web UI (now-playing + HD album art) backed by a small control API. It deliberately stops short of the physical TFT display, GPIO buttons, and 3.5 mm local jack output so the core can be made solid before hardware I/O is layered on. The daemon is the single source of truth; the web UI mirrors it (and later, so will the buttons/screen).

## What Changes

- New Python package `fmradiod` (asyncio, **Starlette + uvicorn**) installed to `/root/fmradio` on the Pi under a venv (`starlette`, `uvicorn`, `pyyaml`).
- **SDR arbiter** (`tuner`) that owns the single RTL-SDR and guarantees exactly one demod backend subprocess pipeline runs at a time; `tune()` serialized behind an asyncio lock.
- Three **demod backends** behind a common interface — `analog` (`rtl_fm` WBFM), `hd` (`nrsc5`), `weather` (`rtl_fm` NBFM) — each piping into `ffmpeg`.
- **Uniform-format MP3 fan-out**: every backend normalizes to 48 kHz / stereo / 256 kbps so one long-lived `/stream.mp3` connection survives tunes; one encoder feeds N browser clients.
- **HD metadata/art**: parse `nrsc5` stderr (title/artist/genre) and watch its `--dump-aas-files` dir for album-art/logo LOT files; expose via API + push over SSE.
- **Web UI** adapted from `docs/radio.html`: wood-cabinet skin wired to the live ring, an album-art / now-playing panel, a play/power control, and SSE live updates.
- **Control API**: `next` / `prev` / `tune/{i}`, a `state` snapshot, an `events` SSE stream, and album-art serving.
- **Config** in editable YAML on the Pi (the starter preset ring below) + `state.json` to resume the last station on boot.
- **systemd unit** `fmradiod.service` (auto-start on boot, `Restart=always`, logs to journald).
- **Dev workflow**: canonical source in this Mac repo, auto-mirrored to the Pi on save (rsync); everything runs/listens on the Pi.

Starter preset ring (editable; "default to HD" is the rule when adding more):

| # | Freq | Mode | Label |
|---|------|------|-------|
| 1 | 97.3 | hd (prog 0) | KBCO – World Class Rock |
| 2 | 162.550 | weather | Denver Weather (KEC76) |
| 3 | 93.3 | hd (prog 0) | Channel 93.3 (KTCL) |
| 4 | 93.3 | hd (prog 1) | Punk Tacos (KTCL HD2) |
| 5 | 102.3 | hd (prog 0) | Indie 102.3 (KVOQ) |
| 6 | 105.5 | hd (prog 0) | The Colorado Sound (KJAC) |

**Non-goals:** physical TFT display, GPIO preset buttons, 3.5 mm local jack output (all later changes); AM, police/trunked, satellite/APT (out of project scope).

## Capabilities

### New Capabilities
- `station-tuning`: own the single SDR, model a curated preset ring across analog/HD/weather modes, switch backends safely (one at a time), recover from backend failures, and resume the last station on boot.
- `audio-streaming`: encode any active backend to a uniform MP3 format and fan it out to many concurrent HTTP listeners from a single encoder, surviving preset switches and isolating slow clients.
- `web-ui`: serve the retro web UI driven by live daemon state, expose a control API, and push now-playing + HD album-art updates to the browser in real time.

### Modified Capabilities
<!-- None — `hd-radio-reception` was a feasibility spike; this change adds new full-app capabilities rather than modifying it. -->

## Impact

- **Pi packages**: a Python venv at `/root/fmradio/.venv` with `starlette`, `uvicorn`, `pyyaml`. `python3` (3.13.5), `ffmpeg`, `rtl_fm`, and `nrsc5` are already present.
- **New code**: the `fmradiod` package at `/root/fmradio`, mirrored from this Mac repo.
- **systemd**: a new `fmradiod.service` owning the SDR on boot. The throwaway spike scripts (`/root/fmstream.py`, `/root/hdstream.py`) are superseded but kept as reference; they must not run alongside the daemon (single SDR).
- **Downstream**: establishes the daemon as the single source of truth and the `tune()` entry point that the future TFT + GPIO-button change and the 3.5 mm local-output change will hook into.
