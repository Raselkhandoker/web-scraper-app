"""Choosing highlight moments to cut into short clips.

Preferred path: Claude reads the timestamped transcript and returns the most
engaging moments as JSON. If no ``ANTHROPIC_API_KEY`` is set (or the SDK is
missing), we fall back to a simple heuristic so the feature still produces clips.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional

from .transcribe import Transcript

log = logging.getLogger("autoedit.highlights")

DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class Highlight:
    start: float
    end: float
    title: str
    reason: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def select_highlights(
    transcript: Transcript,
    duration: float,
    count: int = 3,
    min_len: float = 12.0,
    max_len: float = 60.0,
    model: str = DEFAULT_MODEL,
) -> List[Highlight]:
    """Return up to ``count`` highlight windows, via Claude or a heuristic."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key and transcript.segments:
        try:
            return _select_with_claude(transcript, count, min_len, max_len, model, api_key)
        except Exception as exc:  # noqa: BLE001 - fall back rather than fail the run
            log.warning("Claude highlight selection failed (%s); using heuristic.", exc)
    else:
        log.info("No ANTHROPIC_API_KEY / transcript; using heuristic highlights.")
    return _select_heuristic(transcript, duration, count, min_len, max_len)


def _select_with_claude(
    transcript: Transcript,
    count: int,
    min_len: float,
    max_len: float,
    model: str,
    api_key: str,
) -> List[Highlight]:
    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=api_key)
    lines = [
        f"[{seg.start:.1f}-{seg.end:.1f}] {seg.text}"
        for seg in transcript.segments
        if seg.text.strip()
    ]
    transcript_block = "\n".join(lines)

    prompt = (
        f"You are a short-form video editor. Below is a timestamped transcript "
        f"(seconds). Pick the {count} most engaging, self-contained moments to cut "
        f"into vertical short clips. Each clip must be between {min_len:.0f} and "
        f"{max_len:.0f} seconds and start/end on a natural sentence boundary.\n\n"
        f"Return ONLY a JSON array, no prose, like:\n"
        f'[{{"start": 12.3, "end": 41.0, "title": "short punchy title", '
        f'"reason": "why it hooks"}}]\n\nTranscript:\n{transcript_block}'
    )

    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in msg.content if block.type == "text")
    data = _extract_json_array(text)

    highlights: List[Highlight] = []
    for item in data[:count]:
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        end = min(end, start + max_len)
        if end - start >= min_len:
            highlights.append(
                Highlight(
                    start=start,
                    end=end,
                    title=str(item.get("title", "Highlight")).strip(),
                    reason=str(item.get("reason", "")).strip(),
                )
            )
    return highlights or _select_heuristic(transcript, transcript.segments[-1].end, count, min_len, max_len)


def _select_heuristic(
    transcript: Transcript,
    duration: float,
    count: int,
    min_len: float,
    max_len: float,
) -> List[Highlight]:
    """Evenly spaced windows across the video, snapped to segment boundaries.

    Not smart, but deterministic and dependency-free - a reasonable default when
    Claude isn't available.
    """
    if duration <= 0:
        return []
    window = min(max_len, max(min_len, duration / max(count, 1)))
    highlights: List[Highlight] = []
    step = duration / max(count, 1)
    for i in range(count):
        center = step * (i + 0.5)
        start = max(0.0, center - window / 2)
        end = min(duration, start + window)
        start = max(0.0, end - window)
        if end - start >= min_len - 1e-3:
            highlights.append(
                Highlight(start=round(start, 2), end=round(end, 2), title=f"Highlight {i + 1}")
            )
    return highlights


def _extract_json_array(text: str) -> List[dict]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []
