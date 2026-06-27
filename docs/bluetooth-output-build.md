# Build Log — Bluetooth speaker output

**Goal:** ship the user-facing feature on top of the proven spike — pair/manage a
Bluetooth speaker **from the web UI** and route the live radio to it.

**Result:** ✅ **done & verified on hardware.** Pair/scan/connect from the browser,
switch output Web ⇄ Bluetooth, radio plays out the Echo (user-confirmed), reboot
auto-reconnects + resumes the speaker, clean fail-soft. Mac suite 155 / Pi 152+1skip.

## What it is

An **exclusive, selectable audio output** on the tuner — `web` (the MP3 fan-out,
unchanged) or `bluetooth` (the demod audio piped to a connected A2DP speaker). The
daemon manages BlueZ over D-Bus and stays the single source of truth; the web UI and
TFT mirror it via the existing EventBus/SSE.

- **Dial speaker icon** (replacing the vestigial "AM kHz" indicator): tap it to open a
  scan/select modal; when a speaker is connected it shows 🔊 + the speaker's name.
- **Modal**: Scan, a device list (Pair / Connect / Disconnect / Forget), and a
  **Web ⇄ On-speaker** toggle. Connecting a speaker auto-routes audio to it.
- **Auto-reconnect** the last speaker + resume `bluetooth` output on boot.

## How it's built (the seams)

- `fmradiod/tuner.py` — an `output` mode (`web`/`bluetooth`). The demod stage is
  unchanged; only the pipeline **tail** differs: web → `ffmpeg`→MP3→`FanOut`;
  bluetooth → a 3-stage `source | ffmpeg(-f wav) | aplay -D bluealsa:DEV=<MAC>,PROFILE=a2dp`
  (the proven spike path; SBC 48k/stereo, no resample). `set_output()` rebuilds under
  the tune lock. Backends gain an `alsa_sink` arg in `build_command`.
- `fmradiod/bluetooth/` — a thin `BluetoothController` seam: `FakeBluetoothController`
  for tests, `DbusBluetoothController` over the system bus via **`dbus-fast`** (lazy
  import; Adapter1/Device1 + ObjectManager device cache + a `NoInputNoOutput` agent for
  just-works pairing).
- `web/app.py` — endpoints `POST /api/output/{mode}`, `/api/bt/scan/{state}`,
  `/api/bt/{pair,connect,disconnect,forget}/{mac}`; `build_state` carries `output` + a
  `bluetooth` block; lifespan powers on the adapter, registers the agent, restores the
  last speaker, and tears down cleanly. **Config-gated + fail-soft** like the
  display/buttons (`bluetooth.enabled`, default off; D-Bus/bus failure → web-only).

Config (`config.yaml`):

```yaml
bluetooth:
  enabled: true     # A2DP output via BlueZ + bluez-alsa
```

## Gotchas worth remembering

- **Pairing needs an active scan + the agent in one session** (spike finding) — the
  controller holds discovery + a registered `NoInputNoOutput` agent for its lifetime.
- **`connect` on an auto-reconnected speaker raises "Already Connected"** — tolerate it
  and decide from the controller's refreshed state, not the call's return.
- **The A2DP transport isn't openable for a second or two right after a restart** even
  though BlueZ reports the device connected. So: (a) the supervisor **retries the BT
  pipeline** (with backoff) before falling back to web, and (b) a fallback **does NOT
  persist `web`** — the persisted *intent* stays `bluetooth` so a reboot retries the
  speaker. Boot restore routes immediately if the speaker's up, else background-retries.
- **Exclusive output**: in `bluetooth` mode the web fan-out is suspended (the browser
  `<audio>` goes silent; the page is a remote). Switching back to `web` resumes it.
- **Speaker drop** → after retries, runtime falls back to `web` so audio is never dead;
  the controller reconciles the connection and the user can re-select.
- **`deploy/sync.sh` overwrites `config.yaml`** on the Pi — so `bluetooth.enabled: true`
  must be committed in the repo (it is) to survive a sync; `state.json` (the persisted
  output/last-device) is sync-excluded and survives.

## Verdict

Shipped. Remaining roadmap: the **3.5 mm jack** (reuses this output-router seam as a
third mode) and **mobile web-UI fixes**.
