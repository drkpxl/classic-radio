## ADDED Requirements

### Requirement: Uniform output format across backends
The system SHALL encode every backend's audio to a single uniform format (48 kHz, stereo, 256 kbps MP3) regardless of the source's native rate or channel count, so the broadcast byte stream is format-stable across preset switches.

#### Scenario: All modes produce the same stream format
- **WHEN** the daemon is decoding an analog, HD, or weather preset
- **THEN** the MP3 fan-out is the same 48 kHz / stereo / 256 kbps format in every case

### Requirement: Single-encoder multi-client fan-out
The system SHALL serve the live audio to many concurrent HTTP listeners from a single encoder, broadcasting encoder output to per-client buffers.

#### Scenario: Multiple listeners share one encoder
- **WHEN** two or more clients connect to the stream endpoint
- **THEN** all of them receive the audio without starting additional encoder processes

#### Scenario: Client disconnect does not stop the source
- **WHEN** a connected client disconnects
- **THEN** the encoder keeps running and other listeners are unaffected

### Requirement: Stream survives preset switches
The system SHALL keep a listener's single stream connection open across a preset switch, transitioning the audio to the new station rather than requiring the client to reconnect.

#### Scenario: Tuning does not drop the connection
- **WHEN** the preset changes while a client is listening
- **THEN** the client's existing stream connection continues and begins delivering the new station's audio

### Requirement: Slow clients are isolated
The system SHALL bound each client's buffer and drop or disconnect a client that cannot keep up, so a slow client never blocks the encoder or other listeners.

#### Scenario: A lagging client is dropped, not propagated
- **WHEN** one client consumes its buffer too slowly
- **THEN** that client's oldest data is dropped (and it is disconnected if it cannot recover) while other listeners continue uninterrupted
