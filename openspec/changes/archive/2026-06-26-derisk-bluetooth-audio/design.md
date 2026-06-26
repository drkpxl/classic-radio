## Context

The `fmradiod` daemon is built and verified: `rtl_fm`/`nrsc5` → `ffmpeg` (MP3 256k) → a persistent fan-out serves the web. There is **no local audio output** yet — `aplay -l` shows no cards, and the 3.5 mm jack is deferred. Bluetooth is the first local sink we'd add, and on this Pi the whole stack is absent (no BlueZ, no PipeWire/PulseAudio, no `bluez-alsa`). The Pi 3A+ has **onboard Bluetooth 4.2** (CYW43455, shared with Wi-Fi); the single USB port is the RTL-SDR's, so onboard BT is the only path.

`nrsc5` already runs at ~1 of 4 cores during HD decode. The production Bluetooth feature will use an **exclusive** output model (audio goes to the web stream **or** the BT speaker, not both), so the realistic BT-mode workload is: demod + `ffmpeg` decode/resample to PCM + an A2DP **SBC encode** — *without* the MP3 encode. The unknown is whether that sustains cleanly on 512 MB / quad-A53 over onboard BT, and which open-source tool does the A2DP job most reliably on Debian 13. This spike settles that before the full build, exactly as `derisk-hd-radio` did for HD.

## Goals / Non-Goals

**Goals:**
- Bring up the onboard BT controller and a working BlueZ + A2DP stack on the Pi.
- Pair + trust a real Bluetooth speaker and prove **the live radio plays out of it**.
- Quantify CPU / RAM / temperature under **concurrent demod + A2DP**, and note latency and reconnect behavior — the gating metrics.
- Choose the tooling: `bluez-alsa` (primary) or PipeWire (fallback).
- Produce a written **first-class / best-effort / drop** verdict + the tooling decision.
- Leave a reusable setup/test script and documented pairing steps.

**Non-Goals:**
- No `fmradiod` code: no output-mode seam, no D-Bus controller, no pairing agent, no web UI, no auto-reconnect, no in-UI volume (all in `build-bluetooth-output`).
- No multi-speaker / multi-codec work beyond noting what the speaker negotiates (SBC vs AAC).
- No 3.5 mm jack work (separate phase, though it shares the future output-router seam).

## Decisions

**Primary tooling: `bluez-alsa` (`bluealsa`) for the A2DP path; PipeWire as a pre-authorized fallback.**
`bluez-alsa` is a lightweight A2DP-only daemon that exposes a Bluetooth speaker as an ALSA PCM, with no desktop session manager — a clean fit for a single-purpose headless appliance, and `ffmpeg` can write straight to its ALSA device. Rationale: smallest moving-parts footprint over BlueZ. **If `bluez-alsa` is unavailable/unbuildable or misbehaves on Debian 13 trixie, switch to PipeWire + WirePlumber + `libspa-0.2-bluetooth`** (the modern default with robust BT support) **without pausing** — the user pre-authorized the fallback; record which one won. Alternative considered: PulseAudio — rejected (legacy; PipeWire supersedes it).

**Throwaway scripts, not `fmradiod` integration (mirror the HD spike).**
Pair with `bluetoothctl`; route audio with a standalone command/script (e.g. `ffmpeg … -f alsa bluealsa:DEV=<MAC>,PROFILE=a2dp`, or pipe demod → `bluealsa-aplay`). The exact invocation is confirmed at apply. Rationale: minimal new surface to prove feasibility; the daemon integration is the *next* change. Alternative: wire it into `fmradiod` now — rejected (that's building on the unproven path this spike exists to test).

**Stress the realistic concurrent load.**
Run a live HD station (`nrsc5`, the heaviest demod) **and** route its audio to the speaker at the same time, since the production exclusive-output BT mode is demod + PCM resample + SBC encode. Measure steady-state and peak CPU/RAM/temperature over a sustained interval. Rationale: the gating risk is concurrent CPU on 512 MB / quad-A53, not BT alone.

**Test target: a real A2DP speaker the user has on hand, paired once over SSH.**
Use a known-good speaker; document scan → pair → trust → connect. Note the negotiated codec (most speakers: SBC; AAC if offered).

**Verdict thresholds (refined against observed numbers with the user):**
- *first-class* — sustained clean playback with comfortable CPU margin, no recurring dropouts, tolerable latency, reliable reconnect.
- *best-effort* — plays but with high load, occasional dropouts, or flaky reconnects (offer BT but caveat it).
- *drop* — cannot sustain clean A2DP playback on this hardware/stack.

## Risks / Trade-offs

- **`bluez-alsa` not packaged / won't build on Debian 13** → try `apt install bluez-alsa-utils` first; if absent or broken, take the pre-authorized PipeWire fallback rather than fighting a source build.
- **Onboard BT won't power up on DietPi** (rfkill block, missing `brcm` firmware, `hciuart`/`bluetooth` service not enabled) → `rfkill unblock bluetooth`, ensure firmware + `bluetooth.service`; if the controller is genuinely dead, that's a hard *drop* finding.
- **BT + 2.4 GHz Wi-Fi coexistence** on the one CYW43455 chip → audio stutter or Wi-Fi flakiness under load; watch for it, try the 5 GHz Wi-Fi band if it bites.
- **Concurrent CPU can't sustain demod + SBC encode** → a valid *finding*, not a failure; record the numbers and let them drive the verdict (and whether to `taskset`-pin like `nrsc5`).
- **A2DP latency** → high latency is fine for radio (no lip-sync); note it, don't gate on it.
- **Speaker disconnect/reconnect** → note how the path behaves on drop (for the build phase's fail-back design); don't solve it here.
- **Thermal throttling** under sustained concurrent load → watch `vcgencmd measure_temp` / `get_throttled`; recommend a heatsink if it throttles.

## Open Questions

- Exact invocation to feed `ffmpeg` output into the A2DP sink (`-f alsa bluealsa:DEV=<MAC>` vs piping to `bluealsa-aplay`); device/format/rate confirmed at apply.
- `bluez-alsa` availability on Debian 13 trixie (package `bluez-alsa-utils`?) vs needing a source build.
- DietPi specifics to enable onboard BT (`dietpi-config` Bluetooth option, `hciuart`, enabling `bluetooth.service`).
- Negotiated codec (SBC vs AAC) and whether it matters for quality/CPU.
- Final crisp pass/fail thresholds — agreed with the user once real CPU/temperature/latency numbers are in hand.

## Outcome (verdict)

**Verdict: FIRST-CLASS.** Bluetooth A2DP speaker output is viable on the Pi 3A+ with comfortable margin. **Chosen tooling: `bluez-alsa`** (PipeWire fallback not needed).

Evidence (Echo Pop `50:99:5A:21:F8:BB`, `bluez 5.82` + `bluez-alsa-utils 4.3.1` on Debian 13 trixie):
- **Stack installed cleanly from the trixie apt repo** — no source build, no PipeWire fallback. Onboard BT controller ("fmradio") powered up with the A2DP **source** role; `bluealsa` already ships configured `-p a2dp-source -p a2dp-sink`.
- **End-to-end proven:** test tones, then **live KBCO HD0 audio**, played out the Echo continuously — user-confirmed, no underruns/errors.
- **Codec:** A2DP **SBC, S16_LE, 2ch, 48000 Hz** — identical to `fmradiod`'s existing output, so the BT output path needs **no resample**.
- **Concurrent resource use** (conservative upper bound: `nrsc5` HD decode + daemon MP3 encode + tap MP3 decode + SBC): system **~58% idle**, load ~1.4 of 4 cores, **~306 MB RAM free**, **60–61 °C**. The production exclusive-BT path (demod → PCM → SBC, no MP3 round-trip) will be lighter.
- **Volume** is controllable from the Pi via `bluealsactl volume <path> 0–127` (AVRCP) — set to 60% in testing. Useful for the deferred in-UI volume.

Caveats:
- `get_throttled=0xd0008` showed the **soft temperature limit currently active at ~60 °C** plus sticky under-voltage/throttle bits from earlier load. Not hard-throttling (58% idle). **A heatsink + a solid 5 V supply are recommended** (user is adding a heatsink later — not a blocker).
- Reconnect-on-drop behavior was not stress-tested; handle it in the build.

Implications for `build-bluetooth-output`:
- **Tooling confirmed:** BlueZ + `bluez-alsa`. The output-mode seam's `bluetooth` sink writes PCM to `bluealsa:DEV=<MAC>,PROFILE=a2dp` (48k/stereo/S16_LE, no resample).
- **CPU budget is comfortable** for the exclusive-output model; `taskset`-pinning `nrsc5` is optional insurance, not required.
- The Pi already has the stack installed + the Echo paired/trusted — a running head start for the build.
- Pairing gotcha for the in-browser flow: discovery must stay active and an agent must be registered **in the same session** as `pair`, or the device ages out ("not available"). The daemon's BlueZ D-Bus controller must hold discovery + a `NoInputNoOutput` agent across the pair call.
