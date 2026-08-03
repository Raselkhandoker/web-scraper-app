"""
smoke_test.py
-------------
Quick offline check that the video-to-animation engine works end to end.
It needs NO internet and NO API token -- it only exercises the free local
engine (styles, trimming, logo/text removal, and keep/mute audio).

Run it with:

    py -3.11 smoke_test.py        (Windows)
    python3 smoke_test.py         (Mac / Linux)

A row of "OK" lines and a final "ALL CHECKS PASSED" means you're good.
"""

import os
import sys
import tempfile
import subprocess

import imageio_ffmpeg

from video_animator import (
    VideoAnimator, STYLES, REMOVE_METHODS,
    parse_cut_segments, keep_ranges_from_cuts,
)


def make_test_video(path: str, seconds: int = 4) -> None:
    """Create a small test clip (with audio) using the bundled ffmpeg."""
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ff, "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=25",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="anim_smoke_")
    src = os.path.join(tmp, "src.mp4")
    print("Creating a test video...")
    make_test_video(src)

    anim = VideoAnimator()

    # 1. Parsers
    assert parse_cut_segments("0-1, 2-3") == [(0.0, 1.0), (2.0, 3.0)]
    assert keep_ranges_from_cuts([(1, 2)], 4) == [(0.0, 1.0), (2.0, 4.0)]
    print("OK  parsers")

    # 2. Every style renders
    for style in STYLES:
        out = os.path.join(tmp, f"{style}.mp4")
        st = anim.process(src, out, style=style, audio_mode="mute",
                          max_width=240)
        assert os.path.exists(out) and os.path.getsize(out) > 0
        print(f"OK  style {style:12s} frames={st['frames_written']} "
              f"hold={st['frame_hold']}")

    # 3. Trim + keep audio
    out = os.path.join(tmp, "trim.mp4")
    st = anim.process(src, out, style="cartoon", cut_segments=[(1.0, 2.0)],
                      audio_mode="keep")
    assert st["has_audio"], "expected audio to be kept"
    assert st["frames_written"] == 75, st["frames_written"]  # 4s-1s @25fps
    print("OK  trim + keep audio")

    # 4. Logo/text removal, every method
    for m in REMOVE_METHODS:
        out = os.path.join(tmp, f"rm_{m}.mp4")
        anim.process(src, out, style="cartoon", audio_mode="mute",
                     remove_regions=[(0.0, 0.0, 0.4, 0.15)],
                     remove_method=m, max_width=240)
        assert os.path.exists(out) and os.path.getsize(out) > 0
        print(f"OK  remove method {m}")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print("FAILED:", e)
        sys.exit(1)
