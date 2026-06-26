## Why

The appliance now has a screen but no controls: the TFT readout mirrors the daemon, yet the only way to *change* the station is a browser tapping the web API. The Adafruit Mini PiTFT 1.14" carries two buttons already wired to the Pi, and the headless core already exposes `tuner.next()` / `tuner.prev()`. This change closes the loop — physical buttons cycle the preset ring — turning the build into a self-contained tabletop radio you operate without a phone.

## What Changes

- New **button input task** inside `fmradiod`: a long-running async loop that reads the two Mini PiTFT buttons and, on a press, calls the daemon's existing `tuner.next()` / `tuner.prev()`.
  - **Button A (top, GPIO #23) = next preset; Button B (bottom, GPIO #24) = prev preset** (matching the project's "button A = next, B = prev" plan and the curated ring's wraparound).
  - **Edge + debounce detection**: a press is the high→low transition, software-debounced, so holding a button does not spam tunes and contact bounce produces exactly one action.
- The daemon stays the **single source of truth**: buttons only trigger `tune()`; the web UI and the TFT readout already re-render from the EventBus, so a button press is reflected on the panel and in every browser with **no changes to the web-ui or tft-display code**.
- New **`buttons:` config block** with an `enabled` flag (code default **off** so the dev Mac and any button-less Pi run unchanged; the appliance's shipped `config.yaml` turns it on), plus the GPIO pin assignments and debounce interval.
- **Graceful degradation**: if the GPIO library is unavailable or the pins can't be claimed, the daemon logs a warning and runs without buttons — input hardware is never allowed to take down audio (mirrors the display's fail-soft init).
- Wired into the Starlette **lifespan** alongside the tuner and TFT renderer: the input task starts on boot and is cleanly cancelled on `SIGTERM`, releasing the GPIO lines with no orphaned handles.
- Reuses the **Blinka `digitalio` stack already adopted by the display** — no new runtime dependency beyond what the TFT change pinned.

**Non-goals:** long-press / hold gestures or any second action per button (tight scope: press = next/prev only); a software mute/stop/power control; the 3.5 mm local jack output (separate phase); any change to tuning, audio, web-UI, or TFT behavior; debounce via hardware or kernel interrupts (polling is sufficient and testable).

## Capabilities

### New Capabilities
- `button-controls`: read the two on-device GPIO buttons and map presses to preset-ring navigation (`next` / `prev`) on the daemon, debounced and edge-triggered, with the daemon remaining the single source of truth (web UI and TFT mirror the result), degrading gracefully to no-buttons when the GPIO stack or pins are unavailable, and releasing the GPIO lines cleanly on shutdown.

### Modified Capabilities
<!-- None. The button task is a new input that calls the existing tuner.next()/prev(); it adds no requirements to station-tuning (the ring is already navigable forward/back with wraparound), and both the web-ui and tft-display specs already anticipate "the active preset changes on the daemon, including via a future physical button." No spec-level behavior changes elsewhere. -->

## Impact

- **New code**: a `buttons` module in the `fmradiod` package — the input-loop task plus a thin, swappable button-source seam (real GPIO impl + a fake for tests) so the press/debounce logic is unit-testable on the Mac with no hardware (mirrors the display's `Panel`/`FakePanel` seam).
- **Config**: a new `buttons:` section in `config.yaml`; absent/`enabled: false` keeps today's behavior.
- **Lifespan**: the input task is registered in `web/app.py`'s `lifespan` next to the tuner and renderer; on shutdown it is cancelled/awaited and the GPIO lines released. No change to the tuner, fan-out, web routes, or renderer themselves.
- **Pi packages**: none new — reuses `adafruit-blinka` (`board`/`digitalio`), already installed for the TFT.
- **Hardware**: the Mini PiTFT 1.14" buttons sit on GPIO #23 / #24, which do not collide with the panel's pins (CE0 / D25 / D22 / SPI). Confirm assignments on-device against Adafruit's Mini PiTFT example before locking the constants.
- **Downstream**: completes the on-device control surface; the only remaining phase-sized item is the 3.5 mm local jack output.
- **Docs**: a build-notes section (button wiring, GPIO pins, debounce, gotchas) consistent with `docs/tft-display-build.md`, and an update to the running build log.
