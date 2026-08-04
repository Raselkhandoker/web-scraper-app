"""Rendering with ffmpeg: apply silence cuts + burn captions, and export clips.

The main edit removes silent gaps in a single ffmpeg pass using the ``select`` /
``aselect`` filters (the "jumpcutter" technique) and burns the caption ASS on
top. Highlight clips are trimmed with ``trim`` / ``atrim``, reframed to vertical
and captioned independently.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Sequence, Tuple

from .ffmpeg_utils import MediaInfo, ffmpeg_path, run

log = logging.getLogger("autoedit.render")

Segment = Tuple[float, float]

# Above this many keep-segments the select expression gets unwieldy; callers can
# check and warn. Kept generous - ffmpeg handles large expressions fine in tests.
MAX_INLINE_SEGMENTS = 800

_VCODEC = ["-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p"]
_ACODEC = ["-c:a", "aac", "-b:a", "192k"]


def render_cut(
    input_path: str,
    keep_segments: Sequence[Segment],
    out_path: str,
    info: MediaInfo,
    ass_path: Optional[str] = None,
) -> str:
    """Render the main edit: drop silent gaps, optionally burn captions."""
    if not keep_segments:
        raise ValueError("No segments to keep - nothing to render.")

    select_expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in keep_segments)

    vchain = [f"select='{select_expr}'", "setpts=N/FRAME_RATE/TB"]
    if ass_path:
        vchain.append(f"subtitles={_escape_path(ass_path)}")
    filter_parts = [f"[0:v]{','.join(vchain)}[v]"]

    maps = ["-map", "[v]"]
    if info.has_audio:
        filter_parts.append(f"[0:a]aselect='{select_expr}',asetpts=N/SR/TB[a]")
        maps += ["-map", "[a]"]

    cmd = [
        ffmpeg_path(), "-y", "-i", input_path,
        "-filter_complex", ";".join(filter_parts),
        *maps, *_VCODEC, *(_ACODEC if info.has_audio else []),
        "-movflags", "+faststart", out_path,
    ]
    log.info("Rendering main edit -> %s", out_path)
    run(cmd, capture=True)
    return out_path


def render_clip(
    input_path: str,
    start: float,
    end: float,
    out_path: str,
    info: MediaInfo,
    ass_path: Optional[str] = None,
    vertical: bool = True,
    target: Tuple[int, int] = (1080, 1920),
) -> str:
    """Trim [start, end], reframe to vertical, and optionally burn captions."""
    vchain = [f"trim=start={start:.3f}:end={end:.3f}", "setpts=PTS-STARTPTS"]
    if vertical:
        w, h = target
        vchain.append(
            f"scale={w}:{h}:force_original_aspect_ratio=increase"
        )
        vchain.append(f"crop={w}:{h}")
    if ass_path:
        vchain.append(f"subtitles={_escape_path(ass_path)}")
    filter_parts = [f"[0:v]{','.join(vchain)}[v]"]

    maps = ["-map", "[v]"]
    if info.has_audio:
        filter_parts.append(
            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a]"
        )
        maps += ["-map", "[a]"]

    cmd = [
        ffmpeg_path(), "-y", "-i", input_path,
        "-filter_complex", ";".join(filter_parts),
        *maps, *_VCODEC, *(_ACODEC if info.has_audio else []),
        "-movflags", "+faststart", out_path,
    ]
    log.info("Rendering clip [%.1f-%.1f] -> %s", start, end, out_path)
    run(cmd, capture=True)
    return out_path


def _escape_path(path: str) -> str:
    """Escape a path for use as a value inside an ffmpeg filtergraph."""
    escaped = path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return f"'{escaped}'"
