"""Configuration for the promo video builder.

Everything that controls the *look* of the output lives here so the tool can be
re-themed without touching the rendering code. Values can be overridden per-run
from the CLI or the web form.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional


# Output canvas (vertical 9:16, the short-form / Reels / Shorts format).
WIDTH = 1080
HEIGHT = 1920
FPS = 30

# Where the uploaded footage sits inside the frame.
PANEL_W = 980
PANEL_X = (WIDTH - PANEL_W) // 2
PANEL_Y = 470            # top edge of the footage panel
PANEL_RADIUS = 40        # rounded-corner radius of the footage panel

# Caption block position (bottom-centre, above the logo band).
CAPTION_CENTER_Y = 1560

# Bottom logo band height.
BAND_H = 260


def _find_font(bold: bool = True) -> str:
    """Return the best available bold sans-serif on this machine."""
    import os
    candidates = [
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ] if bold else [
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # Last resort: any dejavu.
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


@dataclass
class BrandConfig:
    """Colours and text that brand the video. Swap these for your own."""

    # Colours (RGB).
    lime: tuple = (139, 199, 63)
    lime_dark: tuple = (122, 178, 52)
    band_color: tuple = (40, 120, 200)
    caption_bg: tuple = (18, 22, 28)          # dark box behind captions
    caption_fg: tuple = (255, 255, 255)
    accent: tuple = (139, 199, 63)            # CTA button colour

    # Text.
    brand_name: str = "YOUR BRAND"            # shown in the bottom logo band
    outro_title: str = "YOUR PRODUCT"         # big text on the outro card
    outro_subtitle: str = "By Your Company"   # small text under the title
    cta_text: str = "START WITH THE FREE VERSION"
    cta_subtext: str = "For PC and Mac"

    # Optional logo image (PNG with transparency) placed in the band / outro.
    logo_path: Optional[str] = None

    # Fonts (auto-detected; override if you install a nicer one).
    font_bold: str = field(default_factory=lambda: _find_font(True))
    font_regular: str = field(default_factory=lambda: _find_font(False))


@dataclass
class BuildConfig:
    """Per-run settings for a single build."""

    input_path: str
    output_path: str = "promo_out.mp4"
    captions: List[str] = field(default_factory=list)   # one line per caption
    outro_seconds: float = 3.0
    music_path: Optional[str] = None
    music_volume: float = 0.25                           # 0..1, relative to original audio
    keep_original_audio: bool = True
    brand: BrandConfig = field(default_factory=BrandConfig)

    def to_dict(self) -> dict:
        return asdict(self)
