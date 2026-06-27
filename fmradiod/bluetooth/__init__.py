"""A2DP Bluetooth speaker output: manage pairing/connection over BlueZ and route
the live radio to a connected speaker (an exclusive alternative to the web stream).

Split into seams so the bulk is testable on a Mac with no system bus:
- `controller` — the `BluetoothController` interface + `FakeBluetoothController` (tests).
- `dbus`       — `DbusBluetoothController`: the real BlueZ/`dbus-fast` implementation,
  lazy-imported so importing this package on the Mac never needs a bus.

The daemon stays the single source of truth: the controller exposes a `state()`
snapshot folded into `build_state`, and any change calls an `on_change` callback
the app wires to the EventBus, so the web UI (and TFT) mirror it.
"""
