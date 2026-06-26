# FM Radio — Roadmap & Backlog

Single source of truth for what's built and what's left. The per-phase build logs
(`headless-core-build.md`, `tft-display-build.md`, …) stay as historical records;
forward-looking work lives **here** so it stops drifting across change docs.

Hardware recap (constrains everything below): Raspberry Pi 3A+ (DietPi, aarch64) ·
single USB (taken by the **Nooelec RTL-SDR**) · **onboard Bluetooth 4.2 + Wi-Fi**
(CYW43455) · Adafruit Mini PiTFT 1.14" (240×135 ST7789 + 2 buttons) · 3.5 mm jack.
Because the lone USB port is occupied by the SDR, **onboard Bluetooth is the only
BT path** — there's no spare port for a dongle.

---

## ✅ Done (archived OpenSpec changes)

- **`derisk-hd-radio`** — HD Radio feasibility spike → verdict: **first-class**.
- **`build-headless-core`** — `fmradiod` daemon: SDR arbiter, 3 backends → uniform
  MP3 fan-out, web UI + control API + SSE, YAML preset ring, resume-on-boot,
  systemd service. Deployed & verified on the Pi.
- **`build-tft-display`** — read-only Mini PiTFT tuner readout mirroring the daemon
  via the EventBus. Deployed & verified on hardware.
- **`build-gpio-buttons`** — the two Mini PiTFT buttons (GPIO #23/#24) drive
  `tuner.next()/prev()`; web UI + TFT mirror the result for free. Deployed &
  verified on hardware (top→next, bottom→prev, clean single-step debounce).
  Build log: `docs/gpio-buttons-build.md`. *(pending OpenSpec archive)*

---

## 🔵 Remaining — phase-sized features

### 1. 3.5 mm local jack output  *("Phase 3")*
Make the radio audible from the Pi's own headphone jack, not just the web stream.
Needs a **local playback path** off the same demod/encoder (e.g. `ffmpeg → ALSA`)
plus daemon/web control to pick the active output. `dtparam` audio enable is
already noted in `pi-flash-setup.md`. **Related to the Bluetooth item below — both
are "local output sinks" and should share one output-routing abstraction.**

### 2. Bluetooth speaker output  *(new — requested)*
Stream the live radio to a paired Bluetooth speaker, managed **from the web UI**,
using open-source Bluetooth tooling.

- **Scope:** scan / pair / connect / disconnect a BT speaker from the web UI;
  choose the active audio output (web stream · 3.5 mm jack · BT speaker); show
  connection status; remember the last speaker and auto-reconnect on boot.
- **Open-source tooling (Linux/Pi):**
  - **BlueZ** — the Linux Bluetooth stack; discovery + pairing via `bluetoothctl`
    or its D-Bus API (the daemon would drive the D-Bus API rather than shell out).
  - **A2DP audio routing** — one of:
    - **bluez-alsa (`bluealsa`)** — lightweight A2DP sink with no PulseAudio/PipeWire
      dependency; well-suited to a headless appliance (likely first choice).
    - **PipeWire + WirePlumber** — heavier but increasingly the modern default;
      richer routing if we also want the 3.5 mm sink managed the same way.
  - Uses the Pi 3A+'s **onboard BT** (no USB dongle — the USB port is the SDR's).
- **Architecture fit:** add a BT-management module to `fmradiod` (D-Bus to BlueZ),
  new web API endpoints + UI controls, and a local decode→sink path
  (`ffmpeg → ALSA → bluealsa A2DP`). The daemon stays the single source of truth;
  output selection rides the same EventBus so the TFT/web reflect it.
- **Decisions locked (2026-06-26):** exclusive output (web **or** BT, one at a
  time — a selectable sink on the tuner that later also absorbs the 3.5 mm jack);
  **full in-browser pairing** (scan/pair/trust/forget + a `NoInputNoOutput` BlueZ
  agent); in-UI **volume deferred** to v2 (use the speaker's buttons); `fmradiod`
  talks to BlueZ over D-Bus via **`dbus-fast`** (async). Split into **two changes**:
  a derisk spike first, then the build.
- **`derisk-bluetooth-audio` — SCAFFOLDED** (`openspec/changes/derisk-bluetooth-audio/`,
  apply-ready): prove A2DP on this Pi (`bluez-alsa` primary, **PipeWire fallback
  pre-authorized**), measure CPU/latency under concurrent demod load, produce a
  go/no-go verdict + tooling choice. Mirrors `derisk-hd-radio`. **Then**
  `build-bluetooth-output`: output-router + BlueZ D-Bus controller + in-browser
  pairing UI + auto-reconnect.
- **Open risks the spike resolves:** `bluealsa` availability on Debian 13; onboard
  BT bring-up on DietPi (rfkill/firmware); BT ↔ 2.4 GHz Wi-Fi coexistence; CPU
  headroom for demod + SBC encode on 512 MB / quad-A53.

---

## 🟡 Remaining — known bugs / limitations

- **Mobile web-UI fixes** *(requested)* — the retro web UI needs responsive/touch
  polish for phones (layout, tap targets, viewport). Specifics TBD with the user.
- **HD album-art bleed** — `nrsc5` dumps LOT image files for *all* subchannels, so
  the "newest image" heuristic can briefly show another program's art. Needs proper
  art→program association. *(web-UI correctness)*
- **Weak NOAA weather reception** here — NBFM recipe / antenna to investigate
  (may be antenna/location, not software).

## 🟢 Remaining — TFT display polish (deferred non-goals)

- Marquee scrolling for long HD titles (v1 ellipsizes).
- PWM backlight brightness (v1 is on/off).
- Ambient dimming / sleep-on-idle.
- Refresh-cadence ceiling beyond event coalescing (only if real bursts warrant it).

## ⚪ Out of scope (dropped by decision — not backlog)

AM · police/trunked · satellite/APT.
