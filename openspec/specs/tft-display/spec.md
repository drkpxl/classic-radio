# tft-display Specification

## Purpose
Render the daemon's live tuner state — frequency, mode, HD subchannel, preset label, now-playing title/artist, and signal status — to the on-device ST7789 TFT as a read-only readout that mirrors the daemon (the single source of truth), degrading gracefully to headless when no panel is present and tearing down cleanly on shutdown.
## Requirements
### Requirement: On-device tuner readout
The system SHALL render the daemon's current tuner state to the on-device ST7789 TFT as a read-only readout, showing the active frequency, mode (analog FM / HD / weather), the HD subchannel when applicable, and the configured preset label.

#### Scenario: HD station readout
- **WHEN** an HD preset with a subchannel is playing
- **THEN** the panel shows its frequency, an HD mode indicator, the subchannel (e.g. HD1/HD2), and the preset label

#### Scenario: Analog FM readout
- **WHEN** an analog FM preset is playing
- **THEN** the panel shows its frequency with an FM indicator and the preset label, and shows no subchannel

#### Scenario: Weather readout
- **WHEN** a weather preset (outside the 88–108 MHz FM dial) is active
- **THEN** the panel shows the weather frequency with a weather indicator and label rather than treating it as an FM dial position

### Requirement: Live mirroring of daemon state
The system SHALL keep the readout in sync with the daemon as the single source of truth, updating the panel whenever the active preset, signal status, or now-playing metadata changes, without polling and without a perceptible lag, and SHALL show the current state on startup before the first change occurs.

#### Scenario: Readout follows a preset change
- **WHEN** the active preset changes on the daemon (now or via a future physical button)
- **THEN** the panel updates to the new frequency, mode, and label without any external refresh

#### Scenario: Initial render on startup
- **WHEN** the renderer starts
- **THEN** the panel immediately shows the current preset and status rather than remaining blank until the next change

#### Scenario: Bursts of changes coalesce
- **WHEN** several state events arrive in quick succession (e.g. during a tune)
- **THEN** the panel renders the latest resulting state without redrawing once per intermediate event

### Requirement: Signal status indication
The system SHALL display the current signal status so that an acquiring, locked/playing, or no-signal station is distinguishable at a glance.

#### Scenario: Acquiring is shown
- **WHEN** the daemon status is acquiring
- **THEN** the panel shows an acquiring indication for the selected station

#### Scenario: No signal is shown
- **WHEN** the daemon status is no_signal
- **THEN** the panel shows a clear no-signal indication rather than stale now-playing text

#### Scenario: Playing is shown
- **WHEN** the daemon status is playing
- **THEN** the panel shows the station as playing

### Requirement: Now-playing text
The system SHALL display the current now-playing title and artist when available, fall back gracefully when they are not, and SHALL NOT render album art on the panel.

#### Scenario: Title and artist appear
- **WHEN** HD now-playing metadata (title/artist) is available for the playing station
- **THEN** the panel displays the title and artist

#### Scenario: Long text is kept legible
- **WHEN** a title or artist is too long for the panel width
- **THEN** the text is truncated (or otherwise kept readable) rather than overflowing or wrapping unboundedly

#### Scenario: No metadata falls back
- **WHEN** no title/artist is available (analog, weather, or not yet received)
- **THEN** the panel shows the preset label without title/artist and renders no album art

### Requirement: Optional, fail-soft display
The system SHALL treat the display as an optional peripheral controlled by configuration. When unconfigured it SHALL default to off so a panel-less or development machine runs headless, while the appliance's shipped configuration SHALL enable it. A missing panel, missing display libraries, or a hardware initialization failure SHALL NOT prevent the daemon from running headless.

#### Scenario: Disabled or unconfigured runs headless
- **WHEN** the display is disabled, or absent from configuration
- **THEN** the daemon runs exactly as it does headless, with no attempt to access display hardware

#### Scenario: Appliance configuration enables the readout
- **WHEN** the appliance's shipped configuration enables the display and a working panel is present
- **THEN** the daemon drives the on-device readout

#### Scenario: Hardware or library unavailable
- **WHEN** the display is enabled but the panel cannot be initialized (libraries absent or hardware not responding)
- **THEN** the daemon logs a warning and continues serving audio and the web UI without the readout

### Requirement: Clean lifecycle
The system SHALL start the readout as part of daemon startup and tear it down cleanly on shutdown, leaving no orphaned display hardware handles.

#### Scenario: Clean shutdown
- **WHEN** the daemon receives a termination signal
- **THEN** the render task stops and the panel is released cleanly with no orphaned SPI/GPIO handles
