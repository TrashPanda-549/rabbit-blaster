"""Transmit IR via ir-ctl on a LIRC character device (default /dev/lirc0,
the GPIO12 gpio-ir-tx transmitter on the Cardputer Zero).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import List

DEFAULT_DEVICE = os.environ.get("RABBIT_BLASTER_TX", "/dev/lirc0")
# 33% carrier duty (vs the driver's 50% default): standard for IR remotes and
# cuts the 10-LED ring's current during marks, which the Zero's 5V rail
# struggles to supply at 50%.
DEFAULT_DUTY = int(os.environ.get("RABBIT_BLASTER_DUTY", "33"))
_GAP = 40000


class IRError(RuntimeError):
    pass


def _build_file(carrier: int, durations: List[int], repeats: int) -> str:
    combined: List[int] = list(durations)
    for _ in range(max(0, repeats - 1)):
        combined.append(_GAP)
        combined.extend(durations)

    lines = []
    if carrier:
        lines.append("carrier %d" % int(carrier))
    for i, d in enumerate(combined):
        lines.append("%s %d" % ("pulse" if i % 2 == 0 else "space", int(d)))
    return "\n".join(lines) + "\n"


def send(carrier: int, durations: List[int], device: str = DEFAULT_DEVICE,
         repeats: int = 1, duty: int = DEFAULT_DUTY) -> None:
    if not durations:
        raise IRError("no durations to send")
    if shutil.which("ir-ctl") is None:
        raise IRError("ir-ctl not found on PATH")

    text = _build_file(carrier, durations, repeats)
    fd, path = tempfile.mkstemp(suffix=".ir-ctl", prefix="rb_", dir="/dev/shm"
                                if os.path.isdir("/dev/shm") else None)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        proc = subprocess.run(["ir-ctl", "-d", device, "--duty-cycle=%d" % duty,
                               "--send=" + path],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise IRError("ir-ctl failed (%d): %s"
                          % (proc.returncode, proc.stderr.strip() or proc.stdout.strip()))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def send_signal(signal, device: str = DEFAULT_DEVICE, repeats: int = 1) -> None:
    carrier, durations = signal.render()
    send(carrier, durations, device=device, repeats=repeats)
