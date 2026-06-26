# Build Log — the GPIO preset buttons

**Goal:** make the appliance operable without a browser — the two Adafruit Mini
PiTFT 1.14" buttons cycle the preset ring. Tightly scoped: **press = next/prev
only** (no long-press, no mute/power). The daemon stays the single source of
truth, so the web UI and the TFT readout mirror each press for free.

**Result:** ✅ **done & verified on hardware.** Unit-tested on the Mac and the
full suite green on the Pi (127 passed, 1 skipped). Live press-test confirmed:
top→next, bottom→prev, clean single-step transitions in both directions (no
double-fire), web UI + TFT track each press, no orphaned GPIO handles on stop.
`buttons.enabled: true` is committed in the repo `config.yaml`.

## What it is

A small async task inside `fmradiod` that polls the two buttons and, on a press,
calls the daemon's existing `tuner.next()` / `tuner.prev()`:

- **Button A (top, GPIO #23) → next preset; Button B (bottom, GPIO #24) → prev.**
- The ring wraps (next from the last → the first), exactly as the web `/api/next`
  and `/api/prev` endpoints already do — buttons are just another trigger.
- A press is **edge-triggered and debounced**: one press = one tune; holding does
  nothing extra; contact bounce collapses to a single action.
- **No UI code touched.** Because a press goes through the tuner and the tuner
  broadcasts on the `EventBus`, the web UI (SSE) and the TFT readout update
  themselves — the button code never talks to either.

## How it's built (the seams)

Mirrors the display package's pure-logic + hardware-seam split, so the bulk is
testable on a Mac with no hardware:

- `fmradiod/buttons/debounce.py` — a **pure** `Debouncer` state machine. Fed one
  `(next_pressed, prev_pressed)` raw sample per poll; an action fires only on a
  *committed* released→pressed edge (a candidate change must agree for
  `stable_samples` consecutive polls). No hardware, no asyncio — bounce/hold/
  re-press are unit-tested with scripted sample sequences.
- `fmradiod/buttons/source.py` — a thin `ButtonSource` interface.
  `FakeButtonSource` replays scripted samples for tests (runs anywhere);
  `GpioButtonSource` reads the real buttons and **lazy-imports** the Pi-only
  Blinka `board`/`digitalio` stack inside `__init__`. Buttons are **active-low**
  (idle high via internal `Pull.UP`, low while pressed) → `pressed = not value`.
- `fmradiod/buttons/input.py` — `ButtonInput`: the async poll loop. Reads are
  cheap non-blocking GPIO reads, so — unlike the panel's SPI blit — they run
  **inline on the event loop, no executor**. A press `await`s the (lock-
  serialized) tune; presses arriving mid-tune simply aren't sampled until it
  returns, so the loop **drops the firehose** instead of queuing a backlog.
- Wired in `__main__.build_app()` + `web/app.py` lifespan: started after the
  tuner (and renderer), torn down **before** them (reverse order), releasing the
  GPIO lines. **Off by default** (`buttons.enabled: false`); enabling it imports
  the GPIO source *only then*, and any failure (no Blinka, contended pin) logs a
  warning and runs without buttons — input hardware can never take down audio.

Config (`config.yaml`):

```yaml
buttons:
  enabled: false    # set true on the Pi once verified
  next_pin: 23      # BCM GPIO #23 (top button) → next preset
  prev_pin: 24      # BCM GPIO #24 (bottom button) → prev preset
  debounce_ms: 25   # stable interval a press must hold before it registers
  poll_ms: 20       # input-loop poll interval
```

## On the Pi (verification runbook)

Status on `fmradio.local` (Pi 3A+, DietPi, Python 3.13):

1. **No new deps** — the buttons reuse the `adafruit-blinka` (`board`/`digitalio`)
   stack already installed for the TFT. Nothing to `pip install`.
2. **Pins claimable** — *confirmed.* With the display service running,
   `GpioButtonSource(23, 24)` constructs, reads idle `(False, False)` (pull-up
   working, active-low polarity correct), and closes cleanly — no collision with
   the panel's CE0/D25/D22/SPI, and Blinka auto-detects the board (no
   `BLINKA_FORCEBOARD` hint needed).
3. **Confirm the pin↔button mapping** against Adafruit's current Mini PiTFT 1.14"
   button example (the two buttons are documented on GPIO #23 top / #24 bottom).
   If a board revision differs, swap `next_pin`/`prev_pin` in config — no code
   change.
4. **Run the suite** — *done:* `python -m pytest -q` → 127 passed, 1 skipped (the
   skip is the display hardware-init guard; debounce/input/fail-soft are covered).
5. **Enable + restart + press** — *done.* Set `buttons.enabled: true`,
   `systemctl restart fmradiod`, then pressed each button and confirmed:
   - top button advances the ring, bottom retreats it, both wrap; ✓
   - the web UI **and** the TFT readout track each press live; ✓
   - a single press moves **exactly one** preset (no double-fire from bounce); ✓
     (an index logger recorded clean `±1` transitions in both directions);
   - holding a button does **not** auto-repeat; ✓
   - one real SDR process, no orphaned GPIO handles. ✓

## Gotchas worth remembering

- **Reads are inline; no executor (unlike the panel).** A `digitalio` read is a
  microsecond GPIO read, not a blocking SPI flush — so the poll loop reads inline
  and stays cooperative via `await asyncio.sleep(poll_ms)`. Only the panel's blit
  needs the thread pool.
- **Don't buffer presses.** `await`-ing the tune inside the poll loop means mid-
  tune presses aren't sampled and the tuner lock serializes everything — no pile
  of queued tunes. A radio can't meaningfully act on five buffered "next" presses.
- **Edge, not level.** Acting on the released→pressed *edge* (not "is pressed")
  is what stops a held button from spinning the ring. Bounce is absorbed by the
  `stable_samples` window.
- **One GPIO stack.** The TFT change deliberately adopted Blinka `digitalio` so
  the buttons could reuse it — the panel and the buttons share one library and
  one fail-soft init pattern.
- **Gated + fail-soft, like the display.** `buttons.enabled` defaults off so the
  Mac and any button-less Pi run unchanged; an init failure degrades to no-buttons
  rather than crashing the daemon — check the journal for the warning.
