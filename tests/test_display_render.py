from PIL import Image, ImageDraw

from fmradiod.display.render import SIZE, _ellipsize, _font, _wrap, build_view, render


def _state(mode, freq, *, hd_program=None, status="playing", title=None, artist=None, label="Station"):
    return {
        "preset": {"index": 0, "label": label, "mode": mode, "freq": freq, "hd_program": hd_program},
        "status": status,
        "now_playing": {"title": title, "artist": artist, "label": label, "art": None},
        "ring": [],
    }


def test_hd_subchannel_shows_hd_chip():
    v0 = build_view(_state("hd", 97.3, hd_program=0))
    assert v0.mode_badge == "HD"
    assert v0.hd_chip == "HD1"
    v1 = build_view(_state("hd", 93.3, hd_program=1))
    assert v1.hd_chip == "HD2"


def test_analog_shows_fm_and_no_subchannel():
    v = build_view(_state("analog", 93.3))
    assert v.mode_badge == "FM"
    assert v.hd_chip is None


def test_weather_shows_wx_and_frequency():
    v = build_view(_state("weather", 162.550))
    assert v.mode_badge == "WX"
    assert v.freq_text == "162.55"
    assert v.hd_chip is None


def test_no_signal_banner_and_no_stale_metadata():
    # now_playing carries stale text, but no_signal must not show it.
    v = build_view(_state("hd", 97.3, hd_program=0, status="no_signal",
                          title="Old Song", artist="Old Artist"))
    assert v.status_text == "NO SIGNAL"
    assert v.title is None
    assert v.artist is None


def test_title_and_artist_shown_when_playing():
    v = build_view(_state("hd", 97.3, hd_program=0, status="playing",
                          title="Song", artist="Artist"))
    assert v.title == "Song"
    assert v.artist == "Artist"


def test_missing_metadata_falls_back_to_label():
    v = build_view(_state("analog", 93.3, label="KTCL", title=None, artist=None))
    assert v.title is None
    assert v.artist is None
    assert v.label == "KTCL"


def test_ellipsize_truncates_long_text():
    img = Image.new("RGB", SIZE)
    d = ImageDraw.Draw(img)
    font = _font(15)
    long = "A really really really long song title that will not fit on the panel"
    out = _ellipsize(d, long, font, max_width=SIZE[0] - 16)
    assert out.endswith("…")
    assert len(out) < len(long)
    assert d.textlength(out, font=font) <= SIZE[0] - 16


def test_wrap_respects_max_lines_and_ellipsizes_overflow():
    img = Image.new("RGB", SIZE)
    d = ImageDraw.Draw(img)
    font = _font(20)
    width = SIZE[0] - 16
    # Short text -> single line, no ellipsis.
    assert _wrap(d, "Short", font, width, max_lines=2) == ["Short"]
    # Long text -> at most max_lines, last line ellipsized to signal the cut.
    lines = _wrap(d, "word " * 40, font, width, max_lines=2)
    assert len(lines) == 2
    assert lines[-1].endswith("…")
    for ln in lines:
        assert d.textlength(ln, font=font) <= width
    assert _wrap(d, "", font, width, max_lines=2) == []


def test_render_produces_correct_size_image_for_every_mode():
    for st in (
        _state("hd", 97.3, hd_program=1, status="playing", title="T", artist="A"),
        _state("analog", 93.3, status="acquiring"),
        _state("weather", 162.550, status="no_signal"),
        _state("hd", 90.1, hd_program=0, status="playing",
               title="An extremely long title " * 5, artist="Some Artist"),
    ):
        img = render(st)
        assert isinstance(img, Image.Image)
        assert img.size == SIZE


def test_render_no_art_drawn_even_when_present():
    # The TFT is a tuner readout; an art URL in state must not change the frame.
    base = _state("hd", 97.3, hd_program=0, title="X", artist="Y")
    with_art = {**base, "now_playing": {**base["now_playing"], "art": "/art/current?v=3"}}
    assert render(base).tobytes() == render(with_art).tobytes()
