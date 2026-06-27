## Why

The `derisk-bluetooth-audio` spike proved A2DP output is **first-class** on this Pi via `bluez-alsa` (live HD radio played out a real speaker at ~58% CPU idle, no dropouts, no resample). Now ship the user-facing feature: **pair and manage a Bluetooth speaker from the web UI and route the radio to it**, so the tabletop radio is actually audible in the room without a browser playing audio. This is the last audio-output feature besides the 3.5 mm jack, and it builds directly on the proven path (the Pi already has the stack installed and a speaker paired).

## What Changes

- **Exclusive output router** on the tuner: an **output mode** — `web` (today's MP3 fan-out) or `bluetooth` — with exactly one active at a time, selectable via API/UI. `bluetooth` routes the demod audio to the connected speaker through `bluealsa` A2DP (PCM, 48 kHz / stereo / S16_LE — no resample). Switching output rebuilds the current preset's pipeline tail, reusing the serialized `tune()` machinery; the demod stage is unchanged. This same seam later absorbs the 3.5 mm jack as a third mode.
- **New `fmradiod/bluetooth/` package** — a BlueZ controller over D-Bus using **`dbus-fast`** (async): adapter power, discovery start/stop, the device list (paired + nearby), pair / connect / disconnect / forget, and live connection status; plus a **`NoInputNoOutput` pairing agent** so A2DP speakers pair "just-works". Behind a thin `BluetoothController` seam with a `FakeBluetoothController` for tests (mirrors the `Panel`/`ButtonSource` pattern).
- **Web UI Bluetooth panel** — a scan toggle, a device list with **pair / connect / disconnect / forget**, live status, and the **Output selector (Web ⇄ Bluetooth)**. New REST endpoints; device + output state ride the existing **EventBus → SSE** path so the panel (and TFT) stay in sync the same way everything else does.
- **Auto-reconnect** the last connected speaker on boot and restore the saved output mode.
- **Config** `bluetooth:` block (`enabled`, default **off**) + persisted output mode / last device.
- **Fail-soft + lifespan** integration symmetric with the display/buttons: enabled-only, lazy import; any D-Bus/bus/stack failure logs a warning and the daemon runs without Bluetooth (web output unaffected).

**Non-goals:** in-UI volume control (deferred — use the speaker's buttons / AVRCP is a fast-follow); the 3.5 mm local jack (separate phase, shares this output-router seam); non-A2DP profiles (HFP/AVRCP-transport); simultaneous multi-speaker output; pairing speakers that require a PIN.

## Capabilities

### New Capabilities
- `bluetooth-output`: discover, pair, connect, and manage an A2DP Bluetooth speaker from the web UI via BlueZ; route the live radio to it as an **exclusive, selectable output** (web ⇄ bluetooth); auto-reconnect the last speaker on boot; mirror all device/output state through the EventBus; and degrade gracefully to web-only when the Bluetooth stack or system bus is unavailable.

### Modified Capabilities
- `audio-streaming`: the single-encoder MP3 fan-out serves listeners **only when the `web` output is selected**; selecting the `bluetooth` output suspends the fan-out (exclusive output, one sink at a time).

## Impact

- **New code**: `fmradiod/bluetooth/` (D-Bus controller, pairing agent, `BluetoothController` seam + fake); an output-mode parameter in `fmradiod/tuner.py` (+ backends' pipeline tail); web API endpoints + a UI panel + the output selector in `web/`.
- **Config / state**: a `bluetooth:` block in `config.yaml`; persisted output mode + last-device in the state store (resume across reboot).
- **Dependencies**: add **`dbus-fast`** (pure-Python async D-Bus; installs and imports fine on the Mac, where it just has no system bus → fail-soft). `bluez` + `bluez-alsa` are already installed on the Pi (from the spike).
- **Pi runtime**: the daemon writes PCM to `bluealsa:DEV=<MAC>,PROFILE=a2dp`; `bluealsa.service` (a2dp-source) is already enabled.
- **Downstream**: the output-router seam is the foundation the future 3.5 mm jack reuses (a third output mode).
