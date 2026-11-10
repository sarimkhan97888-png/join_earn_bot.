"""Payout proof image (Pillow): UPI / USDT / Google Play code / Amazon voucher ke alag-alag design, bot ke naam ke saath."""
import io
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "Poppins-Bold.ttf")
W, H, S = 1280, 720, 2

# kind -> (bg1, bg2, accent, label)
THEMES = {
    "upi": ((10, 14, 48), (40, 38, 130), (110, 160, 255), "UPI TRANSFER"),
    "usdt": ((6, 30, 30), (10, 100, 90), (80, 240, 200), "USDT  ·  BEP20"),
    "gp": ((8, 28, 18), (14, 110, 60), (140, 255, 120), "GOOGLE PLAY CODE"),
    "amz": ((38, 18, 4), (150, 80, 10), (255, 190, 70), "AMAZON VOUCHER"),
}


def _font(size):
    try:
        return ImageFont.truetype(_FONT, size)
    except Exception:
        try:
            return ImageFont.load_default(size)
        except Exception:
            return ImageFont.load_default()


def _grad(c1, c2):
    img = Image.new("RGB", (W * S, H * S))
    px = ImageDraw.Draw(img)
    for y in range(H * S):
        t = y / (H * S)
        px.line([(0, y), (W * S, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return img


def _icon(d, kind, cx, cy, r, acc):
    """Simple shapes (emoji font ki zaroorat nahi)."""
    w = max(6, r // 9)
    if kind == "usdt":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=acc, width=w)
        d.rectangle([cx - r * .5, cy - r * .55, cx + r * .5, cy - r * .35], fill=acc)
        d.rectangle([cx - r * .1, cy - r * .55, cx + r * .1, cy + r * .6], fill=acc)
        d.ellipse([cx - r * .55, cy - r * .12, cx + r * .55, cy + r * .12], outline=acc, width=max(4, w // 2))
    elif kind == "gp":   # gift box
        d.rounded_rectangle([cx - r * .8, cy - r * .2, cx + r * .8, cy + r * .8], radius=r // 8, outline=acc, width=w)
        d.rounded_rectangle([cx - r * .9, cy - r * .5, cx + r * .9, cy - r * .2], radius=r // 8, outline=acc, width=w)
        d.line([cx, cy - r * .5, cx, cy + r * .8], fill=acc, width=w)
        d.arc([cx - r * .6, cy - r * 1.0, cx, cy - r * .35], 90, 360, fill=acc, width=w)
        d.arc([cx, cy - r * 1.0, cx + r * .6, cy - r * .35], 180, 450, fill=acc, width=w)
    elif kind == "amz":  # shopping bag + smile
        d.rounded_rectangle([cx - r * .75, cy - r * .35, cx + r * .75, cy + r * .85], radius=r // 8, outline=acc, width=w)
        d.arc([cx - r * .4, cy - r * .95, cx + r * .4, cy - r * .1], 180, 360, fill=acc, width=w)
        d.arc([cx - r * .45, cy + r * .0, cx + r * .45, cy + r * .6], 20, 160, fill=acc, width=w)
    else:                # upi: phone + tick
        d.rounded_rectangle([cx - r * .5, cy - r * .95, cx + r * .5, cy + r * .95], radius=r // 5, outline=acc, width=w)
        d.line([cx - r * .22, cy + r * .02, cx - r * .04, cy + r * .24, cx + r * .26, cy - r * .2], fill=acc, width=w, joint="curve")
        d.line([cx - r * .15, cy + r * .72, cx + r * .15, cy + r * .72], fill=acc, width=max(4, w // 2))


def render(kind, amount, detail, brand, bot, when, wid=None):
    """kind: upi|usdt|gp|amz. amount: '₹250.00' / '2.5 USDT'. detail: masked receiver. Return BytesIO(PNG)."""
    c1, c2, acc, label = THEMES.get(kind, THEMES["upi"])
    img = _grad(c1, c2).convert("RGBA")
    # soft glow + rings
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse([W * S * .55, -H * S * .35, W * S * 1.3, H * S * .6], fill=acc + (70,))
    g.ellipse([-W * S * .2, H * S * .55, W * S * .35, H * S * 1.3], fill=acc + (40,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90 * S)))
    img = img.convert("RGB")          # RGB par "RGBA" draw = alpha blend hota hai
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(3):
        rr = (230 + i * 90) * S
        d.ellipse([W * S * .86 - rr, H * S * .2 - rr, W * S * .86 + rr, H * S * .2 + rr], outline=acc + (36 - i * 8,), width=3 * S)
    # sparkles
    for k in range(14):
        a = k * 2.399
        x, y = W * S * (.5 + .48 * math.cos(a) * ((k % 5 + 3) / 8)), H * S * (.5 + .46 * math.sin(a * 1.3) * ((k % 4 + 3) / 7))
        s = (3 + k % 4) * S
        d.ellipse([x - s, y - s, x + s, y + s], fill=acc + (90,))
    # glass card
    card = [70 * S, 70 * S, (W - 70) * S, (H - 70) * S]
    d.rounded_rectangle(card, radius=46 * S, fill=(255, 255, 255, 22), outline=acc + (110,), width=2 * S)
    # check badge
    bx, by, br = 150 * S, 180 * S, 52 * S
    d.ellipse([bx - br, by - br, bx + br, by + br], fill=acc + (255,))
    d.line([bx - 22 * S, by + 2 * S, bx - 6 * S, by + 20 * S, bx + 26 * S, by - 18 * S], fill=c1 + (255,), width=11 * S, joint="curve")
    d.text((225 * S, 148 * S), "PAYOUT SUCCESSFUL", font=_font(34 * S), fill=(255, 255, 255, 255))
    d.text((227 * S, 196 * S), label, font=_font(22 * S), fill=acc + (255,))
    # amount
    amt_f = _font(120 * S)
    while d.textlength(amount, font=amt_f) > (W - 470) * S and amt_f.size > 50 * S:
        amt_f = _font(amt_f.size - 6 * S)
    d.text((110 * S, 290 * S), amount, font=amt_f, fill=(255, 255, 255, 255))
    d.text((112 * S, 450 * S), detail, font=_font(32 * S), fill=(255, 255, 255, 200))
    # icon
    _icon(d, kind, int((W - 215) * S), int(335 * S), 105 * S, acc + (255,))
    # footer
    d.line([110 * S, 545 * S, (W - 110) * S, 545 * S], fill=(255, 255, 255, 50), width=2 * S)
    d.text((110 * S, 570 * S), (brand or "").upper(), font=_font(34 * S), fill=acc + (255,))
    d.text((110 * S, 618 * S), f"@{bot}" if bot else "", font=_font(24 * S), fill=(255, 255, 255, 210))
    tail = f"{when}" + (f"   ·   #{wid}" if wid else "")
    tw = d.textlength(tail, font=_font(24 * S))
    d.text(((W - 110) * S - tw, 600 * S), tail, font=_font(24 * S), fill=(255, 255, 255, 190))
    out = io.BytesIO()
    img.resize((W, H), Image.LANCZOS).save(out, "PNG", optimize=True)
    out.seek(0)
    out.name = "payout.png"
    return out
