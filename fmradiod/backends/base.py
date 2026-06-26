"""Common backend interface and the shared ffmpeg normalization stage.

A backend builds a pipeline as a list of argv lists, piped left to right:
the source process (`rtl_fm`/`nrsc5`) emits raw s16le PCM into `ffmpeg`, which
re-encodes to a *uniform* MP3 (the configured rate/channels/bitrate) so the
fan-out byte stream is format-stable across preset switches.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from fmradiod.config import AudioConfig, Preset, SdrConfig


@dataclass(frozen=True)
class PcmFormat:
    """Format of the raw PCM the source process emits into ffmpeg."""

    sample_rate: int
    channels: int


def sdr_flags(sdr: SdrConfig) -> list[str]:
    """`-g`/`-p` flags shared by rtl_fm and nrsc5; omitted at their defaults."""
    flags: list[str] = []
    if sdr.gain != "auto":
        flags += ["-g", str(sdr.gain)]
    if sdr.ppm:
        flags += ["-p", str(sdr.ppm)]
    return flags


class Backend(ABC):
    mode: str

    @property
    @abstractmethod
    def pcm_format(self) -> PcmFormat:
        ...

    @abstractmethod
    def source_command(self, preset: Preset, sdr: SdrConfig, aas_dir: str | None) -> list[str]:
        """argv for the source process (rtl_fm / nrsc5)."""

    def ffmpeg_command(self, audio: AudioConfig) -> list[str]:
        fmt = self.pcm_format
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "s16le", "-ar", str(fmt.sample_rate), "-ac", str(fmt.channels), "-i", "-",
            "-c:a", "libmp3lame", "-b:a", audio.bitrate,
            "-ar", str(audio.sample_rate), "-ac", str(audio.channels),
            "-f", "mp3", "pipe:1",
        ]

    def build_command(
        self,
        preset: Preset,
        audio: AudioConfig,
        sdr: SdrConfig,
        aas_dir: str | None = None,
    ) -> list[list[str]]:
        return [self.source_command(preset, sdr, aas_dir), self.ffmpeg_command(audio)]
