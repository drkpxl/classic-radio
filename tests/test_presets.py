import pytest

from fmradiod.presets import Ring


def test_starts_at_zero():
    r = Ring(["a", "b", "c"])
    assert r.index == 0
    assert r.current == "a"


def test_custom_start_index():
    r = Ring(["a", "b", "c"], start=2)
    assert r.index == 2
    assert r.current == "c"


def test_next_advances():
    r = Ring(["a", "b", "c"])
    assert r.next() == "b"
    assert r.index == 1


def test_next_wraps():
    r = Ring(["a", "b", "c"], start=2)
    assert r.next() == "a"
    assert r.index == 0


def test_prev_wraps():
    r = Ring(["a", "b", "c"], start=0)
    assert r.prev() == "c"
    assert r.index == 2


def test_prev_decrements():
    r = Ring(["a", "b", "c"], start=2)
    assert r.prev() == "b"
    assert r.index == 1


def test_get_jumps_to_index():
    r = Ring(["a", "b", "c"])
    assert r.get(2) == "c"
    assert r.index == 2


def test_get_out_of_range_raises():
    r = Ring(["a", "b", "c"])
    with pytest.raises(IndexError):
        r.get(5)
    with pytest.raises(IndexError):
        r.get(-1)


def test_single_element_wraps_to_self():
    r = Ring(["only"])
    assert r.next() == "only"
    assert r.prev() == "only"
    assert r.index == 0


def test_len():
    assert len(Ring(["a", "b"])) == 2


def test_empty_ring_raises():
    with pytest.raises(ValueError):
        Ring([])


def test_invalid_start_raises():
    with pytest.raises(IndexError):
        Ring(["a"], start=3)
