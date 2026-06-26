"""HD Radio backend — nrsc5 raw s16le 44.1k stereo, with album-art/LOT dump dir."""

from __future__ import annotations

from fmradiod.backends.base import Backend, PcmFormat, sdr_flags
from fmradiod.config import Preset, SdrConfig


class HdBackend(Backend):
    mode = "hd"

    @property
    def pcm_format(self) -> PcmFormat:
        return PcmFormat(sample_rate=44100, channels=2)

    def source_command(self, preset: Preset, sdr: SdrConfig, aas_dir: str | None) -> list[str]:
        cmd = ["nrsc5", *sdr_flags(sdr), "-o", "-", "-t", "raw"]
        if aas_dir:
            cmd += ["--dump-aas-files", aas_dir]
        program = 0 if preset.hd_program is None else preset.hd_program
        cmd += [f"{preset.freq}", str(program)]
        return cmd
