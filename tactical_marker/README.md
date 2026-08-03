# ⚽ Tactical Marker

Automatically annotate a football clip with **tactical markings** — the kind you
see in pro analysis apps:

- 🔴 **Ground rings / ovals** under every detected player
- 🔦 **Spotlight beam** that follows the key player
- ➡️ **Motion arrows** showing that player's movement direction

You upload raw match footage; players are detected and tracked automatically and
the markings are drawn on top. No app menus, no manual frame-by-frame drawing.

## How it works

1. **Detect + track** players every frame with YOLOv8 + ByteTrack (persistent
   IDs, so markings stick to the same player as they move).
2. **Filter** to players on the green pitch (spectators / dugout are ignored).
3. **Draw** a ground ellipse under each player; pick the *key player* (nearest
   the ball, else the most central near-camera player) and give them a spotlight
   plus a motion arrow derived from their recent movement.
4. **Mux** the original audio back and export a browser-friendly MP4.

## Install

```bash
pip install -r tactical_marker/requirements.txt
```

This pulls in `ultralytics` (and PyTorch, CPU is fine). The detection weights
(`yolov8n.pt`, ~6 MB) download automatically on first run.

## Use it — web upload page

```bash
pip install flask
python -m tactical_marker.webapp        # http://localhost:5002
```

Upload a clip, tick the markings you want, click **Mark my video**.

## Use it — command line

```bash
# Auto-mark everything
python -m tactical_marker.cli match.mp4 -o marked.mp4

# Rings only, coloured by team, first 15 seconds
python -m tactical_marker.cli match.mp4 -o marked.mp4 \
    --no-spotlight --no-arrows --color-by-team --max-seconds 15

# Force which player gets the spotlight (by track id), better detection
python -m tactical_marker.cli match.mp4 -o marked.mp4 \
    --spotlight-id 7 --model yolov8s.pt --imgsz 1280
```

Run `python -m tactical_marker.cli -h` for all options.

## Use it — from Python

```python
from tactical_marker import MarkerConfig, process

process(MarkerConfig(
    input_path="match.mp4",
    output_path="marked.mp4",
    rings=True, spotlight=True, arrows=True,
    color_by_team=False,
))
```

## Tuning

| Want… | Do this |
|-------|---------|
| More players detected (small / far) | `--model yolov8s.pt` (or `m`) and `--imgsz 1280` |
| Fewer false marks | raise `--conf 0.35` |
| Mark a specific player only | set `--spotlight-id <id>` after a first pass to read ids |
| Two team colours | `--color-by-team` |
| Faster test | `--max-seconds 10` |

Colours, ellipse size, spotlight/arrow look, etc. live in
[`config.py`](config.py) (`MarkerConfig`) and the primitives in
[`draw.py`](draw.py).

## Limits / honest notes

- Detection is a **nano** model by default for speed; on wide broadcast shots
  some distant players are missed — use `yolov8s/m` + a larger `--imgsz` for
  better coverage (slower).
- "Key player" selection is heuristic. `sports ball` detection is unreliable at
  small sizes, so the spotlight falls back to the central near-camera player;
  use `--spotlight-id` to lock onto exactly who you want.
- Arrows show **actual tracked movement**, not tactical intent. Bespoke
  pass/run arrows between chosen points are a natural next feature.
- Processing is CPU-bound (a few seconds per second of footage). A GPU, if
  present, is used automatically by ultralytics.
