## ADDED Requirements

### Requirement: nrsc5 decoder is built and runnable on the Pi
The system SHALL provide a working `nrsc5` HD Radio (NRSC-5) decoder compiled from source on the Raspberry Pi, since it is not available in the Debian repositories.

#### Scenario: Decoder is installed and reports usage
- **WHEN** `nrsc5` is invoked on the Pi after building
- **THEN** it runs without missing-library errors and prints its usage/version, confirming a successful build

### Requirement: HD lock and decode on a known local station
`nrsc5` SHALL acquire HD synchronization and decode digital audio on a known-strong local HD station (97.3 KBCO) using the existing RTL-SDR.

#### Scenario: Decoder synchronizes and produces audio
- **WHEN** `nrsc5` is tuned to 97.3 MHz with the antenna connected
- **THEN** it reports MER/BER lock and emits decoded audio frames rather than failing to synchronize

#### Scenario: Reception fails gracefully on a weak digital signal
- **WHEN** the digital subcarriers cannot be locked (e.g. signal too weak)
- **THEN** the failure is observable in the decoder output so it can be distinguished from a build or configuration problem

### Requirement: HD program lineup is enumerated
The decoder SHALL report the HD program lineup actually on air for the tuned station (HD1, and any HD2/HD3 subchannels).

#### Scenario: Available programs are listed
- **WHEN** `nrsc5` is locked onto the station
- **THEN** the available program numbers it exposes are captured and recorded for reference

### Requirement: Decoded HD audio is streamable for evaluation
The decoded HD audio SHALL be made available to a remote listener over HTTP, reusing the Phase-1 persistent fan-out approach, so its quality can be A/B compared against the analog FM stream.

#### Scenario: Listener hears HD audio from the desk
- **WHEN** a player connects to the HD stream endpoint from another machine on the network
- **THEN** it plays the decoded HD audio continuously, and a client disconnect does not stop the source

### Requirement: Resource headroom under sustained HD decode is measured
Sustained HD decode SHALL be observed and its CPU, memory, and SoC temperature recorded, since resource headroom is the gating factor for whether HD is viable on this hardware.

#### Scenario: Sustained-load measurement is captured
- **WHEN** HD decode runs continuously for a sustained interval
- **THEN** peak/steady CPU load, memory use, and temperature are captured, and any audio dropouts (xruns) are noted

### Requirement: Feasibility verdict is recorded
A documented go/no-go verdict SHALL be produced classifying HD Radio as **first-class**, **best-effort**, or **dropped**, justified by the measured results, to govern the scope of the future full-app change.

#### Scenario: Verdict drives downstream design
- **WHEN** the measurements and quality comparison are complete
- **THEN** a written verdict with its rationale is recorded so the full-app design knows whether to include an `nrsc5` demod backend, HD presets, and web-UI album art
