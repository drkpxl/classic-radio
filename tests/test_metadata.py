from fmradiod.config import Preset
from fmradiod.events import EventBus
from fmradiod.metadata import Metadata


class LineReader:
    """Stand-in for a source's stderr StreamReader."""

    def __init__(self, lines):
        self._lines = [(s.encode() if isinstance(s, str) else s) for s in lines]

    async def readline(self):
        return self._lines.pop(0) if self._lines else b""

    async def read(self, n):
        return b""


class FakeGroup:
    def __init__(self, reader):
        self.source_stderr = reader


async def test_parses_title_and_artist(tmp_path):
    md = Metadata(EventBus())
    group = FakeGroup(LineReader([
        "13:31:00 Title: Sailor Song\n",
        "13:31:00 Artist: Gigi Perez\n",
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), group, str(tmp_path))
    await md._task  # consume to EOF
    assert md.title == "Sailor Song"
    assert md.artist == "Gigi Perez"
    np = md.now_playing()
    assert np["title"] == "Sailor Song"
    assert np["artist"] == "Gigi Perez"


async def test_xhdr_selects_matching_art(tmp_path):
    # A LOT image alone is NOT shown; the XHDR lot picks the current program's art.
    md = Metadata(EventBus())
    group = FakeGroup(LineReader([
        "13:31:00 LOT file: port=0810 lot=53104 name=KBCOHD01cf70.jpg size=5162 mime=4F328CA0\n",
        "13:31:00 XHDR: 0 BE4B7536 53104\n",
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), group, str(tmp_path))
    await md._task
    assert md.art_path == str(tmp_path / "53104_KBCOHD01cf70.jpg")
    assert md.now_playing()["art"] is not None


async def test_xhdr_before_lot_also_works(tmp_path):
    # Ordering-robust: XHDR can reference a lot whose file arrives afterwards.
    md = Metadata(EventBus())
    group = FakeGroup(LineReader([
        "13:31:00 XHDR: 0 BE4B7536 53104\n",
        "13:31:01 LOT file: port=0810 lot=53104 name=KBCOHD01cf70.jpg size=5162 mime=4F328CA0\n",
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), group, str(tmp_path))
    await md._task
    assert md.art_path == str(tmp_path / "53104_KBCOHD01cf70.jpg")


async def test_art_does_not_bleed_other_subchannel(tmp_path):
    # The bug: KBCO HD1 also receives HD3's art + promo tiles. The XHDR (pointing at
    # the tuned program's lot) must win regardless of arrival order.
    md = Metadata(EventBus())
    group = FakeGroup(LineReader([
        "13:31:00 LOT file: port=0810 lot=53104 name=KBCOHD01cf70.jpg size=1 mime=4F328CA0\n",
        "13:31:00 XHDR: 0 BE4B7536 53104\n",
        "13:31:02 LOT file: port=0810 lot=62496 name=KBCOHD03f420.jpg size=1 mime=4F328CA0\n",
        "13:31:02 LOT file: port=0810 lot=708 name=TMT_promo_tile.png size=1 mime=4F328CA0\n",
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), group, str(tmp_path))
    await md._task
    # still the tuned program's art, NOT the later HD3 image or the promo tile
    assert md.art_path == str(tmp_path / "53104_KBCOHD01cf70.jpg")


async def test_art_is_sticky_across_minus_one(tmp_path):
    # HD pushes art slowly, so blanking on a station-ID gap (XHDR -1) makes it
    # flicker. Art is sticky: once shown it stays until a new song's art arrives.
    md = Metadata(EventBus())
    group = FakeGroup(LineReader([
        "13:31:00 LOT file: port=0810 lot=53104 name=KBCOHD01cf70.jpg size=1 mime=4F328CA0\n",
        "13:31:00 XHDR: 0 BE4B7536 53104\n",
        "13:31:30 XHDR: 1 BE4B7536 -1\n",       # station-ID gap
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), group, str(tmp_path))
    await md._task
    assert md.art_path == str(tmp_path / "53104_KBCOHD01cf70.jpg")   # kept, not blanked


async def test_switch_resets_sticky_art(tmp_path):
    # Sticky art must NOT carry across a preset switch (new program / aas dir).
    md = Metadata(EventBus())
    g1 = FakeGroup(LineReader([
        "13:31:00 LOT file: port=0810 lot=53104 name=KBCOHD01cf70.jpg size=1 mime=4F328CA0\n",
        "13:31:00 XHDR: 0 BE4B7536 53104\n",
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), g1, str(tmp_path))
    await md._task
    assert md.art_path is not None
    await md.switch(Preset("KTCL", "analog", 93.3), FakeGroup(LineReader([])), None)
    await md._task
    assert md.art_path is None


async def test_image_without_xhdr_shows_no_art(tmp_path):
    # Images arrive but no XHDR points at one → nothing shown (prevents the bleed).
    md = Metadata(EventBus())
    group = FakeGroup(LineReader([
        "13:31:00 LOT file: port=0810 lot=708 name=TMT_promo_tile.png size=1 mime=4F328CA0\n",
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), group, str(tmp_path))
    await md._task
    assert md.art_path is None


async def test_non_image_lot_ignored(tmp_path):
    md = Metadata(EventBus())
    group = FakeGroup(LineReader([
        "13:31:00 LOT file: port=0880 lot=1184 name=DWRI_data.txt size=1 mime=BB492AAC\n",
        "13:31:00 XHDR: 0 BE4B7536 1184\n",
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), group, str(tmp_path))
    await md._task
    assert md.art_path is None
    assert md.now_playing()["art"] is None


async def test_non_hd_is_label_only(tmp_path):
    md = Metadata(EventBus())
    group = FakeGroup(LineReader(["13:31:00 Title: should be ignored\n"]))
    await md.switch(Preset("WX", "weather", 162.55), group, None)
    await md._task
    assert md.title is None
    assert md.artist is None
    assert md.label == "WX"
    assert md.now_playing()["art"] is None


async def test_switch_publishes_event(tmp_path):
    bus = EventBus()
    q = bus.subscribe()
    md = Metadata(bus)
    await md.switch(Preset("KBCO", "hd", 97.3, 0), FakeGroup(LineReader([])), str(tmp_path))
    await md._task
    ev = q.get_nowait()
    assert ev["type"] == "now_playing"
    assert ev["label"] == "KBCO"


async def test_switch_resets_previous(tmp_path):
    md = Metadata(EventBus())
    g1 = FakeGroup(LineReader([
        "13:31:00 Title: Song A\n", "13:31:00 Artist: Band A\n",
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), g1, str(tmp_path))
    await md._task
    assert md.title == "Song A"
    await md.switch(Preset("KTCL", "analog", 93.3), FakeGroup(LineReader([])), None)
    await md._task
    assert md.title is None
    assert md.artist is None
    assert md.label == "KTCL"
