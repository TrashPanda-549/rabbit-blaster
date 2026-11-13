"""Build the Rabbit Blaster launcher tile from the Rabbit Labs hare-head logo.

Usage: make_icon.py OUT.png [SOURCE_IMAGE]

The source (default share/images/rabbit-labs-hare.png, black on white) is
trimmed to the artwork, centred on a white rounded square and scaled to the
~100 px APPLaunch tile size. The white background is kept so the logo's white
inner lines stay visible on the dark launcher.
"""

import os
import sys

from PIL import Image, ImageChops, ImageDraw

SIZE = 100
SS = 4            # supersample factor for smooth rounded corners
MARGIN = 9        # px of white around the artwork at final size
RADIUS = 20

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.join(HERE, "..", "share", "images", "rabbit-labs-hare.png")


def main(out, src=DEFAULT_SRC):
    logo = Image.open(src).convert("RGB")
    white = Image.new("RGB", logo.size, (255, 255, 255))
    box = ImageChops.difference(logo, white).convert("L").point(
        lambda v: 255 if v > 24 else 0).getbbox()
    if box:
        logo = logo.crop(box)

    c = SIZE * SS
    inner = c - 2 * MARGIN * SS
    scale = min(inner / logo.width, inner / logo.height)
    logo = logo.resize((max(1, round(logo.width * scale)),
                        max(1, round(logo.height * scale))), Image.LANCZOS)

    tile = Image.new("RGB", (c, c), (255, 255, 255))
    tile.paste(logo, ((c - logo.width) // 2, (c - logo.height) // 2))

    mask = Image.new("L", (c, c), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, c - 1, c - 1],
                                           radius=RADIUS * SS, fill=255)
    tile = tile.convert("RGBA")
    tile.putalpha(mask)
    tile.resize((SIZE, SIZE), Image.LANCZOS).save(out)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rabbit-blaster.png",
         *sys.argv[2:3])
