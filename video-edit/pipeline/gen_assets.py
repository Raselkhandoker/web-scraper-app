#!/usr/bin/env python3
"""
Generate an original motion-graphics asset set for the transformative football reel.

Design language (deliberately different from the reference "FUTEBRO" template):
  - Palette: charcoal ink (#0E1116) + electric cyan (#12E7FF) + hot magenta accent (#FF2E7E)
    + off-white (#F4F8FF). Reference used green/yellow arrows -> we use cyan pills + rings.
  - Typography: heavy condensed-feel sans (DejaVu Sans Bold, letter-spaced + slanted).
  - Elements: rounded pills, thin tracking rings, soft radial spotlight, kinetic title,
    stylised "BOOKED" card, "GOAL" burst, branded end card. All transparent PNGs.
Everything is rendered oversized with soft drop-shadows for a clean broadcast look.
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

W, H = 1080, 1920
OUT = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(OUT, exist_ok=True)

# ---- palette ---------------------------------------------------------------
INK     = (14, 17, 22)
CYAN    = (18, 231, 255)
MAGENTA = (255, 46, 126)
WHITE   = (244, 248, 255)
AMBER   = (255, 199, 0)
BLACK   = (0, 0, 0)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH_BLK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def font(sz):
    return ImageFont.truetype(FONT_PATH, sz)

def new():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))

def tracking_text(draw, xy, text, fnt, fill, track=0, anchor_center=False):
    """Draw text with manual letter-spacing. Returns total width."""
    x, y = xy
    widths = []
    for ch in text:
        bb = draw.textbbox((0, 0), ch, font=fnt)
        widths.append(bb[2] - bb[0])
    total = sum(widths) + track * (len(text) - 1) if text else 0
    if anchor_center:
        x = x - total / 2
    cx = x
    for ch, w in zip(text, widths):
        draw.text((cx, y), ch, font=fnt, fill=fill)
        cx += w + track
    return total

def shadow_layer(draw_fn, blur=18, offset=(0, 10), alpha=150):
    """Render draw_fn onto a scratch layer, return a blurred dark shadow copy."""
    scratch = new()
    d = ImageDraw.Draw(scratch)
    draw_fn(d, scratch)
    a = scratch.split()[3].point(lambda p: min(p, alpha))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh.putalpha(a)
    sh = Image.composite(Image.new("RGBA", (W, H), (0, 0, 0, 255)), sh, a)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    sh = ImageChops.offset(sh, offset[0], offset[1])
    return sh

def rounded(draw, box, r, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)

def save(img, name):
    p = os.path.join(OUT, name)
    img.save(p)
    print("wrote", name, img.size)

# ---------------------------------------------------------------------------
# 1. TITLE CARD  (segment A) - kinetic left-aligned block
# ---------------------------------------------------------------------------
def make_title():
    img = new()
    d = ImageDraw.Draw(img)
    lx = 96
    y = 1180
    # accent bar
    d.rounded_rectangle([lx, y - 20, lx + 150, y + 6], radius=8, fill=CYAN)
    # kicker
    tracking_text(d, (lx, y + 30), "LA LIGA · MATCHDAY", font(38), CYAN, track=8)
    # main title (two lines)
    big = font(150)
    d.text((lx - 4, y + 92), "RAPHINHA", font=big, fill=WHITE)
    # magenta underline sweep
    d.rounded_rectangle([lx, y + 300, lx + 760, y + 322], radius=10, fill=MAGENTA)
    # subtitle
    tracking_text(d, (lx, y + 352), "THE SET-PIECE KING", font(52), WHITE, track=4)
    # drop shadow
    base = new()
    sh = base.copy()
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    alpha = img.split()[3].filter(ImageFilter.GaussianBlur(16)).point(lambda p: int(p * 0.6))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    dark.putalpha(alpha)
    dark = ImageChops.offset(dark, 0, 12)
    out = Image.alpha_composite(dark, img)
    save(out, "title.png")

# ---------------------------------------------------------------------------
# 2. LOGO / brand bug  (all segments) - "PITCH IQ"
# ---------------------------------------------------------------------------
def make_logo():
    img = new()
    d = ImageDraw.Draw(img)
    # small pill top-left region rendered near origin; we crop to a bug
    pad = 30
    fnt = font(46)
    t1, t2 = "PITCH", "IQ"
    w1 = d.textlength(t1, font=fnt)
    w2 = d.textlength(t2, font=fnt)
    gap = 14
    total = w1 + gap + 78
    x0, y0 = 40, 40
    # ink pill
    d.rounded_rectangle([x0, y0, x0 + total + pad*2, y0 + 78], radius=39, fill=(14, 17, 22, 235))
    d.rounded_rectangle([x0, y0, x0 + 8, y0 + 78], radius=4, fill=CYAN)
    tx = x0 + pad
    d.text((tx, y0 + 15), t1, font=fnt, fill=WHITE)
    # cyan chip for IQ
    chx = tx + w1 + gap
    d.rounded_rectangle([chx, y0 + 16, chx + w2 + 24, y0 + 62], radius=12, fill=CYAN)
    d.text((chx + 12, y0 + 15), t2, font=fnt, fill=INK)
    save(img.crop((0, 0, int(x0 + total + pad*2 + 20), 170)).resize((int((x0 + total + pad*2 + 20)), 170)), "logo.png")

# ---------------------------------------------------------------------------
# 3. LOWER-THIRD name pill  (segment B) - "RAPHINHA  #11"
# ---------------------------------------------------------------------------
def make_lower_third():
    img = new()
    d = ImageDraw.Draw(img)
    x0, y0 = 96, 1560
    fnt = font(64)
    num = font(48)
    name = "RAPHINHA"
    tw = d.textlength(name, font=fnt)
    h = 108
    total_w = tw + 250
    # shadow
    sh = new()
    ds = ImageDraw.Draw(sh)
    ds.rounded_rectangle([x0, y0, x0 + total_w, y0 + h], radius=h//2, fill=(0,0,0,180))
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    img = Image.alpha_composite(img, sh)
    d = ImageDraw.Draw(img)
    # main pill
    d.rounded_rectangle([x0, y0, x0 + total_w, y0 + h], radius=h//2, fill=(14,17,22,240))
    # cyan accent number chip
    d.rounded_rectangle([x0 + 12, y0 + 12, x0 + 12 + 120, y0 + h - 12], radius=(h-24)//2, fill=CYAN)
    d.text((x0 + 40, y0 + 26), "11", font=num, fill=INK)
    d.text((x0 + 160, y0 + 20), name, font=fnt, fill=WHITE)
    # tiny role
    tracking_text(d, (x0 + 162, y0 - 44), "LEFT WING · FC BARCELONA", font(30), CYAN, track=4)
    save(img, "lower_third.png")

# ---------------------------------------------------------------------------
# 4. KICKER tag "SET PIECE" (segment B, top)
# ---------------------------------------------------------------------------
def make_kicker():
    img = new()
    d = ImageDraw.Draw(img)
    x0, y0 = 96, 300
    fnt = font(44)
    txt = "SET PIECE"
    w = tracking_text(d, (0, 0), txt, fnt, (0,0,0,0), track=10)  # measure
    d.rounded_rectangle([x0, y0, x0 + w + 60, y0 + 78], radius=16, fill=MAGENTA)
    tracking_text(d, (x0 + 30, y0 + 16), txt, fnt, WHITE, track=10)
    save(img, "kicker.png")

# ---------------------------------------------------------------------------
# 5. SCORE chip  (segment C) - "BAR 3 - 3 CEL"
# ---------------------------------------------------------------------------
def make_score():
    img = new()
    d = ImageDraw.Draw(img)
    cx = W // 2
    y0 = 300
    fnt = font(52)
    small = font(34)
    box_w, box_h = 520, 96
    x0 = cx - box_w // 2
    # shadow
    sh = new(); ds = ImageDraw.Draw(sh)
    ds.rounded_rectangle([x0, y0, x0+box_w, y0+box_h], radius=18, fill=(0,0,0,170))
    sh = sh.filter(ImageFilter.GaussianBlur(20)); img = Image.alpha_composite(img, sh); d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0, x0+box_w, y0+box_h], radius=18, fill=(14,17,22,240))
    # team blocks
    d.rounded_rectangle([x0, y0, x0+150, y0+box_h], radius=18, fill=(0x99,0x1e,0x2b,255))  # barca-ish claret
    d.rounded_rectangle([x0+box_w-150, y0, x0+box_w, y0+box_h], radius=18, fill=(0x6c,0xb4,0xe4,255))  # celta sky
    tracking_text(d, (x0+35, y0+28), "BAR", small, WHITE, track=4)
    tracking_text(d, (x0+box_w-118, y0+28), "CEL", small, INK, track=4)
    # score
    d.text((cx-70, y0+18), "3", font=fnt, fill=WHITE)
    d.text((cx-14, y0+22), "-", font=small, fill=CYAN)
    d.text((cx+38, y0+18), "3", font=fnt, fill=WHITE)
    save(img, "score.png")

# ---------------------------------------------------------------------------
# 6. SPOTLIGHT ring  (segment C) - transparent radial + cyan ring, centred tile
#    (we overlay this and animate its x/y in ffmpeg)
# ---------------------------------------------------------------------------
def make_spotlight():
    size = 520
    img = Image.new("RGBA", (size, size), (0,0,0,0))
    d = ImageDraw.Draw(img)
    c = size // 2
    # bright inner clear, ring
    for i, (rr, a, col) in enumerate([(250, 255, CYAN), (238, 120, CYAN)]):
        d.ellipse([c-rr, c-rr, c+rr, c+rr], outline=col + (a,), width=8)
    # ticks
    import math
    for ang in range(0, 360, 30):
        a = math.radians(ang)
        r1, r2 = 250, 272
        d.line([c+math.cos(a)*r1, c+math.sin(a)*r1, c+math.cos(a)*r2, c+math.sin(a)*r2], fill=CYAN+(200,), width=6)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    save(img, "spotlight.png")

def make_vignette_darken():
    # full-frame soft darken with a clear hole in centre (used under spotlight)
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    d.rectangle([0,0,W,H], fill=(6,8,12,150))
    save(img, "darken.png")

# ---------------------------------------------------------------------------
# 7. BOOKED card graphic (segment D)
# ---------------------------------------------------------------------------
def make_booked():
    img = new()
    d = ImageDraw.Draw(img)
    cx = W//2
    # tilted amber card
    card = Image.new("RGBA", (240, 340), (0,0,0,0))
    dc = ImageDraw.Draw(card)
    dc.rounded_rectangle([0,0,240,340], radius=22, fill=AMBER)
    dc.rounded_rectangle([16,16,224,324], radius=14, outline=(180,140,0,255), width=6)
    card = card.rotate(-12, expand=True, resample=Image.BICUBIC)
    # shadow
    sh = Image.new("RGBA", (W,H), (0,0,0,0))
    sh.paste((0,0,0,150), (cx-160, 640), card.split()[3])
    sh = sh.filter(ImageFilter.GaussianBlur(24))
    img = Image.alpha_composite(img, sh)
    img.paste(card, (cx-150, 620), card)
    d = ImageDraw.Draw(img)
    # text banner
    fnt = font(96)
    txt = "BOOKED"
    w = tracking_text(d, (0,0), txt, fnt, (0,0,0,0), track=8)
    by = 1040
    d.rounded_rectangle([cx-w//2-40, by, cx+w//2+40, by+140], radius=18, fill=INK)
    tracking_text(d, (cx, by+22), txt, fnt, AMBER, track=8, anchor_center=True)
    save(img, "booked.png")

# ---------------------------------------------------------------------------
# 8. GOAL burst (segment E)
# ---------------------------------------------------------------------------
def make_goal():
    img = new()
    d = ImageDraw.Draw(img)
    cx = W//2; cy = 940
    fnt = font(220)
    txt = "GOAL"
    # magenta glow behind
    glow = new(); dg = ImageDraw.Draw(glow)
    tracking_text(dg, (cx, cy), txt, fnt, MAGENTA+(255,), track=6, anchor_center=True)
    glow = glow.filter(ImageFilter.GaussianBlur(30))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    tracking_text(d, (cx, cy), txt, fnt, WHITE, track=6, anchor_center=True)
    # exclaim bar under
    d.rounded_rectangle([cx-180, cy+250, cx+180, cy+284], radius=12, fill=CYAN)
    tracking_text(d, (cx, cy+300), "RAPHINHA STRIKES", font(48), WHITE, track=6, anchor_center=True)
    save(img, "goal.png")

# ---------------------------------------------------------------------------
# 9. END CARD (segment F)
# ---------------------------------------------------------------------------
def make_endcard():
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    # dim scrim
    d.rectangle([0,0,W,H], fill=(8,10,14,180))
    cx = W//2
    # big logo
    fnt = font(120); chip = font(120)
    t1 = "PITCH"
    w1 = d.textlength(t1, font=fnt)
    total = w1 + 40 + 240
    x = cx - total//2
    y = 780
    d.text((x, y), t1, font=fnt, fill=WHITE)
    chx = x + w1 + 40
    d.rounded_rectangle([chx, y+6, chx+240, y+140], radius=24, fill=CYAN)
    d.text((chx+40, y), "IQ", font=chip, fill=INK)
    # accent line
    d.rounded_rectangle([cx-260, y+190, cx+260, y+212], radius=10, fill=MAGENTA)
    # CTA
    tracking_text(d, (cx, y+250), "FOLLOW FOR MORE BREAKDOWNS", font(48), WHITE, track=4, anchor_center=True)
    # handle pill
    hy = y + 360
    txt = "@PITCHIQ"
    w = tracking_text(d, (0,0), txt, font(52), (0,0,0,0), track=6)
    d.rounded_rectangle([cx-w//2-40, hy, cx+w//2+40, hy+96], radius=48, fill=CYAN)
    tracking_text(d, (cx, hy+20), txt, font(52), INK, track=6, anchor_center=True)
    save(img, "endcard.png")

if __name__ == "__main__":
    make_title()
    make_logo()
    make_lower_third()
    make_kicker()
    make_score()
    make_spotlight()
    make_vignette_darken()
    make_booked()
    make_goal()
    make_endcard()
    print("all assets done")
