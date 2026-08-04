"""Mapping times from the original video onto the edited (silence-cut) timeline.

After we drop the silent gaps, every kept moment shifts earlier. Captions are
timed against the original transcript, so we remap each word onto its new
position using the keep-segments.
"""
from __future__ import annotations

from bisect import bisect_right
from typing import List, Optional, Sequence, Tuple

Segment = Tuple[float, float]


class TimelineMap:
    """Maps an original timestamp to its position in the edited output."""

    def __init__(self, keep_segments: Sequence[Segment]):
        self.segments: List[Segment] = list(keep_segments)
        # Cumulative edited-time offset at the start of each keep-segment.
        self._offsets: List[float] = []
        self._starts: List[float] = []
        acc = 0.0
        for start, end in self.segments:
            self._starts.append(start)
            self._offsets.append(acc)
            acc += end - start
        self.output_duration = acc

    def map(self, t: float) -> Optional[float]:
        """Return the edited-timeline time for original time ``t``.

        Returns ``None`` if ``t`` falls in a region that was cut out.
        """
        if not self.segments:
            return None
        idx = bisect_right(self._starts, t) - 1
        if idx < 0:
            return None
        start, end = self.segments[idx]
        if t > end:
            return None
        return self._offsets[idx] + (t - start)

    def map_clamped(self, t: float) -> float:
        """Like :meth:`map` but snaps cut-out times to the nearest kept edge."""
        if not self.segments:
            return 0.0
        idx = bisect_right(self._starts, t) - 1
        if idx < 0:
            return 0.0
        start, end = self.segments[idx]
        clamped = min(max(t, start), end)
        return self._offsets[idx] + (clamped - start)
