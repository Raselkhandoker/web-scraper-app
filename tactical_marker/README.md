# ⚽ Tactical Marker

Automatically annotate a football clip with **tactical markings** — the kind you
see in pro analysis apps. You upload raw match footage; players and the ball are
detected and tracked automatically and the markings are drawn on top. No app
menus, no manual frame-by-frame drawing.

## Two modes

### `ball-follow` (default) — follow the ball

Marks **only the player on the ball**, not everyone:

- 🔦 spotlight + 🔴 ring on the **current ball carrier**
- when the ball is passed, an ➡️ **arrow** from passer to receiver, and the mark
  moves onto the **receiver**
- follows the whole chain: player 1 → 2 → 3 …

This keeps the video clean — one highlighted player at a time. It depends on the
ball being detectable in your footage (see *Limits*).

### `all-players` — ring everyone

- 🔴 ground ring under **every** on-pitch player
- 🔦 spotlight on the key player + ➡️ motion arrow

Use `--mode all-players` for this.

## How it works

**ball-follow** runs two offline passes so it can "see the future":

1. **Analyse** — detect + track players and the ball every frame (YOLOv8 +
   ByteTrack), storing lightweight per-frame data.
2. Build a smoothed **ball trajectory** (gaps interpolated), a **possession
   timeline** (who holds the ball) and the **pass events** between segments.
3. **Render** — draw the mark on the current carrier and a pass arrow across
   each pass window; mux the original audio back; export H.264 MP4.

Spectators / dugout are ignored via a green-pitch mask.

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
# Follow the ball: mark only the carrier + passes (default)
python -m tactical_marker.cli match.mp4 -o marked.mp4

# Better ball/player detection (slower) — recommended for wide footage
python -m tactical_marker.cli match.mp4 -o marked.mp4 \
    --model yolov8s.pt --imgsz 1280

# Ring every player instead, coloured by team, first 15 seconds
python -m tactical_marker.cli match.mp4 -o marked.mp4 \
    --mode all-players --color-by-team --max-seconds 15
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

- **ball-follow depends entirely on ball detection.** On zoomed / broadcast
  footage the ball is detected well enough (gaps are interpolated); on wide,
  low-res or amateur single-camera clips the ball may be too small and the mode
  can't follow it. Use `--model yolov8s.pt --imgsz 1280` to improve it, or fall
  back to `--mode all-players`. If the ball is never seen, ball-follow errors
  out with a clear message rather than guessing.
- Possession and pass detection are heuristic (nearest player to the ball, with
  smoothing). Quick one-twos or crowded areas can produce a wrong carrier for a
  few frames.
- Detection is a **nano** model by default for speed; larger models
  (`yolov8s/m`) + a bigger `--imgsz` detect more, but run slower.
- Processing is CPU-bound (a few seconds per second of footage). A GPU, if
  present, is used automatically by ultralytics.
