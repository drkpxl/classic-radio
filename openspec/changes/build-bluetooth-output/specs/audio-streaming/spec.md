## MODIFIED Requirements

### Requirement: Single-encoder multi-client fan-out
The system SHALL serve the live audio to many concurrent HTTP listeners from a single encoder, broadcasting encoder output to per-client buffers, **whenever the `web` output is selected**. When the `bluetooth` output is selected the fan-out SHALL be suspended (the encoder feeds the speaker instead), since outputs are exclusive — one sink at a time.

#### Scenario: Multiple listeners share one encoder
- **WHEN** two or more clients connect to the stream endpoint while the `web` output is selected
- **THEN** all of them receive the audio without starting additional encoder processes

#### Scenario: Client disconnect does not stop the source
- **WHEN** a connected client disconnects
- **THEN** the encoder keeps running and other listeners are unaffected

#### Scenario: Web fan-out is suspended on the bluetooth output
- **WHEN** the output is switched to `bluetooth`
- **THEN** the MP3 fan-out stops serving new audio to web listeners (audio is routed to the speaker), and switching back to `web` resumes it
