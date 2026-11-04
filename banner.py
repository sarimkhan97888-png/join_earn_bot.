"""Channel post ke liye banner image (Pillow). Font: assets/Poppins-Bold.ttf (na mile to default font)."""
import io
import os
import random
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "Poppins-Bold.ttf")
W, H, S = 1280, 720, 2   # final size, supersample

PALETTES = [
    ((14, 30, 8), (60, 110, 10), (190, 240, 80)),     # lime
    ((10, 10, 40), (50, 40, 110), (255, 210, 90)),    # indigo-gold
    ((30, 14, 4), (130, 62, 8), (255, 170, 60)),      # amber
    ((6, 26, 36), (8, 90, 110), (60, 230, 210)),      # teal
    ((30, 8, 34), (120, 24, 100), (255, 100, 200)),   # pink
    ((6, 14, 34), (18, 52, 120), (80, 140, 255)),     # blue
    ((8, 24, 22), (10, 80, 60), (60, 220, 150)),      # green
    ((24, 8, 40), (80, 30, 140), (190, 110, 255)),    # purple
    ((34, 10, 14), (130, 30, 50), (255, 120, 120)),   # red
    ((10, 18, 40), (20, 90, 130), (80, 220, 255)),    # cyan
]


def _font(size):
    try:
        return ImageFont.truetype(_FONT, size)
    except Exception:
        try:
            return ImageFont.load_default(size)
        except Exception:
            return ImageFont.load_default()


def _clean(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    t = re.sub(r"[^\w\s₹%+&/.,:!?'\-()]", "", t, flags=re.U)   # emoji hatao
    return re.sub(r"\s+", " ", t).strip()


def _wrap(d, text, font, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _coin(img, cx, cy, r, glow=True):
    if glow:
        g = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse((cx - r * 1.5, cy - r * 1.5, cx + r * 1.5, cy + r * 1.5), fill=(255, 180, 40, 70))
        img.alpha_composite(g.filter(ImageFilter.GaussianBlur(r * 0.6)))
    d = ImageDraw.Draw(img)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(217, 130, 0, 255))
    d.ellipse((cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3), fill=(255, 194, 51, 255))
    d.ellipse((cx - r * .78, cy - r * .78, cx + r * .78, cy + r * .78), outline=(217, 130, 0, 255), width=max(2, int(r * .06)))
    d.ellipse((cx - r * .62, cy - r * .7, cx - r * .1, cy - r * .3), fill=(255, 240, 184, 120))
    f = _font(int(r * 1.05))
    d.text((cx, cy), "₹", font=f, fill=(122, 67, 0, 255), anchor="mm")


def _layer(img):
    return Image.new("RGBA", img.size, (0, 0, 0, 0))


def _rays(img, cx, cy, ac, n=14):
    import math
    L = _layer(img)
    d = ImageDraw.Draw(L)
    R = max(img.size) * 1.2
    for i in range(n):
        a0 = 2 * math.pi * i / n
        a1 = a0 + math.pi / n * .8
        d.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)), (cx + R * math.cos(a1), cy + R * math.sin(a1))], fill=ac + (34,))
    img.alpha_composite(L.filter(ImageFilter.GaussianBlur(3)))


def _sparkle(d, x, y, r, col):
    d.polygon([(x, y - r), (x + r * .28, y - r * .28), (x + r, y), (x + r * .28, y + r * .28), (x, y + r), (x - r * .28, y + r * .28), (x - r, y), (x - r * .28, y - r * .28)], fill=col)


def _decor(img, kind, x1, x2, rnd, ac):
    w, h = img.size
    if kind == "coins":
        for _ in range(9):
            r = rnd.randint(34, 92) * S
            _coin(img, rnd.randint(int(x1) + r, max(int(x1) + r, int(x2) - r)), rnd.randint(r, h - r), r)
    elif kind == "bigcoin":
        cx, cy = (x1 + x2) / 2, h * .5
        _rays(img, cx, cy, ac)
        _coin(img, cx, cy, int(min(x2 - x1, h) * .36))
        for _ in range(3):
            r = rnd.randint(30, 52) * S
            _coin(img, rnd.randint(int(x1) + r, int(x2) - r), rnd.choice([rnd.randint(r, int(h * .2)), rnd.randint(int(h * .8), h - r)]), r)
    elif kind == "stars":
        d = ImageDraw.Draw(img)
        for _ in range(26):
            x, y, r = rnd.randint(int(x1), int(x2)), rnd.randint(0, h), rnd.randint(8, 30) * S
            _sparkle(d, x, y, r, rnd.choice([(255, 224, 138, 255), (255, 255, 255, 230), ac + (255,)]))
        for _ in range(3):
            r = rnd.randint(46, 84) * S
            _coin(img, rnd.randint(int(x1) + r, int(x2) - r), rnd.randint(r, h - r), r)
    elif kind == "rings":
        cx, cy = (x1 + x2) / 2, h * .5
        L = _layer(img)
        dl = ImageDraw.Draw(L)
        for i, rr in enumerate((.50, .40, .30)):
            R = int(min(x2 - x1, h) * rr)
            dl.ellipse((cx - R, cy - R, cx + R, cy + R), outline=ac + (200 - i * 50,), width=6 * S)
        img.alpha_composite(L)
        _coin(img, cx, cy, int(min(x2 - x1, h) * .2))
        for _ in range(4):
            r = rnd.randint(22, 38) * S
            _coin(img, rnd.randint(int(x1) + r, int(x2) - r), rnd.choice([rnd.randint(r, int(h * .15)), rnd.randint(int(h * .85), h - r)]), r)
    elif kind == "gifts":
        d = ImageDraw.Draw(img)
        for (fx, fy, sz, col) in [(.5, .62, .30, (230, 60, 90)), (.25, .72, .18, (70, 140, 255)), (.78, .74, .20, (255, 180, 40))]:
            cx = x1 + (x2 - x1) * fx
            sw = min(x2 - x1, h) * sz
            top = h * fy - sw / 2
            d.rounded_rectangle((cx - sw / 2, top, cx + sw / 2, top + sw), radius=int(sw * .1), fill=col + (255,))
            d.rectangle((cx - sw * .08, top, cx + sw * .08, top + sw), fill=(255, 235, 170, 255))
            d.rectangle((cx - sw / 2, top + sw * .42, cx + sw / 2, top + sw * .58), fill=(255, 235, 170, 255))
            d.ellipse((cx - sw * .24, top - sw * .2, cx, top + sw * .04), outline=(255, 235, 170, 255), width=max(4, int(sw * .06)))
            d.ellipse((cx, top - sw * .2, cx + sw * .24, top + sw * .04), outline=(255, 235, 170, 255), width=max(4, int(sw * .06)))
        _coin(img, int(x1 + (x2 - x1) * .3), int(h * .22), int(min(x2 - x1, h) * .1))
        _coin(img, int(x1 + (x2 - x1) * .75), int(h * .3), int(min(x2 - x1, h) * .07))
    else:   # bars: growth chart + coin
        d = ImageDraw.Draw(img)
        n = 5
        bw = (x2 - x1) / (n * 1.6)
        for i in range(n):
            bh = h * (.18 + .13 * i + rnd.random() * .05)
            bx = x1 + (x2 - x1) * .08 + i * bw * 1.6
            d.rounded_rectangle((bx, h * .88 - bh, bx + bw, h * .88), radius=int(bw * .25), fill=ac + (235,))
        _coin(img, int(x2 - (x2 - x1) * .18), int(h * .2), int(min(x2 - x1, h) * .13))


LAYOUTS = ["left", "center", "right"]
DECORS = ["coins", "bigcoin", "stars", "bars", "rings", "gifts"]


def _schedule():
    """30 alag (palette, layout) jodiyan, ek fixed order me: lagatar do posts kabhi same palette/layout nahi."""
    import itertools
    combos = list(itertools.product(range(len(PALETTES)), range(3)))
    rr = random.Random(2024)
    while True:
        rr.shuffle(combos)
        if all(a[0] != b[0] and a[1] != b[1] for a, b in zip(combos, combos[1:] + combos[:1])):
            return combos


SCHEDULE = _schedule()


def render(headline, badge=None, sub=None, bot="", brand="Profitix", seed=0):
    """PNG bytes. Har seed (post number) par alag palette + layout + decoration. headline/badge/sub plain text."""
    seed = int(seed or 0)
    rnd = random.Random(seed * 7919 + 13)
    pi, li = SCHEDULE[seed % len(SCHEDULE)]
    c0, c1, ac = PALETTES[pi]
    layout = LAYOUTS[li]
    decor = DECORS[seed % len(DECORS)]
    w, h = W * S, H * S
    img = Image.new("RGBA", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        px.line([(0, y), (w, y)], fill=tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3)) + (255,))
    for (cx, cy, r, a) in [(0.82 if layout != "right" else .18, 0.25, 0.5, 90), (0.1 if layout != "right" else .9, 0.9, 0.45, 60)]:
        g = _layer(img)
        ImageDraw.Draw(g).ellipse((w * cx - h * r, h * cy - h * r, w * cx + h * r, h * cy + h * r), fill=ac + (a,))
        img.alpha_composite(g.filter(ImageFilter.GaussianBlur(h * 0.18)))
    if layout == "left":
        _decor(img, decor, w * .66, w, rnd, ac); tx0, tw, al = 90 * S, int(w * .56), "l"
    elif layout == "right":
        _decor(img, decor, 0, w * .34, rnd, ac); tx0, tw, al = int(w * .40), int(w * .54), "l"
    else:
        _decor(img, decor, 0, w * .17, rnd, ac); _decor(img, decor, w * .83, w, rnd, ac); tx0, tw, al = w // 2, int(w * .60), "c"
    d = ImageDraw.Draw(img)
    anchor = "ma" if al == "c" else "la"

    def pill(cx_or_x, y, text, font, fill, outline, tcol, hh):
        bw = int(d.textlength(text, font=font)) + 60 * S
        x = cx_or_x - bw / 2 if al == "c" else cx_or_x
        d.rounded_rectangle((x, y, x + bw, y + hh), radius=hh // 2, fill=fill, outline=outline, width=3)
        d.text((x + bw / 2, y + hh / 2 + 2 * S), text, font=font, fill=tcol, anchor="mm")

    pill(tx0, 60 * S, _clean(brand).upper(), _font(26 * S), (20, 28, 56, 255), (255, 224, 138, 255), (255, 224, 138, 255), 56 * S)
    head = _clean(headline)[:70] or brand
    for size in (96, 84, 72, 62, 54, 46):
        f = _font(size * S)
        lines = _wrap(d, head, f, tw)
        if len(lines) <= 3:
            break
    lh = int(size * S * 1.18)
    y = 160 * S
    for ln in lines[:3]:
        d.text((tx0 + 3 * S, y + 4 * S), ln, font=f, fill=(0, 0, 0, 110), anchor=anchor)
        d.text((tx0, y), ln, font=f, fill=(255, 255, 255, 255), anchor=anchor)
        y += lh
    if sub:
        sf = _font(34 * S)
        for ln in _wrap(d, _clean(sub), sf, tw)[:2]:
            d.text((tx0, y + 18 * S), ln, font=sf, fill=(205, 214, 255, 255), anchor=anchor)
            y += 46 * S
        y += 18 * S
    if badge:
        pill(tx0, y + 26 * S, _clean(badge).upper()[:26], _font(48 * S), (255, 194, 51, 255), None, (60, 30, 0, 255), 90 * S)
    if bot:
        pill(tx0, h - 100 * S, "@" + bot.lstrip("@"), _font(30 * S), (10, 14, 28, 255), (255, 255, 255, 255), (255, 255, 255, 255), 62 * S)
    out = img.convert("RGB").resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()
