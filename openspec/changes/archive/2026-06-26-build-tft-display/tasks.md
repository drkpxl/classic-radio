## 1. Config & shared state

- [x] 1.1 Add a `Display` config dataclass and a `display:` block to `fmradiod/config.py` (`enabled: bool = False`, `rotation: int = 90`, `brightness: int|float`); parse it in `load_config` with safe defaults so existing configs without the block still load.
- [x] 1.2 Add a `display:` section to `config.yaml` documented and set `enabled: false` (headless stays the default in-repo).
- [x] 1.3 Lift `build_state(tuner, metadata)` out of `fmradiod/web/app.py` into a neutral module (e.g. `fmradiod/viewstate.py`) and re-import it in `web/app.py`, so the display module can derive state without importing the web app.
- [x] 1.4 Add/adjust unit tests confirming config loads with and without the `display:` block, and that the lifted `build_state` returns the same dict the web layer expects.

## 2. Pure render logic (no hardware)

- [x] 2.1 Create `fmradiod/display/render.py` with a pure `render(state, size) -> PIL.Image` that draws the landscape layout: frequency + mode badge (FM/HD/WX), HD subchannel chip, preset label, signal-status indicator, and now-playing title/artist.
- [x] 2.2 Ship a font file in the package (or use Pillow's bundled DejaVu) and load it deterministically — no system fonts. *(Vendored DejaVuSans Regular+Bold to `fmradiod/display/fonts/`; Pillow's bundled font lacks en/em-dashes and accented Latin used in real labels/metadata.)*
- [x] 2.3 Implement title/artist truncation (ellipsize) so long strings stay within the 240 px width without wrapping unboundedly.
- [x] 2.4 Map status to a clear, color-coded indication for `acquiring` / `no_signal` / `playing`; ensure `no_signal` does not show stale now-playing text.
- [x] 2.5 Unit-test `render()` on the Mac (no hardware) against built states: HD-with-subchannel shows `HD1`; analog shows `FM` and no subchannel; weather shows `WX`/frequency; `no_signal` shows the banner; a long title is truncated; missing metadata falls back to the label and draws no art.

## 3. Panel seam & hardware driver

- [x] 3.1 Define a thin `Panel` interface (`show(image)`, `close()`, `size`) in `fmradiod/display/panel.py`, plus a `FakePanel` used by tests that records the last image.
- [x] 3.2 Implement `St7789Panel` (real hardware) using `adafruit_rgb_display.st7789.ST7789` + Blinka (`board`/`busio`/`digitalio`) with the Mini PiTFT 1.14" pins/offsets/rotation as named constants; lazy-import the driver stack so it is never imported on the Mac.
- [x] 3.3 Drive the backlight on at the configured brightness; release SPI/GPIO cleanly in `close()`.

## 4. Renderer task & lifecycle

- [x] 4.1 Implement `TftRenderer` in `fmradiod/display/renderer.py`: holds `tuner`, `metadata`, a `Panel`, and a dedicated single-worker `ThreadPoolExecutor`; subscribes to `bus.events()`.
- [x] 4.2 On start, render the current state immediately; then on each event re-derive full state via `build_state(tuner, metadata)`, coalesce any immediately-queued events, and render only the latest.
- [x] 4.3 Run every blit via `loop.run_in_executor(panel_executor, panel.show, image)` so SPI never blocks the event loop; serialize through the single worker.
- [x] 4.4 Handle cancellation cleanly: await the in-flight blit, clear/close the panel, shut down the executor — no orphaned handles.
- [x] 4.5 Unit-test the renderer with `FakePanel` and a fake/event-driven bus: initial render happens, a published state event triggers a re-render, and a burst coalesces to one render of the latest state.

## 5. Wire into the daemon

- [x] 5.1 In `fmradiod/__main__.py` `build_app()`, construct the renderer alongside `tuner`/`metadata`/`bus` and stash it on app state (only attempt panel construction when `display.enabled`).
- [x] 5.2 In `web/app.py` `lifespan`, after `tuner.start()` start the render task; on shutdown cancel/await it and `panel.close()` around `tuner.stop()` (symmetric teardown).
- [x] 5.3 Implement fail-soft init: when `display.enabled` is true, attempt the lazy import + panel init; on `ImportError`/init/hardware failure, log a WARNING and skip the renderer so the daemon keeps serving audio + web.
- [x] 5.4 Unit-test that with `display.enabled=false` no display code path is touched, and that a simulated init failure leaves the app starting normally.

## 6. Dependencies & deploy

- [x] 6.1 Add `adafruit-circuitpython-rgb-display`, `adafruit-blinka`, and `Pillow` to `requirements.txt` and `pyproject.toml` (keep them Pi-only at runtime via the lazy import). *(Pillow in main deps; Blinka + rgb-display in requirements.txt and a `[display]` extra; fonts declared as package-data.)*
- [x] 6.2 Confirm `deploy/sync.sh` carries the new `fmradiod/display/` package and any font asset to `/root/fmradio`. *(Verified via rsync dry-run: display package + both .ttf fonts transfer; no exclude matches.)*

## 7. On-device verification (Pi)

- [x] 7.1 Enable SPI on the Pi (`dtparam=spi=on`) and reboot; install the new deps into `/root/fmradio/.venv`. *(SPI was already enabled — `/dev/spidev0.0/0.1` present, no reboot needed. Installed `python3.13-dev` (for RPi.GPIO/rpi_ws281x C-ext build) then `pip install -r requirements.txt`: Pillow 12.2.0, adafruit-blinka 9.1.0, adafruit-circuitpython-rgb-display 3.14.6.)*
- [x] 7.2 Verify the panel pins/offsets/rotation against Adafruit's current `rgb_display_minipitft.py` example; lock the constants once the image is correctly positioned (no shift/garble). Note any `BLINKA_FORCEBOARD`/`BLINKA_FORCECHIP` hint needed on DietPi. *(Confirmed visually on the panel — image upright and correctly positioned with `x_offset=53/y_offset=40/rotation 90`. Blinka auto-detects `RASPBERRY_PI_3A_PLUS`, no force-board hint needed.)*
- [x] 7.3 Run the full test suite on the Pi (`python -m pytest tests/ -v`) — all green, including the new display tests. *(100 passed, 1 skipped on Python 3.13.5 + real Blinka — the skip is the hardware-init guard, deferred to 7.2/7.4.)*
- [x] 7.4 Set `display.enabled: true` in the Pi config, restart `fmradiod.service`, and confirm: readout tracks tunes/HD metadata live, status indications are correct (acquiring/no_signal/playing), long titles truncate, and `systemctl stop` leaves no orphaned SPI/GPIO handles. *(`enabled: true` committed to repo config.yaml (persists across syncs). Verified live: readout tracked tunes + HD title/artist; status dot correct (green/amber/red); clean stop → service inactive, spidev free, no orphaned procs, clean shutdown in journal. Layout revised per feedback: status word dropped → color dot left of the mode badge; bigger title/artist with 2-line wrap.)*

## 8. Docs

- [x] 8.1 Add a build-notes section (wiring, `dtparam=spi=on`, ST7789 1.14" offsets/rotation gotchas, any Blinka force-board hint) consistent with `docs/headless-core-build.md`, and update the project running-log/blog notes. *(New `docs/tft-display-build.md` build log + on-device runbook.)*
