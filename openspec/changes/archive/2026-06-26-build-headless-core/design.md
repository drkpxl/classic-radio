## Context

The de-risk spikes proved analog FM and HD Radio both stream cleanly on the Pi 3A+, and settled the process model: one async Python supervisor plus native subprocess backends (`rtl_fm` / `nrsc5` / `ffmpeg`), fanning MP3 out to web clients over a small persistent HTTP server (no Icecast). This change turns those throwaway scripts into the real headless core. The single RTL-SDR (R820T2) means exactly one demod backend can run at a time — the central constraint the arbiter exists to enforce.

## Goals / Non-Goals

**Goals**
- One systemd-managed daemon that owns the SDR and is the single source of truth for "what's playing."
- A curated, editable preset ring spanning analog FM, HD Radio (with subchannel), and NOAA weather.
- Safe backend switching: never two backends on the dongle at once; never an orphaned `rtl_fm`/`nrsc5` after a switch or shutdown.
- One uniform MP3 stream that survives preset switches; many concurrent listeners from a single encoder.
- A live web UI (retro skin) showing now-playing + HD album art, mirroring daemon state.
- Pure-logic units that are unit-testable without the SDR.

**Non-Goals**
- TFT display, GPIO buttons, 3.5 mm local jack output (later changes).
- AM, police/trunked, satellite/APT (out of project scope).
- Multi-SDR or simultaneous analog+HD.

## Decisions

**Stack: Starlette + uvicorn, asyncio.** Clean routing, native streaming responses for the MP3 fan-out, and trivial SSE via async-generator `StreamingResponse`. Footprint is a few MB — negligible on the ~349 MB free. SSE is hand-rolled (no `sse-starlette` dep). Config validation is plain dataclasses + manual checks (no pydantic). Total third-party deps: `starlette`, `uvicorn`, `pyyaml`.

**Module decomposition** (each a focused, single-purpose unit):

| Module | Responsibility |
|--------|----------------|
| `config.py` | Load/validate `config.yaml` → typed dataclasses (server, sdr, audio, defaults, presets) |
| `presets.py` | Ordered ring + `next()`/`prev()`/`get(i)` (wrapping); `Preset` = label, mode (`analog`/`hd`/`weather`), freq, `hd_program?` |
| `backends/base.py` | `Backend` interface: `build_command(preset, audio_cfg) -> list[list[str]]` (the subprocess pipeline) + declared PCM input format |
| `backends/analog.py` | `rtl_fm` WBFM → `ffmpeg` |
| `backends/hd.py` | `nrsc5 -o - -t raw <freq> <prog> --dump-aas-files <dir>` → `ffmpeg`; exposes the AAS dir + stderr for metadata |
| `backends/weather.py` | `rtl_fm` NBFM @ 162.xxx → `ffmpeg` |
| `tuner.py` | The arbiter. Owns the SDR; `tune(preset)` tears down current, spawns new, repoints fan-out, (re)starts metadata; serialized by an asyncio lock; emits state events |
| `audio.py` | Fan-out: read encoder stdout in fixed chunks → broadcast to per-client bounded queues (drop-oldest); async generator per client for `StreamingResponse` |
| `metadata.py` | HD only: async-read `nrsc5` stderr (title/artist/genre) + watch the AAS dir for art/logo files; expose current now-playing + art; emit change events |
| `events.py` | Tiny async pub/sub the tuner/metadata publish to and SSE subscribes from |
| `state.py` | Persist/restore `last_preset_index` (`state.json`) |
| `web/app.py` | Starlette routes (below); serves UI + static assets |
| `web/static/` | The adapted retro UI (HTML/CSS/JS) |
| `main.py` | asyncio entrypoint: load config, build ring, start server, resume last/default preset, wire events, handle SIGTERM → clean teardown |

**Uniform output format.** Every backend's `ffmpeg` resamples/upmixes to **48 kHz, stereo, 256 kbps MP3** regardless of source (analog mono WBFM, HD 44.1 k stereo, NBFM weather). This keeps the fan-out byte stream format-stable so one long-lived `/stream.mp3` connection survives tunes with at most a brief audible blip, rather than forcing every client to reconnect on each switch.

**Tune flow.** `POST /api/next|prev|tune/{i}` → `tuner.tune(preset)`: SIGTERM the current pipeline's **process group**, await exit (timeout → SIGKILL); spawn the new pipeline; repoint `audio.py` at the new `ffmpeg` stdout; start the HD metadata watcher (or clear to label-only); update state, persist index, publish a state-change event (→ SSE). Browser keeps its `/stream.mp3` connection; UI updates over SSE. `tune()` is serialized so rapid next/next/next can't spawn overlapping pipelines.

**Streaming fan-out.** One `ffmpeg` per active backend → `audio.py` reads fixed chunks → pushes to each connected client's bounded queue (drop-oldest if a client lags), then disconnects unrecoverable clients. Never blocks the encoder or other listeners. Exactly the proven pattern, generalized.

**HD metadata/art.** `nrsc5` prints Title/Artist/Genre to stderr and dumps album-art/logo LOT files to the `--dump-aas-files` dir. `metadata.py` async-reads stderr and watches that dir, exposing the current now-playing + latest art image and emitting change events. Analog/weather have no metadata → now-playing falls back to the preset label and art clears.

**Web API**

| Route | Purpose |
|-------|---------|
| `GET /` | Retro UI page |
| `GET /stream.mp3` | `StreamingResponse` (`audio/mpeg`) from the fan-out |
| `GET /api/state` | JSON: current preset, full ring, now-playing, `art_url`, HD lock/signal status |
| `POST /api/next` · `/api/prev` · `/api/tune/{i}` | Change preset → return new state |
| `GET /api/events` | SSE — preset / now-playing / art changes |
| `GET /art/current.jpg` | Latest HD art (404 → UI default graphic) |
| `GET /static/…` | CSS/JS assets |

**Web UI (adapted from `docs/radio.html`).** Keep the wood-cabinet skin, dial, numbered presets, now-playing footer. Presets are driven by the real ring from `/api/state` (count/labels/freqs from config — not the hardcoded 12). Clicking → `POST /api/tune/{i}`; active button + needle reflect **server** state. Add an album-art / now-playing panel. A play/power control drives an `<audio>` element on `/stream.mp3` (audio starts on click — browsers block autoplay). SSE keeps it a live mirror, including preset changes that later come from physical buttons. Weather (162.55 MHz) sits off the 88–108 dial → park the needle and show a "WX" indicator + label rather than pushing the needle off-scale.

**Config (YAML on the Pi).**
```yaml
server: { host: "0.0.0.0", port: 8000 }
sdr:    { gain: "auto", ppm: 0 }
audio:  { bitrate: "256k", sample_rate: 48000, channels: 2 }
defaults: { start_preset: 0 }   # used when no saved state
presets:
  - { label: "KBCO – World Class Rock", mode: hd, freq: 97.3, hd_program: 0 }
  - { label: "Denver Weather (KEC76)",  mode: weather, freq: 162.550 }
  - { label: "Channel 93.3 (KTCL)",     mode: hd, freq: 93.3, hd_program: 0 }
  - { label: "Punk Tacos (KTCL HD2)",   mode: hd, freq: 93.3, hd_program: 1 }
  - { label: "Indie 102.3 (KVOQ)",      mode: hd, freq: 102.3, hd_program: 0 }
  - { label: "The Colorado Sound (KJAC)", mode: hd, freq: 105.5, hd_program: 0 }
```
`state.json` holds `last_preset_index`, written on each tune; restored on boot, falling back to `defaults.start_preset`.

**Deploy.** systemd `fmradiod.service` runs `/root/fmradio/.venv/bin/python -m fmradiod` after the network target, `Restart=always`, logging to journald. Canonical source in this Mac repo, auto-mirrored to `/root/fmradio` via rsync on save; everything runs/listens on the Pi.

## Risks / Trade-offs

- **MP3 stream discontinuity on tune** → a new `ffmpeg` starts a fresh MP3 stream; most browser decoders re-sync on frame headers, so the cost is a brief blip (acceptable, on-theme). If a client can't re-sync, the fallback is a client-side reconnect on the SSE preset-change event.
- **Orphaned SDR holders** → always signal the whole process group and confirm exit; on shutdown (SIGTERM) tear down children before exiting. A stale `rtl_fm`/`nrsc5` would block the next tune.
- **HD lock on weak signal** → surface a "no signal" status after a timeout; keep trying; the user can tune away. (HD needs a cleaner signal than analog.)
- **Memory on a 512 MB box** → keep per-client queues small and bounded; one encoder regardless of listener count; lean deps.
- **nrsc5 single-threaded** → its one core is the tightest resource; optionally `taskset`-pin later (not required — zero dropouts observed in the spike).

## Open Questions

- Exact `nrsc5` stderr line formats for title/artist/genre across stations (resolve while wiring `metadata.py` against real output).
- Whether `--dump-aas-files` needs periodic cleanup to bound disk (likely yes — prune old art files).
- Whether the brief tune blip is acceptable in practice or warrants the SSE-driven reconnect fallback (decide by ear on-device).
