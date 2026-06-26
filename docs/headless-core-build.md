# Build Log — the headless core (`fmradiod`)

**Goal:** turn the proven analog-FM and HD-Radio spikes into the real appliance — one
daemon that owns the SDR, tunes a curated preset ring, streams to the browser, and
shows now-playing + album art. (TFT screen and physical buttons come later.)

**Result:** done and running as a boot-enabled systemd service. 75 unit tests, all green.

## What it is

A single async Python process (`python -m fmradiod`, Starlette + uvicorn) that:

- Owns the single RTL-SDR through an **arbiter** that guarantees exactly one demod
  backend runs at a time (`tune()` serialized behind a lock).
- Has three **backends** behind one interface: analog (`rtl_fm` WBFM), HD (`nrsc5`),
  weather (`rtl_fm` NBFM) — each piping into `ffmpeg`.
- Normalizes **every** backend to one uniform MP3 (48 kHz / stereo / 256 kbps) so a
  single `/stream.mp3` connection survives preset switches with just a brief blip.
- Fans that one encoder out to many browser listeners (drop-oldest per slow client).
- Parses `nrsc5` stderr for **title/artist** and `LOT file:` lines for **album art**,
  pushing both to the UI live over SSE.
- Serves a retro wood-cabinet web UI (adapted from the original mockup) with a live
  preset ring, tuning dial, album-art panel, and a play/power button.

## How it was built

- **Dev loop:** code lives in the Mac repo, auto-mirrored to `/root/fmradio` on the Pi
  with `rsync` (`deploy/sync.sh`); everything runs and is tested *on the Pi* against the
  real hardware and the real Python 3.13 / ffmpeg / nrsc5.
- **TDD throughout:** every pure-logic and arbiter module was written test-first and run
  on the Pi (config, preset ring, backend command-building, fan-out, arbiter, metadata,
  web). The hardware-touching subprocess layer is thin and injected, so the arbiter logic
  (exclusivity, serialization, resume, retry, teardown) is fully unit-tested with a fake
  spawn; the real subprocess layer is exercised on-device.

## Gotchas worth remembering

- **Free the SDR first.** The de-risk's analog test stream (`fmtest.service`) was still
  holding the dongle (`usb_claim_interface error -6`). The install script now disables it.
- **Graceful shutdown vs. infinite streams.** uvicorn's graceful shutdown waits for open
  requests — but `/stream.mp3` and the SSE feed never end, so `systemctl stop` hung ~90 s.
  Fix: `uvicorn(..., timeout_graceful_shutdown=5)` → clean stop in ~6 s, no orphaned
  `rtl_fm`/`nrsc5`.
- **Uniform output matters.** The spikes emitted different formats (48 k mono analog vs
  44.1 k stereo HD); forcing `-ar 48000 -ac 2` on the ffmpeg *output* keeps the fan-out
  stream continuous across tunes.
- **Flexbox `min-width`.** A long song title with `white-space:nowrap` stretched the whole
  cabinet until `min-width:0` on the flex children let it ellipsis-clip.
- **Autoplay is blocked.** Audio only starts on the user's click of the ON button — by
  design, not a bug.
- **No-signal feedback.** A tune starts as `acquiring`; first audio byte → `playing`; no
  bytes within ~8 s → `no signal` (some HD subchannels here didn't lock).

## Known limitations / follow-ups

- **Album-art bleed:** `nrsc5` dumps LOT files for *all* subchannels, so the "newest image"
  heuristic can briefly show another program's art. Needs art→program association.
- **Weather reception** is weak from this location (transmitter/antenna to investigate).
- Deferred by design: TFT display, GPIO preset buttons, 3.5 mm local jack output.

> **The full forward-looking backlog now lives in [`docs/roadmap.md`](roadmap.md)** — the
> TFT is built and the GPIO buttons are code-complete; remaining phases are the 3.5 mm jack
> and Bluetooth speaker output. This per-phase log stays as a historical record.

## Starter preset ring

97.3 KBCO (HD) · 162.55 NOAA weather · 93.3 KTCL (HD) · 93.3 Punk Tacos (HD2) ·
90.1 CPR News (HD) · 103.5 The Fox (HD). All editable in `config.yaml`.
