"""Process a football clip: detect + track players and draw tactical markings.

Pipeline:
  1. Run YOLO detection + tracking (persistent IDs) frame by frame.
  2. For each frame, draw a ground ellipse under every on-pitch player.
  3. Pick a "key player" (nearest the ball, else most central) and follow them
     with a spotlight beam and a motion arrow derived from their movement.
  4. Write the annotated frames, then mux the original audio back with ffmpeg.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections import defaultdict, deque
from typing import Dict, Optional

import cv2
import numpy as np

from . import draw
from . import pitch
from .config import MarkerConfig


def _find_ffmpeg() -> Optional[str]:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _has_audio(path, ffmpeg) -> bool:
    if not ffmpeg:
        return False
    p = subprocess.run([ffmpeg, "-i", path],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return "Audio:" in p.stderr.decode("utf-8", "ignore")


def _pick_key_id(tracks, ball_xy, frame_shape):
    """Choose the key player's track id for this frame."""
    if not tracks:
        return None
    if ball_xy is not None:
        bx, by = ball_xy
        return min(tracks.keys(),
                   key=lambda k: (tracks[k][0] - bx) ** 2 + (tracks[k][1] - by) ** 2)
    # else most central-and-near-camera player (bottom centre bias)
    h, w = frame_shape[:2]
    cx, cy = w / 2, h * 0.75
    return min(tracks.keys(),
               key=lambda k: (tracks[k][0] - cx) ** 2 + (tracks[k][1] - cy) ** 2)


def process(cfg: MarkerConfig, progress=None) -> str:
    # Ball-follow is a separate two-pass pipeline.
    if cfg.mode == "ball-follow":
        from . import ballfollow
        return ballfollow.process(cfg, progress=progress)
    return _process_all_players(cfg, progress=progress)


def _process_all_players(cfg: MarkerConfig, progress=None) -> str:
    def log(m):
        if progress:
            progress(m)

    from ultralytics import YOLO  # imported lazily (heavy)

    ffmpeg = _find_ffmpeg()
    cap = cv2.VideoCapture(cfg.input_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    max_frames = int(cfg.max_seconds * fps) if cfg.max_seconds else total
    log(f"Input {W}x{H} @ {fps:.0f}fps, {total} frames; "
        f"processing {max_frames or 'all'}")

    model = YOLO(cfg.model)
    log("Model loaded; detecting + tracking…")

    work = tempfile.mkdtemp(prefix="tacmark_")
    silent = os.path.join(work, "silent.mp4")
    writer = cv2.VideoWriter(silent, cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (W, H))

    # recent centre positions per track id (for motion arrows)
    history: Dict[int, deque] = defaultdict(lambda: deque(maxlen=30))

    stream = model.track(
        source=cfg.input_path, stream=True, persist=True,
        classes=[0, 32],                 # 0=person, 32=sports ball
        conf=cfg.conf, imgsz=cfg.imgsz,
        tracker="bytetrack.yaml", verbose=False,
    )

    n = 0
    for res in stream:
        if max_frames and n >= max_frames:
            break
        frame = res.orig_img.copy()
        mask = pitch.pitch_mask(frame) if cfg.only_on_pitch else None

        players = {}       # track_id -> (cx, feet_y, box_w, (x1,y1,x2,y2))
        ball_xy = None
        colors, color_ids = [], []

        if res.boxes is not None and res.boxes.id is not None:
            xyxy = res.boxes.xyxy.cpu().numpy()
            ids = res.boxes.id.cpu().numpy().astype(int)
            clss = res.boxes.cls.cpu().numpy().astype(int)
            for (x1, y1, x2, y2), tid, cl in zip(xyxy, ids, clss):
                if cl == 32:  # ball
                    ball_xy = ((x1 + x2) / 2, (y1 + y2) / 2)
                    continue
                if cfg.only_on_pitch and mask is not None and \
                        not pitch.on_pitch(mask, x1, y1, x2, y2):
                    continue
                cx = (x1 + x2) / 2
                feet = y2
                bw = (x2 - x1)
                players[int(tid)] = (cx, feet, bw, (x1, y1, x2, y2))
                history[int(tid)].append((cx, feet))
                if cfg.color_by_team:
                    colors.append(pitch.jersey_color(frame, x1, y1, x2, y2))
                    color_ids.append(int(tid))

        team_of = {}
        if cfg.color_by_team and colors:
            labels = pitch.classify_teams(colors)
            team_of = dict(zip(color_ids, labels))

        # key player for spotlight + arrow
        key_id = cfg.key_track_id
        if key_id is None or key_id not in players:
            centres = {k: (v[0], v[1]) for k, v in players.items()}
            key_id = _pick_key_id(centres, ball_xy, frame.shape) if centres else None

        # ---- draw (spotlight first so it sits under the rings) ----
        if cfg.spotlight and key_id in players:
            cx, feet, bw, _ = players[key_id]
            draw.spotlight(frame, int(cx), int(feet), max(140, int(bw * 2.2)),
                           color=cfg.spotlight_color, alpha=cfg.spotlight_alpha)

        if cfg.rings:
            for tid, (cx, feet, bw, _) in players.items():
                col = cfg.ring_color
                if cfg.color_by_team and tid in team_of:
                    col = cfg.team_colors[team_of[tid]]
                draw.ground_ellipse(frame, cx, feet, max(46, bw * 1.15),
                                    color=col, alpha=cfg.ring_alpha)

        if cfg.arrows and key_id in players and len(history[key_id]) > cfg.arrow_lookback:
            hx = history[key_id]
            x0, y0 = hx[-cfg.arrow_lookback - 1]
            x1c, y1c = hx[-1]
            dx, dy = (x1c - x0), (y1c - y0)
            if dx * dx + dy * dy > 9:  # only if actually moving
                p1 = (x1c, y1c)
                p2 = (x1c + dx * cfg.arrow_scale, y1c + dy * cfg.arrow_scale)
                draw.arrow(frame, p1, p2, color=cfg.arrow_color)

        writer.write(frame)
        n += 1
        if progress and n % 30 == 0:
            log(f"  {n}/{max_frames or total} frames…")

    writer.release()
    log(f"Rendered {n} frames; muxing audio…")

    out = cfg.output_path
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    if ffmpeg and _has_audio(cfg.input_path, ffmpeg) and not cfg.max_seconds:
        cmd = [ffmpeg, "-y", "-i", silent, "-i", cfg.input_path,
               "-map", "0:v", "-map", "1:a",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
               "-preset", "veryfast", "-c:a", "aac", "-b:a", "160k",
               "-shortest", "-movflags", "+faststart", out]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elif ffmpeg:
        # re-encode to browser-friendly h264 (no/clipped audio)
        cmd = [ffmpeg, "-y", "-i", silent,
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
               "-preset", "veryfast", "-movflags", "+faststart", out]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        shutil.copy(silent, out)

    shutil.rmtree(work, ignore_errors=True)
    log(f"Done → {out}")
    return out
