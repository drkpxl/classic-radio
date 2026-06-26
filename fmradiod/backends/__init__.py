"""Demod backends — each builds a native subprocess pipeline behind a common interface.

analog  : rtl_fm (WBFM)  -> ffmpeg
hd      : nrsc5          -> ffmpeg   (+ metadata / album art)
weather : rtl_fm (NBFM)  -> ffmpeg
"""
