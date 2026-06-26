## Why

The headless core is built, deployed, and verified: the `fmradiod` daemon owns the SDR, tunes the preset ring, fans out one MP3 stream, and serves a live web UI — but the appliance is still **headless**. You can only see what's playing by opening a browser. The whole point of the build is a standalone tabletop radio, and the Adafruit Mini PiTFT 1.14" (240×135 ST7789) is already wired to the Pi waiting for a job.

This change lights up that panel as a **pure tuner readout** that mirrors the daemon's live state — the same now-playing the web UI shows, on the physical screen. It deliberately stays read-only: the two PiTFT buttons (preset next/prev) are the *next* change, and album art stays a web-only luxury (the TFT is a tuner, not a gallery — a scope decision from the project notes).

## What Changes

- New **TFT renderer** inside `fmradiod`: a long-running async task that subscribes to the existing `EventBus` and redraws the panel on every state change, so the screen tracks the daemon without polling.
- The display shows, as a tuner readout:
  - **Frequency + mode badge** — e.g. `97.3 FM`, `97.3 HD`, `162.550 WX`, with the HD subchannel (`HD1`/`HD2`) when present.
  - **Preset label** — the configured station name (e.g. "KBCO – World Class Rock").
  - **Now-playing title / artist** when available (HD metadata); blank/station-name fallback for analog and weather.
  - **Signal status** — a clear indicator for `acquiring` / `no_signal` / `playing` so a dead station is obvious at a glance.
- **No album art** on the TFT (project scope: the panel is a tuner readout). Art remains web-only.
- New **`display:` config block** with an `enabled` flag (code default off so the dev Mac and any panel-less Pi run headless; the appliance's shipped `config.yaml` turns it on), plus rotation and backlight brightness.
- **Graceful degradation**: if the display libraries are unavailable or no panel responds, the daemon logs a warning and continues running headless — the screen is never allowed to take down audio.
- Wired into the Starlette **lifespan** alongside the tuner: the render task starts on boot and is cleanly cancelled on `SIGTERM`; blocking SPI writes run off the event loop so they can't stall the audio fan-out.
- New Pi dependencies for SPI/display rendering (ST7789 driver + Pillow); pinned in `requirements.txt` / `pyproject.toml`.

**Non-goals:** GPIO preset buttons (the *next* change — this one is read-only), album art on the TFT, the 3.5 mm local jack, any change to tuning/audio/web-UI behavior.

## Capabilities

### New Capabilities
- `tft-display`: render the daemon's live tuner state — frequency, mode, HD subchannel, preset label, now-playing title/artist, and signal status — to the on-device ST7789 TFT, mirroring the daemon as the single source of truth, degrading gracefully to headless when no panel is present, and tearing down cleanly on shutdown.

### Modified Capabilities
<!-- None — the TFT renderer is a new, read-only consumer of the existing EventBus/state. It adds no requirements to `station-tuning`, `audio-streaming`, or `web-ui` (the web-ui spec already anticipates the daemon as single source of truth). -->

## Impact

- **Pi packages**: add the ST7789 display driver + Pillow (and the Blinka/`digitalio` SPI stack they need) to the `/root/fmradio/.venv`. SPI must be enabled on the Pi (`dtparam=spi=on`); the Mini PiTFT uses the hardware SPI bus plus a few GPIO lines (DC, reset, backlight) — documented in the design.
- **New code**: a display module in the `fmradiod` package (the renderer task + a thin, swappable panel driver so the render logic is unit-testable on the Mac without hardware).
- **Config**: a new `display:` section in `config.yaml`; absent/`enabled: false` keeps today's headless behavior.
- **Lifespan**: the renderer is registered in `web/app.py`'s lifespan next to `tuner.start()`/`tuner.stop()`; no change to the tuner or fan-out themselves.
- **Downstream**: establishes the on-device UI surface and the panel driver that the upcoming **GPIO preset-buttons** change will build on (buttons drive `tuner.next()/prev()`; this screen reflects the result).
- **Docs**: a build-notes section (wiring, SPI enable, gotchas) consistent with `docs/headless-core-build.md`.
