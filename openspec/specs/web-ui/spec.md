# web-ui Specification

## Purpose
TBD - created by archiving change build-headless-core. Update Purpose after archive.
## Requirements
### Requirement: Retro UI driven by live state
The system SHALL serve a web UI based on the existing retro tabletop-radio design, with its presets, active selection, and tuner readout driven by the daemon's live state rather than hardcoded values.

#### Scenario: Presets reflect the configured ring
- **WHEN** the UI loads
- **THEN** it renders one preset control per configured preset, labeled from the config, and highlights the currently playing one

#### Scenario: UI mirrors server-side preset changes
- **WHEN** the active preset changes on the daemon (including via a future physical button)
- **THEN** the UI updates its active preset and tuner readout to match without a manual refresh

#### Scenario: Off-dial weather is shown sensibly
- **WHEN** a weather preset (outside the 88–108 MHz FM dial) is active
- **THEN** the UI parks the dial needle and shows a weather indicator and label instead of pushing the needle off-scale

### Requirement: Playback control
The system SHALL provide a play/power control that starts browser audio playback of the live stream on user interaction.

#### Scenario: Audio starts on click
- **WHEN** the user activates the play/power control
- **THEN** the browser begins playing the live MP3 stream

### Requirement: Control API for tuning
The system SHALL expose endpoints to select the next preset, the previous preset, or a specific preset by index, each returning the resulting state.

#### Scenario: Tune endpoint changes the station
- **WHEN** a tune request for a valid preset index is received
- **THEN** the daemon switches to that preset and responds with the new current state

### Requirement: State snapshot
The system SHALL expose a state endpoint returning the current preset, the full ring, current now-playing metadata, an album-art URL, and HD lock/signal status.

#### Scenario: State reports now-playing
- **WHEN** the state endpoint is queried while an HD station is playing
- **THEN** the response includes the current title/artist (when available) and an art URL

### Requirement: Live now-playing and album art
The system SHALL push now-playing and album-art changes to connected browsers in real time, and SHALL serve the current HD album art with a graceful fallback when none is available.

#### Scenario: Metadata updates appear live
- **WHEN** the HD metadata or album art changes for the playing station
- **THEN** subscribed browsers update the displayed title/artist and art without a manual refresh

#### Scenario: Missing art falls back
- **WHEN** there is no album art (analog, weather, or not yet received)
- **THEN** the art request returns a not-found result and the UI shows a default station graphic

