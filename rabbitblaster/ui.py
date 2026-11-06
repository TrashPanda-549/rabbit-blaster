"""Rendering for Rabbit Blaster - pure PIL, no device IO.

Every screen is drawn to a PIL image at the panel's native size so the same
code can target the framebuffer or be dumped to a PNG for preview.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

W, H = 320, 170
HEADER_H = 26
FOOTER_H = 16
ROW_H = 20
BODY_TOP = HEADER_H + 4
VISIBLE = (H - FOOTER_H - BODY_TOP) // ROW_H   # 6 rows

BG = (16, 16, 20)
PANEL = (30, 30, 38)
ACCENT = (255, 72, 108)
ACCENT2 = (0, 220, 150)
TEXT = (236, 236, 242)
DIM = (150, 150, 162)
DARK = (14, 14, 18)

_FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


def _font(bold=False, size=14):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(_FONT_DIR + name, size)
    except Exception:
        return ImageFont.load_default()


_F_HDR = _font(True, 15)
_F_ROW = _font(False, 14)
_F_ROWB = _font(True, 14)
_F_FOOT = _font(False, 11)
_F_BIG = _font(True, 26)
_F_SUB = _font(False, 13)


def _truncate(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    ell = "…"
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text + ell


def _header(draw, title, subtitle=None):
    draw.rectangle([0, 0, W, HEADER_H], fill=ACCENT)
    draw.text((8, 5), title, font=_F_HDR, fill=DARK)
    if subtitle:
        s = _truncate(draw, subtitle, _F_SUB, 150)
        sw = draw.textlength(s, font=_F_SUB)
        draw.text((W - 8 - sw, 7), s, font=_F_SUB, fill=DARK)


def _footer(draw, hint):
    draw.rectangle([0, H - FOOTER_H, W, H], fill=PANEL)
    draw.text((8, H - FOOTER_H + 2), hint, font=_F_FOOT, fill=DIM)


def list_screen(title, items, selected, subtitle=None, hint=None, enabled=None):
    """items: list[str]; enabled: optional list[bool] (dim+mark disabled)."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    _header(d, title, subtitle)

    n = len(items)
    if n == 0:
        d.text((12, BODY_TOP + 20), "(nothing here)", font=_F_ROW, fill=DIM)
        _footer(d, hint or "ESC back")
        return img

    top = 0
    if selected >= VISIBLE:
        top = selected - VISIBLE + 1
    if selected < top:
        top = selected
    top = max(0, min(top, max(0, n - VISIBLE)))

    y = BODY_TOP
    for i in range(top, min(n, top + VISIBLE)):
        row_sel = (i == selected)
        ok = True if enabled is None else enabled[i]
        if row_sel:
            d.rectangle([4, y, W - 6, y + ROW_H - 2], fill=ACCENT if ok else PANEL)
            fill = DARK if ok else DIM
            font = _F_ROWB
        else:
            fill = TEXT if ok else DIM
            font = _F_ROW
        label = items[i]
        if not ok:
            label = "! " + label
        label = _truncate(d, label, font, W - 28)
        d.text((12, y + 2), label, font=font, fill=fill)
        y += ROW_H

    # scroll indicators
    if top > 0:
        d.polygon([(W - 12, BODY_TOP + 2), (W - 6, BODY_TOP + 2), (W - 9, BODY_TOP - 3)], fill=DIM)
    if top + VISIBLE < n:
        yb = H - FOOTER_H - 4
        d.polygon([(W - 12, yb - 2), (W - 6, yb - 2), (W - 9, yb + 3)], fill=DIM)

    _footer(d, hint or "↑↓ select   OK send   ESC back")
    return img


def message_screen(big, sub=None, color=ACCENT2):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    bw = d.textlength(big, font=_F_BIG)
    d.text(((W - bw) / 2, 54), big, font=_F_BIG, fill=color)
    if sub:
        s = _truncate(d, sub, _F_SUB, W - 20)
        sw = d.textlength(s, font=_F_SUB)
        d.text(((W - sw) / 2, 92), s, font=_F_SUB, fill=TEXT)
    return img
