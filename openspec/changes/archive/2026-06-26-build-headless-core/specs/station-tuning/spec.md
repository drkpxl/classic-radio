## ADDED Requirements

### Requirement: Curated preset ring across modes
The system SHALL model a curated, ordered ring of presets, each declaring a mode (`analog`, `hd`, or `weather`), a frequency, and — for `hd` — a program number; the ring SHALL be navigable forward and backward with wraparound and SHALL be defined in an editable on-device config file.

#### Scenario: Ring navigation wraps
- **WHEN** the daemon is on the last preset and a "next" is requested
- **THEN** it advances to the first preset (and "prev" from the first wraps to the last)

#### Scenario: Modes are honored per preset
- **WHEN** a preset declaring `mode: hd` with a program number is selected
- **THEN** the HD backend is started for that frequency and program, not the analog backend

#### Scenario: Config defines the ring
- **WHEN** the config file lists the preset entries
- **THEN** the ring length and each preset's label/mode/frequency/program come from the config, not hardcoded values

### Requirement: Single-SDR exclusivity
The system SHALL guarantee that at most one demod backend pipeline holds the RTL-SDR at any time, and tune operations SHALL be serialized so concurrent requests cannot spawn overlapping pipelines.

#### Scenario: Only one backend runs
- **WHEN** the daemon is decoding one preset and a different preset is requested
- **THEN** the current backend pipeline is fully stopped before the new one is started

#### Scenario: Rapid switches do not overlap
- **WHEN** several tune requests arrive in quick succession
- **THEN** they are applied one at a time and no two backend pipelines run concurrently

### Requirement: Clean backend teardown
The system SHALL terminate a backend's entire subprocess group on switch and on shutdown, leaving no orphaned `rtl_fm` or `nrsc5` process holding the SDR.

#### Scenario: Switch leaves no orphans
- **WHEN** the daemon switches away from a preset
- **THEN** the previous pipeline's processes have exited before the next pipeline starts

#### Scenario: Shutdown releases the SDR
- **WHEN** the daemon receives SIGTERM (e.g. systemd stop)
- **THEN** it terminates child processes and exits without leaving the SDR claimed

### Requirement: Backend failure is surfaced and recovered
The system SHALL detect a backend or encoder process exiting unexpectedly, surface an error/retuning status, and attempt a bounded restart without crashing the daemon.

#### Scenario: Crashed backend restarts
- **WHEN** the active backend or its `ffmpeg` exits unexpectedly
- **THEN** the daemon reports an error status and attempts to restart the pipeline with backoff rather than terminating

#### Scenario: Missing SDR does not crash the daemon
- **WHEN** the SDR is absent or busy at tune time
- **THEN** the daemon reports a clear error in its state and stays running

### Requirement: Resume last station on boot
The system SHALL persist the currently selected preset and restore it on startup, falling back to a configured default when no valid saved state exists.

#### Scenario: Reboot resumes the prior station
- **WHEN** the daemon restarts after previously tuning to a preset
- **THEN** it tunes to that same preset on startup

#### Scenario: First run uses the default
- **WHEN** no saved state is present
- **THEN** the daemon tunes to the configured default preset
