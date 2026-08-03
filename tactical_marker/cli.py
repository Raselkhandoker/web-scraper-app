"""Command-line interface for the tactical marker.

Examples
--------
    # Auto-mark all players + spotlight + arrows
    python -m tactical_marker.cli match.mp4 -o marked.mp4

    # Only ground rings, coloured by team, first 15s
    python -m tactical_marker.cli match.mp4 -o marked.mp4 \
        --no-spotlight --no-arrows --color-by-team --max-seconds 15
"""
from __future__ import annotations

import argparse
import sys

from .config import MarkerConfig
from .processor import process


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="tactical_marker",
        description="Auto-draw tactical markings on a football clip.")
    p.add_argument("input", help="input football video")
    p.add_argument("-o", "--output", default="marked.mp4")

    p.add_argument("--no-rings", action="store_true", help="don't draw ground rings")
    p.add_argument("--no-spotlight", action="store_true", help="don't draw the spotlight")
    p.add_argument("--no-arrows", action="store_true", help="don't draw motion arrows")

    p.add_argument("--color-by-team", action="store_true",
                   help="colour rings by detected team (2 clusters)")
    p.add_argument("--include-crowd", action="store_true",
                   help="also mark people off the pitch (default: pitch only)")
    p.add_argument("--spotlight-id", type=int, default=None,
                   help="force the key player's track id")

    p.add_argument("--conf", type=float, default=0.25, help="detection confidence")
    p.add_argument("--imgsz", type=int, default=960, help="detection input size")
    p.add_argument("--model", default="yolov8n.pt",
                   help="YOLO weights (yolov8n/s/m…); larger = better, slower")
    p.add_argument("--max-seconds", type=float, default=None,
                   help="only process the first N seconds")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    cfg = MarkerConfig(
        input_path=a.input, output_path=a.output,
        rings=not a.no_rings, spotlight=not a.no_spotlight,
        arrows=not a.no_arrows, color_by_team=a.color_by_team,
        only_on_pitch=not a.include_crowd, key_track_id=a.spotlight_id,
        conf=a.conf, imgsz=a.imgsz, model=a.model, max_seconds=a.max_seconds,
    )
    try:
        process(cfg, progress=lambda m: print(f"[tacmark] {m}", flush=True))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
