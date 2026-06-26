from fmradiod.buttons.debounce import NEXT, PREV, Debouncer, stable_samples_for


def _feed_next(d, raw_sequence):
    """Feed a sequence of raw `next` samples (prev held released), collect actions."""
    out = []
    for raw in raw_sequence:
        out.extend(d.update(raw, False))
    return out


def test_stable_samples_for_rounds_up():
    assert stable_samples_for(25, 20) == 2   # 1.25 polls -> 2
    assert stable_samples_for(20, 20) == 1
    assert stable_samples_for(60, 20) == 3
    assert stable_samples_for(0, 20) == 1     # never below 1


def test_clean_press_emits_once():
    d = Debouncer(stable_samples=2)
    # released, then pressed-and-held: commits on the 2nd pressed sample.
    actions = _feed_next(d, [False, True, True, True, True])
    assert actions == [NEXT]


def test_bouncy_press_collapses_to_one_action():
    d = Debouncer(stable_samples=2)
    # Contact bounce (flicker) then settles pressed — still exactly one action.
    actions = _feed_next(d, [False, True, False, True, True, True])
    assert actions == [NEXT]


def test_holding_does_not_repeat():
    d = Debouncer(stable_samples=2)
    # A long hold after the press edge must emit nothing further.
    actions = _feed_next(d, [True, True] + [True] * 50)
    assert actions == [NEXT]


def test_release_then_press_emits_again():
    d = Debouncer(stable_samples=2)
    seq = [True, True]          # press -> 1 action
    seq += [False, False]       # committed release (no action)
    seq += [True, True]         # press again -> 1 action
    actions = _feed_next(d, seq)
    assert actions == [NEXT, NEXT]


def test_too_short_to_commit_is_ignored():
    # A single pressed sample with a 2-sample window never commits.
    d = Debouncer(stable_samples=2)
    actions = _feed_next(d, [True, False, False])
    assert actions == []


def test_stable_one_is_immediate():
    d = Debouncer(stable_samples=1)
    actions = _feed_next(d, [True])
    assert actions == [NEXT]


def test_two_buttons_independent():
    d = Debouncer(stable_samples=1)
    assert d.update(False, True) == [PREV]
    assert d.update(True, True) == [NEXT]   # prev already committed-pressed, only next edges
    assert d.update(True, True) == []       # both held, no new edges


def test_simultaneous_press_is_deterministic():
    # Both buttons cross the press edge on the same sample: next before prev,
    # both reported (never silently dropped).
    d = Debouncer(stable_samples=1)
    assert d.update(True, True) == [NEXT, PREV]
