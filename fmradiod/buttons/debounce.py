"""Pure edge + debounce logic for the two preset buttons.

No hardware, no asyncio — just a state machine fed one raw poll sample at a time.
Keeping it pure means the tricky parts (bounce, hold, re-press) are unit-tested
on a Mac with scripted sample sequences, mirroring the display's pure `render()`.

Model: each button is debounced by an integrator — a candidate change must agree
for `stable_samples` consecutive polls before it's committed. An action fires
only on a *committed* released->pressed transition, so:
  - contact bounce around an edge never reaches `stable_samples` and is ignored;
  - holding a button emits exactly one action (the press edge), nothing after;
  - a new action needs a committed release followed by a fresh committed press.
"""

from __future__ import annotations

import math

NEXT = "next"
PREV = "prev"


def stable_samples_for(debounce_ms: int, poll_ms: int) -> int:
    """How many consecutive same-value polls equal the debounce window."""
    return max(1, math.ceil(debounce_ms / poll_ms))


class Debouncer:
    """Debounce two active-high (already normalized to pressed=True) buttons.

    Feed one `(next_pressed, prev_pressed)` sample per poll via `update`; it
    returns the actions whose button just committed a press this sample (a list
    so a same-sample double press is deterministic and never silently dropped).
    """

    def __init__(self, stable_samples: int = 2):
        self._stable = max(1, int(stable_samples))
        # Committed (debounced) state per button; both start released.
        self._committed = {NEXT: False, PREV: False}
        # In-progress candidate change per button: (candidate_value, run_length).
        self._cand = {NEXT: (False, 0), PREV: (False, 0)}

    def update(self, next_pressed: bool, prev_pressed: bool) -> list[str]:
        actions: list[str] = []
        for name, raw in ((NEXT, bool(next_pressed)), (PREV, bool(prev_pressed))):
            if self._feed(name, raw):
                actions.append(name)
        return actions

    def _feed(self, name: str, raw: bool) -> bool:
        committed = self._committed[name]
        if raw == committed:
            # Settled back to the committed level — drop any pending candidate.
            self._cand[name] = (committed, 0)
            return False

        cand_val, cand_n = self._cand[name]
        cand_n = cand_n + 1 if raw == cand_val else 1
        cand_val = raw

        if cand_n >= self._stable:
            self._committed[name] = raw
            self._cand[name] = (raw, 0)
            return raw  # True only for a released->pressed commit (the press edge)

        self._cand[name] = (cand_val, cand_n)
        return False
