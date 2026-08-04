"""Generating burned-in, word-by-word captions as an ASS subtitle file.

We group words into short phrases and, for each phrase, emit one event per word
so the currently-spoken word is highlighted in an accent colour - the animated
"TikTok / Reels" caption look. The renderer burns the ASS onto the video with
ffmpeg's ``subtitles`` filter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from .transcribe import Word


@dataclass
class CaptionStyle:
    font: str = "Arial"
    # Sizes/margins are fractions of the output height (resolution-independent).
    font_frac: float = 0.050
    bottom_frac: float = 0.20
    outline: int = 4
    shadow: int = 2
    primary: str = "&H00FFFFFF"     # white  (AABBGGRR, AA=00 opaque)
    accent: str = "&H0000F7FF"      # yellow highlight for the active word
    max_words_per_line: int = 3
    line_break_gap: float = 0.7     # start a new phrase after a pause this long
    uppercase: bool = True


def build_ass(
    words: Sequence[Word],
    width: int,
    height: int,
    style: CaptionStyle | None = None,
) -> str:
    """Return the full text of an ASS subtitle file for ``words`` (edited times)."""
    style = style or CaptionStyle()
    font_size = max(12, int(height * style.font_frac))
    margin_v = int(height * style.bottom_frac)

    header = _header(width, height, font_size, margin_v, style)
    lines = _group(words, style)
    events = "\n".join(_events_for_line(line, style) for line in lines if line)
    return header + events + "\n"


def _group(words: Sequence[Word], style: CaptionStyle) -> List[List[Word]]:
    lines: List[List[Word]] = []
    current: List[Word] = []
    for w in words:
        if current:
            gap = w.start - current[-1].end
            if len(current) >= style.max_words_per_line or gap > style.line_break_gap:
                lines.append(current)
                current = []
        current.append(w)
    if current:
        lines.append(current)
    return lines


def _events_for_line(line: List[Word], style: CaptionStyle) -> str:
    """Emit one Dialogue per word; the active word is coloured with the accent."""
    out: List[str] = []
    for i, active in enumerate(line):
        start = active.start
        # Show until the next word begins so the phrase stays on screen.
        end = line[i + 1].start if i + 1 < len(line) else active.end + 0.35
        text = _render_line(line, i, style)
        out.append(
            f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,0,0,0,,{text}"
        )
    return "\n".join(out)


def _render_line(line: List[Word], active_idx: int, style: CaptionStyle) -> str:
    parts: List[str] = []
    for i, w in enumerate(line):
        token = _escape(w.text)
        if style.uppercase:
            token = token.upper()
        if i == active_idx:
            token = f"{{\\c{style.accent}\\b1}}{token}{{\\c{style.primary}\\b0}}"
        parts.append(token)
    return " ".join(parts)


def _header(width: int, height: int, font_size: int, margin_v: int, style: CaptionStyle) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{style.font},{font_size},{style.primary},{style.primary},&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,{style.outline},{style.shadow},2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:  # rounding spill
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "(")
        .replace("}", ")")
        .strip()
    )
