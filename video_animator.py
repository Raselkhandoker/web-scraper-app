"""
video_animator.py
-----------------
Core engine that turns a normal video into an "animated" / cartoon-styled
video.

It supports two things the user asked for:

1. Trimming  -- remove unwanted segments (seconds) from the video.
2. Animating -- apply a cartoon / sketch / anime style to every kept frame.

Two engines are available:

* ``local`` -- pure OpenCV. Free, offline, no API key. This is the default
  and is fully self contained.
* ``ai``    -- delegates the whole video to an external AI service
  (Replicate). Higher quality, but needs an API token and costs money.
  See ``ai_backends.py``.

Audio from the original video is preserved and trimmed to match the kept
segments, then muxed back onto the stylized video with ffmpeg (the ffmpeg
binary bundled with ``imageio-ffmpeg`` is used, so no system install is
required).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import logging
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np
import imageio.v2 as imageio
import imageio_ffmpeg

logger = logging.getLogger(__name__)

# Type alias: a progress callback receives an int percentage 0..100.
ProgressCB = Optional[Callable[[int], None]]


# --------------------------------------------------------------------------- #
#  Styles
# --------------------------------------------------------------------------- #

# Human readable list used by the API / UI.
STYLES = {
    "cartoon": "Smooth colours with bold outlines (classic cartoon look)",
    "anime": "Fewer, flatter colours - anime / cel-shaded feel",
    "sketch": "Black & white pencil sketch",
    "paint": "Soft oil-painting / watercolour look",
}


def _clamp(img: np.ndarray) -> np.ndarray:
    return np.clip(img, 0, 255).astype(np.uint8)


def cartoonize(frame: np.ndarray, style: str = "cartoon") -> np.ndarray:
    """Apply a stylisation to a single BGR frame and return a BGR frame."""

    if style == "sketch":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        inv = 255 - gray
        blur = cv2.GaussianBlur(inv, (21, 21), 0)
        # Colour dodge blend -> pencil sketch.
        sketch = cv2.divide(gray, 255 - blur, scale=256)
        return cv2.cvtColor(_clamp(sketch), cv2.COLOR_GRAY2BGR)

    if style == "paint":
        # stylization gives a smooth, painterly result.
        return cv2.stylization(frame, sigma_s=60, sigma_r=0.45)

    # ---- cartoon / anime share the edge + colour-quantise pipeline ---------
    # 1. Smooth colours while keeping edges sharp.
    color = frame
    for _ in range(2):
        color = cv2.bilateralFilter(color, d=9, sigmaColor=75, sigmaSpace=75)

    # 2. Colour quantisation -> flat regions of colour.
    n_levels = 6 if style == "anime" else 9
    div = 256 // n_levels
    color = (color // div) * div + div // 2
    color = _clamp(color)

    # 3. Edge mask (bold black outlines).
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    edges = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        blockSize=9,
        C=(3 if style == "anime" else 2),
    )
    edges = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

    # 4. Combine colour with outlines.
    return cv2.bitwise_and(color, edges)


# --------------------------------------------------------------------------- #
#  Trim helpers
# --------------------------------------------------------------------------- #

def parse_cut_segments(raw: str) -> List[Tuple[float, float]]:
    """Parse a string like ``"0-3, 10-12.5"`` into ``[(0,3),(10,12.5)]``.

    Each pair is a span **to remove** (in seconds). Invalid pieces are
    skipped rather than raising, so a messy UI value never crashes a job.
    """
    segments: List[Tuple[float, float]] = []
    if not raw:
        return segments
    for piece in raw.replace(";", ",").split(","):
        piece = piece.strip()
        if not piece:
            continue
        for sep in ("-", ":", "to"):
            if sep in piece:
                a, _, b = piece.partition(sep)
                try:
                    start, end = float(a.strip()), float(b.strip())
                except ValueError:
                    break
                if end > start >= 0:
                    segments.append((start, end))
                break
    return sorted(segments)


def keep_ranges_from_cuts(
    cuts: List[Tuple[float, float]], duration: float
) -> List[Tuple[float, float]]:
    """Invert a list of cut spans into the spans that should be *kept*."""
    if not cuts:
        return [(0.0, duration)]
    keep: List[Tuple[float, float]] = []
    cursor = 0.0
    for start, end in sorted(cuts):
        start = max(0.0, min(start, duration))
        end = max(0.0, min(end, duration))
        if start > cursor:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        keep.append((cursor, duration))
    return keep


def _frame_is_kept(time_s: float, cuts: List[Tuple[float, float]]) -> bool:
    for start, end in cuts:
        if start <= time_s < end:
            return False
    return True


# --------------------------------------------------------------------------- #
#  Main engine
# --------------------------------------------------------------------------- #

class VideoAnimator:
    """Turns an input video file into a stylised output video file."""

    def __init__(self, ffmpeg_exe: Optional[str] = None):
        self.ffmpeg = ffmpeg_exe or imageio_ffmpeg.get_ffmpeg_exe()

    # -- public ------------------------------------------------------------- #

    def process(
        self,
        input_path: str,
        output_path: str,
        style: str = "cartoon",
        cut_segments: Optional[List[Tuple[float, float]]] = None,
        keep_audio: bool = True,
        max_width: int = 960,
        progress_cb: ProgressCB = None,
    ) -> dict:
        """Run the local (OpenCV) pipeline.

        Returns a small dict of stats about the produced file.
        """
        cut_segments = cut_segments or []

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise ValueError("Could not open the video file. Is it a valid video?")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if fps <= 0 or fps > 120:
            fps = 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = total_frames / fps if total_frames else 0.0

        # Optional downscale for speed; keep aspect ratio, even dimensions.
        scale = 1.0
        if max_width and src_w > max_width:
            scale = max_width / float(src_w)
        out_w = int(round(src_w * scale)) // 2 * 2 or src_w
        out_h = int(round(src_h * scale)) // 2 * 2 or src_h

        # Write stylised frames to a temporary *silent* mp4 first.
        tmp_silent = tempfile.mktemp(suffix=".mp4")
        writer = imageio.get_writer(
            tmp_silent,
            fps=fps,
            codec="libx264",
            quality=8,
            macro_block_size=None,
            ffmpeg_log_level="error",
        )

        kept = 0
        processed = 0
        try:
            idx = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                time_s = idx / fps
                idx += 1

                if not _frame_is_kept(time_s, cut_segments):
                    processed += 1
                    self._maybe_progress(progress_cb, processed, total_frames)
                    continue

                if scale != 1.0:
                    frame = cv2.resize(frame, (out_w, out_h),
                                       interpolation=cv2.INTER_AREA)

                styled = cartoonize(frame, style)
                writer.append_data(cv2.cvtColor(styled, cv2.COLOR_BGR2RGB))
                kept += 1
                processed += 1
                self._maybe_progress(progress_cb, processed, total_frames)
        finally:
            writer.close()
            cap.release()

        if kept == 0:
            raise ValueError(
                "No frames left after trimming - the cut segments removed "
                "the whole video."
            )

        # Mux audio (trimmed to the kept ranges) back on, if requested.
        muxed = False
        if keep_audio:
            try:
                self._mux_trimmed_audio(
                    stylised_silent=tmp_silent,
                    original=input_path,
                    output=output_path,
                    cuts=cut_segments,
                    duration=duration,
                )
                muxed = True
            except Exception as e:  # noqa: BLE001 - audio is best-effort
                logger.warning("Audio mux failed, writing silent video: %s", e)

        if not muxed:
            # Just move/transcode the silent file to the final path.
            self._copy_video(tmp_silent, output_path)

        try:
            os.remove(tmp_silent)
        except OSError:
            pass

        if progress_cb:
            progress_cb(100)

        return {
            "fps": round(fps, 2),
            "frames_written": kept,
            "frames_total": total_frames,
            "width": out_w,
            "height": out_h,
            "has_audio": muxed,
            "style": style,
        }

    # -- internals ---------------------------------------------------------- #

    @staticmethod
    def _maybe_progress(cb: ProgressCB, done: int, total: int) -> None:
        if cb and total:
            pct = int(done * 95 / total)  # reserve last 5% for muxing
            cb(min(95, pct))

    def _copy_video(self, src: str, dst: str) -> None:
        cmd = [self.ffmpeg, "-y", "-i", src, "-c", "copy", dst]
        subprocess.run(cmd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def _mux_trimmed_audio(
        self,
        stylised_silent: str,
        original: str,
        output: str,
        cuts: List[Tuple[float, float]],
        duration: float,
    ) -> None:
        """Trim the original audio to the kept ranges and mux it on."""
        keep = keep_ranges_from_cuts(cuts, duration) if duration else [(0.0, 0.0)]

        if not cuts or not duration:
            # Simple case: just copy audio straight across.
            cmd = [
                self.ffmpeg, "-y",
                "-i", stylised_silent,
                "-i", original,
                "-map", "0:v:0", "-map", "1:a:0?",
                "-c:v", "copy", "-c:a", "aac", "-shortest",
                output,
            ]
            subprocess.run(cmd, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            return

        # Build an atrim+concat filter over the kept ranges.
        parts = []
        for i, (start, end) in enumerate(keep):
            parts.append(
                f"[1:a]atrim=start={start:.3f}:end={end:.3f},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )
        concat_inputs = "".join(f"[a{i}]" for i in range(len(keep)))
        filter_complex = (
            ";".join(parts)
            + f";{concat_inputs}concat=n={len(keep)}:v=0:a=1[aout]"
        )
        cmd = [
            self.ffmpeg, "-y",
            "-i", stylised_silent,
            "-i", original,
            "-filter_complex", filter_complex,
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            output,
        ]
        subprocess.run(cmd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
