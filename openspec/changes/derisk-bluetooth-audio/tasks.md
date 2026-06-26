## 1. Prep — bring up the onboard Bluetooth controller

- [ ] 1.1 Check the onboard BT controller state: `rfkill list`, `hciconfig`/`bluetoothctl list`; unblock if soft-blocked. Note any DietPi step needed (`dietpi-config` Bluetooth, `hciuart`, enabling `bluetooth.service`) and any missing `brcm` firmware.
- [ ] 1.2 Install the stack: `bluez` (+ `bluetoothd` running) and `bluez-alsa` (`apt install bluez-alsa-utils` if available on Debian 13 trixie; otherwise note it for the fallback). Confirm `bluetoothctl` shows a powered controller with the A2DP sink role.

## 2. Pair a speaker

- [ ] 2.1 Put a real A2DP speaker in pairing mode; via `bluetoothctl`: `scan on` → `pair <MAC>` → `trust <MAC>` → `connect <MAC>`. Confirm it reaches connected with A2DP active.
- [ ] 2.2 Record the pairing steps + the speaker's MAC and negotiated codec (SBC/AAC) for reuse in the build change.

## 3. Prove A2DP playback

- [ ] 3.1 Start `bluealsa` (A2DP profile) and play a known test tone/file to the speaker (e.g. `aplay`/`bluealsa-aplay` or `ffmpeg -f alsa bluealsa:DEV=<MAC>`). Confirm clean sound. Determine the exact ALSA device/invocation for the next step.

## 4. Route the live radio to the speaker

- [ ] 4.1 Tune a real station (reuse `fmradiod` or a standalone `rtl_fm`/`nrsc5`) and route its decoded audio to the A2DP sink (`ffmpeg` decode/resample → `bluealsa` ALSA PCM). Confirm the radio is audible from the speaker continuously.
- [ ] 4.2 Capture the exact working invocation (device, sample rate, format) and the negotiated codec — the build change's output-mode seam targets this sink.

## 5. Measure resource headroom (the gating metric)

- [ ] 5.1 Run a live **HD** station (`nrsc5`, heaviest demod) **while** routing to the speaker for a sustained interval (~10–15 min); capture steady-state and peak CPU and RAM (this is the concurrent load the exclusive BT mode will run).
- [ ] 5.2 Capture SoC temperature and `vcgencmd get_throttled` under sustained concurrent load.
- [ ] 5.3 Note audio dropouts/xruns, qualitative latency, and any BT ↔ 2.4 GHz Wi-Fi coexistence glitches; note reconnect behavior if the speaker drops.

## 6. PipeWire fallback (only if `bluez-alsa` fails — pre-authorized)

- [ ] 6.1 If `bluez-alsa` is unavailable/unbuildable or won't sustain A2DP on Debian 13, install `pipewire` + `wireplumber` + `libspa-0.2-bluetooth`, re-pair, and repeat tasks 3–5 through PipeWire. Record which tool won and why (no need to pause and ask — the fallback is pre-authorized).

## 7. Verdict, cleanup & docs

- [ ] 7.1 Record the **first-class / best-effort / drop** verdict in `design.md`'s Outcome section, justified by the measured numbers, plus the **chosen tooling** (`bluez-alsa` or PipeWire).
- [ ] 7.2 Note implications for `build-bluetooth-output`: the confirmed ALSA sink the output-mode seam targets, the CPU budget for the exclusive-output model, and whether `taskset`-pinning is warranted.
- [ ] 7.3 Restore the Pi to its normal state (re-tune `fmradiod` to a station / confirm the service is serving as before); leave the reusable setup/test script on the Pi.
- [ ] 7.4 Add a build-log/blog entry for the Bluetooth spike (commands, pairing steps, gotchas, results) consistent with `docs/hd-radio-spike.md`; update `docs/roadmap.md`.
