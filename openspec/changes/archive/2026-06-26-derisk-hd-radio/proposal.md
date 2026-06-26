## Why

HD Radio is one of the three station types the project intends to support (alongside analog FM and NOAA weather radio), but decoding it (`nrsc5`: OFDM demodulation + AAC) is by far the heaviest workload and the single biggest unknown on a constrained Raspberry Pi 3A+ (512 MB RAM, quad-core A53). Whether this hardware can sustain a clean HD decode determines whether HD is a first-class feature, a best-effort extra, or dropped — and that decision shapes the whole app's demod-backend architecture. We must prove it **before** building the full application, so we don't architect around an unproven assumption. Analog FM web streaming is already validated and ran with plenty of CPU headroom, which is encouraging but not conclusive for HD.

## What Changes

- Build and install `nrsc5` from source on the Pi (it is not in the Debian repositories) and verify it runs.
- Validate that `nrsc5` locks and decodes a known-strong local HD station (97.3 KBCO).
- Enumerate the HD program lineup actually on air (HD1/HD2/HD3) as reported by the decoder.
- Stream decoded HD audio to the desk over HTTP, reusing the Phase-1 persistent fan-out pattern, for an A/B quality comparison against analog FM.
- Measure CPU, RAM, and thermal headroom under sustained HD decode (this is the gating metric).
- Record a go/no-go outcome — **first-class / best-effort / drop** — to feed the future full-app design.
- Non-goals: building the full app, presets, web UI, TFT, or physical buttons; those are later changes. This change is a focused feasibility spike that leaves behind a reusable HD test script and a documented decision.

## Capabilities

### New Capabilities
- `hd-radio-reception`: receive and decode an HD Radio (NRSC-5) station on the Pi via `nrsc5`, enumerate its program lineup, stream the decoded audio for evaluation, and produce a documented feasibility verdict (including measured resource headroom) that governs whether HD is carried into the full app.

### Modified Capabilities
<!-- None — no existing specs in openspec/specs/ yet. -->

## Impact

- **Pi packages**: adds `nrsc5` build dependencies (e.g. `cmake`, `libao-dev`, `libfftw3-dev`, `librtlsdr-dev`, autotools as needed) and the compiled `nrsc5` binary. `build-essential`, `git`, `libusb-1.0-0-dev` are already installed.
- **SDR contention**: the single RTL-SDR means the HD test cannot run alongside the analog `fmtest` stream — the analog stream must be stopped for the duration of the HD decode test.
- **Outputs**: a feasibility decision (recorded in this change), a reusable HD test/stream script on the Pi, and an entry in the build-log/blog docs.
- **Downstream**: directly informs the future full-app change — specifically whether the SDR arbiter needs an `nrsc5` demod backend and whether HD presets and web-UI album art are in scope.
