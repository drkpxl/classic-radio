from fmradiod.backends.analog import AnalogBackend
from fmradiod.backends.hd import HdBackend
from fmradiod.backends.weather import WeatherBackend
from fmradiod.config import AudioConfig, Preset, SdrConfig

AUDIO = AudioConfig(bitrate="256k", sample_rate=48000, channels=2)
SDR_AUTO = SdrConfig(gain="auto", ppm=0)

UNIFORM_OUT_TAIL = [
    "-c:a", "libmp3lame", "-b:a", "256k", "-ar", "48000", "-ac", "2", "-f", "mp3", "pipe:1",
]


def test_analog_pipeline():
    src, ff = AnalogBackend().build_command(
        Preset("KBCO", "analog", 97.3), AUDIO, SDR_AUTO
    )
    assert src == ["rtl_fm", "-f", "97.3M", "-M", "fm", "-s", "200000",
                   "-A", "std", "-r", "48000", "-E", "deemp", "-l", "0", "-"]
    assert ff == ["ffmpeg", "-hide_banner", "-loglevel", "error",
                  "-f", "s16le", "-ar", "48000", "-ac", "1", "-i", "-"] + UNIFORM_OUT_TAIL


def test_hd_pipeline_includes_program_and_aas_dir():
    src, ff = HdBackend().build_command(
        Preset("KBCO", "hd", 97.3, 0), AUDIO, SDR_AUTO, aas_dir="/tmp/aas"
    )
    assert src == ["nrsc5", "-o", "-", "-t", "raw", "--dump-aas-files", "/tmp/aas", "97.3", "0"]
    assert ff[:11] == ["ffmpeg", "-hide_banner", "-loglevel", "error",
                       "-f", "s16le", "-ar", "44100", "-ac", "2", "-i"]
    assert ff[-len(UNIFORM_OUT_TAIL):] == UNIFORM_OUT_TAIL


def test_hd_program_one():
    src, _ = HdBackend().build_command(
        Preset("Punk Tacos", "hd", 93.3, 1), AUDIO, SDR_AUTO, aas_dir="/tmp/x"
    )
    assert src[-2:] == ["93.3", "1"]


def test_weather_pipeline():
    src, ff = WeatherBackend().build_command(
        Preset("WX", "weather", 162.55), AUDIO, SDR_AUTO
    )
    assert src == ["rtl_fm", "-f", "162.55M", "-M", "fm", "-s", "22050",
                   "-r", "22050", "-E", "deemp", "-l", "0", "-"]
    assert ff[:11] == ["ffmpeg", "-hide_banner", "-loglevel", "error",
                       "-f", "s16le", "-ar", "22050", "-ac", "1", "-i"]


def test_uniform_output_across_backends():
    out_a = AnalogBackend().build_command(Preset("a", "analog", 97.3), AUDIO, SDR_AUTO)[1]
    out_h = HdBackend().build_command(Preset("h", "hd", 97.3, 0), AUDIO, SDR_AUTO, aas_dir="/tmp/x")[1]
    out_w = WeatherBackend().build_command(Preset("w", "weather", 162.55), AUDIO, SDR_AUTO)[1]
    for out in (out_a, out_h, out_w):
        assert out[-len(UNIFORM_OUT_TAIL):] == UNIFORM_OUT_TAIL


def test_gain_and_ppm_flags_injected():
    sdr = SdrConfig(gain=40, ppm=2)
    src, _ = AnalogBackend().build_command(Preset("a", "analog", 97.3), AUDIO, sdr)
    assert src[:5] == ["rtl_fm", "-g", "40", "-p", "2"]
    src_hd, _ = HdBackend().build_command(Preset("h", "hd", 97.3, 0), AUDIO, sdr, aas_dir="/tmp/x")
    assert src_hd[:5] == ["nrsc5", "-g", "40", "-p", "2"]


def test_auto_gain_and_zero_ppm_omit_flags():
    src, _ = AnalogBackend().build_command(Preset("a", "analog", 97.3), AUDIO, SDR_AUTO)
    assert "-g" not in src
    assert "-p" not in src


SINK = "bluealsa:DEV=50:99:5A:21:F8:BB,PROFILE=a2dp"


def test_bluetooth_output_is_three_stage_aplay_pipeline():
    cmds = AnalogBackend().build_command(
        Preset("KBCO", "analog", 97.3), AUDIO, SDR_AUTO, alsa_sink=SINK
    )
    assert len(cmds) == 3
    src, ff, ap = cmds
    assert src[0] == "rtl_fm"
    # ffmpeg emits uniform WAV to the pipe (no MP3 re-encode on the BT path)
    assert ff[0] == "ffmpeg"
    assert ff[-7:] == ["-ar", "48000", "-ac", "2", "-f", "wav", "pipe:1"]
    assert "libmp3lame" not in ff
    # final stage streams to the connected speaker's bluealsa A2DP sink
    assert ap == ["aplay", "-q", "-D", SINK, "-"]


def test_web_output_unchanged_when_no_sink():
    cmds = AnalogBackend().build_command(Preset("a", "analog", 97.3), AUDIO, SDR_AUTO)
    assert len(cmds) == 2
    assert cmds[1][-len(UNIFORM_OUT_TAIL):] == UNIFORM_OUT_TAIL
