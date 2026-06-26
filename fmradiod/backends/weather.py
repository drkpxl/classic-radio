"""NOAA Weather Radio (NBFM) backend.

NBFM voice on the 162 MHz band. The recipe below follows the documented rtl_fm
NOAA example (narrowband, 22.05 kHz mono); the exact filter/rate is worth a
by-ear check on-device (see tasks Phase 10).
"""

from __future__ import annotations

from fmradiod.backends.base import Backend, PcmFormat, sdr_flags
from fmradiod.config import Preset, SdrConfig


class WeatherBackend(Backend):
    mode = "weather"

    @property
    def pcm_format(self) -> PcmFormat:
        return PcmFormat(sample_rate=22050, channels=1)

    def source_command(self, preset: Preset, sdr: SdrConfig, aas_dir: str | None) -> list[str]:
        return [
            "rtl_fm", *sdr_flags(sdr),
            "-f", f"{preset.freq}M",
            "-M", "fm", "-s", "22050", "-r", "22050",
            "-E", "deemp", "-l", "0", "-",
        ]
