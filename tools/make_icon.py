"""Build the Rabbit Blaster launcher tile (100x100 PNG).

Usage: make_icon.py OUT.png [LOGO_IMAGE]

If a logo image is given (or share/images/rabbit-labs-hare.png exists), the
tile is that image, trimmed to the artwork and centred on a white rounded
square; the white background keeps a black logo's inner lines visible on the
dark launcher. Otherwise the tile is drawn from scratch: a pink rabbit head
with IR waves on a dark rounded square.
"""

import os
import sys

from PIL import Image, ImageChops, ImageDraw

SIZE = 100
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOGO = os.path.join(HERE, "..", "share", "images", "rabbit-labs-hare.png")


def logo_tile(src):
    ss, margin, radius = 4, 9, 20
    logo = Image.open(src).convert("RGB")
    white = Image.new("RGB", logo.size, (255, 255, 255))
    box = ImageChops.difference(logo, white).convert("L").point(
        lambda v: 255 if v > 24 else 0).getbbox()
    if box:
        logo = logo.crop(box)

    c = SIZE * ss
    inner = c - 2 * margin * ss
    scale = min(inner / logo.width, inner / logo.height)
    logo = logo.resize((max(1, round(logo.width * scale)),
                        max(1, round(logo.height * scale))), Image.LANCZOS)

    tile = Image.new("RGB", (c, c), (255, 255, 255))
    tile.paste(logo, ((c - logo.width) // 2, (c - logo.height) // 2))
    mask = Image.new("L", (c, c), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, c - 1, c - 1],
                                           radius=radius * ss, fill=255)
    tile = tile.convert("RGBA")
    tile.putalpha(mask)
    return tile.resize((SIZE, SIZE), Image.LANCZOS)


def drawn_tile():
    ss = 5
    c = SIZE * ss
    bg, edge = (18, 17, 24, 255), (44, 40, 56, 255)
    pink, pink_hi, wave = (255, 45, 149, 255), (255, 120, 185, 255), (255, 150, 200, 255)

    img = Image.new("RGBA", (c, c), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, c - 1, c - 1], radius=int(0.22 * c), fill=bg,
                           outline=edge, width=max(1, int(0.012 * c)))

    w, h = int(0.15 * c), int(0.42 * c)
    ear = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ear)
    d.ellipse([0, 0, w - 1, h - 1], fill=pink)
    iw, ih = int(w * 0.46), int(h * 0.60)
    ix, iy = (w - iw) // 2, int(h * 0.14)
    d.ellipse([ix, iy, ix + iw, iy + ih], fill=pink_hi)

    hx, hy, hw, hh = 0.43 * c, 0.615 * c, 0.48 * c, 0.46 * c
    lear = ear.rotate(16, expand=True, resample=Image.BICUBIC)
    rear = ear.rotate(-16, expand=True, resample=Image.BICUBIC)
    ear_bottom = int(hy - hh * 0.32)
    img.alpha_composite(lear, (int(hx - 0.195 * c), ear_bottom - lear.height))
    img.alpha_composite(rear, (int(hx + 0.045 * c), ear_bottom - rear.height))

    draw.ellipse([hx - hw / 2, hy - hh / 2, hx + hw / 2, hy + hh / 2], fill=pink)
    draw.ellipse([hx - hw / 2 * 0.98, hy - hh * 0.10,
                  hx + hw / 2 * 0.98, hy + hh / 2 + hh * 0.06], fill=pink)
    er = 0.045 * c
    for ex in (hx - 0.135 * c, hx + 0.135 * c):
        ey = hy - 0.02 * c
        draw.ellipse([ex - er, ey - er, ex + er, ey + er], fill=bg)
    nx, ny, nw = hx, hy + 0.11 * c, 0.055 * c
    draw.polygon([(nx - nw, ny - nw * 0.7), (nx + nw, ny - nw * 0.7),
                  (nx, ny + nw * 0.8)], fill=bg)

    wx, wy = 0.80 * c, 0.26 * c
    for i, r in enumerate((0.11, 0.17, 0.23)):
        rr = r * c
        draw.arc([wx - rr, wy - rr, wx + rr, wy + rr], start=120, end=250,
                 fill=wave[:3] + (255 - i * 55,), width=max(2, int(0.022 * c)))
    draw.ellipse([wx - 0.025 * c, wy - 0.025 * c,
                  wx + 0.025 * c, wy + 0.025 * c], fill=wave)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main(out, logo=None):
    logo = logo or (DEFAULT_LOGO if os.path.exists(DEFAULT_LOGO) else None)
    (logo_tile(logo) if logo else drawn_tile()).save(out)
    print("wrote %s (%s)" % (out, "logo: " + logo if logo else "drawn icon"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rabbit-blaster.png",
         *sys.argv[2:3])
