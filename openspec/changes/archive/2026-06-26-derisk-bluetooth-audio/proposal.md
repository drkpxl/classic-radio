## Why

Bluetooth speaker output is one of the two remaining features (with the 3.5 mm jack). But unlike the GPIO buttons — which built on already-proven seams — Bluetooth is **from-scratch on this Pi**: there is no BlueZ, no A2DP routing stack, and **no local audio sink at all** (`aplay -l` reports no cards). The single biggest unknown is whether this 512 MB Pi 3A+ can sustain **A2DP playback of the live radio over its onboard Bluetooth**, *concurrently with the SDR demod* (`nrsc5` already uses ~1 core), with acceptable latency and stability — and **which open-source tool** does it best (`bluez-alsa` vs PipeWire). That answer governs the whole `build-bluetooth-output` design (the exclusive output-router + in-browser pairing UI), so we must settle it **before** building a UI on an unproven path. This mirrors the HD-radio feasibility spike that preceded the full app.

## What Changes

- Confirm the Pi's **onboard Bluetooth controller** comes up (power, `rfkill`, firmware) — the single USB port is the SDR's, so a dongle is not an option.
- Install **BlueZ** (`bluetoothd`) + **`bluez-alsa`** on the Pi and bring up the A2DP profile.
- **Pair + trust a real Bluetooth speaker** over SSH (`bluetoothctl`); document the steps.
- Route the **live radio's demod audio** (`rtl_fm`/`nrsc5` → `ffmpeg` → ALSA `bluealsa` A2DP PCM) to the speaker while a station is tuned; confirm sound.
- **Measure CPU / RAM / SoC temperature** under sustained **concurrent** load (demod + A2DP/SBC encode) and note **latency and reconnect stability** — the gating metrics.
- If `bluez-alsa` won't behave on Debian 13, **fall back to PipeWire + WirePlumber + `libspa-0.2-bluetooth`** (pre-authorized — no pause at the gate) and repeat the test.
- Record a go/no-go **verdict — first-class / best-effort / drop — plus the chosen tooling**, to govern `build-bluetooth-output`.

**Non-goals:** the output-mode seam in `fmradiod`, the web UI, the BlueZ D-Bus controller, the pairing agent, auto-reconnect, and in-UI volume — all belong to the `build-bluetooth-output` change. This is a focused feasibility spike that leaves behind a reusable setup/test script and a documented decision.

## Capabilities

### New Capabilities
- `bluetooth-audio`: pair an A2DP Bluetooth speaker to the Pi via BlueZ over the onboard Bluetooth radio, route the live radio audio to it through an open-source A2DP path (`bluez-alsa` or PipeWire), measure resource headroom under concurrent demod load, and produce a documented feasibility verdict + tooling choice that governs the full Bluetooth-output build.

### Modified Capabilities
<!-- None — this is a feasibility spike with no fmradiod code or spec changes. The output-router requirement (web ⇄ bluetooth) and the in-browser pairing requirements land in the follow-up `build-bluetooth-output` change. -->

## Impact

- **Pi packages**: `bluez` + `bluez-alsa` (Debian `bluez-alsa-utils` if available, else build from source); on the fallback path `pipewire` + `wireplumber` + `libspa-0.2-bluetooth`. `alsa-utils` (`aplay`) and `ffmpeg` are already installed.
- **Radio hardware**: the onboard CYW43455 (BT 4.2 + 2.4/5 GHz Wi-Fi). Wi-Fi is how we SSH/serve, so **BT + 2.4 GHz Wi-Fi coexistence** on the one chip is itself a thing to watch.
- **Concurrency**: unlike the HD spike (which had a single-SDR *conflict* with analog), Bluetooth output runs **alongside** the demod — this spike specifically stresses **concurrent CPU** (`nrsc5` + A2DP/SBC encode) on the 512 MB / quad-A53 board. Note the production model is *exclusive* (web **or** BT), so the realistic BT-mode load is demod + ffmpeg-to-PCM + SBC encode, **without** the MP3 encode.
- **Outputs**: a feasibility decision (recorded in this change), a reusable setup/test script on the Pi, and a build-log/blog entry.
- **Downstream**: directly informs `build-bluetooth-output` — the confirmed tooling, the exact ALSA sink the output-mode seam will target, and the CPU budget for the exclusive-output design.
