# autoedit — automatic video editor

Upload a video, get a finished edited MP4 back. It:

1. **Removes dead air** — cuts silent gaps for a tight, jump-cut feel.
2. **Burns in captions** — word-by-word animated subtitles (the TikTok/Reels look).
3. **Cuts highlight clips** — picks the best moments and exports them as vertical (9:16) shorts.

It does the editing itself with **ffmpeg** — it does *not* drive Adobe Premiere or
CapCut. (Neither can be automated headlessly from an upload: CapCut has no public
API, and Premiere scripting requires the app open with a plugin.) If you want the
cuts inside Premiere instead of a finished file, that's a separate "export an XML"
feature — ask and it can be added.

## How it works

```
video ─▶ extract audio ─▶ transcribe (faster-whisper, word timestamps)
            │                        │
            ▼                        ▼
     silence detection        caption timing        highlight selection
     (words or ffmpeg)        (word-by-word ASS)     (Claude, or heuristic)
            │                        │                        │
            └────────────▶ ffmpeg render ◀───────────────────┘
                                   │
                     edited.mp4  +  highlight_1.mp4 …
```

## Install

```bash
pip install -r autoedit/requirements.txt
# ffmpeg: install a full build (recommended), e.g.  brew install ffmpeg
# or rely on the bundled imageio-ffmpeg fallback (installed above).
```

For Claude-picked highlights (optional), set an API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Without it, highlights fall back to a simple evenly-spaced heuristic.

## Usage

```bash
# everything on: silence cut + captions + 3 highlight clips
python -m autoedit myvideo.mp4 -o out/

# just tighten and caption, no shorts
python -m autoedit myvideo.mp4 --no-highlights

# faster/lower quality transcript, cut pauses longer than 0.3s, 5 clips
python -m autoedit myvideo.mp4 --model tiny --max-gap 0.3 --highlight-count 5
```

Outputs land in the output directory:

- `<name>_edited.mp4` — the main edit (silence removed, captions burned)
- `<name>_highlight_1.mp4`, `_2.mp4`, … — vertical highlight clips

### Options

| Flag | Default | Meaning |
|------|---------|---------|
| `-o, --output-dir` | `autoedit_out` | Where outputs are written |
| `--no-silence` | off | Keep all pauses |
| `--no-captions` | off | Skip burned captions |
| `--no-highlights` | off | Skip highlight clips |
| `--highlight-count N` | 3 | Number of highlight clips |
| `--max-gap SECONDS` | 0.4 | Cut silences longer than this |
| `--model SIZE` | base | Whisper size: tiny/base/small/medium/large-v3 |
| `--anthropic-model` | claude-opus-4-8 | Claude model for highlight picks |
| `--language` | auto | Force transcript language, e.g. `en` |

## Use from Python

```python
from autoedit import process, Config

result = process("myvideo.mp4", "out/", Config(highlight_count=4))
print(result.main_output, result.clips, f"removed {result.seconds_removed:.1f}s")
```

## Notes & limits

- **First run downloads the Whisper model** from HuggingFace (cached after).
  If transcription is unavailable, silence removal still works via ffmpeg audio
  detection, and captions are skipped.
- The main edit keeps the source aspect ratio; only highlight clips are reframed
  to vertical 9:16 (center-crop).
- Very long videos produce many keep-segments; the single-pass `select` filter
  handles this, but expect longer render times.

## Tests

```bash
python -m pytest tests/test_autoedit.py -q
```
