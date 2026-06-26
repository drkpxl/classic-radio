## ADDED Requirements

### Requirement: Exclusive selectable audio output
The system SHALL expose an audio **output mode** that is either `web` or `bluetooth`, with exactly one active at a time. Selecting `bluetooth` SHALL route the live radio to the connected speaker and suspend the web fan-out; selecting `web` SHALL restore the web fan-out. The selected output SHALL be settable through the control API and reflected in the daemon state.

#### Scenario: Switching to bluetooth routes audio to the speaker
- **WHEN** a speaker is connected and the output is set to `bluetooth`
- **THEN** the live radio plays out the speaker and the web stream is suspended, with the demod/preset unchanged

#### Scenario: Switching back to web restores the stream
- **WHEN** the output is set back to `web`
- **THEN** the MP3 fan-out resumes serving listeners and audio stops going to the speaker

#### Scenario: Output switching does not overlap a tune
- **WHEN** an output change and a preset tune are requested close together
- **THEN** they are serialized so no two backend pipelines run at once (the existing single-SDR guarantee holds)

### Requirement: Discover and pair speakers from the web UI
The system SHALL let a user scan for nearby A2DP speakers and pair one from the web UI, using a just-works pairing agent (no PIN entry).

#### Scenario: Scan surfaces nearby speakers
- **WHEN** the user starts a scan from the UI
- **THEN** discovered devices (name + address + paired/connected status) appear in the daemon state and the UI list

#### Scenario: Pair a discovered speaker
- **WHEN** the user pairs a discovered speaker that is in pairing mode
- **THEN** the daemon pairs and trusts it via BlueZ without requiring a PIN, and the device shows as paired

### Requirement: Manage connection of paired speakers
The system SHALL let a user connect, disconnect, and forget paired speakers from the web UI.

#### Scenario: Connect and disconnect
- **WHEN** the user connects a paired speaker, then later disconnects it
- **THEN** the daemon connects/disconnects it via BlueZ and the connection status updates in the state

#### Scenario: Forget a speaker
- **WHEN** the user forgets a speaker
- **THEN** the daemon removes the pairing via BlueZ and the device leaves the paired list

### Requirement: Connected speaker drop falls back to web output
The system SHALL detect when the connected speaker drops while the output is `bluetooth`, surface it, and fall back to the `web` output so audio is never silently dead.

#### Scenario: Mid-playback disconnect recovers
- **WHEN** the connected speaker disconnects while output is `bluetooth`
- **THEN** the daemon surfaces the disconnect and switches the output back to `web`, keeping the daemon running

### Requirement: Bluetooth and output state mirrored through the daemon
The system SHALL include the Bluetooth device list, scanning state, connected device, and current output mode in the daemon state and broadcast changes on the existing event stream, so the web UI and TFT mirror the daemon as the single source of truth.

#### Scenario: UI reflects a device/output change without refresh
- **WHEN** a device connects/disconnects or the output mode changes on the daemon
- **THEN** the web UI updates its Bluetooth panel and output selector from the broadcast state without a manual refresh

### Requirement: Auto-reconnect and resume output on boot
The system SHALL persist the last connected speaker and the selected output mode and restore them on startup.

#### Scenario: Reboot reconnects the last speaker
- **WHEN** the daemon restarts after the output was `bluetooth` with a speaker connected
- **THEN** it attempts to reconnect that speaker and restore `bluetooth` output, falling back to `web` if the speaker is unavailable

### Requirement: Config-gated, fail-soft Bluetooth
The system SHALL gate Bluetooth behind a `bluetooth.enabled` config flag that defaults off, and SHALL degrade to web-only operation (logging a warning) when the Bluetooth stack or system bus is unavailable, never taking down audio or the web UI.

#### Scenario: Disabled by default touches no bus
- **WHEN** `bluetooth.enabled` is false or absent
- **THEN** no D-Bus/BlueZ code path runs and the daemon behaves exactly as before this change

#### Scenario: Unavailable stack degrades gracefully
- **WHEN** Bluetooth is enabled but the system bus or BlueZ is unavailable
- **THEN** the daemon logs a warning and runs with web output only, rather than crashing
