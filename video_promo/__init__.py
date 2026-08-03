"""video_promo — turn a raw clip into a styled vertical promo video.

Public API::

    from video_promo import BuildConfig, BrandConfig, build
    build(BuildConfig(input_path="clip.mp4", output_path="promo.mp4",
                      captions=["LINE ONE", "LINE TWO"]))
"""
from .config import BuildConfig, BrandConfig
from .builder import build

__all__ = ["BuildConfig", "BrandConfig", "build"]
