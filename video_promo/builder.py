"""Render a styled promo video from a raw clip using ffmpeg.

Pipeline:
  1. Probe the input clip (size / duration).
  2. Draw the static assets (background, panel mask, captions, outro card).
  3. Render the MAIN segment: background + rounded footage panel + captions.
  4. Render the OUTRO segment: the closing CTA card.
  5. Concatenate the two segments into the final vertical video.

The only hard dependencies are Pillow and an ffmpeg binary. If ffmpeg is not on
PATH, a static one is used via the optional ``imageio-ffmpeg`` package.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

from . import config as C
from . import style


# --------------------------------------------------------------------------- #
# ffmpeg discovery
# --------------------------------------------------------------------------- #
def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "ffmpeg not found. Install it (apt install ffmpeg) or "
            "`pip install imageio-ffmpeg`."
        ) from exc


def _run(cmd: List[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "ignore")[-2000:]
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}):\n{tail}")


# --------------------------------------------------------------------------- #
# Probing
# --------------------------------------------------------------------------- #
def probe(path: str, ffmpeg: str) -> Tuple[int, int, float, bool]:
    """Return (width, height, duration_seconds, has_audio)."""
    width = height = 0
    duration = 0.0
    has_audio = False
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or C.FPS
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        duration = frames / fps if fps else 0
        cap.release()
    except Exception:
        pass

    # Fall back to / confirm via ffmpeg banner, and detect audio.
    proc = subprocess.run([ffmpeg, "-i", path],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    info = proc.stderr.decode("utf-8", "ignore")
    has_audio = "Audio:" in info
    if (not width or not height or duration <= 0):
        for line in info.splitlines():
            if "Video:" in line and ("x" in line):
                import re
                m = re.search(r"(\d{2,5})x(\d{2,5})", line)
                if m:
                    width, height = int(m.group(1)), int(m.group(2))
            if "Duration:" in line:
                import re
                m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", line)
                if m:
                    h, mi, s = m.groups()
                    duration = int(h) * 3600 + int(mi) * 60 + float(s)
    if not width or not height:
        raise RuntimeError(f"Could not read video dimensions from {path}")
    if duration <= 0:
        duration = 10.0
    return width, height, duration, has_audio


# --------------------------------------------------------------------------- #
# Layout helpers
# --------------------------------------------------------------------------- #
PANEL_MAX_W = C.PANEL_W        # 980
PANEL_MAX_H = 1080


def _panel_size(iw: int, ih: int) -> Tuple[int, int]:
    """Fit the source inside the panel bounding box, preserving aspect ratio.

    Landscape clips become a wide short panel; portrait clips a tall narrow
    one. Either way the footage fills its panel edge to edge — no black bars.
    """
    scale = min(PANEL_MAX_W / iw, PANEL_MAX_H / ih)
    w = int(round(iw * scale))
    h = int(round(ih * scale))
    if w % 2:
        w += 1
    if h % 2:
        h += 1
    return w, h


# --------------------------------------------------------------------------- #
# Main build
# --------------------------------------------------------------------------- #
def build(cfg: C.BuildConfig, progress=None) -> str:
    """Build the promo described by ``cfg`` and return the output path."""
    def log(msg: str):
        if progress:
            progress(msg)

    ffmpeg = find_ffmpeg()
    iw, ih, dur, has_audio = probe(cfg.input_path, ffmpeg)
    log(f"Input: {iw}x{ih}, {dur:.1f}s, audio={has_audio}")

    panel_w, panel_h = _panel_size(iw, ih)
    panel_x = (C.WIDTH - panel_w) // 2
    # Vertically place the panel; keep the reference top position when it fits,
    # otherwise centre it in the space above the logo band.
    panel_y = C.PANEL_Y
    if panel_y + panel_h > C.HEIGHT - C.BAND_H - 40:
        panel_y = max(120, (C.HEIGHT - C.BAND_H - panel_h) // 2)

    work = tempfile.mkdtemp(prefix="promo_")
    try:
        # ---- assets ----
        log("Drawing assets…")
        bg = style.make_background(cfg.brand, os.path.join(work, "bg.png"))
        mask = style.make_panel_mask(panel_w, panel_h, C.PANEL_RADIUS,
                                     os.path.join(work, "mask.png"))
        outro = style.make_outro(cfg.brand, os.path.join(work, "outro.png"))

        cap_pngs: List[str] = []
        for i, text in enumerate(cfg.captions):
            p, _, _ = style.make_caption(text, cfg.brand,
                                         os.path.join(work, f"cap_{i}.png"))
            cap_pngs.append(p)

        main_mp4 = os.path.join(work, "main.mp4")
        outro_mp4 = os.path.join(work, "outro.mp4")

        # ---- main segment ----
        log("Rendering main segment…")
        _render_main(ffmpeg, cfg, bg, mask, cap_pngs, panel_w, panel_h,
                     panel_x, panel_y, dur, has_audio, main_mp4)

        # ---- outro segment ----
        log("Rendering outro…")
        _render_outro(ffmpeg, outro, cfg.outro_seconds, outro_mp4)

        # ---- concat ----
        log("Joining segments…")
        os.makedirs(os.path.dirname(os.path.abspath(cfg.output_path)) or ".",
                    exist_ok=True)
        _concat(ffmpeg, [main_mp4, outro_mp4], cfg.output_path)

        log(f"Done → {cfg.output_path}")
        return cfg.output_path
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _render_main(ffmpeg, cfg, bg, mask, cap_pngs, panel_w, panel_h, panel_x,
                 panel_y, dur, has_audio, out_mp4):
    W, H = C.WIDTH, C.HEIGHT
    inputs: List[str] = []

    # 0: background (looped image)
    inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", bg]
    # 1: source video
    inputs += ["-i", cfg.input_path]
    # 2: panel mask
    inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", mask]
    # 3..: captions
    cap_start_idx = 3
    for p in cap_pngs:
        inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", p]

    # audio inputs come after the images
    next_idx = cap_start_idx + len(cap_pngs)
    music_idx = None
    silence_idx = None
    use_music = bool(cfg.music_path and os.path.exists(cfg.music_path))
    if use_music:
        inputs += ["-stream_loop", "-1", "-i", cfg.music_path]
        music_idx = next_idx
        next_idx += 1
    need_silence = not (has_audio and cfg.keep_original_audio) and not use_music
    if need_silence:
        inputs += ["-f", "lavfi", "-t", f"{dur:.3f}",
                   "-i", "anullsrc=r=44100:cl=stereo"]
        silence_idx = next_idx
        next_idx += 1

    # ---- video filtergraph ----
    fc = []
    fc.append(f"[1:v]scale={panel_w}:{panel_h},setsar=1[vid]")
    fc.append(f"[vid][2:v]alphamerge[vidr]")
    fc.append(f"[0:v][vidr]overlay={panel_x}:{panel_y}[b0]")

    prev = "b0"
    n = len(cfg.captions)
    seg = dur / n if n else dur
    for i in range(n):
        start = i * seg
        end = (i + 1) * seg
        idx = cap_start_idx + i
        y_expr = f"{C.CAPTION_CENTER_Y}-overlay_h/2"
        out_lbl = f"b{i+1}"
        fc.append(
            f"[{prev}][{idx}:v]overlay=x=(main_w-overlay_w)/2:y={y_expr}:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{out_lbl}]"
        )
        prev = out_lbl
    fc.append(f"[{prev}]format=yuv420p[vout]")

    # ---- audio filtergraph ----
    if has_audio and cfg.keep_original_audio and use_music:
        fc.append(f"[1:a]aresample=44100[oa]")
        fc.append(f"[{music_idx}:a]volume={cfg.music_volume},aresample=44100[ma]")
        fc.append("[oa][ma]amix=inputs=2:duration=first:dropout_transition=0[aout]")
        amap = "[aout]"
    elif has_audio and cfg.keep_original_audio:
        fc.append("[1:a]aresample=44100,aformat=channel_layouts=stereo[aout]")
        amap = "[aout]"
    elif use_music:
        fc.append(f"[{music_idx}:a]volume={cfg.music_volume},aresample=44100,"
                  f"aformat=channel_layouts=stereo[aout]")
        amap = "[aout]"
    else:
        amap = f"{silence_idx}:a"

    cmd = [ffmpeg, "-y", *inputs,
           "-filter_complex", ";".join(fc),
           "-map", "[vout]", "-map", amap,
           "-t", f"{dur:.3f}",
           "-r", str(C.FPS),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
           "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
           out_mp4]
    _run(cmd)


def _render_outro(ffmpeg, outro_png, seconds, out_mp4):
    cmd = [ffmpeg, "-y",
           "-loop", "1", "-t", f"{seconds:.3f}", "-i", outro_png,
           "-f", "lavfi", "-t", f"{seconds:.3f}", "-i",
           "anullsrc=r=44100:cl=stereo",
           "-filter_complex", "[0:v]format=yuv420p[v]",
           "-map", "[v]", "-map", "1:a",
           "-r", str(C.FPS),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
           "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
           out_mp4]
    _run(cmd)


def _concat(ffmpeg, segments: List[str], out_path: str):
    inputs = []
    for s in segments:
        inputs += ["-i", s]
    n = len(segments)
    streams = "".join(f"[{i}:v][{i}:a]" for i in range(n))
    fc = f"{streams}concat=n={n}:v=1:a=1[v][a]"
    cmd = [ffmpeg, "-y", *inputs,
           "-filter_complex", fc,
           "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
           "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
           "-movflags", "+faststart",
           out_path]
    _run(cmd)
