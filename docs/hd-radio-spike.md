# Build Log — HD Radio de-risk (nrsc5 on the Pi 3A+)

**Question:** can a 512 MB Raspberry Pi 3A+ decode HD Radio, before we build the app around it?
**Answer: yes, easily.** ~1 of 4 cores, with album art and metadata for free.

## What we did

1. **Freed the SDR** — stopped the analog test stream (single dongle, can't do both at once).
2. **Installed build deps**: `cmake libao-dev libfftw3-dev librtlsdr-dev` (`build-essential`, `git`, `libusb` already present).
3. **Built `nrsc5` from source** (it isn't packaged for Debian):
   ```bash
   git clone --depth 1 https://github.com/theori-io/nrsc5.git
   cd nrsc5 && mkdir build && cd build && cmake .. && make -j4 && make install
   ```
   A few minutes on the Pi; installs to `/usr/local/bin/nrsc5`.
4. **Tuned 97.3 KBCO HD1**: `nrsc5 -o /dev/null 97.3 0`.

## Results

- **Lock**: MER ~12.5 dB, BER ~1e-5 — pristine signal.
- **Metadata**: live Title / Artist / Genre (e.g. "Sailor Song" — Gigi Perez).
- **Album art / logos**: LOT files (`KBCOHD01ceef.jpg`, station PNGs) arrive automatically.
- **Lineup**: HD1 Rock (KBCO), HD2 Rock (Studio C), HD3 News (KOA) — matches the station research.
- **CPU**: `nrsc5` single-threaded at ~80–90% of one core; `ffmpeg` ~15%; total ~1 of 4 cores. RAM fine (336 MB free). 44.5 °C.
- **No dropouts.** HD sounds cleaner than analog by ear.

## Gotchas / notes

- `nrsc5` isn't in Debian → build from source.
- `nrsc5` is **single-threaded** (~one core). Lots of *total* headroom, but its one core is the tightest resource — give it room (optionally `taskset`-pin it; let everything else use the other 3 cores).
- The 4-core compile briefly tripped the 75 °C soft-temp limit (sticky flag in `vcgencmd get_throttled`). Decode itself runs cool — a small heatsink is still a good idea.
- Audio pipe for streaming: `nrsc5 -o - -t raw 97.3 0 | ffmpeg -f s16le -ar 44100 -ac 2 -i - ...` (raw s16le, 44.1 kHz, stereo).

## Verdict

**First-class.** The full app will include an `nrsc5` demod backend, HD presets, and web-UI album art.
