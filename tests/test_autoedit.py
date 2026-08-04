"""Unit tests for the offline logic (no ffmpeg / model downloads needed)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoedit import captions, highlights, silence  # noqa: E402
from autoedit.timeline import TimelineMap  # noqa: E402
from autoedit.transcribe import Segment, Transcript, Word  # noqa: E402


def _words(*spans):
    return [Word(start=s, end=e, text=t) for s, e, t in spans]


def test_keep_segments_from_words_cuts_long_gaps():
    words = _words((0.0, 1.0, "hello"), (1.2, 2.0, "there"), (5.0, 6.0, "again"))
    keep = silence.keep_segments_from_words(words, duration=6.0, max_gap=0.4, padding=0.0)
    # The 3s gap (2.0 -> 5.0) is cut; the 0.2s gap is kept (merged).
    assert keep == [(0.0, 2.0), (5.0, 6.0)]


def test_keep_segments_empty_returns_full():
    assert silence.keep_segments_from_words([], duration=10.0) == [(0.0, 10.0)]


def test_timeline_map_shifts_after_cuts():
    tmap = TimelineMap([(0.0, 2.0), (5.0, 6.0)])
    assert tmap.output_duration == 3.0
    assert tmap.map(0.0) == 0.0
    assert tmap.map(1.5) == 1.5
    assert tmap.map(3.0) is None          # inside a cut region
    assert tmap.map(5.5) == 2.5           # shifted earlier by the removed 3s


def test_timeline_map_clamped_snaps_cut_times():
    tmap = TimelineMap([(0.0, 2.0), (5.0, 6.0)])
    assert tmap.map_clamped(3.0) == 2.0   # snapped to end of first kept segment


def test_build_ass_has_styles_and_events():
    words = _words((0.0, 0.4, "hey"), (0.4, 0.9, "there"), (0.9, 1.5, "friends"))
    ass = captions.build_ass(words, width=1080, height=1920)
    assert "[V4+ Styles]" in ass
    assert "Dialogue:" in ass
    assert "HEY" in ass  # uppercased by default
    # active-word highlight uses the accent colour tag
    assert "\\c&H0000F7FF" in ass


def test_heuristic_highlights_within_bounds():
    transcript = Transcript(segments=[Segment(0.0, 90.0, "a", [])])
    hl = highlights._select_heuristic(transcript, duration=90.0, count=3, min_len=12.0, max_len=60.0)
    assert len(hl) == 3
    for h in hl:
        assert 12.0 - 1e-3 <= h.duration <= 60.0 + 1e-3
        assert 0.0 <= h.start < h.end <= 90.0


def test_extract_json_array_parses_claude_output():
    text = 'Sure! Here you go:\n[{"start": 1.0, "end": 20.0, "title": "hook"}] done'
    data = highlights._extract_json_array(text)
    assert data and data[0]["title"] == "hook"
