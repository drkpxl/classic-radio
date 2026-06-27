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


def test_output_round_trip_and_default(tmp_path):
    s = StateStore(tmp_path / "state.json")
    assert s.load_output(default="web") == "web"      # absent → default
    s.save_output("bluetooth")
    assert s.load_output() == "bluetooth"
    s.save_output("garbage")
    assert s.load_output(default="web") == "web"       # invalid → default


def test_device_round_trip(tmp_path):
    s = StateStore(tmp_path / "state.json")
    assert s.load_device() is None
    s.save_device("50:99:5A:21:F8:BB")
    assert s.load_device() == "50:99:5A:21:F8:BB"
    s.save_device(None)
    assert s.load_device() is None


def test_writes_merge_not_clobber(tmp_path):
    # saving output must not wipe the preset index and vice versa
    s = StateStore(tmp_path / "state.json")
    s.save_index(3)
    s.save_output("bluetooth")
    s.save_device("AA:BB:CC:DD:EE:FF")
    assert s.load_index() == 3
    assert s.load_output() == "bluetooth"
    assert s.load_device() == "AA:BB:CC:DD:EE:FF"
