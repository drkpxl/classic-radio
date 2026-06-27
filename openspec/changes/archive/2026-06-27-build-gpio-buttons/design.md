## Context

The `fmradiod` daemon is the single source of truth for what's playing. It already exposes `tuner.next()` and `tuner.prev()` (`fmradiod/tuner.py`), which advance/retreat the curated ring with wraparound, are serialized behind a single `asyncio.Lock`, and publish a state snapshot on the `EventBus`. Both the web UI (via `/api/events` SSE) and the TFT readout (the `TftRenderer` task) already subscribe to that bus and re-derive the full picture with `build_state`, so any preset change — *however triggered* — fans out to both surfaces with no extra wiring. The web-ui and tft-display specs were written anticipating exactly this: "the active preset changes on the daemon (including via a future physical button)."

The hardware is the **Adafruit Mini PiTFT 1.14"**, whose two tactile buttons sit on **GPIO #23 (top)** and **GPIO #24 (bottom)** — distinct from the panel's own lines (CE0/cs, D25/dc, D22/backlight, hardware SPI), so there is no pin contention with the already-shipped display. The buttons are wired active-low: the line idles high (internal pull-up) and reads low while pressed. The display change already brought the **Blinka `digitalio`** stack onto the Pi venv specifically so this change could reuse one GPIO library; `St7789Panel` constructs `digitalio.DigitalInOut(...)` lines today.

The daemon runs under systemd on a DietPi (aarch64) Pi 3A+, started/stopped through Starlette's `lifespan`, and must tear down cleanly on `SIGTERM` with no orphaned hardware handles (the project's standing "no orphans" discipline). Development happens on a Mac with no buttons attached; tests run on the Pi.

The design problem is narrow: stand up a long-running async task that turns button edges into `tuner.next()/prev()` calls — debounced so one press is one action, never blocking the audio loop, never crashing the daemon when no GPIO is present, and unit-testable on a Mac with no hardware.

## Goals / Non-Goals

**Goals:**
- Two physical buttons that cycle the preset ring forward/back, with the result reflected on the web UI and the TFT for free (one source of truth).
- One press = exactly one action; holding does nothing extra; contact bounce is absorbed.
- Reuse the Blinka `digitalio` stack already on the Pi — no new runtime dependency.
- Keep all GPIO work off the critical path so the MP3 fan-out and tune lock are never stalled by input handling.
- Degrade gracefully to no-buttons when the GPIO stack or pins are absent (dev Mac, button-less Pi) — input hardware must never take down audio.
- Make the press/debounce logic pure and unit-testable on the Mac without hardware (mirror the display's `render()` + `Panel`/`FakePanel` seam).
- Clean startup/teardown through the existing Starlette lifespan, symmetric with the tuner and renderer.

**Non-Goals:**
- Long-press / hold gestures or any second action per button (press = next/prev only).
- A software mute / stop / power-off control via the buttons.
- The 3.5 mm local jack output (separate phase).
- Any change to tuning, audio, web-UI, or TFT behavior or layout.
- Kernel edge-interrupt / `gpiod` event wiring — polling is sufficient, simpler, and testable (see Decision 2).

## Decisions

### Decision 1: GPIO stack — reuse Blinka `digitalio` with internal pull-ups
Read each button through `digitalio.DigitalInOut(board.D23 / board.D24)` configured as an input with `Pull.UP`. A pressed button reads `False` (line pulled to ground); released reads `True`. Pin numbers and the next/prev assignment are config-driven named values, not literals buried in code.

- **Why:** This is the exact stack the display already uses and that Adafruit's Mini PiTFT examples use to read these same two buttons, so the pins (#23/#24), pull-up wiring, and active-low convention are documented and battle-tested. Adopting it adds zero new dependencies.
- **Alternatives considered:** `RPi.GPIO` directly (already transitively present) — rejected to keep one GPIO library across display + buttons. `gpiozero` `Button` with its own callback thread — rejected: it spins a background thread whose callbacks would need marshaling back onto the asyncio loop, more moving parts than a poll loop needs.
- **Trade-off:** A read is a cheap, non-blocking memory/SPI-less GPIO read (microseconds), so unlike the panel blit it does **not** need an executor — it runs inline in the async loop.

### Decision 2: Poll + software debounce in an async task (not interrupts)
A single long-running async task polls both lines on a fixed interval (~15–25 ms) and emits a "press" only on a released→pressed edge that is stable across the debounce window. The debounce/edge logic is a **pure state machine** — given a stream of raw (a, b) samples it yields press events — with no hardware or asyncio in it.

- **Why:** Polling at ~20 ms gives sub-frame-imperceptible latency for a human button while being trivially testable: feed the pure state machine a scripted sample sequence (bounce, hold, double-press) and assert the emitted actions. Edge interrupts via Blinka are not reliably exposed and would require a callback thread + loop hand-off for no real benefit at this cadence.
- **Coalescing/serialization:** On a detected press the task issues the action and (because tunes are serialized by the tuner lock and take real time) does not buffer a backlog — presses landing during an in-flight tune are handled by the existing lock; the poll loop naturally drops the firehose rather than queuing dozens of pending tunes. This satisfies the "no unbounded backlog" requirement.
- **Alternative:** `loop.add_reader` / edge IRQ — rejected as above.

### Decision 3: Thin `ButtonSource` seam for hardware isolation + testability
Define a minimal interface — `read() -> (bool, bool)` for the two lines (pressed = True) and `close()` — with one real implementation (`GpioButtonSource`, constructed only on the Pi, lazy-importing Blinka in `__init__`) and a `FakeButtonSource` for tests that returns scripted samples. The input task owns the `ButtonSource`, the pure debounce state machine, and a reference to the `tuner`.

- **Why:** Mirrors the display's proven `Panel`/`FakePanel` split. The whole press→action path is unit-tested on the Mac with no hardware; the only untested seam is the tiny `GpioButtonSource` (two `DigitalInOut` reads + `deinit`).
- **Alternative:** Mock `digitalio` in tests — rejected; testing the pure state machine + fake source is simpler and catches the actual debounce bugs.

### Decision 4: Config-gated, fail-soft initialization
Add a `buttons:` block to `config.py`/`config.yaml` (`enabled`, pin assignments, `debounce_ms`, next/prev mapping). The **code default is off** (`ButtonsConfig()` / a missing block), so a button-less or dev machine runs unchanged; the **appliance's shipped `config.yaml` sets `enabled: true`**. In `build_app`, only when `buttons.enabled` is true do we attempt to lazily import the GPIO stack and construct the source. Any `ImportError`/init/claim failure is logged at WARNING and the input task simply doesn't start — the daemon keeps serving audio, web, and the display.

- **Why:** Keeps Mac dev and any button-less Pi working unchanged, and ensures a missing/contended pin can never crash the radio. Exactly mirrors the display's Decision 5, so the daemon has one consistent fail-soft pattern for optional peripherals.
- **Alternative:** Hard dependency / always-on — rejected; it would break Mac dev and couple audio uptime to a cosmetic peripheral.

### Decision 5: Lifespan integration symmetric with the tuner and renderer
Construct the button source + task holder in `build_app()` alongside `tuner`/`metadata`/`renderer` (only attempting GPIO construction when `buttons.enabled`), pass it into `create_app`, and in `web/app.py`'s `lifespan`: start the poll task after `tuner.start()` (and the renderer start), and on shutdown cancel/await it and `source.close()` before/around `tuner.stop()`.

- **Why:** Matches the established lifecycle pattern (systemd `SIGTERM` → lifespan `finally` → ordered teardown). The buttons slot in next to the renderer as another optional, fail-soft, cleanly-torn-down consumer/producer around the tuner. No new lifecycle concept.

## Risks / Trade-offs

- **Wrong pin assignment (#23/#24) or active-low assumption** → presses do nothing or fire constantly. → Keep pins + polarity as named config-backed constants; verify on-device against Adafruit's Mini PiTFT button example before locking (verification task). Do not treat #23/#24 as final until confirmed on hardware.
- **Switch bounce double-firing** → a single press cycles two presets. → Debounce window in the pure state machine; unit-tested with a bounce sample sequence.
- **Holding a button auto-repeating tunes** → ring spins while held. → Edge-triggered (released→pressed only); a held line emits nothing after the first edge. Unit-tested with a hold sequence.
- **Poll loop or a press handler blocking the event loop** → audio jitter. → Reads are non-blocking microsecond GPIO reads (no executor needed, unlike the SPI blit); `tuner.next()/prev()` already run on the loop and are lock-serialized. The poll `await asyncio.sleep(interval)` keeps the task cooperative.
- **Press backlog during slow tunes** → a pile of queued tunes. → No buffering; the lock serializes and the loop drops the firehose (Decision 2).
- **Blinka/pin claim failing on DietPi** → import/init error. → Fail-soft init (Decision 4); daemon survives headless-of-buttons.
- **Pin contention with the display** → init failure. → #23/#24 are confirmed distinct from CE0/D25/D22/SPI; documented and verified on-device.

## Migration Plan

1. Add a `buttons:` block to `config.py` (dataclass + parse with safe defaults) and document it in `config.yaml` with `enabled: false` (headless stays the in-repo default).
2. Implement the `buttons` module (pure debounce state machine, `ButtonSource` seam + `FakeButtonSource`, `GpioButtonSource` with lazy Blinka import, the input task) with Mac-side unit tests.
3. Wire into `build_app`/`lifespan` symmetric with the renderer; unit-test that `enabled: false` touches no GPIO and that a simulated init failure leaves the app starting normally.
4. Deploy via `deploy/sync.sh`; on the Pi confirm pins #23/#24 against Adafruit's example, then set `buttons.enabled: true` in the Pi's `config.yaml`.
5. Restart `fmradiod.service`; verify next/prev cycle the ring, the web UI + TFT track each press, holding/bounce behave, and `systemctl stop` leaves no orphaned GPIO handles.
6. **Rollback:** set `buttons.enabled: false` (or revert the change) and restart — the daemon returns to verified display-only behavior. The feature is purely additive and gated, so rollback is risk-free.

## Open Questions

- **Exact button pins/polarity** for this Mini PiTFT 1.14" board revision — confirm GPIO #23/#24 and the active-low pull-up convention against Adafruit's current example during on-device verification before locking the constants.
- **Poll interval / debounce window** — start ~20 ms poll with a short debounce; tune after feeling real button latency vs accidental double-fires on the actual switches.
- **Optional later actions** (long-press for stop/mute, hold-both for sleep) are explicitly out of scope here; the edge/debounce state machine should leave room to add a hold timer later without restructuring.
