## Context

Analog FM web streaming is validated on the Pi 3A+ and ran with ample CPU headroom: `rtl_fm` → `ffmpeg` (libmp3lame 256k) → a small persistent Python fan-out HTTP server (`/root/fmstream.py`, transient unit `fmtest`, port 8000). HD Radio is fundamentally heavier — `nrsc5` does OFDM demodulation plus AAC/HDC audio decode in software — and it is the one component whose viability is unknown on this 512 MB / quad-A53 board. The single RTL-SDR (R820T2) means HD and analog cannot run at once. This change is a focused spike to settle HD feasibility before the full app is designed.

## Goals / Non-Goals

**Goals:**
- Get a working `nrsc5` build on the Pi.
- Prove (or disprove) clean, sustained HD decode of a real local station (97.3 KBCO).
- Reuse the proven fan-out streaming pattern so HD can be A/B compared against analog by ear.
- Quantify CPU / RAM / thermal headroom under sustained HD decode — the gating metric.
- Produce a written first-class / best-effort / drop verdict.

**Non-Goals:**
- No full app, presets, web UI, TFT, or buttons (later changes).
- No album-art / metadata extraction work beyond noting that `nrsc5` exposes it.
- No multi-SDR or simultaneous analog+HD operation.

## Decisions

**Build `nrsc5` from source (theori-io/nrsc5) via its CMake build.**
It is not packaged for Debian and there is no trustworthy arm64 prebuilt. Dependencies: `cmake`, `build-essential` (present), `libao-dev`, `libfftw3-dev`, `librtlsdr-dev`, plus autotools if the pinned revision needs them. Rationale: source build is the only reliable path and lets us pin a known-good revision. Alternative considered: prebuilt binaries — rejected (none reliable, opaque provenance).

**Reuse the Phase-1 fan-out streamer, swapping the source command.**
Keep the persistent multi-client HTTP server; replace `rtl_fm` with `nrsc5 → ffmpeg`. A separate throwaway script (e.g. `/root/hdstream.py`) is fine for the spike rather than generalizing the existing one. Rationale: minimal new surface, identical listening experience for a fair A/B. Alternative: stand up Icecast — rejected (contradicts the no-Icecast decision and adds a component we'd remove).

**Pipeline: `nrsc5 -> ffmpeg(MP3 256k) -> :8000`.**
`nrsc5` emits HD audio as 44.1 kHz 16-bit stereo PCM; `ffmpeg` re-encodes to MP3 256k for the browser (input `-ar 44100 -ac 2`). The exact `nrsc5` stdout flag/format (raw vs WAV) is confirmed at apply time. Note this is heavier than analog (stereo, 44.1 kHz, plus the decode itself).

**Test target: 97.3 KBCO, program 0 (HD1) first, then probe HD2/HD3.**
Same dial position used for the analog test (clean continuity), and a strong local signal — HD needs a cleaner signal than analog to lock.

**Stop the analog `fmtest` service for the duration of the HD test; restore it after.**
Single SDR. Script the stop/restore so the analog stream isn't left dead.

**Verdict thresholds (refined against observed numbers with the user):**
- *first-class* — sustained decode with comfortable CPU margin and no recurring audio dropouts.
- *best-effort* — decodes but with high load or occasional dropouts (offer HD only on strong stations).
- *drop* — cannot sustain a clean decode on this hardware.

## Risks / Trade-offs

- **nrsc5 build fails / missing dep** → install the full dependency set up front; pin a known-good revision; keep build logs.
- **Station won't lock (antenna/signal)** → 97.3 KBCO is strong; if it won't lock, try another strong local HD station and reposition the antenna before concluding HD is unviable.
- **CPU can't sustain clean decode** → this is a valid *finding*, not a failure; record the numbers and let it drive the verdict.
- **Thermal throttling under sustained load** → `temp_limit` is set to 75 °C; watch `vcgencmd measure_temp` / `get_throttled`; recommend a heatsink if it throttles.
- **Single-SDR disruption** → the analog stream is intentionally stopped during the test and restored after.
- **Patent note** → `nrsc5` decodes a patented standard; use here is personal/experimental — noted, not a blocker.

## Open Questions

- Exact `nrsc5` invocation for piping audio to stdout (raw vs WAV; mono/stereo confirmation) — resolve at apply.
- Current `nrsc5` build system specifics for the pinned revision (CMake vs autotools).
- Final, crisp pass/fail thresholds — to be agreed with the user once real CPU/temperature numbers are in hand.

## Outcome (verdict)

**Verdict: FIRST-CLASS.** HD Radio is viable on the Pi 3A+ with comfortable margin — `nrsc5` will be a first-class demod backend in the full app.

Evidence (97.3 KBCO, nrsc5 `34aa77c`):
- Clean decode: MER ~12.5 dB, BER ~1e-5, **zero audio dropouts** over a sustained run.
- Full lineup decoded: HD1 (Rock), HD2 (Rock / "Studio C"), HD3 (News, = KOA) — plus live title/artist and album-art/logo images (LOT files), for free.
- Resource use: `nrsc5` single-threaded at ~80–90% of **one** core; `ffmpeg` ~0.15 core; Python server ~few %. Total ~1 of 4 cores (~22%); 336 MB RAM free; 44.5 °C.
- HD audio confirmed cleaner than analog by ear.

Resolved open questions:
- `nrsc5` audio for piping: `-o - -t raw` → raw s16le, 44.1 kHz, stereo (ffmpeg `-ar 44100 -ac 2`).
- Build system: CMake (revision `34aa77c`).
- Threshold: comfortably passed (well below saturation, no dropouts) → first-class.

Implications for the full app:
- Include an `nrsc5` demod backend in the SDR arbiter; **HD presets** and **web-UI album art** are in scope (the data arrives free with the decode).
- Process model confirmed: one Python supervisor app + native subprocesses (`nrsc5`, `ffmpeg`) is already multi-process; the kernel spreads them across cores. The Python app is I/O-bound (GIL irrelevant) and light. No need to split the web server into worker processes.
- Optional robustness: pin `nrsc5` to a dedicated core (`taskset -c <n>`) and/or raise its priority so its single core never contends. Not required (zero dropouts observed), but cheap insurance.
- Recommend a small heatsink for sustained-load margin (the soft-temp bit tripped during the 4-core compile, not during decode).
