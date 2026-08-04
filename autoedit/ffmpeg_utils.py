"""Locating ffmpeg/ffprobe and small helpers for probing and running them.

We prefer a system ``ffmpeg``/``ffprobe`` on PATH (full builds, best codec
support). If none is found we fall back to the ffmpeg binary bundled with the
``imageio-ffmpeg`` wheel so the tool still works out of the box.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional


class FFmpegError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def ffmpeg_path() -> str:
    """Return a usable ffmpeg executable path."""
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - only when nothing is available
        raise FFmpegError(
            "ffmpeg not found. Install ffmpeg (recommended) or "
            "`pip install imageio-ffmpeg`."
        ) from exc


@lru_cache(maxsize=1)
def ffprobe_path() -> Optional[str]:
    """Return ffprobe path if available, else ``None`` (we parse ffmpeg output)."""
    return shutil.which("ffprobe")


def run(cmd: List[str], *, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a command, raising :class:`FFmpegError` on failure."""
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-2000:]
        raise FFmpegError(f"Command failed ({proc.returncode}): {' '.join(cmd[:3])}\n{tail}")
    return proc


@dataclass
class MediaInfo:
    duration: float          # seconds
    width: int
    height: int
    fps: float
    has_audio: bool
    sample_rate: int

    @property
    def is_vertical(self) -> bool:
        return self.height >= self.width


def probe(path: str) -> MediaInfo:
    """Probe a media file for duration, resolution, fps and audio info."""
    probe_bin = ffprobe_path()
    if probe_bin:
        return _probe_with_ffprobe(probe_bin, path)
    return _probe_with_ffmpeg(path)


def _probe_with_ffprobe(probe_bin: str, path: str) -> MediaInfo:
    proc = run([
        probe_bin, "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ])
    data = json.loads(proc.stdout)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    a = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    if v is None:
        raise FFmpegError("No video stream found in input.")
    duration = float(data.get("format", {}).get("duration") or v.get("duration") or 0.0)
    return MediaInfo(
        duration=duration,
        width=int(v["width"]),
        height=int(v["height"]),
        fps=_parse_fraction(v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1"),
        has_audio=a is not None,
        sample_rate=int(a["sample_rate"]) if a and a.get("sample_rate") else 44100,
    )


def _probe_with_ffmpeg(path: str) -> MediaInfo:
    # ffmpeg prints stream info to stderr and exits non-zero (no output file),
    # so we don't use run() here.
    proc = subprocess.run(
        [ffmpeg_path(), "-i", path], stderr=subprocess.PIPE, text=True
    )
    text = proc.stderr

    dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", text)
    duration = 0.0
    if dur:
        h, m, s = dur.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s)

    vid = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    if not vid:
        raise FFmpegError("Could not parse video resolution from ffmpeg output.")
    width, height = int(vid.group(1)), int(vid.group(2))

    fps_m = re.search(r"(\d+\.?\d*)\s*fps", text)
    fps = float(fps_m.group(1)) if fps_m else 30.0

    aud = re.search(r"Audio:.*?(\d+)\s*Hz", text)
    return MediaInfo(
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        has_audio=aud is not None,
        sample_rate=int(aud.group(1)) if aud else 44100,
    )


def _parse_fraction(value: str) -> float:
    try:
        if "/" in value:
            num, den = value.split("/")
            den_f = float(den)
            return float(num) / den_f if den_f else 30.0
        return float(value)
    except (ValueError, ZeroDivisionError):
        return 30.0


def extract_audio(video_path: str, out_wav: str, sample_rate: int = 16000) -> str:
    """Extract mono PCM audio suitable for speech-to-text."""
    run([
        ffmpeg_path(), "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le",
        out_wav,
    ])
    return out_wav
