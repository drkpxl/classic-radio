## Context

The spike (`docs/bluetooth-spike.md`, verdict FIRST-CLASS) settled feasibility: BlueZ + `bluez-alsa` are installed on the Pi, an Echo Pop is paired/trusted, and live radio plays out it via `bluealsa:DEV=<MAC>,PROFILE=a2dp` (SBC, 48 kHz / stereo / S16_LE — identical to `fmradiod`'s output, so no resample). CPU headroom is comfortable (~58% idle under a conservative concurrent load).

`fmradiod` today: `tune(index)` builds one pipeline per preset — `rtl_fm`/`nrsc5` → `ffmpeg` (MP3 256k) → `FanOut` → web — serialized behind a lock, with a per-pipeline supervisor and state broadcast on the `EventBus`. The web UI and TFT both re-derive full state from `build_state` on every bus event. Peripherals (TFT renderer, button input) are constructed in `build_app()`, gated by config, started/stopped in the Starlette `lifespan`, and fail-soft. This change follows those exact patterns.

The user's decisions (locked during brainstorming): **exclusive output** (web **or** BT, one selectable sink), **full in-browser pairing**, **in-UI volume deferred**, BlueZ via **`dbus-fast`** (async, fits the asyncio loop).

## Goals / Non-Goals

**Goals:**
- A selectable, **exclusive** output on the tuner: `web` (MP3 fan-out, unchanged) or `bluetooth` (PCM → `bluealsa` A2DP). Switching reuses the serialized tune/teardown machinery.
- Full Bluetooth device management from the web UI (scan, pair, connect, disconnect, forget, status) via BlueZ over D-Bus.
- Daemon stays the single source of truth — device/output state broadcasts on the EventBus; the panel and TFT mirror it.
- Auto-reconnect the last speaker + restore the saved output mode on boot.
- Fail-soft: no BT stack / no system bus → log + run web-only; never take down audio or web.
- Pure/seam-testable on the Mac with no hardware or bus.

**Non-Goals:**
- In-UI volume (deferred); non-A2DP profiles; multi-speaker; PIN-pairing; the 3.5 mm jack (later, shares the seam).

## Decisions

### Decision 1: Output mode is a tuner pipeline parameter, switched via re-tune
Add `output: "web" | "bluetooth"` to the tuner. The demod stage is identical; only the **encoder tail** differs: `web` → `ffmpeg` MP3 → `FanOut`; `bluetooth` → `ffmpeg` PCM (s16le/48k/stereo) → the `bluealsa` ALSA device. `set_output(mode)` persists the choice and rebuilds the current preset's pipeline under the existing tune lock (so switching output can't overlap a tune). The backends' `build_command` gains a sink/output argument selecting the tail.
- **Why:** reuses the proven serialized pipeline lifecycle (teardown → spawn → supervise) and keeps the SDR-exclusivity guarantees intact; no parallel audio path to reason about. **Alternative:** tee `ffmpeg` to both outputs and gate — rejected (contradicts the exclusive model the user chose and wastes the MP3 encode while on BT).
- **Exclusivity:** in `bluetooth` mode the `FanOut` receives no data, so web listeners are suspended (the modified `audio-streaming` requirement). The web UI, when output is BT, shows "playing on <speaker>" and stops its `<audio>`.

### Decision 2: BlueZ over D-Bus via `dbus-fast` (async), behind a `BluetoothController` seam
A `BluetoothController` interface wraps BlueZ: `power(on)`, `start_discovery()/stop_discovery()`, `devices()` (paired + discovered, with name/connected/paired), `pair(mac)`, `connect(mac)`, `disconnect(mac)`, `forget(mac)`, and an async event stream for device/adapter changes. The real `DbusBluetoothController` uses `dbus-fast` on the **system bus** (`org.bluez`), lazy-imported. A `FakeBluetoothController` (scripted devices/events) backs unit tests.
- **Why:** `dbus-fast` is pure-Python async D-Bus with no glib loop — it lives naturally on our asyncio loop. The seam keeps all BlueZ specifics in one tested-by-fake place and lets the API/UI/state logic be tested on the Mac with no bus.
- **Pairing agent:** register a BlueZ `Agent1` with `NoInputNoOutput` capability + `RequestDefaultAgent` so A2DP speakers pair just-works. The spike's gotcha — *discovery must stay active and the agent registered across the `pair` call* — is handled by keeping the controller's discovery + agent alive for the session, not per-call.
- **Alternative:** shell out to `bluetoothctl` — rejected (brittle parsing, the "device ages out" race, no clean async events).

### Decision 3: Routing to the speaker = the `bluealsa` ALSA device; reconnect surfaces as backend status
`bluetooth` mode's `ffmpeg` writes to `bluealsa:DEV=<MAC>,PROFILE=a2dp` (the connected speaker). If the speaker drops, the `ffmpeg`/ALSA write fails → the existing pipeline supervisor surfaces an error status; the daemon **auto-falls back to `web` output** (so audio isn't silently dead) and the UI/TFT reflect it. The BlueZ controller also attempts reconnect.
- **Why:** reuses the supervisor's crash-detection; fail-back to web is the safe default. **Alternative:** hold BT mode and retry forever — rejected (silent dead air).

### Decision 4: State, persistence, and the EventBus
`build_state` gains a `bluetooth` block (enabled, scanning, devices[], connected device) and the current `output` mode. The BlueZ controller publishes a `type:"bluetooth"`-ish event on the EventBus on any device/adapter change; the SSE handler re-derives full state (one render path, as today). The **last connected device MAC** and the **output mode** persist in the state store and are restored on boot (auto-reconnect + re-select output).
- **Why:** one source of truth; the panel/TFT never diverge. Keeps the established "events are just triggers; re-derive full state" model.

### Decision 5: Config-gated, fail-soft, lifespan-symmetric (as display/buttons)
`bluetooth.enabled` defaults off. Only when enabled does `build_app()` lazily import the controller and construct it; any `ImportError`/bus/init failure logs a WARNING and the daemon runs web-only. The controller starts in `lifespan` after the tuner (power on, register agent, restore last device/auto-reconnect, restore output mode) and stops before the tuner (stop discovery, unregister agent, disconnect cleanly).
- **Why:** identical fail-soft contract to the other optional peripherals; a flaky bus or missing stack can never take down audio/web.

### Decision 6: Web UI panel as additive surface
A new Bluetooth section in the existing page: scan toggle, device list (status badges + pair/connect/disconnect/forget buttons), and an Output toggle (Web ⇄ BT). Driven entirely by `/api/state` + the SSE stream (no new client state model). New endpoints: `GET /api/bt/devices` (in state), `POST /api/bt/scan` (on/off), `POST /api/bt/{pair,connect,disconnect,forget}/<mac>`, `POST /api/output` (`web`|`bluetooth`).
- **Why:** reuses the one-render-path UI model; the BT controls are just more state + more POSTs.

## Risks / Trade-offs

- **D-Bus / BlueZ async complexity** → isolate entirely behind `BluetoothController`; unit-test the API/UI/state with the fake; keep the real controller thin. → On-device verification covers the real bus.
- **Pairing race (device ages out)** → keep discovery + the agent alive for the controller's lifetime, not per-call (spike finding).
- **Speaker drops mid-playback** → supervisor surfaces it; auto-fall-back to web output; controller retries reconnect.
- **`dbus-fast` on the Mac** → it imports fine but there's no `org.bluez`; `bluetooth.enabled` is off on the Mac and init is fail-soft, so nothing touches the bus. Tests use the fake.
- **Output switch gap** → rebuilding the pipeline tail causes a brief (~1–2 s) audio gap on switch, same as a tune; acceptable and expected.
- **Exclusivity surprises a web listener** → documented behavior (the user chose exclusive); the UI clearly shows when output is on the speaker.
- **CPU** → the spike showed comfortable headroom; BT mode drops the MP3 encode, so it's lighter than web mode + tap was.

## Migration Plan

1. Add `dbus-fast` to deps; `bluetooth:` config block (off in repo until verified) + persisted output/device in the state store.
2. Build the output-mode seam in the tuner/backends; unit-test pipeline selection.
3. Build `fmradiod/bluetooth/` (seam + fake + `DbusBluetoothController` + agent); unit-test with the fake.
4. Wire API + UI + EventBus; unit-test endpoints/state with the fake.
5. Lifespan wiring + fail-soft; unit-test enabled=false touches no bus and init-failure still starts.
6. Deploy; on the Pi set `bluetooth.enabled: true`, restart, and verify end-to-end (scan/pair/connect from the browser, switch output to BT → radio out the Echo, switch back to web, auto-reconnect on reboot, clean teardown). The Echo is already paired from the spike.
7. **Rollback:** `bluetooth.enabled: false` + restart → web-only, verified behavior. Purely additive + gated.

## Open Questions

- Exact `dbus-fast` object/interface calls for `org.bluez` Adapter1/Device1 + `Agent1` registration — resolve at apply against the installed BlueZ 5.82.
- Whether the persisted output/last-device lives in `state.json` (alongside the preset index) or the config — lean `state.json` (runtime state, already there).
- Discovery lifetime/UX: continuous scan while the panel is open vs a timed scan button — start with an explicit on/off scan toggle.
