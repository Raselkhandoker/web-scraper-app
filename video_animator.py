"""
video_animator.py
-----------------
Core engine that turns a normal video into an "animated" / stylised video.

It supports:

1. Trimming  -- remove unwanted segments (seconds) from the video.
2. Animating -- apply one of many animation-inspired styles to every frame.
3. Audio     -- keep, mute, replace with an uploaded track, or (via the
                worker) swap in AI-generated music that matches the style.

Two engines are available:

* ``local`` -- pure OpenCV. Free, offline, no API key. This is the default.
  The styles here are *stylised approximations* of real animation
  techniques (a cartoon filter, a claymation-ish look, stop-motion frame
  holding, etc.) -- not a literal reproduction of hand-made animation.
* ``ai``    -- delegates the whole video to a hosted model (Replicate),
  passing the chosen style name as a prompt. See ``ai_backends.py``.

Audio is trimmed to match the kept segments and muxed back with the ffmpeg
binary bundled with ``imageio-ffmpeg`` (no system ffmpeg required).
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

ProgressCB = Optional[Callable[[int], None]]


# --------------------------------------------------------------------------- #
#  Styles
# --------------------------------------------------------------------------- #
#
# Each style maps to: (human description, frame_hold).
#   frame_hold = N means a new stylised frame is only computed every N source
#   frames and repeated in between -> the choppy "on twos/threes" look of
#   stop-motion / flipbook animation.
#
# NOTE: "Audio-Animatronics / Autonomatronics" is a physical robotics
# technique (animated puppets), not a video look, so it is intentionally not
# offered as a filter.

STYLE_CONFIG = {
    # id            (description,                                               hold)
    "cartoon":      ("Smooth colours with bold outlines (classic cartoon)",     1),
    "anime":        ("Flat, cel-shaded anime feel",                             1),
    "2d":           ("Clean flat 2D cartoon - bold outlines, vivid flat colour", 1),
    "traditional":  ("Traditional hand-drawn cel look (soft, warm)",            1),
    "flipbook":     ("Pencil flipbook - sketchy lines, hand-flipped timing",    3),
    "stop_motion":  ("Stop-motion - real texture with choppy 'on threes' timing", 3),
    "cutout":       ("Paper cut-out / puppet - big flat shapes, thin cut lines", 1),
    "sand":         ("Sand-on-glass - grainy warm monochrome",                  2),
    "paint_glass":  ("Paint-on-glass - soft smeared oil painting",              1),
    "clay":         ("Claymation-ish - smooth, glossy, saturated",              2),
    "rotoscope":    ("Rotoscope - traced live footage, banded colour + edges",  1),
    "whiteboard":   ("Whiteboard - black marker lines on white",                1),
    "experimental": ("Experimental - abstract painterly colour-map",           1),
    "sketch":       ("Black & white pencil sketch",                             1),
}

# Simple id -> description map used by the API / UI.
STYLES = {k: v[0] for k, v in STYLE_CONFIG.items()}


def _clamp(img: np.ndarray) -> np.ndarray:
    return np.clip(img, 0, 255).astype(np.uint8)


def _quantize(img: np.ndarray, n_levels: int) -> np.ndarray:
    div = max(1, 256 // n_levels)
    return _clamp((img.astype(np.int16) // div) * div + div // 2)


def _edge_mask(frame: np.ndarray, block: int = 9, c: int = 2) -> np.ndarray:
    """Return a 1-channel mask: 0 on edges, 255 elsewhere."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, block, c
    )


def _pencil_sketch(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    inv = 255 - gray
    blur = cv2.GaussianBlur(inv, (21, 21), 0)
    sketch = cv2.divide(gray, 255 - blur, scale=256)
    return _clamp(sketch)


def _cel(frame: np.ndarray, n_levels: int, smooth_passes: int = 2,
         canny: Tuple[int, int] = (60, 150), min_frac: float = 0.00015,
         thicken: int = 1) -> np.ndarray:
    """Shared cel-shading pipeline: smooth + quantise colour + clean dark
    outlines. Uses the speckle-removing _clean_line_mask (Canny + connected
    component filter) instead of adaptiveThreshold, so textured areas like
    grass and crowds stay flat rather than filling with grain/scribble."""
    color = frame
    for _ in range(smooth_passes):
        color = cv2.bilateralFilter(color, d=9, sigmaColor=75, sigmaSpace=75)
    quant = _quantize(color, n_levels)
    line_mask = _clean_line_mask(color, lo=canny[0], hi=canny[1],
                                 min_frac=min_frac, thicken=thicken)
    return cv2.bitwise_and(quant, line_mask)


def _clean_line_mask(smooth: np.ndarray, lo: int, hi: int,
                     min_frac: float = 0.0006, thicken: int = 1) -> np.ndarray:
    """Return a BGR mask (black lines on white) that keeps only the *big*
    outlines and drops small speckle -- so textured areas like grass and
    crowds stay flat instead of filling with noisy lines."""
    gray = cv2.cvtColor(smooth, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 7)
    edges = cv2.Canny(gray, lo, hi)

    # Remove small connected components (speckle).
    n, labels, stats, _ = cv2.connectedComponentsWithStats(edges, 8)
    if n > 1:
        h, w = edges.shape
        min_area = max(12, int(min_frac * h * w))
        big = [i for i in range(1, n)
               if stats[i, cv2.CC_STAT_AREA] >= min_area]
        edges = np.isin(labels, big).astype(np.uint8) * 255

    if thicken > 0:
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=thicken)
    return cv2.cvtColor(255 - edges, cv2.COLOR_GRAY2BGR)


def _clean_2d(frame: np.ndarray) -> np.ndarray:
    """A clean, flat 2D-cartoon look: smooth flat colour fields, punchy
    saturation, and bold clean black outlines (less speckle than the
    adaptive-threshold styles)."""
    # 1. Edge-preserving smoothing that flattens colour but KEEPS detail
    #    (bilateral, not the smeary edgePreservingFilter) so players stay sharp.
    smooth = cv2.bilateralFilter(frame, 9, 70, 70)
    smooth = cv2.bilateralFilter(smooth, 9, 70, 70)

    # 2. Quantise to a palette (kept fairly large so faces/kit stay readable).
    quant = _quantize(smooth, 10)
    hsv = cv2.cvtColor(quant, cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.25, 0, 255)   # saturation
    hsv[..., 2] = np.clip(hsv[..., 2] * 1.05, 0, 255)   # brightness
    quant = cv2.cvtColor(_clamp(hsv).astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 3. Bold outlines; drop only tiny grass speckle, keep small player edges.
    line_mask = _clean_line_mask(smooth, lo=70, hi=160,
                                 min_frac=0.00015, thicken=1)
    return cv2.bitwise_and(quant, line_mask)


def _paper_cutout(frame: np.ndarray) -> np.ndarray:
    """Paper cut-out / puppet look: big flat colour regions like pieces of
    coloured paper, with thin clean cut lines. Flatter and softer-edged than
    the 2d style."""
    # 1. Flatten into paper-flat regions but keep detail (bilateral, not the
    #    smeary edgePreservingFilter) so players don't melt into blobs.
    smooth = cv2.bilateralFilter(frame, 7, 60, 60)
    smooth = cv2.bilateralFilter(smooth, 7, 60, 60)

    # 2. Reduce to a small palette (flat coloured-paper feel).
    quant = _quantize(smooth, 8)
    hsv = cv2.cvtColor(quant, cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.20, 0, 255)   # gentle saturation
    quant = cv2.cvtColor(_clamp(hsv).astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 3. Cut lines around pieces; drop only tiny grass speckle, keep small
    #    player/ball outlines so they stay recognisable.
    line_mask = _clean_line_mask(smooth, lo=50, hi=130,
                                 min_frac=0.00015, thicken=1)
    return cv2.bitwise_and(quant, line_mask)


# Haar cascades for face-aware experimental style (bundled with OpenCV).
_HAAR = cv2.data.haarcascades
_FACE_CASCADE = cv2.CascadeClassifier(_HAAR + 'haarcascade_frontalface_default.xml')
_PROFILE_CASCADE = cv2.CascadeClassifier(_HAAR + 'haarcascade_profileface.xml')
_UPPERBODY_CASCADE = cv2.CascadeClassifier(_HAAR + 'haarcascade_upperbody.xml')


def _detect_faces(gray: np.ndarray) -> list:
    """Frontal + left/right profile faces. Returns [(x,y,w,h), ...]."""
    boxes = []
    for casc in (_FACE_CASCADE, _PROFILE_CASCADE):
        if casc.empty():
            continue
        for (x, y, w, h) in casc.detectMultiScale(gray, 1.1, 5, minSize=(24, 24)):
            boxes.append((int(x), int(y), int(w), int(h)))
    # Right-facing profiles: flip and detect, then mirror the x coordinate.
    if not _PROFILE_CASCADE.empty():
        W = gray.shape[1]
        flipped = cv2.flip(gray, 1)
        for (x, y, w, h) in _PROFILE_CASCADE.detectMultiScale(
                flipped, 1.1, 5, minSize=(24, 24)):
            boxes.append((int(W - x - w), int(y), int(w), int(h)))
    return boxes


def _experimental(frame: np.ndarray) -> np.ndarray:
    """Abstract painterly colour-map, but protect faces/upper bodies so people
    stay recognisable instead of being fully distorted."""
    base = cv2.stylization(frame, sigma_s=40, sigma_r=0.5)
    gray_b = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    mapped = cv2.applyColorMap(gray_b, cv2.COLORMAP_TWILIGHT_SHIFTED)
    effect = cv2.addWeighted(base, 0.5, mapped, 0.5, 0)   # full effect
    # Protected regions blend toward the raw frame so faces stay clearly
    # recognisable (feathering keeps the transition smooth, not a hard cutout).
    safe = frame

    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    protect = np.zeros((h, w), np.float32)

    faces = _detect_faces(gray)
    if faces:
        for (x, y, fw, fh) in faces:            # strong protection on faces
            x0, y0 = max(0, int(x - 0.15 * fw)), max(0, int(y - 0.20 * fh))
            x1, y1 = min(w, int(x + 1.15 * fw)), min(h, int(y + 1.40 * fh))
            protect[y0:y1, x0:x1] = 1.0
    else:
        bodies = ([] if _UPPERBODY_CASCADE.empty()
                  else _UPPERBODY_CASCADE.detectMultiScale(
                      gray, 1.1, 4, minSize=(60, 60)))
        if len(bodies):                          # fallback: upper-body area
            for (x, y, bw, bh) in bodies:
                x1, y1 = min(w, x + bw), min(h, int(y + bh * 0.6))
                protect[max(0, y):y1, max(0, x):x1] = 0.6
        else:                                    # last resort: mild global
            protect[:] = 0.30

    protect = cv2.GaussianBlur(protect, (0, 0), sigmaX=max(4.0, w * 0.02))
    protect = np.clip(protect, 0.0, 1.0)[..., None]
    out = effect.astype(np.float32) * (1 - protect) + safe.astype(np.float32) * protect
    return _clamp(out)


def cartoonize(frame: np.ndarray, style: str = "cartoon") -> np.ndarray:
    """Apply a stylisation to a single BGR frame and return a BGR frame."""

    if style == "2d":
        return _clean_2d(frame)

    if style == "cutout":
        return _paper_cutout(frame)

    if style == "sketch":
        return cv2.cvtColor(_pencil_sketch(frame), cv2.COLOR_GRAY2BGR)

    if style == "flipbook":
        # Sketchy lines, faint colour wash.
        sk = cv2.cvtColor(_pencil_sketch(frame), cv2.COLOR_GRAY2BGR)
        wash = cv2.bilateralFilter(frame, 9, 60, 60)
        return cv2.addWeighted(sk, 0.7, _quantize(wash, 6), 0.3, 0)

    if style == "whiteboard":
        # Black marker lines on a white board -- clean lines only (no crowd
        # / grass speckle), so it reads like a real whiteboard drawing.
        smooth = cv2.bilateralFilter(frame, 9, 75, 75)
        return _clean_line_mask(smooth, lo=60, hi=150,
                                min_frac=0.0004, thicken=1)

    if style in ("paint_glass", "paint"):
        return cv2.stylization(frame, sigma_s=60, sigma_r=0.45)

    if style == "experimental":
        return _experimental(frame)

    if style == "sand":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        noise = np.random.normal(0, 14, gray.shape).astype(np.int16)
        grainy = _clamp(gray.astype(np.int16) + noise)
        # Warm sepia tone (BGR weights).
        sepia = np.stack([
            grainy * 0.55, grainy * 0.70, grainy * 0.98
        ], axis=-1)
        return _clamp(sepia)

    if style == "clay":
        # Claymation: smooth matte surfaces + conservative posterise so the
        # colour reads as moulded clay, without hard outlines (soft edges) and
        # without breaking player/ball boundaries.
        smooth = frame
        for _ in range(3):
            smooth = cv2.bilateralFilter(smooth, 9, 90, 90)
        quant = _quantize(smooth, 10)                       # conservative
        hsv = cv2.cvtColor(quant, cv2.COLOR_BGR2HSV).astype(np.int16)
        hsv[..., 1] = np.clip(hsv[..., 1] * 1.30, 0, 255)   # saturation
        hsv[..., 2] = np.clip(hsv[..., 2] * 1.08, 0, 255)   # soft sheen
        clay = cv2.cvtColor(_clamp(hsv).astype(np.uint8), cv2.COLOR_HSV2BGR)
        return cv2.GaussianBlur(clay, (3, 3), 0)            # soft matte

    if style == "stop_motion":
        # Toy / puppet look: conservative posterise + a thin clean outline so
        # objects read as solid models. The choppy "on threes" timing comes
        # from frame_hold in the caller.
        s = cv2.bilateralFilter(frame, 9, 60, 60)
        s = cv2.bilateralFilter(s, 9, 60, 60)
        quant = _quantize(s, 12)                            # conservative
        hsv = cv2.cvtColor(quant, cv2.COLOR_BGR2HSV).astype(np.int16)
        hsv[..., 1] = np.clip(hsv[..., 1] * 1.25, 0, 255)   # saturation
        hsv[..., 2] = np.clip(hsv[..., 2] * 1.02, 0, 255)
        toy = cv2.cvtColor(_clamp(hsv).astype(np.uint8), cv2.COLOR_HSV2BGR)
        line_mask = _clean_line_mask(s, lo=60, hi=150,
                                     min_frac=0.0004, thicken=1)
        return cv2.bitwise_and(toy, line_mask)

    if style == "rotoscope":
        # Traced-live look: keep detail, band the colours, clean bold edges.
        color = cv2.bilateralFilter(frame, 9, 60, 60)
        color = _quantize(color, 5)
        line_mask = _clean_line_mask(color, lo=60, hi=150,
                                     min_frac=0.00015, thicken=1)
        return cv2.bitwise_and(color, line_mask)

    if style == "anime":
        return _cel(frame, n_levels=6)

    if style == "traditional":
        return _cel(frame, n_levels=8, smooth_passes=3)

    # default: cartoon
    return _cel(frame, n_levels=9)


def frame_hold_for(style: str) -> int:
    return STYLE_CONFIG.get(style, ("", 1))[1]


# --------------------------------------------------------------------------- #
#  Region removal (hide logos / text / watermarks)
# --------------------------------------------------------------------------- #
#
# Regions are given as fractions of the frame: (x, y, w, h) each in 0..1, so
# they survive any resize. Each region is covered on every frame using the
# chosen method. This hides logos and burned-in text rather than perfectly
# reconstructing what was behind them (that needs AI video inpainting).

REMOVE_METHODS = ("blur", "pixelate", "black", "inpaint")


def apply_removals(frame: np.ndarray,
                   regions: List[Tuple[float, float, float, float]],
                   method: str = "blur") -> np.ndarray:
    if not regions:
        return frame
    h, w = frame.shape[:2]
    inpaint_mask = None
    for (rx, ry, rw, rh) in regions:
        x1 = max(0, int(round(rx * w)))
        y1 = max(0, int(round(ry * h)))
        x2 = min(w, int(round((rx + rw) * w)))
        y2 = min(h, int(round((ry + rh) * h)))
        if x2 <= x1 or y2 <= y1:
            continue

        if method == "inpaint":
            if inpaint_mask is None:
                inpaint_mask = np.zeros((h, w), dtype=np.uint8)
            inpaint_mask[y1:y2, x1:x2] = 255
            continue

        roi = frame[y1:y2, x1:x2]
        if method == "black":
            frame[y1:y2, x1:x2] = 0
        elif method == "pixelate":
            small = cv2.resize(roi, (max(1, (x2 - x1) // 12),
                                     max(1, (y2 - y1) // 12)),
                               interpolation=cv2.INTER_LINEAR)
            frame[y1:y2, x1:x2] = cv2.resize(
                small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
        else:  # blur (default)
            sigma = max(8.0, (x2 - x1) / 10.0)
            frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (0, 0), sigmaX=sigma)

    if inpaint_mask is not None:
        frame = cv2.inpaint(frame, inpaint_mask, 3, cv2.INPAINT_TELEA)
    return frame


# --------------------------------------------------------------------------- #
#  Flat pitch, look adjustments, quality presets
# --------------------------------------------------------------------------- #

# preset name -> (max output width, x264 quality 0..10)
QUALITY_PRESETS = {
    "fast":     (480, 6),
    "balanced": (720, 8),
    "high":     (1080, 9),
}


def hex_to_bgr(hex_color: str,
               default: Tuple[int, int, int] = (60, 60, 200)) -> Tuple[int, int, int]:
    """'#c0392b' -> (B, G, R). Falls back to a red-ish default."""
    try:
        h = hex_color.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (b, g, r)
    except (ValueError, AttributeError, IndexError):
        return default


def replace_pitch(styled: np.ndarray, source: np.ndarray,
                  color_bgr: Tuple[int, int, int]) -> np.ndarray:
    """Replace the green grass with a flat solid colour, keeping the players,
    lines and ball (which are not green). Grass detection is by colour, so it
    is approximate."""
    hsv = cv2.cvtColor(source, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (30, 35, 35), (95, 255, 255))   # green range
    k = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    styled[mask > 0] = color_bgr
    return styled


def apply_adjustments(styled: np.ndarray, source: np.ndarray,
                      saturation: float = 1.0, brightness: float = 1.0,
                      outline_extra: int = 0) -> np.ndarray:
    """Post-process any style: saturation / brightness multipliers and an
    optional extra bold outline pass. Defaults are no-ops."""
    if saturation != 1.0 or brightness != 1.0:
        hsv = cv2.cvtColor(styled, cv2.COLOR_BGR2HSV).astype(np.int16)
        if saturation != 1.0:
            hsv[..., 1] = np.clip(hsv[..., 1] * saturation, 0, 255)
        if brightness != 1.0:
            hsv[..., 2] = np.clip(hsv[..., 2] * brightness, 0, 255)
        styled = cv2.cvtColor(_clamp(hsv).astype(np.uint8), cv2.COLOR_HSV2BGR)
    if outline_extra and outline_extra > 0:
        line_mask = _clean_line_mask(source, lo=60, hi=150,
                                     min_frac=0.0006, thicken=int(outline_extra))
        styled = cv2.bitwise_and(styled, line_mask)
    return styled


# --------------------------------------------------------------------------- #
#  Trim helpers
# --------------------------------------------------------------------------- #

def parse_cut_segments(raw: str) -> List[Tuple[float, float]]:
    """Parse ``"0-3, 10-12.5"`` into ``[(0,3),(10,12.5)]`` (spans to remove)."""
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
    """Invert cut spans into the spans that should be kept."""
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

    def process(
        self,
        input_path: str,
        output_path: str,
        style: str = "cartoon",
        cut_segments: Optional[List[Tuple[float, float]]] = None,
        audio_mode: str = "keep",           # keep | mute | replace
        replacement_audio: Optional[str] = None,  # path, for audio_mode=replace
        remove_regions: Optional[List[Tuple[float, float, float, float]]] = None,
        remove_method: str = "blur",
        flat_pitch: bool = False,
        pitch_color: Tuple[int, int, int] = (60, 60, 200),
        saturation: float = 1.0,
        brightness: float = 1.0,
        outline_extra: int = 0,
        quality: Optional[str] = None,
        max_width: int = 960,
        progress_cb: ProgressCB = None,
    ) -> dict:
        """Run the local (OpenCV) pipeline. Returns a dict of stats."""
        cut_segments = cut_segments or []
        remove_regions = remove_regions or []
        hold = frame_hold_for(style)

        # Quality preset controls output width + encoder quality.
        enc_quality = 8
        if quality in QUALITY_PRESETS:
            max_width, enc_quality = QUALITY_PRESETS[quality]

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

        scale = 1.0
        if max_width and src_w > max_width:
            scale = max_width / float(src_w)
        out_w = int(round(src_w * scale)) // 2 * 2 or src_w
        out_h = int(round(src_h * scale)) // 2 * 2 or src_h

        tmp_silent = tempfile.mktemp(suffix=".mp4")
        writer = imageio.get_writer(
            tmp_silent, fps=fps, codec="libx264", quality=enc_quality,
            macro_block_size=None, ffmpeg_log_level="error",
        )

        kept = 0
        processed = 0
        kept_index = 0
        last_styled: Optional[np.ndarray] = None
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

                # Hide logos / text before stylising.
                if remove_regions:
                    frame = apply_removals(frame, remove_regions, remove_method)

                # Frame holding for stop-motion / flipbook styles.
                if hold > 1 and last_styled is not None and kept_index % hold != 0:
                    styled = last_styled
                else:
                    styled = cartoonize(frame, style)
                    if flat_pitch:
                        styled = replace_pitch(styled, frame, pitch_color)
                    styled = apply_adjustments(styled, frame, saturation,
                                               brightness, outline_extra)
                    last_styled = styled
                kept_index += 1

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

        # ---- audio -------------------------------------------------------- #
        has_audio = False
        try:
            if audio_mode == "mute":
                self._copy_video(tmp_silent, output_path)
            elif audio_mode == "replace" and replacement_audio:
                self._mux_replacement_audio(tmp_silent, replacement_audio,
                                            output_path)
                has_audio = True
            else:  # keep
                self._mux_trimmed_audio(tmp_silent, input_path, output_path,
                                        cut_segments, duration)
                has_audio = True
        except Exception as e:  # noqa: BLE001 - audio is best-effort
            logger.warning("Audio step failed (%s); writing silent video", e)
            self._copy_video(tmp_silent, output_path)
            has_audio = False

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
            "has_audio": has_audio,
            "audio_mode": audio_mode,
            "style": style,
            "frame_hold": hold,
        }

    # -- internals ---------------------------------------------------------- #

    @staticmethod
    def _maybe_progress(cb: ProgressCB, done: int, total: int) -> None:
        if cb and total:
            cb(min(95, int(done * 95 / total)))

    def _run(self, cmd: List[str]) -> None:
        subprocess.run(cmd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def _copy_video(self, src: str, dst: str) -> None:
        self._run([self.ffmpeg, "-y", "-i", src, "-c", "copy", dst])

    def _mux_replacement_audio(self, video: str, audio: str, out: str) -> None:
        """Put a new audio track onto the video, cut to the video length."""
        self._run([
            self.ffmpeg, "-y",
            "-i", video, "-i", audio,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-shortest", out,
        ])

    def _mux_trimmed_audio(self, video: str, original: str, out: str,
                           cuts: List[Tuple[float, float]],
                           duration: float) -> None:
        """Trim the original audio to the kept ranges and mux it on."""
        if not cuts or not duration:
            self._run([
                self.ffmpeg, "-y", "-i", video, "-i", original,
                "-map", "0:v:0", "-map", "1:a:0?",
                "-c:v", "copy", "-c:a", "aac", "-shortest", out,
            ])
            return

        keep = keep_ranges_from_cuts(cuts, duration)
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
        self._run([
            self.ffmpeg, "-y", "-i", video, "-i", original,
            "-filter_complex", filter_complex,
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-shortest", out,
        ])
