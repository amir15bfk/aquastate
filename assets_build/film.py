"""
AquaState — 30 second hackathon film.

Renders 1920x1080 @ 30fps to an H.264 MP4 via ffmpeg.
Usage:
    python assets_build/film.py --stills 0.8,2.4,5.0,9.5,13.0,17.0,22.6,25.6,28.0
    python assets_build/film.py --render
"""

import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, DUR = 1920, 1080, 30, 30.0

# --- Palette: sampled from the app -----------------------------------------
BG = (8, 14, 16)
INK = (242, 248, 246)
MUTED = (146, 163, 157)
FAINT = (96, 113, 108)
ACCENT = (94, 234, 212)
ACCENT_INK = (12, 74, 68)
AMBER = (246, 190, 92)
CORAL = (255, 120, 100)
BLUE = (96, 172, 222)
OCHRE = (196, 150, 84)

# --- Timeline: cut on the voiceover ---------------------------------------
T_EARTH = (0.00, 1.49)
T_NILE = (1.49, 3.73)
T_DROUGHT_A = (3.73, 6.15)
T_DROUGHT_B = (6.15, 8.61)
T_FLOOD = (8.61, 11.44)
T_REVEAL = (11.44, 16.10)
T_WORLD = (16.10, 21.85)
T_COUNTRY = (21.85, 23.51)
T_DAM = (23.51, 26.42)
T_END = (26.42, 30.00)

# word-boundary hits from the voiceover
W_249 = 16.10
W_FOUR = 17.85
W_82394 = 19.03
W_YOUR_NUMBER = 22.70
W_QUESTION = 24.74
W_AQUASTATE = 26.42


# --- Fonts ----------------------------------------------------------------
FONT_FILES = {
    "sans": "instrument-sans-400.ttf",
    "sans500": "instrument-sans-500.ttf",
    "sans600": "instrument-sans-600.ttf",
    "mono": "jetbrains-mono-400.ttf",
    "mono500": "jetbrains-mono-500.ttf",
}
_font_cache = {}


def font(kind, size):
    key = (kind, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(
            os.path.join(HERE, "fonts", FONT_FILES[kind]), size
        )
    return _font_cache[key]


# --- Small helpers --------------------------------------------------------
def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out(p):
    p = clamp(p)
    return 1 - (1 - p) ** 3


def ease_in_out(p):
    p = clamp(p)
    return 3 * p * p - 2 * p * p * p


def smooth(p):
    p = clamp(p)
    return p * p * (3 - 2 * p)


def lerp(a, b, p):
    return a + (b - a) * p


def local(t, span):
    return clamp((t - span[0]) / (span[1] - span[0]))


def tint(img, mul=(1, 1, 1), add=(0, 0, 0), saturation=1.0, contrast=1.0):
    arr = np.asarray(img.convert("RGB")).astype(np.float32)
    if saturation != 1.0:
        lum = arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        arr = lum[..., None] + (arr - lum[..., None]) * saturation
    arr = (arr - 127.5) * contrast + 127.5
    arr = arr * np.array(mul, dtype=np.float32) + np.array(add, dtype=np.float32)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def fit_cover(img, w, h, focus=(0.5, 0.5), zoom=1.0):
    sw, sh = img.size
    scale = max(w / sw, h / sh) * zoom
    nw, nh = int(sw * scale + 0.5), int(sh * scale + 0.5)
    im = img.resize((nw, nh), Image.LANCZOS)
    x = int((nw - w) * clamp(focus[0]))
    y = int((nh - h) * clamp(focus[1]))
    return im.crop((x, y, x + w, y + h))


def load_rgb(name):
    return Image.open(os.path.join(HERE, "raw", name)).convert("RGB")


def load_shot(name):
    return Image.open(os.path.join(HERE, "shots", name)).convert("RGB")


# --- Text -----------------------------------------------------------------
def line_layer(segments, tracking=0.0):
    """segments: [(text, font, rgba), ...]. Returns an RGBA line."""
    widths = []
    for text, fnt, _ in segments:
        widths.append(fnt.getlength(text) + tracking * max(0, len(text) - 1))
    height = max(f.size for _, f, _ in segments) * 1.34
    layer = Image.new("RGBA", (max(8, int(sum(widths)) + 8), int(height) + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = 4.0
    for (text, fnt, fill), w in zip(segments, widths):
        if tracking == 0:
            d.text((x, 4), text, font=fnt, fill=fill, anchor="la")
        else:
            cx = x
            for ch in text:
                d.text((cx, 4), ch, font=fnt, fill=fill, anchor="la")
                cx += fnt.getlength(ch) + tracking
        x += w
    return layer


def block_layer(lines, line_height, tracking=0.0, align="left"):
    """lines: list of segment lists. Vertically stacked RGBA block."""
    layers = [line_layer(line, tracking) for line in lines]
    width = max(l.width for l in layers)
    height = int(line_height * (len(layers) - 1)) + max(l.height for l in layers)
    block = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for i, l in enumerate(layers):
        x = 0 if align == "left" else (width - l.width) // 2
        block.paste(l, (x, int(i * line_height)), l)
    return block


def simple(text, kind, size, fill, tracking=0.0):
    return line_layer([(text, font(kind, size), fill)], tracking)


def paste(base, layer, xy, alpha=1.0, dy=0):
    if alpha <= 0.001:
        return
    if alpha < 0.999:
        layer = layer.copy()
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer.putalpha(a)
    base.paste(layer, (int(xy[0]), int(xy[1] + dy)), layer)


def centered(base, layer, y, alpha=1.0, dy=0):
    paste(base, layer, ((W - layer.width) // 2, y), alpha, dy)


def kicker_layer(text, color=ACCENT):
    return simple(text, "mono", 14, color + (255,), tracking=2.4)


# --- Logo -----------------------------------------------------------------
def logo_mark(size, color=ACCENT, alpha=255):
    s = 4
    layer = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    stroke = max(2, int(size * s * 0.069))

    segs = [
        ((4.0, 21.0), (8.8, 21.0), (8.8, 17.0), (13.6, 17.0)),
        ((13.6, 17.0), (18.4, 17.0), (18.4, 21.0), (23.2, 21.0)),
        ((23.2, 21.0), (28.0, 21.0), (28.0, 17.0), (28.0, 17.0)),
    ]

    def cubic(p0, c1, c2, p1, n=26):
        out = []
        for i in range(n + 1):
            t = i / n
            u = 1 - t
            x = u**3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * p1[0]
            y = u**3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * p1[1]
            out.append((x, y))
        return out

    for yoff, op in ((0.0, 255), (-6.0, 145)):
        pts = []
        for p0, c1, c2, p1 in segs:
            shift = lambda p: (p[0], p[1] + yoff)
            seg = cubic(shift(p0), shift(c1), shift(c2), shift(p1))
            pts.extend(seg[1:] if pts else seg)
        pts = [(x * size * s / 32.0, y * size * s / 32.0) for x, y in pts]
        d.line(pts, fill=color + (int(op * alpha / 255),), width=stroke, joint="curve")
        r = stroke // 2
        for p in (pts[0], pts[-1]):
            d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=color + (int(op * alpha / 255),))
    return layer.resize((size, size), Image.LANCZOS)


# --- Gradients / texture --------------------------------------------------
def hgrad(stops, w=W, h=H):
    """stops: [(pos, (r,g,b,a)), ...] left → right."""
    arr = np.zeros((h, w, 4), dtype=np.float32)
    xs = np.arange(w) / max(1, w - 1)
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        m = (xs >= p0) & (xs <= p1)
        f = (xs[m] - p0) / max(1e-6, p1 - p0)
        for k in range(4):
            arr[:, m, k] = c0[k] + (c1[k] - c0[k]) * f
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def vgrad(stops, w=W, h=H):
    arr = np.zeros((h, w, 4), dtype=np.float32)
    ys = np.arange(h) / max(1, h - 1)
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        m = (ys >= p0) & (ys <= p1)
        f = (ys[m] - p0) / max(1e-6, p1 - p0)
        for k in range(4):
            arr[m, :, k] = c0[k] + (c1[k] - c0[k]) * f[:, None]
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def vignette_mask():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, H / 2
    r = np.sqrt(((xx - cx) / (W * 0.62)) ** 2 + ((yy - cy) / (H * 0.62)) ** 2)
    v = np.clip(1.0 - 0.32 * np.clip(r - 0.55, 0, None) ** 1.7, 0.60, 1.0)
    return v.astype(np.float32)


def grain_frames():
    rng = np.random.default_rng(7)
    out = []
    for _ in range(8):
        n = rng.normal(0, 1, (H, W, 1)).astype(np.float32)
        out.append(n)
    return out


# --- Assets ---------------------------------------------------------------
EARTH = None
NILE = None
MEAD = None
FLOOD = None
WORLD = None
COUNTRY = None
DAM = None
WORLD_GHOST = None
LEFT_DARK = None
RIGHT_DARK = None
WORLD_DARK = None
TOP_DARK = None
BOTTOM_DARK = None
VIGNETTE = None
GRAIN = None


def find_earth_disk(img):
    small = img.resize((900, 900))
    arr = np.asarray(small)
    mask = arr.max(axis=2) > 10
    ys, xs = np.where(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = max(x1 - x0, y1 - y0) / 2
    # back to source coordinates
    sx = img.width / 900
    box = (
        int((cx - r) * sx) - 6,
        int((cy - r) * sx) - 6,
        int((cx + r) * sx) + 6,
        int((cy + r) * sx) + 6,
    )
    return img.crop(box)


def prepare():
    global EARTH, NILE, MEAD, FLOOD, WORLD, COUNTRY, DAM, WORLD_GHOST
    global LEFT_DARK, BOTTOM_DARK, RIGHT_DARK, WORLD_DARK, TOP_DARK, VIGNETTE, GRAIN

    bm = find_earth_disk(load_rgb("blue_marble.jpg"))
    bm = bm.resize((1200, 1200), Image.LANCZOS)
    mask = Image.new("L", (1200, 1200), 0)
    ImageDraw.Draw(mask).ellipse((2, 2, 1197, 1197), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.4))
    bm.putalpha(mask)
    EARTH = bm

    nile = load_rgb("nile_iss.jpg").crop((3300, 2000, 7700, 4475))
    NILE = tint(nile, mul=(1.14, 1.09, 1.05), saturation=0.94, contrast=1.06)

    mead = load_rgb("lake_mead.jpg").crop((0, 80, 2000, 1205))
    MEAD = tint(mead, mul=(1.03, 0.97, 0.90), saturation=0.78, contrast=1.05)

    flood = load_rgb("flood_aerial.jpg").crop((0, 99, 1920, 1179))
    FLOOD = tint(flood, mul=(0.88, 0.97, 1.03), saturation=0.72, contrast=1.04)

    WORLD = load_shot("world_view.png")
    COUNTRY = load_shot("country_dz_view.png")
    DAM = load_shot("dam_beni_view.png")

    # ghost map behind the reveal
    ghost = WORLD.crop((700, 600, 3300, 2050)).resize((1920, 1075), Image.LANCZOS)
    ghost = ghost.filter(ImageFilter.GaussianBlur(7))
    WORLD_GHOST = tint(ghost, mul=(0.55, 0.85, 0.80), saturation=0.5, contrast=0.8)

    LEFT_DARK = hgrad([(0.0, (8, 14, 16, 252)), (0.42, (8, 14, 16, 228)), (0.72, (8, 14, 16, 70)), (1.0, (8, 14, 16, 0))])
    RIGHT_DARK = hgrad([(0.0, (8, 14, 16, 0)), (0.46, (8, 14, 16, 30)), (0.72, (8, 14, 16, 210)), (1.0, (8, 14, 16, 252))])
    WORLD_DARK = hgrad([(0.0, (8, 14, 16, 252)), (0.34, (8, 14, 16, 236)), (0.50, (8, 14, 16, 90)), (0.64, (8, 14, 16, 0)), (1.0, (8, 14, 16, 0))])
    TOP_DARK = vgrad([(0.0, (8, 14, 16, 238)), (0.10, (8, 14, 16, 0)), (1.0, (8, 14, 16, 0))])
    BOTTOM_DARK = vgrad([(0.0, (8, 14, 16, 0)), (0.55, (8, 14, 16, 15)), (0.78, (8, 14, 16, 175)), (1.0, (8, 14, 16, 240))])
    VIGNETTE = vignette_mask()
    GRAIN = grain_frames()


# --- Scene pieces ---------------------------------------------------------
def compose_bg(img, focus=(0.5, 0.5), zoom=1.0, dark=1.0):
    fr = fit_cover(img, W, H, focus, zoom).convert("RGBA")
    if dark < 1.0:
        black = Image.new("RGBA", (W, H), (0, 0, 0, int(255 * (1 - dark))))
        fr = Image.alpha_composite(fr, black)
    return fr


def overlay(frame, layer, alpha=1.0):
    if alpha < 1.0:
        layer = layer.copy()
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer.putalpha(a)
    return Image.alpha_composite(frame.convert("RGBA"), layer)


def scene_earth(t):
    p = local(t, T_EARTH)
    fr = Image.new("RGBA", (W, H), BG + (255,))
    # atmosphere glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = 1370, 540
    gd.ellipse((cx - 510, cy - 510, cx + 510, cy + 510), fill=(34, 122, 128, 34))
    glow = glow.filter(ImageFilter.GaussianBlur(46))
    fr = Image.alpha_composite(fr, glow)

    size = int(lerp(930, 912, ease_out(p)))
    earth = EARTH.resize((size, size), Image.LANCZOS)
    # feather atmosphere ring
    ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((cx - size // 2 - 5, cy - size // 2 - 5, cx + size // 2 + 5, cy + size // 2 + 5),
               outline=(70, 190, 210, 70), width=2)
    ring = ring.filter(ImageFilter.GaussianBlur(2))
    fr = Image.alpha_composite(fr, ring)
    fr.paste(earth, (cx - size // 2, cy - size // 2), earth)

    # text
    a = ease_out(clamp((t - 0.06) / 0.42))
    rise = int((1 - a) * 16)
    k = kicker_layer("01 — ORIGIN", MUTED)
    paste(fr, k, (120, 356), a, rise)
    line1 = simple("Water shaped", "sans500", 86, INK + (255,), tracking=-0.6)
    line2 = simple("the world.", "sans500", 86, INK + (255,), tracking=-0.6)
    paste(fr, line1, (120, 402), a, rise)
    paste(fr, line2, (120, 492), a, rise)
    a2 = ease_out(clamp((t - 0.5) / 0.5))
    cap = simple("H₂O · 71% OF EARTH'S SURFACE", "mono", 12, MUTED + (255,), tracking=2.0)
    paste(fr, cap, (122, 640), a2, 8)
    # rule
    rw = int(86 * ease_out(clamp((t - 0.15) / 0.55)))
    d = ImageDraw.Draw(fr)
    d.rectangle((120, 386, 120 + rw, 387), fill=ACCENT + (200,))
    # credit
    cr = simple("NASA · BLUE MARBLE", "mono", 10, FAINT + (255,), tracking=1.8)
    paste(fr, cr, (W - 120 - cr.width, H - 70), 0.8)
    return fr.convert("RGB")


def scene_nile(t):
    p = local(t, T_NILE)
    fr = compose_bg(NILE, focus=(lerp(0.38, 0.34, p), 0.47), zoom=lerp(1.02, 1.08, ease_in_out(p)), dark=1.0)
    fr = overlay(fr, RIGHT_DARK)
    fr = overlay(fr, BOTTOM_DARK, 0.45)
    a = ease_out(clamp((t - 1.55) / 0.45))
    rise = int((1 - a) * 16)
    paste(fr, kicker_layer("02 — CIVILIZATION", ACCENT), (1072, 596), a, rise)
    l1 = simple("Every civilization", "sans500", 60, INK + (255,), tracking=-0.4)
    l2 = simple("grew along a river.", "sans500", 60, INK + (255,), tracking=-0.4)
    paste(fr, l1, (1072, 646), a, rise)
    paste(fr, l2, (1072, 718), a, rise)
    a2 = ease_out(clamp((t - 2.15) / 0.55))
    body = simple("CITY LIGHTS ALONG THE NILE", "mono", 12, MUTED + (255,), tracking=2.0)
    paste(fr, body, (1074, 824), a2, 8)
    d = ImageDraw.Draw(fr)
    rw = int(86 * ease_out(clamp((t - 1.62) / 0.55)))
    d.rectangle((1072, 626, 1072 + rw, 627), fill=ACCENT + (210,))
    cr = simple("NASA / ESA · S. ADENOT · ISS", "mono", 10, FAINT + (255,), tracking=1.6)
    paste(fr, cr, (W - 120 - cr.width, H - 70), 0.85)
    return fr.convert("RGB")


def scene_drought(t):
    p = local(t, T_DROUGHT_A)
    fr = compose_bg(MEAD, focus=(0.54, 0.55), zoom=lerp(1.075, 1.005, ease_in_out(p)), dark=0.86)
    fr = overlay(fr, LEFT_DARK, 0.93)
    fr = overlay(fr, BOTTOM_DARK, 0.7)
    a = ease_out(clamp((t - 3.79) / 0.45))
    rise = int((1 - a) * 16)
    paste(fr, kicker_layer("03 — CLIMATE CHANGE / DROUGHT", AMBER), (120, 336), a, rise)
    b = ease_out(clamp((t - 6.18) / 0.38))
    a1 = a * (1 - b)
    l1 = simple("A changing climate", "sans500", 66, INK + (255,), tracking=-0.5)
    l2 = simple("is rewriting the map.", "sans500", 66, INK + (255,), tracking=-0.5)
    paste(fr, l1, (120, 388), a1, rise)
    paste(fr, l2, (120, 466), a1, rise)
    d = ImageDraw.Draw(fr)
    rw = int(86 * ease_out(clamp((t - 3.86) / 0.55)))
    d.rectangle((120, 366, 120 + rw, 367), fill=AMBER + (220,))

    # second thought at the farmer line
    if b > 0:
        f1 = block_layer([
            [("Some farmers find", font("sans500", 66), INK + (255,))],
            [("no water.", font("sans500", 66), AMBER + (255,))],
        ], 78, tracking=-0.5)
        paste(fr, f1, (120, 388), b, int((1 - b) * 16))
    cr = simple("LAKE MEAD, NEVADA · 2021 · NASA / JPL", "mono", 10, FAINT + (255,), tracking=1.5)
    paste(fr, cr, (W - 120 - cr.width, H - 70), 0.85)
    return fr.convert("RGB")


def scene_flood(t):
    p = local(t, T_FLOOD)
    fr = compose_bg(FLOOD, focus=(0.55, 0.5), zoom=lerp(1.01, 1.09, ease_in_out(p)), dark=0.82)
    fr = overlay(fr, LEFT_DARK, 0.55)
    fr = overlay(fr, BOTTOM_DARK, 1.0)
    a = ease_out(clamp((t - 8.68) / 0.45))
    rise = int((1 - a) * 16)
    paste(fr, kicker_layer("04 — FLOOD", CORAL), (120, 690), a, rise)
    l1 = simple("Elsewhere, floods take", "sans500", 58, INK + (255,), tracking=-0.4)
    l2 = simple("the harvest — and the city.", "sans500", 58, INK + (255,), tracking=-0.4)
    paste(fr, l1, (120, 738), a, rise)
    paste(fr, l2, (120, 804), a, rise)
    d = ImageDraw.Draw(fr)
    rw = int(86 * ease_out(clamp((t - 8.75) / 0.55)))
    d.rectangle((120, 720, 120 + rw, 721), fill=CORAL + (220,))
    cr = simple("MISSISSIPPI RIVER · 2008 · FEMA", "mono", 10, (230, 236, 232, 160), tracking=1.5)
    paste(fr, cr, (W - 120 - cr.width, H - 70), 0.9)
    # dip out at the cut
    fade = smooth(clamp((t - 11.12) / 0.32))
    if fade > 0:
        fr = Image.alpha_composite(fr, Image.new("RGBA", (W, H), (5, 8, 9, int(255 * fade))))
    return fr.convert("RGB")


def ring_layer(radius, value_frac, width=5, color=ACCENT, track=(255, 255, 255, 22)):
    s = 2
    size = radius * 2 + 20
    layer = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    box = (10 * s, 10 * s, (size - 10) * s, (size - 10) * s)
    d.arc(box, 0, 360, fill=track, width=width * s)
    if value_frac > 0.001:
        d.arc(box, -90, -90 + 360 * value_frac, fill=color + (255,), width=width * s)
    return layer.resize((size, size), Image.LANCZOS)


def scene_reveal(t):
    p = local(t, T_REVEAL)
    fr = Image.new("RGBA", (W, H), BG + (255,))
    # ghost world
    if t > 11.7:
        a = ease_out(clamp((t - 11.7) / 1.4))
        ghost = fit_cover(WORLD_GHOST, W, H, (0.5, 0.5), 1.0 + 0.03 * p).convert("RGBA")
        ghost.putalpha(int(255 * 0.13 * a))
        fr = Image.alpha_composite(fr, ghost)
    # subtle horizon
    d = ImageDraw.Draw(fr)
    d.line((0, 860, W, 860), fill=(255, 255, 255, 10), width=1)

    # brand lockup
    a = ease_out(clamp((t - 11.48) / 0.55))
    rise = int((1 - a) * 14)
    mark = logo_mark(62, ACCENT, int(255 * a))
    fr.paste(mark, (120, 232 + rise), mark)
    word = simple("AquaState", "sans600", 42, INK + (255,), tracking=-1.2)
    paste(fr, word, (196, 236), a, rise)
    sub = simple("THE WATER LEDGER", "mono", 9, MUTED + (255,), tracking=2.6)
    paste(fr, sub, (198, 292), a, rise)

    a2 = ease_out(clamp((t - 11.75) / 0.5))
    paste(fr, simple("NASA EARTH DATA  /  ONE INDEX", "mono", 12, ACCENT + (255,), tracking=2.2), (122, 376), a2, int((1 - a2) * 12))
    idx1 = simple("Water-Climate", "sans500", 44, INK + (255,), tracking=-0.5)
    idx2 = simple("Resilience Index", "sans500", 44, INK + (255,), tracking=-0.5)
    paste(fr, idx1, (120, 414), a2, int((1 - a2) * 12))
    paste(fr, idx2, (120, 470), a2, int((1 - a2) * 12))
    paste(fr, simple("WCRI-2.0", "mono", 11, MUTED + (255,), tracking=2.4), (122, 540), a2, int((1 - a2) * 12))

    # ring
    ring_p = ease_out(clamp((t - 12.0) / 1.55))
    frac = 0.615 * ring_p
    rl = ring_layer(214, frac, width=5)
    cx, cy = 1450, 500
    fr.paste(rl, (cx - rl.width // 2, cy - rl.height // 2), rl)
    num = f"{61.5 * ring_p:.1f}"
    n = simple(num, "mono500", 128, INK + (255,))
    paste(fr, n, (cx - n.width // 2, cy - 82), ease_out(clamp((t - 12.05) / 0.4)))
    sub = simple("/ 100", "mono", 17, MUTED + (255,), tracking=1.0)
    paste(fr, sub, (cx - sub.width // 2, cy + 72), 0.9)
    lab = simple("GLOBAL AVERAGE · WCRI-2.0", "mono", 10, MUTED + (255,), tracking=2.0)
    paste(fr, lab, (cx - lab.width // 2, cy + 118), ease_out(clamp((t - 13.4) / 0.5)), 6)

    a3 = ease_out(clamp((t - 14.15) / 0.55))
    foot = simple("249 COUNTRIES SCORED  ·  82,394 DAMS CATALOGUED", "mono", 10, FAINT + (255,), tracking=1.8)
    paste(fr, foot, (cx - foot.width // 2, cy + 164), a3, 8)
    return fr.convert("RGB")


def number_card(frame, t, start, end, number, label, sublabel, color=ACCENT):
    """One big number beat, with slide-up transition."""
    if t < start or t > end:
        return
    p_in = ease_out(clamp((t - start) / 0.32))
    p_out = ease_out(clamp((t - end + 0.22) / 0.22))
    alpha = p_in * (1 - p_out)
    if alpha <= 0:
        return
    dy = int((1 - p_in) * 34) - int(p_out * 24)
    n = simple(number, "mono500", 148, INK + (255,))
    paste(frame, n, (120, 360 + dy), alpha)
    lab = simple(label, "mono", 16, color + (255,), tracking=3.2)
    paste(frame, lab, (124, 540 + dy), alpha)
    sub = simple(sublabel, "mono", 11, MUTED + (255,), tracking=1.8)
    paste(frame, sub, (124, 572 + dy), alpha * 0.95)
    # rule above
    rw = int(92 * p_in)
    d = ImageDraw.Draw(frame)
    d.rectangle((120, 330, 120 + rw, 331), fill=color + (int(210 * alpha),))


def scene_world(t):
    p = local(t, T_WORLD)
    fr = compose_bg(WORLD, focus=(lerp(0.46, 0.63, ease_in_out(p)), lerp(0.62, 0.56, ease_in_out(p))), zoom=lerp(1.86, 1.96, ease_in_out(p)), dark=0.92)
    fr = overlay(fr, WORLD_DARK, 1.0)
    fr = overlay(fr, TOP_DARK, 1.0)
    fr = overlay(fr, BOTTOM_DARK, 0.30)
    d = ImageDraw.Draw(fr)
    # top marker
    paste(fr, kicker_layer("THE PLANET, IN ONE LEDGER", ACCENT), (122, 120), 0.95)
    d.line((120, 150, 520, 150), fill=(255, 255, 255, 26), width=1)

    number_card(fr, t, W_249 - 0.32, W_FOUR - 0.30, "249", "COUNTRIES SCORED", "WCRI-2.0 · 249 OF 249 · SNAPSHOT 15 NOV 2026", ACCENT)
    number_card(fr, t, W_FOUR - 0.30, W_82394 - 0.33, "4", "LIVE PRESSURES", "DROUGHT · FLOOD · WILDFIRE · DESERTIFICATION", AMBER)
    number_card(fr, t, W_82394 - 0.33, T_WORLD[1] + 0.1, "82,394", "DAMS CATALOGUED", "172 COUNTRIES · 33 MONITORED FOR LIVE STATUS", ACCENT)

    # pressure legend for the four beat
    b = ease_out(clamp((t - W_FOUR - 0.12) / 0.35)) * (1 - ease_out(clamp((t - W_82394 + 0.05) / 0.2)))
    if b > 0:
        items = [("DROUGHT", "50", AMBER), ("FLOOD", "32", BLUE), ("WILDFIRE", "26", CORAL), ("DESERTIFICATION", "34", OCHRE)]
        x = 124
        for name, val, col in items:
            dd = ImageDraw.Draw(fr)
            dd.ellipse((x, 646, x + 6, 652), fill=col + (int(255 * b),))
            txt = simple(f"{name} {val}", "mono", 11, (222, 232, 228, int(210 * b)), tracking=1.2)
            paste(fr, txt, (x + 13, 638), b)
            x += txt.width + 34
    cr = simple("LIVE SOURCES · NASA POWER / MERRA-2 · NASA EONET · GLOFAS · WORLD BANK", "mono", 9, FAINT + (255,), tracking=1.4)
    paste(fr, cr, (122, H - 70), 0.75)
    return fr.convert("RGB")


def scene_country(t):
    p = local(t, T_COUNTRY)
    fr = compose_bg(COUNTRY, focus=(0.51, 0.19), zoom=lerp(1.02, 1.075, ease_out(p)), dark=1.0)
    # lower third
    bar = Image.new("RGBA", (W, 122), (8, 14, 16, 238))
    fr = Image.alpha_composite(fr, Image.new("RGBA", (W, H), (0, 0, 0, 0)))
    fr.paste(bar, (0, H - 122), bar)
    d = ImageDraw.Draw(fr)
    d.rectangle((0, H - 122, W, H - 121), fill=(255, 255, 255, 26))
    a = ease_out(clamp((t - 21.9) / 0.35))
    paste(fr, simple("COUNTRY SHEET", "mono", 10, MUTED + (255,), tracking=2.4), (122, H - 100), a)
    paste(fr, simple("ALGERIA", "mono500", 17, INK + (255,), tracking=2.0), (122, H - 76), a)
    # number appears on "your number"
    b = ease_out(clamp((t - W_YOUR_NUMBER) / 0.28))
    n = simple("45.6", "mono500", 34, ACCENT + (255,))
    paste(fr, n, (760, H - 94), b, int((1 - b) * 12))
    paste(fr, simple("/ 100  ·  WCRI-2.0", "mono", 11, MUTED + (255,), tracking=1.6), (880, H - 78), b)
    pill = simple("WATCH  ·  RANK 232 OF 249", "mono", 11, AMBER + (255,), tracking=1.8)
    paste(fr, pill, (W - 120 - pill.width, H - 78), b)
    # small top rule
    d.rectangle((0, 0, W, 3), fill=ACCENT + (210,))
    return fr.convert("RGB")


def scene_dam(t):
    p = local(t, T_DAM)
    fr = compose_bg(DAM, focus=(lerp(0.38, 0.34, p), lerp(0.30, 0.27, p)), zoom=lerp(1.03, 1.13, ease_in_out(p)), dark=0.90)
    veil_p = smooth(clamp((t - W_QUESTION) / 0.55))
    if veil_p > 0:
        veil = Image.new("RGBA", (W, H), (6, 10, 11, int(234 * veil_p)))
        fr = Image.alpha_composite(fr, veil)

    a = ease_out(clamp((t - W_QUESTION - 0.05) / 0.5))
    if a > 0:
        qk = simple("THE ONE QUESTION", "mono", 12, ACCENT + (255,), tracking=3.0)
        centered(fr, qk, 338, a, int((1 - a) * 12))
        block = block_layer([
            [("Are we covered", font("sans500", 64), INK + (255,))],
            [("until the ", font("sans500", 64), INK + (255,)), ("next rain?", font("sans500", 64), ACCENT + (255,))],
        ], 78, tracking=-0.5, align="center")
        paste(fr, block, ((W - block.width) // 2, 400), a, int((1 - a) * 16))
        proof = simple("38.6  TO  83.3   /   BUFFER 0.950   /   +1 DAY TO RAIN", "mono", 11, (210, 224, 219, 170), tracking=1.5)
        centered(fr, proof, 614, a * 0.9, int((1 - a) * 12))
        d = ImageDraw.Draw(fr)
        rw = int(96 * a)
        d.rectangle((W // 2 - rw // 2, 380, W // 2 + rw // 2, 381), fill=ACCENT + (210,))
    return fr.convert("RGB")


def scene_end(t):
    p = local(t, T_END)
    fr = Image.new("RGBA", (W, H), (5, 9, 10, 255))
    # faint central glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W // 2 - 520, 170, W // 2 + 520, 900), fill=(22, 92, 88, 26))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    fr = Image.alpha_composite(fr, glow)

    a = ease_out(clamp((t - W_AQUASTATE + 0.12) / 0.45))
    rise = int((1 - a) * 14)
    mark = logo_mark(82, ACCENT, int(255 * a))
    # center lockup width
    lock_w = 82 + 18 + 262
    x0 = (W - lock_w) // 2
    fr.paste(mark, (x0, 300 + rise), mark)
    word = simple("AquaState", "sans600", 62, INK + (255,), tracking=-1.8)
    paste(fr, word, (x0 + 100, 304), a, rise)
    sub = simple("THE WATER LEDGER", "mono", 10, MUTED + (255,), tracking=3.0)
    paste(fr, sub, (x0 + 102, 382), a, rise)

    tag = simple("Water is the secret of life. This is its ledger.", "sans", 27, (206, 220, 214, 255), tracking=-0.2)
    ta = ease_out(clamp((t - 27.30) / 0.6))
    centered(fr, tag, 500, ta, int((1 - ta) * 12))

    d = ImageDraw.Draw(fr)
    rw = int(360 * ease_out(clamp((t - 27.6) / 0.7)))
    if rw > 2:
        d.rectangle((W // 2 - rw // 2, 562, W // 2 + rw // 2, 563), fill=ACCENT + (190,))

    row = simple("DROUGHT   ·   FLOOD   ·   WILDFIRE   ·   DESERTIFICATION", "mono", 9, FAINT + (255,), tracking=2.2)
    ua = ease_out(clamp((t - 27.9) / 0.5))
    centered(fr, row, 606, ua * 0.9, int((1 - ua) * 8))

    ca = ease_out(clamp((t - 27.8) / 0.6))
    chal = simple("NASA SPACE APPS CHALLENGE", "mono500", 12, INK + (255,), tracking=3.4)
    centered(fr, chal, 872, ca, int((1 - ca) * 8))
    desc = simple("AQUASTATE  ·  WORLD WATER & CLIMATE OBSERVATORY", "mono", 8, MUTED + (255,), tracking=2.0)
    centered(fr, desc, 906, ca * 0.9, int((1 - ca) * 8))

    cra = ease_out(clamp((t - 28.15) / 0.7))
    c1 = simple("IMAGERY  NASA EARTH OBSERVATORY · ESA/S. ADENOT · FEMA", "mono", 8, FAINT + (255,), tracking=1.2)
    c2 = simple("DATA  NASA POWER / MERRA-2 · NASA EONET · GLOFAS · WORLD BANK", "mono", 8, FAINT + (255,), tracking=1.2)
    centered(fr, c1, 968, cra * 0.85, int((1 - cra) * 6))
    centered(fr, c2, 990, cra * 0.85, int((1 - cra) * 6))

    # fade out
    fade = smooth(clamp((t - 29.25) / 0.65))
    if fade > 0:
        fr = Image.alpha_composite(fr, Image.new("RGBA", (W, H), (0, 0, 0, int(255 * fade))))
    return fr.convert("RGB")


# --- Master render --------------------------------------------------------
def render(t):
    if t < T_NILE[0]:
        fr = scene_earth(t)
    elif t < T_DROUGHT_A[0]:
        fr = scene_nile(t)
    elif t < T_FLOOD[0]:
        fr = scene_drought(t)
    elif t < T_REVEAL[0]:
        fr = scene_flood(t)
    elif t < T_WORLD[0]:
        fr = scene_reveal(t)
    elif t < T_COUNTRY[0]:
        fr = scene_world(t)
    elif t < T_DAM[0]:
        fr = scene_country(t)
    elif t < T_END[0]:
        fr = scene_dam(t)
    else:
        fr = scene_end(t)

    arr = np.asarray(fr).astype(np.float32)
    # unify with a gentle vignette and grain
    arr *= VIGNETTE[..., None]
    gi = int(t * 12) % len(GRAIN)
    arr += GRAIN[gi] * 2.0
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", type=str, default=None)
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--out", type=str, default=os.path.join(HERE, "out", "aquastate_30s.mp4"))
    args = ap.parse_args()
    prepare()
    if args.stills:
        os.makedirs(os.path.join(HERE, "stills"), exist_ok=True)
        for s in args.stills.split(","):
            t = float(s)
            im = render(t)
            p = os.path.join(HERE, "stills", f"still_{t:05.2f}.png")
            im.save(p)
            print("wrote", p)
        return
    if not args.render:
        print("pass --render or --stills")
        return
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    ffmpeg = os.environ.get("FFMPEG") or _find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "16",
        "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", args.out,
    ]
    print("encoding to", args.out)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    total = int(round(DUR * FPS))
    for i in range(total):
        proc.stdin.write(render(i / FPS).tobytes())
        if i % 90 == 0:
            print(f"  frame {i}/{total}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("done", args.out)


def _find_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


if __name__ == "__main__":
    main()
