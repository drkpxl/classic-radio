## 1. Prep — free the SDR & install build deps

- [x] 1.1 Stop the analog `fmtest` stream to free the single SDR; confirm port 8000 is released
- [x] 1.2 Install `nrsc5` build dependencies (`cmake`, `libao-dev`, `libfftw3-dev`, `librtlsdr-dev`, and autotools if the pinned revision needs them)

## 2. Build nrsc5

- [x] 2.1 Clone `theori-io/nrsc5` at a pinned revision into `/root/src/nrsc5` — built `34aa77c`
- [x] 2.2 Build via CMake (`mkdir build && cd build && cmake .. && make`) and install the binary — `/usr/local/bin/nrsc5`
- [x] 2.3 Verify `nrsc5` runs and prints usage/version with no missing-library errors

## 3. Validate HD reception on 97.3 KBCO

- [x] 3.1 Run `nrsc5` on 97.3 MHz program 0 (HD1) with the antenna on; confirm it acquires lock (MER/BER) and decodes audio — MER ~12.5 dB, BER ~1e-5
- [x] 3.2 Capture and record the reported HD program lineup (HD1/HD2/HD3) — HD1 Rock, HD2 Rock (Studio C), HD3 News (KOA)
- [x] 3.3 Confirm a failed/weak lock is observable (so a signal problem is distinguishable from a build/config problem) — 88.5 produced zero lock

## 4. Stream HD for an A/B comparison

- [x] 4.1 Determine `nrsc5` stdout audio format (raw vs WAV, sample rate, channels) for the ffmpeg input — raw s16le, 44.1 kHz, stereo
- [x] 4.2 Adapt the fan-out streamer (`/root/hdstream.py`) to source `nrsc5 → ffmpeg` (MP3 256k) on port 8000
- [x] 4.3 Connect from the desk and confirm continuous HD audio; verify a client disconnect does not kill the source
- [x] 4.4 A/B compare HD vs analog FM quality by ear and note the difference — HD confirmed cleaner

## 5. Measure resource headroom (the gating metric)

- [x] 5.1 Run HD decode sustained (~10–15 min); capture steady-state and peak CPU and RAM usage — ~1 of 4 cores (~22% total), 336 MB free
- [x] 5.2 Capture SoC temperature and `vcgencmd get_throttled` during sustained load — 44.5 °C; only the sticky soft-temp bit (from the compile), no live throttle
- [x] 5.3 Note any audio dropouts / xruns reported by `nrsc5` over the interval — none observed

## 6. Verdict & cleanup

- [x] 6.1 Record the **first-class / best-effort / drop** verdict, justified by the measured numbers — FIRST-CLASS (see design.md Outcome)
- [x] 6.2 Note implications for the full-app design (whether to include an `nrsc5` demod backend, HD presets, and web-UI album art) — all in scope; single Python supervisor + native subprocesses confirmed multi-core-friendly
- [x] 6.3 Restore the analog `fmtest` stream and confirm it is serving again — active on :8000
- [x] 6.4 Add a build-log/blog entry for the HD spike (commands, gotchas, results) — docs/hd-radio-spike.md
