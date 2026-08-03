"""Configuration for the tactical marker."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class MarkerConfig:
    input_path: str
    output_path: str = "marked.mp4"

    # marking mode:
    #   "ball-follow" -> mark only the ball carrier + pass arrows (default)
    #   "all-players" -> ring every detected player
    mode: str = "ball-follow"

    # detection / tracking
    model: str = "yolov8n.pt"      # auto-downloaded on first use
    conf: float = 0.25             # detection confidence threshold
    imgsz: int = 960               # detection input size (bigger = more small players)
    only_on_pitch: bool = True     # drop crowd / dugout detections

    # which markings to draw
    rings: bool = True             # ground ellipse under every player
    spotlight: bool = True         # beam following the key player
    arrows: bool = True            # motion arrow on the key player

    # ring appearance
    ring_color: Tuple[int, int, int] = (60, 60, 220)     # BGR (red)
    ring_alpha: float = 0.55
    color_by_team: bool = False    # colour rings by detected team (2 clusters)
    team_colors: Tuple[Tuple[int, int, int], Tuple[int, int, int]] = (
        (60, 60, 220), (220, 140, 40))                    # BGR red / blue

    # key player (spotlight + arrow target): "auto" = nearest ball, else centre
    spotlight_color: Tuple[int, int, int] = (0, 180, 255)  # BGR amber
    spotlight_alpha: float = 0.28
    key_track_id: Optional[int] = None   # force a specific tracked id
    arrow_color: Tuple[int, int, int] = (60, 230, 90)      # BGR green
    arrow_lookback: int = 8              # frames used to compute motion vector
    arrow_scale: float = 3.5             # how far to project the motion arrow

    # ball-follow tuning
    bridge_ball: bool = True         # bridge ball-detection gaps with optical flow
    max_bridge_frames: int = 20      # max consecutive frames to bridge without a real hit
    sticky_frames: int = 12          # keep marking the carrier through this many ball-less frames

    # performance
    max_seconds: Optional[float] = None  # cap processing length (None = full)
