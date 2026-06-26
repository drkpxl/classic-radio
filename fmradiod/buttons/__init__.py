"""On-device GPIO buttons: the two Mini PiTFT 1.14" buttons drive the preset ring.

The daemon stays the single source of truth — a press only calls
`tuner.next()` / `tuner.prev()`, and the web UI + TFT mirror the result via the
existing EventBus. Split into seams so the bulk is testable on a Mac with no
hardware:

- `debounce` — pure edge/debounce state machine (raw samples -> "next"/"prev"),
  no hardware, no asyncio.
- `source`   — thin `ButtonSource` interface (`GpioButtonSource`) + `FakeButtonSource`.
- `input`    — the async poll task that wires a source + debouncer to the tuner.

The Pi-only Blinka stack is imported lazily inside `source`, so importing this
package on the Mac (or a button-less Pi) costs nothing.
"""
