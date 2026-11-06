"""Write PIL images to a Linux framebuffer as RGB565 (16bpp).

Tuned for the Cardputer Zero panel (/dev/fb0, 320x170, 16bpp, stride 640)
but auto-detects geometry from /sys/class/graphics/<fb>/ when available.
"""

from __future__ import annotations

import os

import numpy as np
from PIL import Image


def _detect(dev_path):
    name = os.path.basename(dev_path)
    base = "/sys/class/graphics/%s" % name
    w, h, stride, bpp = 320, 170, 640, 16
    try:
        vs = open(base + "/virtual_size").read().strip()
        w, h = (int(x) for x in vs.split(","))
    except Exception:
        pass
    try:
        bpp = int(open(base + "/bits_per_pixel").read().strip())
    except Exception:
        pass
    try:
        stride = int(open(base + "/stride").read().strip())
    except Exception:
        stride = w * (bpp // 8)
    return w, h, stride, bpp


def rgb565_bytes(img: Image.Image, w: int, h: int, stride: int) -> bytes:
    if img.size != (w, h):
        img = img.resize((w, h))
    arr = np.asarray(img.convert("RGB"), dtype=np.uint16)
    r = (arr[..., 0] >> 3) & 0x1F
    g = (arr[..., 1] >> 2) & 0x3F
    b = (arr[..., 2] >> 3) & 0x1F
    rgb565 = ((r << 11) | (g << 5) | b).astype("<u2")
    row = rgb565.view(np.uint8).reshape(h, w * 2)
    if stride == w * 2:
        return row.tobytes()
    frame = np.zeros((h, stride), dtype=np.uint8)
    frame[:, : w * 2] = row
    return frame.tobytes()


class Framebuffer:
    def __init__(self, dev_path: str = "/dev/fb0"):
        self.path = dev_path
        self.width, self.height, self.stride, self.bpp = _detect(dev_path)
        self.fd = os.open(dev_path, os.O_RDWR)

    @property
    def size(self):
        return (self.width, self.height)

    def show(self, img: Image.Image):
        data = rgb565_bytes(img, self.width, self.height, self.stride)
        os.lseek(self.fd, 0, os.SEEK_SET)
        os.write(self.fd, data)

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
