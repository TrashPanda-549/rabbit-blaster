"""Generate the Rabbit Blaster launcher icon (PNG). Usage: make_icon.py OUT.png"""

import sys

from PIL import Image, ImageDraw

SIZE = 100
BG = (20, 20, 28)
PINK = (255, 72, 108)
WHITE = (240, 240, 245)
GREEN = (0, 220, 150)


def main(out):
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, SIZE - 3, SIZE - 3], radius=18, fill=BG, outline=PINK, width=3)

    # rabbit ears
    d.ellipse([26, 14, 38, 52], fill=WHITE)
    d.ellipse([40, 14, 52, 52], fill=WHITE)
    d.ellipse([29, 20, 35, 48], fill=PINK)
    d.ellipse([43, 20, 49, 48], fill=PINK)
    # head
    d.ellipse([24, 44, 56, 76], fill=WHITE)
    # eye + nose
    d.ellipse([34, 56, 39, 61], fill=BG)
    d.ellipse([44, 56, 49, 61], fill=BG)
    d.ellipse([38, 64, 44, 69], fill=PINK)

    # IR blast waves (upper-right)
    for i, r in enumerate((10, 18, 26)):
        box = [62 - r, 30 - r, 62 + r, 30 + r]
        d.arc(box, start=-55, end=55, fill=GREEN, width=3)

    img.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rabbit-blaster.png")
