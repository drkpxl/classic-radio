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
already noted in `pi-flash-setup.md`. **Reuses the output-router seam built for
Bluetooth** (the tuner's `output` mode) — the jack becomes a third sink alongside
`web` and `bluetooth`, so this is mostly a new ALSA tail + a UI/control option.
This is now the only remaining phase-sized feature.

<!-- Bluetooth speaker output shipped — see the Done list above and
     docs/bluetooth-spike.md (derisk) + docs/bluetooth-output-build.md (build). -->

---

## 🟡 Remaining — known bugs / limitations

- **Mobile web-UI fixes** *(requested)* — the retro web UI needs responsive/touch
  polish for phones (layout, tap targets, viewport). Specifics TBD with the user.
- **Bluetooth audio can skip/buffer** — observed in the field; CPU is fine (htop
  reasonable) and the web stream is smooth, so it's the **A2DP link**, not software:
  likely RF range and/or **BT ↔ 2.4 GHz Wi-Fi coexistence** on the shared CYW43455
  (flagged as a spike risk). Mitigations: move the speaker closer, put Wi-Fi on the
  5 GHz band, or use the (deferred) 3.5 mm jack. Not a code bug.
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
