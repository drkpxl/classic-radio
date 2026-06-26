from fmradiod.state import StateStore


def test_save_then_load(tmp_path):
    s = StateStore(tmp_path / "state.json")
    s.save_index(3)
    assert s.load_index(default=0) == 3


def test_load_missing_returns_default(tmp_path):
    s = StateStore(tmp_path / "nope.json")
    assert s.load_index(default=2) == 2


def test_load_corrupt_returns_default(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{not valid json")
    assert StateStore(p).load_index(default=1) == 1


def test_out_of_range_returns_default(tmp_path):
    s = StateStore(tmp_path / "state.json")
    s.save_index(9)
    assert s.load_index(default=0, count=6) == 0


def test_in_range_with_count(tmp_path):
    s = StateStore(tmp_path / "state.json")
    s.save_index(4)
    assert s.load_index(default=0, count=6) == 4
