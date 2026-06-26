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


async def test_lot_image_sets_art_path(tmp_path):
    md = Metadata(EventBus())
    group = FakeGroup(LineReader([
        "13:31:00 LOT file: port=0800 lot=53000 name=KBCOHD01cf08.jpg size=5162 mime=1E653E9C expiry=2026\n",
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), group, str(tmp_path))
    await md._task
    assert md.art_path == str(tmp_path / "53000_KBCOHD01cf08.jpg")
    assert md.now_playing()["art"] is not None


async def test_newest_image_wins(tmp_path):
    md = Metadata(EventBus())
    group = FakeGroup(LineReader([
        "13:31:00 LOT file: port=0800 lot=1 name=old.jpg size=1 mime=X\n",
        "13:31:05 LOT file: port=0800 lot=2 name=new.png size=1 mime=X\n",
    ]))
    await md.switch(Preset("KBCO", "hd", 97.3, 0), group, str(tmp_path))
    await md._task
    assert md.art_path == str(tmp_path / "2_new.png")


async def test_non_image_lot_ignored(tmp_path):
    md = Metadata(EventBus())
    group = FakeGroup(LineReader([
        "13:31:00 LOT file: port=0880 lot=1 name=stuff.bin size=1 mime=X\n",
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
