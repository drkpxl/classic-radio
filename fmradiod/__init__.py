"""fmradiod — headless FM / HD Radio / NOAA Weather radio daemon for the Pi 3A+.

A single asyncio process that owns the RTL-SDR, tunes a curated preset ring across
analog FM, HD Radio (nrsc5), and NOAA weather, encodes everything to one uniform
MP3 stream, and serves a retro web UI with a control API. The daemon is the single
source of truth for "what's playing"; the web UI (and, later, the TFT + buttons)
mirror it.
"""

__version__ = "0.1.0"
