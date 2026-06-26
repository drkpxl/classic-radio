## 1. Config & persisted state

- [ ] 1.1 Add a `BluetoothConfig` dataclass + a `bluetooth:` block to `fmradiod/config.py` (`enabled: bool = False`) and `config.yaml` (`enabled: false`), parsed with safe defaults like the `display:`/`buttons:` blocks; unit-test load with/without the block.
- [ ] 1.2 Persist the selected **output mode** (`web`/`bluetooth`) and **last connected device MAC** in `fmradiod/state.py` (StateStore) alongside the preset index, with safe defaults; unit-test save/load round-trip.

## 2. Output-mode seam in the tuner

- [ ] 2.1 Add an `output` mode (`web`|`bluetooth`) to `Tuner`; thread a sink selector into the backends' `build_command` so the pipeline **tail** is either `ffmpeg`→MP3→`FanOut` (web) or `ffmpeg`→PCM(s16le/48k/stereo)→`bluealsa:DEV=<MAC>,PROFILE=a2dp` (bluetooth). The demod stage is unchanged.
- [ ] 2.2 Implement `set_output(mode)` that persists the mode and rebuilds the current preset's pipeline **under the existing tune lock** (no overlap with a tune); publish state on the EventBus.
- [ ] 2.3 In `bluetooth` mode the `FanOut` receives no data (web suspended); in `web` mode behavior is exactly as today. Include `output` in `build_state` (`fmradiod/viewstate.py`).
- [ ] 2.4 Unit-test: output-mode selects the right pipeline tail; switching is serialized; web-mode behavior unchanged; `build_state` reports the mode.

## 3. Bluetooth controller seam (D-Bus)

- [ ] 3.1 Define a thin `BluetoothController` interface in `fmradiod/bluetooth/controller.py` — `power(on)`, `start_discovery()/stop_discovery()`, `devices()`, `pair/connect/disconnect/forget(mac)`, and an async change-event stream — plus a `FakeBluetoothController` (scripted devices/events) for tests.
- [ ] 3.2 Implement `DbusBluetoothController` (`fmradiod/bluetooth/dbus.py`) over the **system bus** `org.bluez` via `dbus-fast` (Adapter1/Device1, ObjectManager for the device list + InterfacesAdded/PropertiesChanged signals); lazy-import `dbus-fast` so the Mac never needs a bus.
- [ ] 3.3 Register a BlueZ `Agent1` with `NoInputNoOutput` capability + request default-agent for just-works pairing; keep **discovery + agent alive for the controller's lifetime** (spike race: device "ages out" if discovery stops before pair).
- [ ] 3.4 Unit-test the controller-driven logic with `FakeBluetoothController`: scan populates the device list, pair/connect/disconnect/forget transition state, and change-events propagate.

## 4. Web API + UI

- [ ] 4.1 Add endpoints in `web/app.py`: `POST /api/output` (`web`|`bluetooth`), `POST /api/bt/scan` (on/off), `POST /api/bt/{pair,connect,disconnect,forget}/<mac>`; include a `bluetooth` block (devices, scanning, connected) and `output` in `/api/state` and the SSE payload.
- [ ] 4.2 Add a **Bluetooth panel** to the web UI (`web/static`): scan toggle, device list with status badges + pair/connect/disconnect/forget, and an **Output selector (Web ⇄ Bluetooth)** — all driven by `/api/state` + the existing SSE stream (one render path).
- [ ] 4.3 Unit-test the endpoints + state shape with the `FakeBluetoothController` (scan toggles, actions call the controller, `/api/output` switches mode, state reflects it).

## 5. Wire into the daemon (lifespan + fail-soft)

- [ ] 5.1 In `build_app()`, construct the controller when `bluetooth.enabled` (lazy import); pass it to `create_app` and give the tuner the means to route to the connected device's `bluealsa` PCM.
- [ ] 5.2 In `web/app.py` `lifespan`: after `tuner.start()` power on the adapter, register the agent, restore the last device (auto-reconnect) + saved output mode; on shutdown stop discovery, unregister the agent, disconnect cleanly — before `tuner.stop()` (symmetric teardown).
- [ ] 5.3 Fail-soft init: `bluetooth.enabled` true but the bus/stack/init fails → log WARNING and run web-only (no crash).
- [ ] 5.4 Wire speaker-drop → auto-fall-back to `web` output (from the controller's disconnect event and/or the pipeline supervisor), surfaced in state.
- [ ] 5.5 Unit-test: `enabled=false` touches no bus; a simulated init failure still starts the app web-only; a simulated speaker drop falls back to `web`.

## 6. Dependencies & deploy

- [ ] 6.1 Add `dbus-fast` to `pyproject.toml`/`requirements.txt`; install into the Pi venv.
- [ ] 6.2 Confirm `deploy/sync.sh` carries `fmradiod/bluetooth/` (rsync dry-run; no exclude matches).

## 7. On-device verification (Pi)

- [ ] 7.1 Install `dbus-fast` into `/root/fmradio/.venv`; run the full suite on the Pi (`pytest`) — all green incl. the new bluetooth/output tests.
- [ ] 7.2 Set `bluetooth.enabled: true` in the Pi config, restart `fmradiod.service`, and verify from the browser: scan shows the Echo; connect; switch Output → Bluetooth ⇒ **radio plays out the Echo**; switch → Web ⇒ browser audio resumes; disconnect/forget/re-pair work; the web UI + TFT track every change; reboot ⇒ auto-reconnect + resume `bluetooth` output; `systemctl stop` leaves no orphans and releases the bus/agent.

## 8. Docs

- [ ] 8.1 Add a build-notes doc (BlueZ D-Bus via dbus-fast, the pairing agent, the output-router seam, gotchas) consistent with `docs/bluetooth-spike.md`; update `docs/roadmap.md` (Bluetooth shipped → only the 3.5 mm jack + mobile UI fixes remain).
