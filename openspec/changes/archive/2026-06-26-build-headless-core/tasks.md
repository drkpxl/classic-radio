## 1. Project scaffold & dev workflow

- [x] 1.1 Create the `fmradiod/` package in this Mac repo (`fmradiod/__init__.py`, `__main__.py`, module stubs, `requirements.txt`: starlette, uvicorn, pyyaml)
- [x] 1.2 Set up auto-mirror: an rsync-on-save sync from the Mac repo to `root@fmradio.local:/root/fmradio` (script + how it's triggered); verify a round-trip — `deploy/sync.sh` (one-shot or `--watch`)
- [x] 1.3 Create the venv on the Pi (`/root/fmradio/.venv`) and `pip install -r requirements.txt`; confirm imports — starlette 1.3.1, uvicorn 0.49.0, pyyaml 6.0.3
- [x] 1.4 Add a `pytest` setup so pure-logic tests run on the Pi (or Mac) — root `conftest.py` + `tests/`, smoke test green

## 2. Config & preset ring (pure, TDD)

- [x] 2.1 `config.py`: dataclasses for server/sdr/audio/defaults/preset; load + validate `config.yaml`; clear errors on bad/missing fields. Tests: valid file, missing field, bad mode, weather-without-program OK, hd-without-program defaults to 0 — 9 tests green
- [x] 2.2 `presets.py`: ring with `next()`/`prev()`/`get(i)` wrapping. Tests: wrap forward/back, single-element ring, index bounds — 12 tests green
- [x] 2.3 Write the starter `config.yaml` with the 6-preset ring — parses via real loader (6 presets)

## 3. Demod backends (command-building pure & tested)

- [x] 3.1 `backends/base.py`: `Backend` interface (`build_command(preset, audio, sdr, aas_dir=None)` → pipeline argv list; declared PCM input format; shared `sdr_flags`/ffmpeg stage)
- [x] 3.2 `backends/analog.py`: `rtl_fm` WBFM → `ffmpeg` to 48k/stereo/256k MP3. Test: exact argv
- [x] 3.3 `backends/hd.py`: `nrsc5 -o - -t raw --dump-aas-files <dir> <freq> <prog>` → `ffmpeg` (-f s16le -ar 44100 -ac 2). Test: exact argv incl. program + AAS dir
- [x] 3.4 `backends/weather.py`: `rtl_fm` NBFM @ 162.xxx → `ffmpeg`. Test: exact argv (recipe to confirm by ear in Phase 10)
- [x] 3.5 Confirm all three normalize to the identical uniform MP3 output args — `test_uniform_output_across_backends`

## 4. Audio fan-out (pure, tested with a fake source)

- [x] 4.1 `audio.py`: register/unregister client queues (bounded, drop-oldest); broadcast loop reads source chunks → all queues; per-client async generator
- [x] 4.2 Tests: two clients both receive; slow client drops oldest, never blocks others; disconnect unregisters cleanly; source-swap continues delivery — 6 tests green

## 5. Arbiter / tuner (logic tested; spawning thin)

- [x] 5.1 `events.py`: minimal async pub/sub — 4 tests green
- [x] 5.2 `tuner.py` (+ `process.py` spawn layer): `tune()` teardown→spawn→repoint fan-out→(re)start metadata→persist+publish; asyncio-lock serialized; supervisor retries on unexpected exit
- [x] 5.3 `state.py`: persist/restore `last_preset_index` — 5 tests green
- [x] 5.4 Tests (injected fake spawn): exclusivity (max 1 backend), serialized rapid switches, teardown stops group, state persisted, resume-last, error→retry — 10 tests green

## 6. HD metadata & album art

- [x] 6.1 `metadata.py`: async-read `nrsc5` stderr → title/artist + `LOT file:` → newest art image; expose current + emit change events; non-HD drains stderr (label-only). (Grounded on real 97.3 nrsc5 output.)
- [x] 6.2 Tests: parse Title/Artist; newest image wins; non-image LOT ignored; non-HD label-only; switch publishes/resets — 7 tests green
- [x] 6.3 Clear/replace metadata on tune-away from HD — `test_switch_resets_previous`

## 7. Web layer (Starlette)

- [x] 7.1 `web/app.py`: `GET /` (UI), `GET /static/…` (StaticFiles mount)
- [x] 7.2 `GET /stream.mp3` → `StreamingResponse` from the fan-out
- [x] 7.3 `GET /api/state`; `POST /api/next|prev|tune/{i}` → new state
- [x] 7.4 `GET /api/events` (SSE, full-state per event); `GET /art/current` (404 → UI default)
- [x] 7.5 Tests via real tuner + injected spawn (TestClient + raw-ASGI for infinite streams): state shape, tune/next/prev, bad index 404, stream/SSE headers, art 404/served — 10 tests green

## 8. Web UI (adapt docs/radio.html)

- [x] 8.1 Port the retro skin into `web/static/index.html`; presets rendered from `/api/state` (real ring)
- [x] 8.2 Preset clicks → `POST /api/tune/{i}`; needle + active button reflect server state; weather → parked needle + "WX" tag
- [x] 8.3 Album-art panel (fills the speaker) with grille fallback; now-playing title/artist
- [x] 8.4 Play/power control drives `<audio>` on `/stream.mp3` (starts on click)
- [x] 8.5 Subscribe to `/api/events`; live-update now-playing, art, active preset (+ one-shot `/api/state` fallback)

## 9. Supervisor & service

- [x] 9.1 `__main__.py`: load config, build ring/tuner, start uvicorn, resume last/default preset, lifespan wires start/stop; uvicorn SIGTERM → lifespan → clean teardown. Smoke test green. Verified live: launches, resumes saved preset, serves UI/API/stream.
- [x] 9.2 `deploy/fmradiod.service` + `deploy/install-service.sh` installed + enabled; verified active, boots default KBCO. Added `uvicorn timeout_graceful_shutdown=5` so long-lived streams don't block SIGTERM — clean stop now ~6s (was ~90s).
- [x] 9.3 `fmtest.service` disabled; verified **no orphaned rtl_fm/nrsc5 after stop** (SDR released cleanly).

## 10. On-device integration & soak (by ear)

- [x] 10.1 HD verified (KBCO streams + title/artist + art); user confirmed **all stations work** by ear. Found: 102.3/105.5 HD didn't lock here → swapped to CPR 90.1 + 103.5 KRFX; weather signal weak (user to investigate transmitter/antenna later).
- [x] 10.2 Rapid switching exercised live (user clicked through presets) + arbiter exclusivity/serialization unit-tested; no overlap/orphans observed.
- [x] 10.3 Multiple clients at once verified (user browser + curl concurrently, both served from one encoder); slow-client drop covered by unit tests.
- [x] 10.4 Soak run — 8 samples: 56.9–58.0 °C, ~1 of 4 cores (95% of one), no active throttle, 325MB available. Healthy.
- [x] 10.5 Reboot test passed: fresh boot → service auto-starts (enabled), resumes last station (103.5), streaming, 1 SDR proc (no orphans).
- [x] 10.6 Add a build-log/blog entry for the headless-core build — `docs/headless-core-build.md`

Deferred to a follow-up change (out of scope here):
- HD album art can show another subchannel's image (nrsc5 dumps all LOT ports) — refine art→program association.
- Weather NBFM recipe / antenna — reception weak at this location.
