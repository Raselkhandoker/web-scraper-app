"""Ball-follow marking: mark only the player on the ball, and passes.

Instead of ringing every player, this mode follows the ball:

  * mark **only the current ball carrier** (spotlight + ring),
  * when the ball moves to another player, that's a **pass** — draw an arrow
    from the passer to the receiver and move the mark onto the receiver,
  * repeat down the chain (player 1 → 2 → 3 …).

It works in two passes over the clip (offline), so it can "see the future":

  1. **Analyse** — detect + track players and the ball every frame; store the
     lightweight per-frame data (no images kept).
  2. Build a smoothed **ball trajectory**, a **possession timeline** (who holds
     the ball, when) and the **pass events** between possession segments.
  3. **Render** — re-read the frames and draw the mark on the current carrier
     plus a pass arrow across each pass window.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from . import draw
from . import pitch
from .config import MarkerConfig


# --------------------------------------------------------------------------- #
# small helpers (ffmpeg / audio) — shared shape with processor.py
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #
class FrameData:
    __slots__ = ("players", "ball", "ball_real")

    def __init__(self):
        self.players: Dict[int, Tuple[float, float, float]] = {}  # tid -> (cx, feet, w)
        self.ball: Optional[Tuple[float, float]] = None
        self.ball_real: bool = False   # True = YOLO detection, False = optical-flow bridge


_LK = dict(winSize=(21, 21), maxLevel=3,
           criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03))


def _analyse(model, cfg: MarkerConfig, max_frames: int, log):
    """Detect + track players/ball, and bridge ball gaps with optical flow.

    Returns (frames, real_ball_count).
    """
    frames: List[FrameData] = []
    stream = model.track(
        source=cfg.input_path, stream=True, persist=True,
        classes=[0, 32], conf=cfg.conf, imgsz=cfg.imgsz,
        tracker="bytetrack.yaml", verbose=False,
    )
    prev_gray = None
    ball_pt = None            # current best (x, y) estimate
    bridge = 0                # consecutive frames tracked without a real detection
    real_count = 0
    n = 0
    for res in stream:
        if max_frames and n >= max_frames:
            break
        fd = FrameData()
        img = res.orig_img
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = pitch.pitch_mask(img) if cfg.only_on_pitch else None

        best_ball = None
        if res.boxes is not None and res.boxes.id is not None:
            xyxy = res.boxes.xyxy.cpu().numpy()
            ids = res.boxes.id.cpu().numpy().astype(int)
            clss = res.boxes.cls.cpu().numpy().astype(int)
            for (x1, y1, x2, y2), tid, cl in zip(xyxy, ids, clss):
                if cl == 32:
                    if best_ball is None:
                        best_ball = ((x1 + x2) / 2, (y1 + y2) / 2)
                    continue
                if cfg.only_on_pitch and mask is not None and \
                        not pitch.on_pitch(mask, x1, y1, x2, y2):
                    continue
                fd.players[int(tid)] = ((x1 + x2) / 2, y2, (x2 - x1))

        if best_ball is not None:
            # real detection anchors the tracker
            ball_pt = best_ball
            fd.ball, fd.ball_real, bridge = best_ball, True, 0
            real_count += 1
        elif (cfg.bridge_ball and ball_pt is not None and prev_gray is not None
              and bridge < cfg.max_bridge_frames):
            p0 = np.array([[ball_pt]], np.float32)
            p1, st, err = cv2.calcOpticalFlowPyrLK(prev_gray, gray, p0, None, **_LK)
            if st is not None and st[0][0] == 1 and err is not None and err[0][0] < 40:
                nx, ny = float(p1[0][0][0]), float(p1[0][0][1])
                # reject implausible jumps
                if abs(nx - ball_pt[0]) < 80 and abs(ny - ball_pt[1]) < 80:
                    ball_pt = (nx, ny)
                    fd.ball, fd.ball_real, bridge = ball_pt, False, bridge + 1
                else:
                    ball_pt = None
            else:
                ball_pt = None
        else:
            ball_pt = None

        prev_gray = gray
        frames.append(fd)
        n += 1
        if n % 30 == 0:
            log(f"  analysed {n}/{max_frames or '?'} frames…")
    return frames, real_count


def _interp_ball(frames: List[FrameData]) -> List[Optional[Tuple[float, float]]]:
    """Fill gaps in the ball trajectory by linear interpolation."""
    known = [(i, f.ball) for i, f in enumerate(frames) if f.ball is not None]
    traj: List[Optional[Tuple[float, float]]] = [None] * len(frames)
    if not known:
        return traj
    for i, b in known:
        traj[i] = b
    # interpolate interior gaps
    for a in range(len(known) - 1):
        (i0, b0), (i1, b1) = known[a], known[a + 1]
        if i1 - i0 <= 1:
            continue
        if i1 - i0 > 45:            # too long a gap: leave as None (ball lost)
            continue
        for k in range(i0 + 1, i1):
            t = (k - i0) / (i1 - i0)
            traj[k] = (b0[0] * (1 - t) + b1[0] * t,
                       b0[1] * (1 - t) + b1[1] * t)
    # pad the ends with the nearest known position
    first_i = known[0][0]
    for k in range(0, first_i):
        traj[k] = known[0][1]
    last_i = known[-1][0]
    for k in range(last_i + 1, len(frames)):
        traj[k] = known[-1][1]
    return traj


def _carrier_per_frame(frames, traj, dist_scale=1.6) -> List[Optional[int]]:
    """Nearest player to the ball, if close enough (else None = in flight)."""
    out: List[Optional[int]] = []
    for f, ball in zip(frames, traj):
        if ball is None or not f.players:
            out.append(None)
            continue
        bx, by = ball
        best, bestd, bestw = None, 1e18, 1.0
        for tid, (cx, feet, w) in f.players.items():
            d = (cx - bx) ** 2 + (feet - by) ** 2
            if d < bestd:
                best, bestd, bestw = tid, d, w
        thresh = (max(55, bestw * dist_scale)) ** 2
        out.append(best if bestd <= thresh else None)
    return out


def _smooth_carrier(raw: List[Optional[int]], win=7) -> List[Optional[int]]:
    """Majority-vote smoothing + fill short None gaps to stabilise possession."""
    n = len(raw)
    sm: List[Optional[int]] = [None] * n
    for i in range(n):
        lo, hi = max(0, i - win // 2), min(n, i + win // 2 + 1)
        counts: Dict[int, int] = {}
        for k in range(lo, hi):
            if raw[k] is not None:
                counts[raw[k]] = counts.get(raw[k], 0) + 1
        if counts:
            sm[i] = max(counts, key=counts.get)
    return sm


def _sticky_fill(carrier: List[Optional[int]], hold: int) -> List[Optional[int]]:
    """Hold the last carrier across short None gaps (ball briefly lost).

    Only bridges a gap if the SAME player holds the ball on both sides, so we
    don't invent possession across an actual pass/turnover.
    """
    if hold <= 0:
        return carrier
    out = list(carrier)
    n = len(out)
    i = 0
    while i < n:
        if out[i] is None:
            j = i
            while j < n and out[j] is None:
                j += 1
            before = out[i - 1] if i > 0 else None
            after = out[j] if j < n else None
            if before is not None and before == after and (j - i) <= hold:
                for k in range(i, j):
                    out[k] = before
            i = j
        else:
            i += 1
    return out


def _segments(carrier: List[Optional[int]], min_len=5):
    """Contiguous possession runs -> list of (tid, start, end) inclusive."""
    segs = []
    i, n = 0, len(carrier)
    while i < n:
        if carrier[i] is None:
            i += 1
            continue
        tid = carrier[i]
        j = i
        while j + 1 < n and carrier[j + 1] == tid:
            j += 1
        if j - i + 1 >= min_len:
            segs.append((tid, i, j))
        i = j + 1
    return segs


def _latched_possession(frames, traj, cfg):
    """Follow possession using reliable player tracking, anchored by the ball.

    The ball only tells us *when* possession changes; between those moments the
    mark stays latched onto the current carrier (whose player track is reliable),
    so marking stays continuous even when the ball is briefly undetected.

    Returns (carrier_per_frame, passes) where passes = [(frame, from_tid, to_tid)].
    """
    n = len(frames)
    cand = _carrier_per_frame(frames, traj)   # nearest player to the ball, or None
    carrier = [None] * n
    passes = []
    cur = None
    pend = None
    pend_count = 0
    last_seen = {}
    for i in range(n):
        c = cand[i]
        if c is not None and c == cur:
            pend, pend_count = None, 0
        elif c is not None and c != cur:
            if c == pend:
                pend_count += 1
            else:
                pend, pend_count = c, 1
            if pend_count >= cfg.switch_frames or cur is None:
                if cur is not None:
                    passes.append((i, cur, c))
                cur, pend, pend_count = c, None, 0
        # drop a carrier whose player track has been gone too long
        if cur is not None:
            if cur in frames[i].players:
                last_seen[cur] = i
            elif i - last_seen.get(cur, i) > cfg.carrier_drop_frames:
                cur = None
        carrier[i] = cur
    return carrier, passes


# --------------------------------------------------------------------------- #
# public entry
# --------------------------------------------------------------------------- #
def process(cfg: MarkerConfig, progress=None) -> str:
    def log(m):
        if progress:
            progress(m)

    from ultralytics import YOLO

    ffmpeg = _find_ffmpeg()
    cap = cv2.VideoCapture(cfg.input_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    max_frames = int(cfg.max_seconds * fps) if cfg.max_seconds else total

    model = YOLO(cfg.model)
    log("Analysing clip (detect + track ball & players)…")
    frames, real_count = _analyse(model, cfg, max_frames, log)

    traj = _interp_ball(frames)
    covered = sum(1 for f in frames if f.ball is not None)
    nf = max(len(frames), 1)
    log(f"Ball: detected {real_count}/{len(frames)} ({100*real_count/nf:.0f}%), "
        f"bridged to {covered}/{len(frames)} ({100*covered/nf:.0f}%) coverage.")
    if real_count == 0:
        raise RuntimeError(
            "The ball was never detected — ball-follow mode can't work on this "
            "clip automatically. Try a clearer/zoomed clip, a bigger model "
            "(--model yolov8s.pt --imgsz 1280), or the all-players mode.")

    carrier, passes = _latched_possession(frames, traj, cfg)
    marked_cov = sum(1 for c in carrier if c is not None)
    log(f"Marked carrier in {marked_cov}/{len(frames)} frames "
        f"({100*marked_cov/nf:.0f}%) → {len(passes)} passes.")

    # Per-frame plan: the marked player, and any active pass arrow.
    marked: List[Optional[int]] = list(carrier)
    arrows: List[Optional[Tuple[int, int]]] = [None] * len(frames)
    for (fr, a, b) in passes:
        for k in range(max(0, fr - 6), min(len(frames), fr + 6)):
            arrows[k] = (a, b)

    # ---- render pass ----
    work = tempfile.mkdtemp(prefix="ballfollow_")
    silent = os.path.join(work, "silent.mp4")
    writer = cv2.VideoWriter(silent, cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (W, H))
    cap = cv2.VideoCapture(cfg.input_path)
    log("Rendering marked video…")
    idx = 0
    while idx < len(frames):
        ok, frame = cap.read()
        if not ok:
            break
        fd = frames[idx]

        # pass arrow (draw under the ring)
        ar = arrows[idx]
        if cfg.arrows and ar is not None:
            a_tid, b_tid = ar
            if a_tid in fd.players and b_tid in fd.players:
                ax, afeet, _ = fd.players[a_tid]
                bx, bfeet, _ = fd.players[b_tid]
                draw.arrow(frame, (ax, afeet), (bx, bfeet),
                           color=cfg.arrow_color)

        mk = marked[idx]
        if mk in fd.players:
            cx, feet, w = fd.players[mk]
            if cfg.spotlight:
                draw.spotlight(frame, int(cx), int(feet), max(140, int(w * 2.2)),
                               color=cfg.spotlight_color, alpha=cfg.spotlight_alpha,
                               top_y=int(H * cfg.spotlight_top_frac))
            if cfg.rings:
                draw.ground_ellipse(frame, cx, feet, max(50, w * 1.2),
                                    color=cfg.ring_color, alpha=cfg.ring_alpha)
        # also mark the receiver as the ball arrives
        if cfg.rings and ar is not None and ar[1] in fd.players:
            rx, rfeet, rw = fd.players[ar[1]]
            draw.ground_ellipse(frame, rx, rfeet, max(50, rw * 1.2),
                                color=cfg.ring_color, alpha=cfg.ring_alpha * 0.7)

        writer.write(frame)
        idx += 1
        if idx % 30 == 0:
            log(f"  rendered {idx}/{len(frames)} frames…")
    writer.release()
    cap.release()

    out = cfg.output_path
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    if ffmpeg and _has_audio(cfg.input_path, ffmpeg):
        # mux the original audio (trimmed to the rendered length for segments)
        rendered_secs = idx / fps
        audio_in = ["-i", cfg.input_path]
        trim = ["-t", f"{rendered_secs:.3f}"] if cfg.max_seconds else []
        subprocess.run([ffmpeg, "-y", "-i", silent, *audio_in,
                        "-map", "0:v", "-map", "1:a", *trim,
                        "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast",
                        "-c:a", "aac", "-b:a", "160k", "-shortest",
                        "-movflags", "+faststart", out],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elif ffmpeg:
        subprocess.run([ffmpeg, "-y", "-i", silent, "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast",
                        "-movflags", "+faststart", out],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        shutil.copy(silent, out)
    shutil.rmtree(work, ignore_errors=True)
    log(f"Done → {out}")
    return out
