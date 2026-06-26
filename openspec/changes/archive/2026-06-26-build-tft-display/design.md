## Context

The `fmradiod` daemon is the single source of truth for what's playing. It already broadcasts every state change over a tiny pub/sub `EventBus` (`fmradiod/events.py`), and the web UI mirrors that state via SSE: the SSE handler ignores each event's payload and instead re-derives the **full** current picture with `build_state(tuner, metadata)` (`fmradiod/web/app.py`), giving the browser one render path. That `build_state` dict already carries everything a tuner readout needs — `preset.{label,mode,freq,hd_program}`, `status` (`acquiring`/`no_signal`/`playing`), and `now_playing.{title,artist}`.

The hardware is an **Adafruit Mini PiTFT 1.14"** — a 240×135 IPS panel on an **ST7789** controller, driven over the Pi's hardware SPI bus with a handful of GPIO control lines and a backlight pin. The board also carries two buttons, but those are out of scope here (next change). The daemon runs under systemd on a DietPi (aarch64) Pi 3A+, started/stopped through Starlette's `lifespan`, and must tear down cleanly on `SIGTERM` with no orphaned hardware handles. Development happens on a Mac with no panel attached, and tests run on the Pi.

The design problem is therefore narrow: stand up a long-running async task that turns the same `build_state` snapshot the web UI consumes into pixels on the ST7789 — without blocking the audio fan-out, without crashing the daemon when no panel is present, and in a way that's unit-testable on a Mac with no hardware.

## Goals / Non-Goals

**Goals:**
- A read-only on-device tuner readout that mirrors the daemon's live state with no perceptible lag after a tune or metadata change.
- Reuse the existing `EventBus` + `build_state` path so the TFT and the web UI can never disagree (one source of truth).
- Keep all blocking SPI/draw work off the asyncio event loop so the MP3 fan-out is never stalled by a screen refresh.
- Degrade gracefully to today's headless behavior when the panel/libraries are absent (dev Mac, panel-less Pi) — the screen must never take down audio.
- Make the render logic (state → image) pure and testable on the Mac without hardware.
- Clean startup/teardown through the existing Starlette lifespan, symmetric with `tuner.start()/stop()`.

**Non-Goals:**
- GPIO preset buttons (separate change; this renderer is read-only).
- Album art on the TFT (project scope: the panel is a tuner readout).
- Brightness automation / ambient dimming / sleep-on-idle (full-on backlight first; revisit later).
- Any change to tuning, audio, or web-UI behavior.
- Animations beyond what's needed to make long titles legible and `no_signal` obvious.

## Decisions

### Decision 1: Driver stack — Adafruit `rgb_display` (ST7789) + Blinka + Pillow
Use `adafruit-circuitpython-rgb-display` (the `adafruit_rgb_display.st7789.ST7789` class), `adafruit-blinka` (provides `board`/`busio`/`digitalio` on the Pi), and `Pillow` for composing the frame as an RGB `Image`.

- **Why:** This is the exact stack Adafruit's own Mini PiTFT guide and `rgb_display_minipitft.py` example use, so the 240×135 offsets, rotation, and wiring are documented and battle-tested. Pillow gives a clean, testable "draw to an image, then blit" model. Blinka's `digitalio` is also what the *next* change needs to read the two buttons, so we adopt one GPIO stack now instead of mixing libraries later.
- **Alternatives considered:** `luma.lcd` + `luma.core` (lighter, no Blinka dependency) — rejected to stay on the vendor-supported path the hardware guide documents and to share a GPIO stack with the buttons change. Raw `spidev` hand-rolled ST7789 init — rejected as needless risk for a well-supported panel.
- **Trade-off:** Blinka does board auto-detection at import; on DietPi it may need `BLINKA_FORCEBOARD`/`BLINKA_FORCECHIP` env hints if detection misses (mitigated below). These deps land only on the Pi venv; the Mac never imports them (see Decision 5).

### Decision 2: Render on EventBus events, re-deriving full state (mirror the SSE path)
The renderer subscribes via `bus.events()` and, on **every** event, ignores the payload and re-derives the complete picture from `build_state(tuner, metadata)` — identical to the SSE handler. It renders once immediately on start (so the panel isn't blank before the first event), then re-renders per event.

- **Why:** One render path shared with the web UI guarantees the TFT and browser never diverge, and it sidesteps reasoning about partial event payloads (the bus emits `type:"state"` and `type:"now_playing"` dicts separately). It's event-driven, so it's idle when nothing changes.
- **Refactor:** `build_state` currently lives in `web/app.py`. Lift it (or a TFT-shaped subset that drops the art URL) into a neutral module both the web layer and the renderer import, so the display module doesn't import the web app. Small, mechanical, keeps layering clean.
- **Coalescing:** A tune can emit a burst (`state` then `now_playing`...). After waking on an event, drain any immediately-available queued events and render only the latest snapshot, so SPI isn't thrashed.
- **Alternative:** Poll `build_state` every N ms — rejected (laggy and wasteful; the bus already exists).

### Decision 3: Do blocking SPI work off the event loop, serialized
Composing the Pillow image is cheap; pushing ~64 KB over SPI (`disp.image(...)`) blocks for tens of ms. Run the blit via `loop.run_in_executor(panel_executor, panel.show, image)` using a **dedicated single-worker `ThreadPoolExecutor`**. The single worker serializes all panel access (no torn frames) and isolates the blocking call from the fan-out pump and tune lock.

- **Why:** The audio path (`FanOut.pump`) and the tune lock live on the same event loop; a synchronous SPI flush there would jitter audio. One executor thread keeps panel writes ordered and off-loop.
- **Alternative:** Async SPI — not meaningfully available through this driver; the executor is the idiomatic asyncio escape hatch.

### Decision 4: Thin `Panel` seam for hardware isolation + testability
Define a minimal panel interface — `show(image)`, `close()`, and `size` — with one real implementation (`St7789Panel`, constructed only on the Pi) and the render step as a **pure function** `render(state, size) -> PIL.Image`. The `TftRenderer` owns the state source (`tuner`, `metadata`), the pure `render`, and a `Panel`.

- **Why:** Pillow runs fine on the Mac, so `render(state, size)` is unit-tested with no hardware — assert that a `no_signal` state draws the "NO SIGNAL" banner, that HD subchannel shows `HD1`, that a long title is truncated, that a weather preset shows `WX`/frequency rather than an FM dial, etc. Hardware (`St7789Panel`) is the only untested seam and it's tiny.
- **Alternative:** Mock the SPI driver in tests — rejected; testing the pure image is simpler and catches the actual layout bugs.

### Decision 5: Config-gated, fail-soft initialization
Add a `display:` block to `config.yaml` (`enabled`, `rotation`, `brightness`). The **code default is off** (`DisplayConfig()` / a missing block), so a panel-less or dev machine runs headless; the **appliance's shipped `config.yaml` sets `enabled: true`**. In the lifespan, only when `display.enabled` is true do we *attempt* to import the driver stack and init the panel. Any `ImportError`/init/hardware failure is logged at WARNING and the renderer simply doesn't start — the daemon keeps serving audio and web.

- **Why:** Keeps Mac dev and any panel-less Pi working unchanged, and ensures a flaky panel or a Blinka detection miss can never crash the radio. The import is lazy (inside the enabled branch) so the heavy Pi-only deps are never touched on the Mac.
- **Alternative:** Hard dependency, always-on — rejected; it would break Mac dev and couple audio uptime to a cosmetic peripheral.

### Decision 6: Lifespan integration symmetric with the tuner
Construct the renderer in `build_app()` alongside `tuner`/`metadata`/`bus`, and in `web/app.py`'s `lifespan`: start the render task after `tuner.start()`, and on shutdown cancel/await it and `panel.close()` before/around `tuner.stop()`. The task wraps its loop so cancellation is clean (await the in-flight executor blit, then close the panel and clear the screen).

- **Why:** Matches the established lifecycle pattern; systemd `SIGTERM` → lifespan finally → ordered teardown, no orphaned SPI/GPIO handles (consistent with the daemon's existing "no SDR orphans" discipline).

### Decision 7: Layout for 240×135 landscape
Render in landscape (rotation 90, the documented Mini PiTFT orientation), composing zones top-to-bottom:
- **Header:** large frequency + a mode badge (`FM` / `HD` / `WX`) and an `HD1`/`HD2` chip when `hd_program` is set.
- **Status:** a clear `acquiring` / `NO SIGNAL` / playing indicator (color-coded) so a dead station reads at a glance.
- **Preset label:** the configured station name.
- **Now playing:** title + artist when present (HD); blank/station fallback for analog/weather. Long strings are ellipsized (mirroring the web UI's title behavior); a scrolling marquee is an optional later refinement, not required.

Fonts come from a font file shipped in the package (or Pillow's bundled DejaVu) — never system fonts — so rendering is deterministic across Mac and Pi.

## Risks / Trade-offs

- **Blinka board detection on DietPi/aarch64 may fail at import** → fail-soft init (Decision 5) means the daemon survives; document setting `BLINKA_FORCEBOARD`/`BLINKA_FORCECHIP` and verify import on-device early.
- **Wrong ST7789 offsets/rotation → shifted or garbled image** (the classic 1.14" gotcha: it needs non-zero column/row offsets, commonly `x_offset≈53`, `y_offset≈40`, rotated 90°) → keep offsets/pins as named constants, and verify against Adafruit's current `rgb_display_minipitft.py` on the device (verification task). Do not treat the constants below as final until confirmed on hardware.
- **SPI not enabled on the Pi** (`dtparam=spi=on`) → init fails → graceful degradation; documented as a one-time setup step + reboot.
- **A slow/blocking blit jittering audio** → dedicated single-worker executor keeps it off the loop and serialized (Decision 3); coalescing bounds refresh frequency (Decision 2).
- **Heavy Pi-only deps leaking into Mac dev / CI** → lazy import inside the `enabled` branch; tests exercise only the pure `render()` and a fake `Panel`.
- **Long HD titles overflow the 240 px width** → ellipsize first; marquee deferred.
- **Backlight handling** → start with full-on (simple GPIO/PWM set from `brightness`); ambient dimming/sleep is a non-goal.

## Migration Plan

1. Enable SPI on the Pi (`dtparam=spi=on` in `/boot/config.txt`) and reboot — one-time.
2. Add `adafruit-circuitpython-rgb-display`, `adafruit-blinka`, `Pillow` to `requirements.txt`/`pyproject.toml`; install into `/root/fmradio/.venv`.
3. Deploy via `deploy/sync.sh`; set `display.enabled: true` (+ rotation/brightness) in the Pi's `config.yaml`.
4. Restart `fmradiod.service`; verify the readout tracks tunes and HD metadata; confirm clean stop (no GPIO/SPI orphans) on `systemctl stop`.
5. **Rollback:** set `display.enabled: false` (or revert the change) and restart — the daemon returns to verified headless behavior. The feature is purely additive and gated, so rollback is risk-free.

## Open Questions

- **Exact pins/offsets** for this specific Mini PiTFT 1.14" board revision — confirm `dc`, `backlight`, `cs`, `reset` GPIO assignments and the `x_offset`/`y_offset`/`rotation` against Adafruit's current example during on-device verification before locking the constants.
- **Backlight control:** simple on/off vs PWM brightness — start on/off mapped from `brightness`; PWM only if needed.
- **Long-title treatment:** ellipsis (chosen for v1) vs marquee — revisit after seeing real HD titles on the panel.
- **Refresh cadence ceiling:** whether to add a minimum interval between blits beyond event coalescing — decide after observing real event bursts during a tune.
