"""Write PIL images to a Linux framebuffer as RGB565 (16bpp).

Tuned for the Cardputer Zero panel (/dev/fb0, 320x170, 16bpp, stride 640)
but auto-detects geometry from /sys/class/graphics/<fb>/ when available.
"""

from __future__ import annotations

import os

from PIL import Image, ImageChops

# Per-channel lookup tables for the two bytes of an RGB565 pixel:
# high = RRRRRGGG, low = GGGBBBBB.
_R_HI = [v & 0xF8 for v in range(256)]
_G_HI = [v >> 5 for v in range(256)]
_G_LO = [(v << 3) & 0xE0 for v in range(256)]
_B_LO = [v >> 3 for v in range(256)]


def _detect(dev_path):
    base = "/sys/class/graphics/%s/" % os.path.basename(dev_path)

    def read(name):
        with open(base + name) as f:
            return f.read().strip()

    w, h = 320, 170
    try:
        w, h = (int(x) for x in read("virtual_size").split(","))
    except Exception:
        pass
    try:
        stride = int(read("stride"))
    except Exception:
        stride = w * 2
    return w, h, stride


def rgb565_bytes(img: Image.Image, w: int, h: int, stride: int) -> bytes:
    """Little-endian RGB565, done inside PIL (no numpy: importing it cost
    0.8 s and 11 MB on the Zero for this one conversion)."""
    if img.size != (w, h):
        img = img.resize((w, h))
    if img.mode != "RGB":
        img = img.convert("RGB")
    r, g, b = img.split()
    hi = ImageChops.add(r.point(_R_HI), g.point(_G_HI))
    lo = ImageChops.add(g.point(_G_LO), b.point(_B_LO))
    data = Image.merge("LA", (lo, hi)).tobytes()    # lo, hi, lo, hi, ...
    if stride == w * 2:
        return data
    pad = bytes(stride - w * 2)
    return b"".join(data[y * w * 2:(y + 1) * w * 2] + pad for y in range(h))


class Framebuffer:
    def __init__(self, dev_path: str = "/dev/fb0"):
        self.width, self.height, self.stride = _detect(dev_path)
        self.fd = os.open(dev_path, os.O_RDWR)

    def show(self, img: Image.Image):
        data = rgb565_bytes(img, self.width, self.height, self.stride)
        os.lseek(self.fd, 0, os.SEEK_SET)
        os.write(self.fd, data)

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass
