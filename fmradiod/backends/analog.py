"""Analog FM (WBFM) backend — the higher-quality rtl_fm recipe proven in the spike."""

from __future__ import annotations

from fmradiod.backends.base import Backend, PcmFormat, sdr_flags
from fmradiod.config import Preset, SdrConfig


class AnalogBackend(Backend):
    mode = "analog"

    @property
    def pcm_format(self) -> PcmFormat:
        return PcmFormat(sample_rate=48000, channels=1)

    def source_command(self, preset: Preset, sdr: SdrConfig, aas_dir: str | None) -> list[str]:
        return [
            "rtl_fm", *sdr_flags(sdr),
            "-f", f"{preset.freq}M",
            "-M", "fm", "-s", "200000", "-A", "std", "-r", "48000",
            "-E", "deemp", "-l", "0", "-",
        ]
