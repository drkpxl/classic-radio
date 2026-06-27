## 1. Config

- [x] 1.1 Add a `ButtonsConfig` dataclass and a `buttons:` block to `fmradiod/config.py` (`enabled: bool = False`, `next_pin: int = 23`, `prev_pin: int = 24`, `debounce_ms: int = 25`, `poll_ms: int = 20`); parse it in `load_config` with safe defaults so existing configs without the block still load, validating pin/interval types like the `display:` block does. *(Added `ButtonsConfig` + `_buttons_from`; validates int types, non-negative distinct pins, positive intervals.)*
- [x] 1.2 Add a documented `buttons:` section to `config.yaml` with `enabled: false` (button-less stays the in-repo default). *(Added; `enabled: false` until on-device verification flips it on the Pi, task 7.3.)*
- [x] 1.3 Unit-test that config loads with and without the `buttons:` block, that bad field types raise `ConfigError`, and that defaults match the code defaults. *(7 tests in `tests/test_config.py`: defaults, parsed block, bad pin type, same-pin, non-positive interval, non-mapping.)*

## 2. Pure debounce / edge logic (no hardware)

- [x] 2.1 Create `fmradiod/buttons/debounce.py` with a pure state machine that, given a stream of raw `(next_pressed, prev_pressed)` samples and the debounce window, emits a `"next"` / `"prev"` action exactly once on a stable released→pressed edge. *(`Debouncer` integrator: candidate must agree for `stable_samples` polls; `stable_samples_for(debounce_ms, poll_ms)` helper.)*
- [x] 2.2 Ensure holding a button emits nothing after the initial edge, and that contact bounce around an edge collapses to a single action. *(Edge fires only on a committed released→pressed transition; hold/bounce covered by tests.)*
- [x] 2.3 Unit-test the state machine on the Mac (no hardware): a clean single press → one action; a bouncy press → one action; a held button → one action then silence until release+repress; simultaneous-ish presses resolve deterministically. *(9 tests in `tests/test_buttons_debounce.py`, all green.)*

## 3. Button-source seam & GPIO driver

- [x] 3.1 Define a thin `ButtonSource` interface (`read() -> (bool, bool)` with pressed = True, `close()`) in `fmradiod/buttons/source.py`, plus a `FakeButtonSource` used by tests that returns scripted samples. *(`FakeButtonSource` replays scripted samples then returns released forever.)*
- [x] 3.2 Implement `GpioButtonSource` (real hardware) using Blinka `board`/`digitalio` — two `DigitalInOut` inputs with `Pull.UP` on the configured pins, mapping active-low to pressed = True; lazy-import the Blinka stack inside `__init__` so it is never imported on the Mac. *(`board.D{pin}`, `Direction.INPUT` + `Pull.UP`, `pressed = not value`.)*
- [x] 3.3 Release the GPIO lines cleanly in `close()` (best-effort `deinit`, safe to call twice), consistent with `St7789Panel.close()`. *(Best-effort `deinit` on both lines, exceptions swallowed.)*

## 4. Input task & lifecycle

- [x] 4.1 Implement the button input task in `fmradiod/buttons/input.py`: holds a `ButtonSource`, the debounce state machine, and the `tuner`; polls every `poll_ms`, feeds samples through the state machine, and on an emitted action awaits `tuner.next()` / `tuner.prev()`. *(`ButtonInput` with `start()`/`run()`/`stop()`; `create_button_input` factory mirrors `create_renderer`.)*
- [x] 4.2 Confirm reads run inline (no executor — GPIO reads are non-blocking) and the loop stays cooperative via `await asyncio.sleep(poll_ms)`; do not buffer a backlog of presses (let the tuner lock serialize). *(Dispatch awaits the tune, so mid-tune presses aren't sampled — loop drops the firehose, no backlog.)*
- [x] 4.3 Handle cancellation cleanly: on cancel, stop polling and `source.close()` — no orphaned GPIO handles. *(`run()` `finally: source.close()`; `stop()` cancels+awaits, idempotent, closes even if never started.)*
- [x] 4.4 Unit-test the input task with `FakeButtonSource` and a fake/recording tuner: a scripted press calls `tuner.next()`/`prev()`, a held button calls once, and cancellation closes the source. *(8 tests in `tests/test_buttons_input.py`, all green.)*

## 5. Wire into the daemon

- [x] 5.1 In `fmradiod/__main__.py` `build_app()`, construct the button input holder alongside `tuner`/`renderer` (only attempt `GpioButtonSource` construction when `buttons.enabled`); pass it into `create_app`. *(Gated block mirrors the renderer; passes `button_input=` to `create_app`.)*
- [x] 5.2 In `web/app.py` `lifespan`, after `tuner.start()` (and renderer start) start the input task; on shutdown cancel/await it and `source.close()` around `tuner.stop()` (symmetric teardown). *(Started after renderer; stopped first on shutdown — reverse of startup. Covered by an end-to-end lifespan test in `test_web.py`.)*
- [x] 5.3 Implement fail-soft init: when `buttons.enabled` is true, attempt the lazy import + source construction; on `ImportError`/init/claim failure log a WARNING and skip the input task so the daemon keeps serving audio + web + display. *(In `create_button_input`; WARNING + `None` on failure.)*
- [x] 5.4 Unit-test that with `buttons.enabled=false` no GPIO code path is touched, and that a simulated init failure leaves the app starting normally. *(2 tests in `test_main.py`: disabled never calls `create_source`; enabled-but-failing still builds a working app.)*

## 6. Deploy

- [x] 6.1 Confirm `deploy/sync.sh` carries the new `fmradiod/buttons/` package to `/root/fmradio` (rsync dry-run; no exclude matches). No new pinned dependency — Blinka is already installed for the display. *(Verified via `rsync -n`: `fmradiod/buttons/{__init__,debounce,input,source}.py` + updated `config.py`/`__main__.py`/`web/app.py` + `config.yaml` all transfer; `.venv`/`__pycache__`/`.egg-info` excluded. No new dep.)*

## 7. On-device verification (Pi)

- [x] 7.1 Verify the button pins/polarity against Adafruit's current Mini PiTFT 1.14" button example; confirm GPIO #23/#24 and active-low pull-up, and that they do not collide with the panel's pins. Lock the constants once presses register correctly. *(Verified on hardware: pins #23/#24 claim cleanly alongside the running display (no collision), idle reads `(False,False)`, Blinka auto-detects the board (no force-board hint). Physical presses confirmed by the user — top→next, bottom→prev — constants locked.)*
- [x] 7.2 Run the full test suite on the Pi (`python -m pytest tests/ -v`) — all green, including the new button tests. *(127 passed, 1 skipped on the Pi — the skip is the display hardware-init guard; all button tests green.)*
- [x] 7.3 Set `buttons.enabled: true` in the Pi config, restart `fmradiod.service`, and confirm: next/prev cycle the ring with wraparound; the web UI and the TFT readout track each press live; a single press advances exactly one preset (no double-fire); holding does not auto-repeat; and `systemctl stop` leaves no orphaned GPIO handles. *(Verified: enabled + restarted clean (button source initialized, no fail-soft warning); index logger recorded clean single-step transitions `3→2→1→2` in both directions (no double-fire); user confirmed it works; one real SDR process (no orphan). `enabled: true` committed to repo `config.yaml` so it persists across syncs.)*

## 8. Docs

- [x] 8.1 Add a build-notes section (button wiring, GPIO #23/#24, debounce, any gotchas) consistent with `docs/tft-display-build.md`; update the project running-log/blog notes and the "Known limitations / follow-ups" list (buttons done → only the 3.5 mm jack remains as a phase). *(New `docs/gpio-buttons-build.md` build log + runbook; consolidated backlog in `docs/roadmap.md` (also added the Bluetooth-speaker phase); `headless-core-build.md` follow-ups now point to the roadmap.)*
