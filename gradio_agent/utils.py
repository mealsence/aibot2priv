from __future__ import annotations

import numpy as np


def determine_pause(
    audio_stream: np.ndarray,
    sampling_rate: int,
    state,
    silence_threshold_db: float = -35.0,
    min_silence_duration_s: float = 0.6,
):
    """Heuristic pause detector.

    Returns a tuple (pause_detected, started_talking).

    - Uses a short-term energy estimate converted to dBFS relative to 16-bit range.
    - Considers the last min_silence_duration_s segment; if it stays under threshold,
      we consider it a pause.
    - Sets started_talking True once we have energy above threshold.

    This is a lightweight stand-in for the omni-mini project's pause logic.
    """
    if audio_stream is None or sampling_rate <= 0 or audio_stream.size == 0:
        return False, False

    # Ensure mono for analysis
    if audio_stream.ndim > 1:
        mono = np.mean(audio_stream, axis=1)
    else:
        mono = audio_stream

    # Normalize to int16-like range if float input
    if mono.dtype.kind == "f":
        # Assume float32/64 in [-1, 1]
        scaled = np.clip(mono, -1.0, 1.0) * 32767.0
    else:
        scaled = mono.astype(np.float32)

    # Determine the window for silence check
    window_samples = int(min_silence_duration_s * sampling_rate)
    if window_samples <= 0 or window_samples > scaled.shape[0]:
        window_samples = scaled.shape[0]

    recent = scaled[-window_samples:]

    # Root-mean-square to dBFS
    rms_recent = np.sqrt(np.mean(recent ** 2) + 1e-12)
    dbfs_recent = 20.0 * np.log10(rms_recent / 32767.0 + 1e-12)

    # Determine whether we've started talking at any point
    rms_full = np.sqrt(np.mean(scaled ** 2) + 1e-12)
    dbfs_full = 20.0 * np.log10(rms_full / 32767.0 + 1e-12)
    started_talking = dbfs_full > silence_threshold_db

    pause_detected = dbfs_recent < silence_threshold_db and started_talking
    return pause_detected, started_talking


