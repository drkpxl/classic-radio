## 1. Prep — bring up the onboard Bluetooth controller

- [x] 1.1 Check the onboard BT controller state: `rfkill list`, `hciconfig`/`bluetoothctl list`; unblock if soft-blocked. Note any DietPi step needed (`dietpi-config` Bluetooth, `hciuart`, enabling `bluetooth.service`) and any missing `brcm` firmware. *(hci0 already probed at boot — BCM combo-chip firmware present (BCM4345/6). No rfkill block. No dietpi-config/reboot needed.)*
- [x] 1.2 Install the stack: `bluez` (+ `bluetoothd` running) and `bluez-alsa` (`apt install bluez-alsa-utils` if available on Debian 13 trixie; otherwise note it for the fallback). Confirm `bluetoothctl` shows a powered controller with the A2DP sink role. *(`bluez 5.82` + `bluez-alsa-utils 4.3.1` installed straight from the trixie repo — no source build. `bluetooth.service` enabled; controller "fmradio" Powered: yes, Audio Source UUID present. bluez-alsa primary path is GO — PipeWire fallback not needed.)*

## 2. Pair a speaker

- [x] 2.1 Put a real A2DP speaker in pairing mode; via `bluetoothctl`: `scan on` → `pair <MAC>` → `trust <MAC>` → `connect <MAC>`. Confirm it reaches connected with A2DP active. *(Echo Pop `50:99:5A:21:F8:BB` — paired/trusted/connected. Gotcha: pairing needs an active scan + registered agent in ONE session; a stopped scan ages the device out ("not available"). Scripted a persistent `bluetoothctl` session via FIFO.)*
- [x] 2.2 Record the pairing steps + the speaker's MAC and negotiated codec (SBC/AAC) for reuse in the build change. *(MAC `50:99:5A:21:F8:BB`; `bluealsa` runs `-p a2dp-source -p a2dp-sink`; PCM `bluealsa:DEV=50:99:5A:21:F8:BB,PROFILE=a2dp` negotiates **A2DP SBC, S16_LE, 2ch, 48000 Hz** — matches fmradiod's 48k-stereo output, so NO resample needed.)*

## 3. Prove A2DP playback

- [x] 3.1 Start `bluealsa` (A2DP profile) and play a known test tone/file to the speaker (e.g. `aplay`/`bluealsa-aplay` or `ffmpeg -f alsa bluealsa:DEV=<MAC>`). Confirm clean sound. Determine the exact ALSA device/invocation for the next step. *(User heard 440/880 Hz tones cleanly. Working invocation: `ffmpeg … -f wav - | aplay -D "bluealsa:DEV=50:99:5A:21:F8:BB,PROFILE=a2dp"`. Bonus: volume controllable via `bluealsactl volume <path> 0-127` (set 76 = 60%) — AVRCP works, useful for the deferred in-UI volume.)*

## 4. Route the live radio to the speaker

- [x] 4.1 Tune a real station (reuse `fmradiod` or a standalone `rtl_fm`/`nrsc5`) and route its decoded audio to the A2DP sink (`ffmpeg` decode/resample → `bluealsa` ALSA PCM). Confirm the radio is audible from the speaker continuously. *(Tuned KBCO 97.3 HD0; routed the daemon's live stream to the Echo — `ffmpeg -i http://localhost:8000/stream.mp3 -ac 2 -ar 48000 -f wav - | aplay -D "bluealsa:DEV=…,PROFILE=a2dp"`. User confirmed live music playing on the Echo, continuous, clean.)*
- [x] 4.2 Capture the exact working invocation (device, sample rate, format) and the negotiated codec — the build change's output-mode seam targets this sink. *(Sink: `bluealsa:DEV=50:99:5A:21:F8:BB,PROFILE=a2dp`; codec A2DP SBC, S16_LE, 2ch, 48000 Hz = fmradiod's native output → the build's BT output-mode can write PCM straight to this sink with NO resample.)*

## 5. Measure resource headroom (the gating metric)

- [x] 5.1 Run a live **HD** station (`nrsc5`, heaviest demod) **while** routing to the speaker for a sustained interval (~10–15 min); capture steady-state and peak CPU and RAM (this is the concurrent load the exclusive BT mode will run). *(KBCO HD0 + tap: system ~38%us+4%sy → **~58% idle**, load ~1.4/4 cores. `nrsc5` ~1 core, daemon ffmpeg ~25–36%, bluealsa SBC low single digits. RAM **~306 MB available** of 512. Measured a CONSERVATIVE upper bound — includes the daemon MP3 encode + the tap's MP3 decode that production exclusive-BT mode won't have, so production is lighter.)*
- [x] 5.2 Capture SoC temperature and `vcgencmd get_throttled` under sustained concurrent load. *(60–61 °C. `throttled=0xd0008`: bit 3 soft-temp-limit currently active at ~60 °C + sticky under-voltage/throttle bits from earlier. Not hard-throttling (58% idle). Heatsink + solid 5V supply recommended — user is adding a heatsink later; not a blocker.)*
- [x] 5.3 Note audio dropouts/xruns, qualitative latency, and any BT ↔ 2.4 GHz Wi-Fi coexistence glitches; note reconnect behavior if the speaker drops. *(No underruns/errors across the run; aplay clean exit. Latency unmeasured but irrelevant for radio (no lip-sync). No Wi-Fi coexistence glitch observed (SSH/stream stayed responsive throughout). Reconnect-on-drop to be handled in the build phase.)*

## 6. PipeWire fallback (only if `bluez-alsa` fails — pre-authorized)

- [x] 6.1 If `bluez-alsa` is unavailable/unbuildable or won't sustain A2DP on Debian 13, install `pipewire` + `wireplumber` + `libspa-0.2-bluetooth`, re-pair, and repeat tasks 3–5 through PipeWire. Record which tool won and why (no need to pause and ask — the fallback is pre-authorized). *(N/A — not needed. `bluez-alsa` (4.3.1, straight from the trixie repo) worked end-to-end on the first try; PipeWire fallback not exercised. **Winner: bluez-alsa.**)*

## 7. Verdict, cleanup & docs

- [x] 7.1 Record the **first-class / best-effort / drop** verdict in `design.md`'s Outcome section, justified by the measured numbers, plus the **chosen tooling** (`bluez-alsa` or PipeWire). *(Verdict: **FIRST-CLASS** with bluez-alsa — recorded in design.md Outcome.)*
- [x] 7.2 Note implications for `build-bluetooth-output`: the confirmed ALSA sink the output-mode seam targets, the CPU budget for the exclusive-output model, and whether `taskset`-pinning is warranted. *(Recorded in design.md Outcome: sink string, no-resample 48k path, comfortable CPU budget, taskset optional.)*
- [x] 7.3 Restore the Pi to its normal state (re-tune `fmradiod` to a station / confirm the service is serving as before); leave the reusable setup/test script on the Pi. *(Tap stopped; fmradiod serving KBCO HD0 "playing", one `nrsc5` proc (no orphan); Echo left paired/trusted/connected for the build phase; `/root/src/bt-pair.sh` saved. Note: bluez + bluez-alsa remain installed + enabled on the Pi (the build change needs them) — a head start, not reverted.)*
- [x] 7.4 Add a build-log/blog entry for the Bluetooth spike (commands, pairing steps, gotchas, results) consistent with `docs/hd-radio-spike.md`; update `docs/roadmap.md`. *(New `docs/bluetooth-spike.md`; roadmap updated with the verdict.)*
