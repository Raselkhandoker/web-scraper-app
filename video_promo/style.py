"""Pillow asset generation for the promo template.

All the static visual pieces — the branded background, the rounded-corner mask
for the footage panel, the caption boxes, and the outro card — are drawn here
and written to PNGs that :mod:`video_promo.builder` feeds into ffmpeg.
"""
from __future__ import annotations

import os
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

from . import config as C


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> Tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


# --------------------------------------------------------------------------- #
# Decorative shapes
# --------------------------------------------------------------------------- #
def _draw_x(d: ImageDraw.ImageDraw, cx, cy, s, w, col):
    d.line([(cx - s, cy - s), (cx + s, cy + s)], fill=col, width=w)
    d.line([(cx - s, cy + s), (cx + s, cy - s)], fill=col, width=w)


def _draw_chevron(d: ImageDraw.ImageDraw, cx, cy, s, w, col):
    for off in (0, s):
        d.line([(cx - s, cy - s + off), (cx, cy + off)], fill=col, width=w)
        d.line([(cx, cy + off), (cx + s, cy - s + off)], fill=col, width=w)


# --------------------------------------------------------------------------- #
# Background
# --------------------------------------------------------------------------- #
def make_background(brand: C.BrandConfig, out_path: str) -> str:
    """The branded green background with scattered shapes and a logo band."""
    W, H = C.WIDTH, C.HEIGHT
    img = Image.new("RGB", (W, H), brand.lime)
    d = ImageDraw.Draw(img)

    # subtle vertical gradient
    for y in range(H):
        t = y / H
        r = int(brand.lime[0] * (1 - t * 0.12))
        g = int(brand.lime[1] * (1 - t * 0.08))
        b = int(brand.lime[2] * (1 - t * 0.05))
        d.line([(0, y), (W, y)], fill=(r, g, b))

    dk = brand.lime_dark
    shapes = [
        ("x", 70, 90, 34), ("chev", 72, 300, 30), ("x", 60, 560, 26),
        ("rr", 130, 430, 40),
        ("x", 1010, 120, 34), ("chev", 1012, 360, 30), ("x", 1020, 620, 26),
        ("rr", 950, 210, 40),
        ("chev", 80, 1180, 28), ("x", 1010, 1240, 30),
    ]
    for kind, x, y, s in shapes:
        if kind == "x":
            _draw_x(d, x, y, s, 10, dk)
        elif kind == "chev":
            _draw_chevron(d, x, y, s, 10, dk)
        elif kind == "rr":
            d.rounded_rectangle([x - s, y - s, x + s, y + s], radius=14, fill=dk)

    # bottom logo band (slight diagonal)
    band = Image.new("RGBA", (W, C.BAND_H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    bd.polygon([(0, 60), (W, 0), (W, C.BAND_H), (0, C.BAND_H)],
               fill=tuple(brand.band_color) + (255,))
    for x in (120, 200, 900, 980):
        _draw_chevron(bd, x, C.BAND_H - 60, 20, 8, (255, 255, 255))
    img.paste(band, (0, H - C.BAND_H), band)

    # brand text / logo in the band
    band_center_y = H - C.BAND_H // 2 + 20
    if brand.logo_path and os.path.exists(brand.logo_path):
        logo = Image.open(brand.logo_path).convert("RGBA")
        target_h = 90
        scale = target_h / logo.height
        logo = logo.resize((int(logo.width * scale), target_h))
        img.paste(logo, ((W - logo.width) // 2, band_center_y - target_h // 2), logo)
    else:
        f = _font(brand.font_bold, 58)
        tw, th = _text_size(d, brand.brand_name, f)
        d.text(((W - tw) // 2, band_center_y - th // 2 - 6),
               brand.brand_name, font=f, fill=(255, 255, 255))

    img.save(out_path)
    return out_path


# --------------------------------------------------------------------------- #
# Rounded-corner mask for the footage panel
# --------------------------------------------------------------------------- #
def make_panel_mask(w: int, h: int, radius: int, out_path: str) -> str:
    """White rounded rectangle on black — used as an alpha mask in ffmpeg."""
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    mask.convert("RGB").save(out_path)
    return out_path


# --------------------------------------------------------------------------- #
# Caption boxes
# --------------------------------------------------------------------------- #
def make_caption(text: str, brand: C.BrandConfig, out_path: str,
                 max_width: int = 940) -> Tuple[str, int, int]:
    """Render one caption as a transparent PNG (dark rounded box + bold text).

    Returns (path, width, height).
    """
    text = text.upper()
    pad_x, pad_y, line_gap = 34, 20, 8
    font_size = 60
    f = _font(brand.font_bold, font_size)

    tmp = Image.new("RGBA", (10, 10))
    td = ImageDraw.Draw(tmp)

    # wrap words to fit max_width
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if _text_size(td, trial, f)[0] + 2 * pad_x <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)

    line_sizes = [_text_size(td, ln, f) for ln in lines]
    box_w = max(w for w, _ in line_sizes) + 2 * pad_x
    line_h = max(h for _, h in line_sizes) + line_gap
    box_h = line_h * len(lines) + 2 * pad_y

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, box_w - 1, box_h - 1], radius=22,
                        fill=tuple(brand.caption_bg) + (235,))
    y = pad_y
    for ln, (lw, lh) in zip(lines, line_sizes):
        d.text(((box_w - lw) // 2, y), ln, font=f, fill=tuple(brand.caption_fg))
        y += line_h

    img.save(out_path)
    return out_path, box_w, box_h


# --------------------------------------------------------------------------- #
# Outro card
# --------------------------------------------------------------------------- #
def make_outro(brand: C.BrandConfig, out_path: str) -> str:
    """Full-screen closing card: title, subtitle, and a CTA button."""
    W, H = C.WIDTH, C.HEIGHT
    img = Image.new("RGB", (W, H), brand.band_color)
    d = ImageDraw.Draw(img)

    # diagonal gradient from band colour to lime
    for y in range(H):
        t = y / H
        r = int(brand.band_color[0] * (1 - t) + brand.lime[0] * t)
        g = int(brand.band_color[1] * (1 - t) + brand.lime[1] * t)
        b = int(brand.band_color[2] * (1 - t) + brand.lime[2] * t)
        d.line([(0, y), (W, y)], fill=(r, g, b))

    cy = 520
    # logo or title
    if brand.logo_path and os.path.exists(brand.logo_path):
        logo = Image.open(brand.logo_path).convert("RGBA")
        target_h = 200
        scale = target_h / logo.height
        logo = logo.resize((int(logo.width * scale), target_h))
        img.paste(logo, ((W - logo.width) // 2, cy - target_h // 2), logo)
        cy += target_h
    else:
        f_title = _font(brand.font_bold, 120)
        tw, th = _text_size(d, brand.outro_title, f_title)
        d.text(((W - tw) // 2, cy), brand.outro_title, font=f_title,
               fill=(255, 255, 255))
        cy += th + 40

    f_sub = _font(brand.font_regular, 46)
    tw, th = _text_size(d, brand.outro_subtitle, f_sub)
    d.text(((W - tw) // 2, cy), brand.outro_subtitle, font=f_sub,
           fill=(235, 235, 235))

    # CTA button near the bottom
    f_cta = _font(brand.font_bold, 52)
    cta = brand.cta_text.upper()
    tw, th = _text_size(d, cta, f_cta)
    btn_w, btn_h = tw + 120, th + 70
    bx, by = (W - btn_w) // 2, 1420
    d.rounded_rectangle([bx, by, bx + btn_w, by + btn_h], radius=btn_h // 2,
                        fill=tuple(brand.accent))
    # dark text on lime button for contrast
    d.text((bx + (btn_w - tw) // 2, by + (btn_h - th) // 2 - 6), cta,
           font=f_cta, fill=(20, 30, 12))

    f_cs = _font(brand.font_regular, 40)
    tw2, th2 = _text_size(d, brand.cta_subtext, f_cs)
    d.text(((W - tw2) // 2, by + btn_h + 26), brand.cta_subtext, font=f_cs,
           fill=(240, 240, 240))

    img.save(out_path)
    return out_path
