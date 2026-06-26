## ADDED Requirements

### Requirement: Two-button preset navigation
The system SHALL read two on-device GPIO buttons and map a press of each to preset-ring navigation on the daemon: the configured **next** button SHALL invoke `tuner.next()` and the configured **prev** button SHALL invoke `tuner.prev()`, advancing or retreating one entry through the curated ring with wraparound. Button-to-action assignment and GPIO pin numbers SHALL come from config, not hardcoded values.

#### Scenario: Next button advances the ring
- **WHEN** the next button is pressed while the daemon is tuned to a preset
- **THEN** the daemon tunes to the following preset in the ring (wrapping from the last to the first)

#### Scenario: Prev button retreats the ring
- **WHEN** the prev button is pressed while the daemon is tuned to a preset
- **THEN** the daemon tunes to the preceding preset in the ring (wrapping from the first to the last)

#### Scenario: Assignment comes from config
- **WHEN** the config maps each button to a pin and an action
- **THEN** which physical button triggers next vs prev follows the config, not hardcoded pin values

### Requirement: Edge-triggered, debounced presses
The system SHALL treat a press as the button's transition from released to pressed (a single edge), debounced in software, so that contact bounce produces exactly one action and holding a button down does NOT repeat the action.

#### Scenario: One press yields one action
- **WHEN** a button is pressed and released once, including electrical contact bounce around the transition
- **THEN** exactly one navigation action is issued

#### Scenario: Holding does not repeat
- **WHEN** a button is held down continuously
- **THEN** only the initial press issues an action and no further actions are issued until the button is released and pressed again

### Requirement: Daemon remains the single source of truth
The system SHALL route button presses solely through the daemon's existing tune entry points so that the daemon stays the single source of truth; button presses SHALL NOT update the web UI or TFT directly. Presses arriving while a tune is in progress SHALL be serialized by the existing tune lock and SHALL NOT queue an unbounded backlog of pending tunes.

#### Scenario: Web UI and TFT reflect a button press
- **WHEN** a button press changes the active preset
- **THEN** the web UI and the TFT readout update from the daemon's state broadcast, without the button code touching either surface

#### Scenario: Presses during an in-flight tune do not pile up
- **WHEN** several presses arrive in quick succession while a tune is still completing
- **THEN** they are applied through the serialized tune path without spawning overlapping tunes or accumulating an unbounded queue of deferred presses

### Requirement: Config-gated, fail-soft initialization
The system SHALL gate button input behind a `buttons.enabled` config flag that defaults to off, so a machine without the buttons (the dev Mac, a button-less Pi) runs unchanged. When enabled, any failure to import the GPIO stack or claim the pins SHALL be logged at WARNING and the daemon SHALL continue serving audio, web, and display without buttons.

#### Scenario: Disabled by default touches no GPIO
- **WHEN** the config has no `buttons` block or `buttons.enabled` is false
- **THEN** no GPIO library is imported and no input task runs, and the daemon behaves exactly as it did before this change

#### Scenario: Init failure degrades gracefully
- **WHEN** buttons are enabled but the GPIO stack is unavailable or the pins cannot be claimed
- **THEN** the daemon logs a warning and keeps running normally without button input rather than crashing

### Requirement: Clean teardown releases GPIO
The system SHALL start the button input task within the daemon lifespan and, on shutdown (e.g. systemd SIGTERM), cancel and await the task and release the GPIO lines, leaving no orphaned GPIO handles.

#### Scenario: Shutdown releases the buttons
- **WHEN** the daemon receives SIGTERM
- **THEN** the input task is cancelled and the button GPIO lines are released, with no orphaned handles holding the pins

#### Scenario: Buttons never block audio shutdown
- **WHEN** the daemon is shutting down
- **THEN** button teardown completes promptly and does not delay or block the tuner teardown or the audio fan-out stop
