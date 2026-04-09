"""Streaming assistant speech generator (stub).

This module provides a placeholder `speaking` generator that takes the user's WAV bytes
and returns MP3 chunks that are suitable for streaming to a Gradio `Audio(streaming=True)`
component. For demonstration, we convert the input WAV to MP3 and yield it in small chunks.

Replace this implementation with the omni-mini model's streaming TTS for real usage.
"""

from __future__ import annotations

import io
from typing import Generator, Iterable
import numpy as np
import soundfile as sf

def chunk_bytes(data: bytes, chunk_size: int = 32_000) -> Iterable[bytes]:
    for start in range(0, len(data), chunk_size):
        yield data[start : start + chunk_size]


def speaking(wav_bytes: bytes) -> Generator[bytes, None, None]:
    """Yield MP3 bytes progressively for the assistant response.

    This stub converts the input WAV to MP3 and yields it in fixed-size chunks to emulate
    a streaming TTS system. Swap this out with omni-mini's streaming API.
    """
    try:
        # Try using pydub (requires ffmpeg)
        from pydub import AudioSegment
        segment = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
        processed = segment - 3
        out = io.BytesIO()
        processed.export(out, format="mp3", bitrate="64k")
        mp3_bytes = out.getvalue()
    except (ImportError, FileNotFoundError):
        # Fallback: return the original WAV bytes if ffmpeg is not available
        # This is not ideal but prevents the application from crashing
        print("Warning: ffmpeg not available, using WAV format instead of MP3")
        mp3_bytes = wav_bytes

    for part in chunk_bytes(mp3_bytes):
        yield part


