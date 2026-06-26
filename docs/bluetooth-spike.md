# Build Log — Bluetooth audio de-risk (A2DP out on the Pi 3A+)

**Question:** can the Pi 3A+ play the live radio out a Bluetooth speaker over its
**onboard** BT (the USB is the SDR's), and which open-source tool does it — before
we build the output-router + in-browser pairing UI?
**Answer: yes, easily, with `bluez-alsa`.** Live HD radio played out an Echo Pop with
~58% CPU idle and no dropouts.

## What we did

1. **Brought up onboard BT** — `hci0` was already probed at boot (BCM4345/6 combo
   chip firmware present); no rfkill block, no DietPi/reboot dance needed.
2. **Installed the stack from the trixie apt repo** (no source build — unlike nrsc5):
   ```bash
   apt-get install -y bluez bluez-alsa-utils rfkill
   systemctl enable --now bluetooth
   ```
   `bluez 5.82` + `bluez-alsa-utils 4.3.1`. `bluealsa.service` ships configured
   `-p a2dp-source -p a2dp-sink`, so the Pi can act as an A2DP **source**.
3. **Paired a speaker** (Echo Pop, `50:99:5A:21:F8:BB`) over SSH — see the gotcha below.
4. **Test tone** to confirm the path:
   ```bash
   ffmpeg -f lavfi -i "sine=frequency=440:duration=4" -ac 2 -ar 48000 -f wav - \
     | aplay -D "bluealsa:DEV=50:99:5A:21:F8:BB,PROFILE=a2dp" -
   ```
5. **Live radio** to the speaker (tap the running daemon's stream):
   ```bash
   ffmpeg -i http://localhost:8000/stream.mp3 -ac 2 -ar 48000 -f wav - \
     | aplay -D "bluealsa:DEV=50:99:5A:21:F8:BB,PROFILE=a2dp" -
   ```

## Results

- **Codec**: A2DP **SBC, S16_LE, 2ch, 48000 Hz** — exactly `fmradiod`'s output, so
  the production BT path needs **no resample**.
- **CPU** (conservative upper bound: `nrsc5` + daemon MP3 encode + tap MP3 decode +
  SBC): system **~58% idle**, load ~1.4 of 4 cores. The real exclusive-BT path
  (demod → PCM → SBC, no MP3) will be lighter.
- **RAM**: ~306 MB free of 512. **Temp**: 60–61 °C. **No underruns/dropouts.**
- **Volume**: controllable from the Pi — `bluealsactl volume <pcm-path> 0..127`
  (AVRCP); set to 76 (≈60%) in testing.

## Gotchas / notes

- **Pairing needs an active scan + a registered agent in ONE `bluetoothctl`
  session.** If the scan stops, the device ages out and `pair` fails with
  "not available". The daemon's BlueZ D-Bus controller must hold discovery + a
  `NoInputNoOutput` agent across the pair call. (Spike worked around it with a
  persistent FIFO-fed session — saved as `/root/src/bt-pair.sh`.)
- **Don't `pkill -f "stream.mp3"`** from a shell whose own command line contains
  that string — it matches and kills itself. Kill by PID or run from a script file.
- `get_throttled=0xd0008`: soft temp-limit active at ~60 °C (no hard throttle, 58%
  idle) — a **heatsink + solid 5 V supply** are recommended (deferred for now).
- The Pi now has the BT stack installed/enabled and the Echo paired/trusted — a
  head start for `build-bluetooth-output`, not reverted.

## Verdict

**First-class, with `bluez-alsa`.** `build-bluetooth-output` will add the exclusive
output-router (web ⇄ BT), a BlueZ D-Bus controller + `NoInputNoOutput` pairing
agent, the in-browser scan/pair/connect UI, and auto-reconnect — writing PCM to
`bluealsa:DEV=<MAC>,PROFILE=a2dp`.
