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

_To be recorded at apply time, once the spike has run and the numbers are in hand: the **first-class / best-effort / drop** verdict, the **chosen tooling** (`bluez-alsa` or PipeWire), the measured CPU/RAM/temperature under concurrent load, latency/reconnect notes, and the implications for the `build-bluetooth-output` design (the ALSA sink target and CPU budget for the exclusive-output model)._
