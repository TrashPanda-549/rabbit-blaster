"""Generate the Rabbit Blaster launcher icon (PNG). Usage: make_icon.py OUT.png

Original art (not Rabbit Labs' logo file): Rabbit Labs' pink-on-dark style -
a hot-magenta rabbit head with IR "blast" waves. Drawn from primitives,
supersampled then LANCZOS-downscaled for clean edges at the ~100px tile size.
"""

import sys

from PIL import Image, ImageDraw

S = 100          # final tile size
SS = 5           # supersample factor
C = S * SS       # working canvas

BG = (18, 17, 24, 255)        # near-black, faint cool tint
BG_EDGE = (44, 40, 56, 255)   # subtle lighter border
PINK = (255, 45, 149, 255)    # hot magenta - the rabbit
PINK_HI = (255, 120, 185, 255)  # lighter magenta - inner ear
WAVE = (255, 150, 200, 255)   # IR blast waves
DARK = (18, 17, 24, 255)      # eyes / nose cut-outs (== bg)


def _make_ear():
    w, h = int(0.15 * C), int(0.42 * C)
    ear = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ear)
    d.ellipse([0, 0, w - 1, h - 1], fill=PINK)
    iw, ih = int(w * 0.46), int(h * 0.60)
    ix, iy = (w - iw) // 2, int(h * 0.14)
    d.ellipse([ix, iy, ix + iw, iy + ih], fill=PINK_HI)
    return ear


def main(out):
    img = Image.new("RGBA", (C, C), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # rounded-square background
    rad = int(0.22 * C)
    draw.rounded_rectangle([0, 0, C - 1, C - 1], radius=rad, fill=BG,
                           outline=BG_EDGE, width=max(1, int(0.012 * C)))

    # ears (rotated on their own layers)
    ear = _make_ear()
    hx, hy = 0.43 * C, 0.615 * C     # head center
    hw, hh = 0.48 * C, 0.46 * C
    lear = ear.rotate(16, expand=True, resample=Image.BICUBIC)
    rear = ear.rotate(-16, expand=True, resample=Image.BICUBIC)
    ear_bottom = int(hy - hh * 0.32)
    img.alpha_composite(lear, (int(hx - 0.195 * C), ear_bottom - lear.height))
    img.alpha_composite(rear, (int(hx + 0.045 * C), ear_bottom - rear.height))

    # head
    draw.ellipse([hx - hw / 2, hy - hh / 2, hx + hw / 2, hy + hh / 2], fill=PINK)
    draw.ellipse([hx - hw / 2 * 0.98, hy - hh * 0.10,
                  hx + hw / 2 * 0.98, hy + hh / 2 + hh * 0.06], fill=PINK)

    # face: two eyes + nose
    er = 0.045 * C
    for ex in (hx - 0.135 * C, hx + 0.135 * C):
        ey = hy - 0.02 * C
        draw.ellipse([ex - er, ey - er, ex + er, ey + er], fill=DARK)
    nx, ny, nw = hx, hy + 0.11 * C, 0.055 * C
    draw.polygon([(nx - nw, ny - nw * 0.7), (nx + nw, ny - nw * 0.7),
                  (nx, ny + nw * 0.8)], fill=DARK)

    # IR blast waves (upper-right, radiating from near the right ear)
    wx, wy = 0.80 * C, 0.26 * C
    lw = max(2, int(0.022 * C))
    for i, r in enumerate((0.11, 0.17, 0.23)):
        R = r * C
        col = (WAVE[0], WAVE[1], WAVE[2], 255 - i * 55)
        draw.arc([wx - R, wy - R, wx + R, wy + R], start=120, end=250,
                 fill=col, width=lw)
    draw.ellipse([wx - 0.025 * C, wy - 0.025 * C,
                  wx + 0.025 * C, wy + 0.025 * C], fill=WAVE)

    img.resize((S, S), Image.LANCZOS).save(out)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rabbit-blaster.png")
