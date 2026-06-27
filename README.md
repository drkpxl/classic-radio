# classic-radio — a Raspberry Pi tabletop FM / HD / Weather radio

A self-contained software-defined radio appliance: tune a curated ring of
Denver/Golden CO stations (analog FM, **HD Radio**, and NOAA weather), with a
retro web UI, an on-device TFT readout, two physical preset buttons, and
**Bluetooth speaker output** — all driven by one small async Python daemon
(`fmradiod`, branded **HubertFM** in the UI).

![status](https://img.shields.io/badge/status-running%20on%20hardware-success)

## Hardware

- Raspberry Pi 3A+ (DietPi, aarch64) · Nooelec RTL-SDR (R820T2)
- Adafruit Mini PiTFT 1.14" (240×135 ST7789 + 2 buttons)
- Onboard Bluetooth · 3.5 mm jack (planned)

## Features

- **Curated preset ring** across modes — analog FM, HD Radio (`nrsc5`), NOAA weather — in an editable `config.yaml`; resumes the last station on boot.
- **One SDR, one backend at a time** — a serialized arbiter spawns `rtl_fm`/`nrsc5` → `ffmpeg`, with clean teardown (no orphaned processes).
- **Live audio + web UI** — a single MP3 encoder fans out to many browser listeners; a retro tabletop-radio UI mirrors daemon state over SSE, including HD now-playing + **album art** (associated to the tuned program via `nrsc5`'s `XHDR`).
- **TFT readout** — a read-only on-device tuner display that mirrors the daemon.
- **GPIO buttons** — the two Mini PiTFT buttons cycle the preset ring.
- **Bluetooth speaker output** — pair/connect a speaker from the web UI (BlueZ over D-Bus via `dbus-fast` + `bluez-alsa` A2DP); audio routes to the speaker as an exclusive, selectable output, with auto-reconnect on boot.
- **Responsive UI** — works on phones; keyboard-focus + reduced-motion friendly.

## Architecture

One async (Starlette/uvicorn) supervisor owns the SDR and spawns native
subprocesses; the audio stream is folded into the web app (no Icecast). Optional
peripherals (TFT, buttons, Bluetooth) are config-gated and **fail-soft** — a
missing panel, GPIO, or Bluetooth stack degrades gracefully and never takes down
audio or the web UI. The daemon is the single source of truth; every surface
(web, TFT) re-derives the same state snapshot on each change.

```
RTL-SDR → rtl_fm / nrsc5 → ffmpeg ─┬─ MP3 fan-out → web listeners      (output: web)
                                   └─ PCM → bluealsa A2DP → speaker    (output: bluetooth)
```

## Layout

- `fmradiod/` — the daemon: `tuner`, `backends/`, `audio` (fan-out), `web/`,
  `display/` (TFT), `buttons/` (GPIO), `bluetooth/` (BlueZ).
- `config.yaml` — presets + runtime settings.
- `deploy/` — `sync.sh` (rsync to the Pi) + the systemd unit.
- `docs/` — build logs and the running roadmap (`docs/roadmap.md`).
- `openspec/` — the spec-driven change history (specs + archived changes).

## Develop & deploy

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest        # runs on macOS (hardware seams are faked)
deploy/sync.sh                    # rsync to the Pi; tests + app run there too
```

The Pi installs the hardware extras (`pip install -r requirements.txt`: Pillow +
Blinka for the TFT, `dbus-fast` for Bluetooth) and runs `fmradiod.service`.

## Status

FM/HD/Weather, web UI, TFT, buttons, and Bluetooth output are built and verified
on hardware. Remaining: the 3.5 mm jack (a third output sink). See
`docs/roadmap.md`.
