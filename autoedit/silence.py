"""Deciding which parts of the video to keep (dead-air / silence removal).

Two strategies:

* :func:`keep_segments_from_words` - preferred, uses word timestamps from the
  transcript. Cuts any gap between words longer than ``max_gap``.
* :func:`keep_segments_from_audio` - fallback, uses ffmpeg ``silencedetect`` on
  the audio energy. Works without a transcript.

Both return a list of ``(start, end)`` keep-segments in the *original* timeline,
merged and padded, ready to feed the renderer.
"""
from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from .ffmpeg_utils import ffmpeg_path, run
from .transcribe import Word

Segment = Tuple[float, float]


def keep_segments_from_words(
    words: Sequence[Word],
    duration: float,
    max_gap: float = 0.4,
    padding: float = 0.08,
) -> List[Segment]:
    """Keep spoken words, cutting silent gaps longer than ``max_gap`` seconds."""
    if not words:
        return [(0.0, duration)]

    raw: List[Segment] = []
    for w in words:
        start = max(0.0, w.start - padding)
        end = min(duration, w.end + padding)
        if end > start:
            raw.append((start, end))

    merged = _merge(raw, join_gap=max_gap)
    return _clamp(merged, duration)


def keep_segments_from_audio(
    video_path: str,
    duration: float,
    noise_db: float = -30.0,
    min_silence: float = 0.4,
    padding: float = 0.08,
    min_keep: float = 0.15,
) -> List[Segment]:
    """Keep non-silent regions detected by ffmpeg ``silencedetect``."""
    proc = subprocess_run_silencedetect(video_path, noise_db, min_silence)
    silences = _parse_silencedetect(proc, duration)

    # Invert silence intervals to get the segments we keep.
    keep: List[Segment] = []
    cursor = 0.0
    for s_start, s_end in silences:
        if s_start - cursor > min_keep:
            keep.append((cursor, s_start))
        cursor = s_end
    if duration - cursor > min_keep:
        keep.append((cursor, duration))

    if not keep:
        return [(0.0, duration)]

    padded = [
        (max(0.0, s - padding), min(duration, e + padding)) for s, e in keep
    ]
    return _clamp(_merge(padded, join_gap=0.0), duration)


def subprocess_run_silencedetect(video_path: str, noise_db: float, min_silence: float):
    return run([
        ffmpeg_path(), "-i", video_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f", "null", "-",
    ])


def _parse_silencedetect(proc, duration: float) -> List[Segment]:
    text = proc.stderr or ""
    starts = [float(m) for m in re.findall(r"silence_start:\s*(-?\d+\.?\d*)", text)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*(-?\d+\.?\d*)", text)]
    silences: List[Segment] = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else duration
        silences.append((max(0.0, s), min(duration, e)))
    return silences


def total_kept(segments: Sequence[Segment]) -> float:
    return sum(e - s for s, e in segments)


def _merge(segments: List[Segment], join_gap: float) -> List[Segment]:
    """Merge overlapping segments and those separated by <= ``join_gap``."""
    if not segments:
        return []
    ordered = sorted(segments)
    out = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = out[-1]
        if start - last_end <= join_gap:
            out[-1] = (last_start, max(last_end, end))
        else:
            out.append((start, end))
    return out


def _clamp(segments: List[Segment], duration: float) -> List[Segment]:
    out: List[Segment] = []
    for s, e in segments:
        s = max(0.0, min(s, duration))
        e = max(0.0, min(e, duration))
        if e - s > 1e-3:
            out.append((round(s, 3), round(e, 3)))
    return out
