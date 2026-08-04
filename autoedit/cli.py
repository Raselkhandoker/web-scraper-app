"""Command-line interface for the auto-editor.

Example::

    python -m autoedit input.mp4 -o out/
    python -m autoedit input.mp4 --no-highlights --model small
"""
from __future__ import annotations

import argparse
import logging
import sys

from .pipeline import Config, process


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="autoedit",
        description="Upload a video, get an auto-edited MP4: silence removed, "
                    "captions burned in, and short highlight clips.",
    )
    p.add_argument("input", help="Path to the source video file.")
    p.add_argument("-o", "--output-dir", default="autoedit_out",
                   help="Directory for the outputs (default: autoedit_out).")

    p.add_argument("--no-silence", dest="remove_silence", action="store_false",
                   help="Do not remove silent gaps.")
    p.add_argument("--no-captions", dest="captions", action="store_false",
                   help="Do not burn in captions.")
    p.add_argument("--no-highlights", dest="highlights", action="store_false",
                   help="Do not generate highlight clips.")

    p.add_argument("--highlight-count", type=int, default=3,
                   help="How many highlight clips to make (default: 3).")
    p.add_argument("--max-gap", type=float, default=0.4,
                   help="Cut silences longer than this many seconds (default: 0.4).")
    p.add_argument("--model", default="base",
                   help="faster-whisper model size: tiny/base/small/medium/large-v3 "
                        "(default: base).")
    p.add_argument("--anthropic-model", default=Config.anthropic_model,
                   help="Claude model for highlight selection.")
    p.add_argument("--language", default=None,
                   help="Force transcript language (e.g. 'en'); default auto-detect.")
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging.")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config = Config(
        remove_silence=args.remove_silence,
        captions=args.captions,
        highlights=args.highlights,
        highlight_count=args.highlight_count,
        max_gap=args.max_gap,
        model_size=args.model,
        anthropic_model=args.anthropic_model,
        language=args.language,
    )

    try:
        result = process(args.input, args.output_dir, config)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("\n=== Auto-edit complete ===")
    print(f"Original : {result.original_duration:.1f}s")
    print(f"Edited   : {result.edited_duration:.1f}s "
          f"(removed {result.seconds_removed:.1f}s)")
    if result.main_output:
        print(f"Output   : {result.main_output}")
    for clip in result.clips:
        print(f"Clip     : {clip}")
    for note in result.notes:
        print(f"note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
