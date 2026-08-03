"""Command-line interface for the promo builder.

Examples
--------
Minimal (just style the clip, placeholder branding)::

    python -m video_promo.cli clip.mp4 -o promo.mp4

With captions and branding::

    python -m video_promo.cli clip.mp4 -o promo.mp4 \
        --caption "TURN ANALYSIS INTO A" \
        --caption "TACTICAL DEMONSTRATION" \
        --brand "MY BRAND" --outro-title "MYAPP" \
        --cta "START FREE" --music track.mp3

Captions from a file (one line per caption)::

    python -m video_promo.cli clip.mp4 -o promo.mp4 --captions-file lines.txt
"""
from __future__ import annotations

import argparse
import sys

from .config import BuildConfig, BrandConfig
from .builder import build


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="video_promo",
        description="Turn a raw clip into a styled vertical promo video.",
    )
    p.add_argument("input", help="path to the raw video clip")
    p.add_argument("-o", "--output", default="promo_out.mp4",
                   help="output mp4 path (default: promo_out.mp4)")

    p.add_argument("--caption", action="append", default=[],
                   help="a caption line (repeat for multiple)")
    p.add_argument("--captions-file",
                   help="text file with one caption per line")

    p.add_argument("--brand", help="brand name shown in the bottom band")
    p.add_argument("--logo", help="path to a transparent PNG logo")
    p.add_argument("--outro-title", help="big text on the closing card")
    p.add_argument("--outro-subtitle", help="small text under the title")
    p.add_argument("--cta", help="call-to-action button text")
    p.add_argument("--cta-subtext", help="text under the CTA button")
    p.add_argument("--outro-seconds", type=float, default=3.0,
                   help="length of the closing card (default: 3)")

    p.add_argument("--music", help="background music file")
    p.add_argument("--music-volume", type=float, default=0.25,
                   help="music volume 0..1 relative to original (default: 0.25)")
    p.add_argument("--no-original-audio", action="store_true",
                   help="drop the clip's own audio")

    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    captions = list(args.caption)
    if args.captions_file:
        with open(args.captions_file, encoding="utf-8") as fh:
            captions += [ln.strip() for ln in fh if ln.strip()]

    brand = BrandConfig()
    if args.brand:
        brand.brand_name = args.brand
    if args.logo:
        brand.logo_path = args.logo
    if args.outro_title:
        brand.outro_title = args.outro_title
    if args.outro_subtitle:
        brand.outro_subtitle = args.outro_subtitle
    if args.cta:
        brand.cta_text = args.cta
    if args.cta_subtext:
        brand.cta_subtext = args.cta_subtext

    cfg = BuildConfig(
        input_path=args.input,
        output_path=args.output,
        captions=captions,
        outro_seconds=args.outro_seconds,
        music_path=args.music,
        music_volume=args.music_volume,
        keep_original_audio=not args.no_original_audio,
        brand=brand,
    )

    try:
        build(cfg, progress=lambda m: print(f"[promo] {m}", flush=True))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
