## ADDED Requirements

### Requirement: Onboard Bluetooth controller and A2DP stack are up
The system SHALL bring up the Pi's onboard Bluetooth controller and a working BlueZ + A2DP stack, since none of it is present today and the single USB port is occupied by the RTL-SDR (no dongle is possible).

#### Scenario: Controller powers on and BlueZ is running
- **WHEN** the Bluetooth stack is installed and the controller is enabled (rfkill unblocked, service started)
- **THEN** `bluetoothctl` lists a powered controller and the A2DP sink role is available, with no missing-firmware errors

#### Scenario: A dead controller is an observable finding
- **WHEN** the onboard controller cannot be powered up on this DietPi image
- **THEN** the failure is captured (rfkill/firmware/service state) so it is distinguishable from a routing problem and can justify a drop verdict

### Requirement: A real Bluetooth speaker pairs and connects
The system SHALL pair, trust, and connect a real A2DP Bluetooth speaker over the onboard radio, with the steps documented for reuse.

#### Scenario: Speaker pairs and connects
- **WHEN** a speaker is put in pairing mode and `bluetoothctl` scan → pair → trust → connect is run
- **THEN** the speaker reaches the connected state with the A2DP profile active, and the pairing steps are recorded

### Requirement: Live radio audio routes to the speaker
The live radio's demod audio SHALL be routed to the connected speaker through an open-source A2DP path (`bluez-alsa` or, on fallback, PipeWire), proving the radio can play out of the speaker.

#### Scenario: Radio plays out of the speaker
- **WHEN** a station is tuned and its decoded audio is routed to the A2DP sink
- **THEN** the radio is audible from the speaker continuously, and the negotiated codec (e.g. SBC/AAC) is noted

#### Scenario: Tooling choice is recorded
- **WHEN** the A2DP path is working
- **THEN** the tool that achieved it (`bluez-alsa` primary, or PipeWire fallback if bluez-alsa failed) is recorded along with why

### Requirement: Resource headroom under concurrent demod + A2DP is measured
Sustained playback SHALL be observed with the demod and the A2DP encode running **concurrently**, and CPU, memory, and SoC temperature recorded, since concurrent headroom on the 512 MB / quad-A53 board is the gating factor.

#### Scenario: Concurrent sustained-load measurement is captured
- **WHEN** a live HD station decodes while its audio is routed to the speaker for a sustained interval
- **THEN** steady-state and peak CPU load, memory use, and temperature are captured, and any audio dropouts, latency, or reconnect glitches are noted

### Requirement: Feasibility verdict is recorded
A documented go/no-go verdict SHALL be produced classifying Bluetooth audio output as **first-class**, **best-effort**, or **dropped**, justified by the measured results, to govern the scope of the `build-bluetooth-output` change.

#### Scenario: Verdict drives downstream design
- **WHEN** the measurements, tooling choice, and stability notes are complete
- **THEN** a written verdict with its rationale is recorded so the build change knows the confirmed tooling, the ALSA sink the output-mode seam targets, and the CPU budget for the exclusive-output model
