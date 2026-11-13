"""Transmit IR via ir-ctl on a LIRC character device.

The transmitter is the gpio-ir-tx node feeding the external COBRA Commander.
Its /dev/lircN number can change when the TX pin is reassigned, so we
auto-detect the send-capable device at run time (overridable with
RABBIT_BLASTER_TX). Carrier is 38 kHz at 33 % duty, matching the ADV.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional

# None means "auto-detect at send time" (see find_tx_device).
DEFAULT_DEVICE: Optional[str] = os.environ.get("RABBIT_BLASTER_TX")

_tx_device_cache: Optional[str] = None


def _device_can_send(dev: str) -> bool:
    try:
        out = subprocess.run(["ir-ctl", "-d", dev, "--features"],
                             capture_output=True, text=True, timeout=5)
        return "can send" in (out.stdout + out.stderr).lower()
    except Exception:
        return False


def _header_tx_device() -> Optional[str]:
    """The LIRC device of the gpio-ir-tx node on the header pin (power.IR_TX_GPIO).
    A unit with built-in IR has a second transmitter; we must not pick that one."""
    from . import power
    tag = "gpio-ir-transmitter@%x" % power.IR_TX_GPIO
    for link in sorted(glob.glob("/sys/class/lirc/lirc*")):
        if tag in os.path.realpath(link).split("/"):
            return "/dev/" + os.path.basename(link)
    return None


def find_tx_device() -> str:
    """The LIRC char device to transmit on. Honors RABBIT_BLASTER_TX, else the
    header transmitter, else any send-capable /dev/lirc*, else /dev/lirc0."""
    global _tx_device_cache
    env = os.environ.get("RABBIT_BLASTER_TX")
    if env:
        return env
    if _tx_device_cache:
        return _tx_device_cache
    dev = _header_tx_device()
    if dev:
        _tx_device_cache = dev
        return dev
    for dev in sorted(glob.glob("/dev/lirc*")):
        if _device_can_send(dev):
            _tx_device_cache = dev
            return dev
    return "/dev/lirc0"


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


def send(carrier: int, durations: List[int], device: Optional[str] = None,
         repeats: int = 1, duty: int = DEFAULT_DUTY) -> None:
    if not durations:
        raise IRError("no durations to send")
    if shutil.which("ir-ctl") is None:
        raise IRError("ir-ctl not found on PATH")
    if device is None:
        device = find_tx_device()

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


def send_signal(signal, device: Optional[str] = None, repeats: int = 1) -> None:
    carrier, durations = signal.render()
    send(carrier, durations, device=device, repeats=repeats)
