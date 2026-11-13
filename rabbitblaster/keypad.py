"""Cardputer Zero keyboard (tca8418c) -> UI events, read straight from the
kernel input device (no python-evdev: importing it cost 0.45 s on the Zero).

wait() returns a (kind, value) tuple:
    ("nav", "UP"|"DOWN"|"LEFT"|"RIGHT")   arrow keys (auto-repeat)
    ("ok", None)                          Enter
    ("back", None)                        Esc
    ("bksp", None)                        Backspace
    ("char", "<c>")                       a printable key (for type-to-filter)
"""

from __future__ import annotations

import glob
import os
import struct

# struct input_event: timeval (two native longs), type, code, value.
_EVENT = struct.Struct("llHHi")
_EV_KEY = 1

# Key codes from linux/input-event-codes.h.
_ESC, _BACKSPACE, _TAB, _ENTER, _KPENTER = 1, 14, 15, 28, 96
_SHIFTS = (42, 54)
_NAV = {103: "UP", 108: "DOWN", 105: "LEFT", 106: "RIGHT"}
_CHARS = {12: "-", 52: ".", 57: " "}
for _first, _row in ((2, "1234567890"), (16, "qwertyuiop"),
                     (30, "asdfghjkl"), (44, "zxcvbnm")):
    for _i, _ch in enumerate(_row):
        _CHARS[_first + _i] = _ch

_DEFAULT_PATH = "/dev/input/cardputer-zero-internal"


def find_keyboard() -> str:
    if os.path.exists(_DEFAULT_PATH):
        return _DEFAULT_PATH
    for name_file in sorted(glob.glob("/sys/class/input/event*/device/name")):
        try:
            with open(name_file) as f:
                if "tca8418" in f.read().lower():
                    return "/dev/input/" + name_file.split("/")[4]
        except OSError:
            continue
    raise RuntimeError("Cardputer keyboard not found under /dev/input")


class Keypad:
    def __init__(self, path: str | None = None):
        self.fd = os.open(path or find_keyboard(), os.O_RDONLY)
        self._shift = False

    def wait(self):
        # On this keyboard the arrows are an Fn layer we can't see as KEY_UP,
        # so base-layer Tab / Shift+Tab drive up/down with no Fn needed.
        while True:
            data = os.read(self.fd, _EVENT.size)    # the kernel returns whole events
            if len(data) < _EVENT.size:
                continue
            _sec, _usec, etype, code, val = _EVENT.unpack(data)
            if etype != _EV_KEY:
                continue
            if code in _SHIFTS:
                self._shift = val != 0
            elif code in _NAV:
                if val:                             # press or auto-repeat
                    return ("nav", _NAV[code])
            elif code == _TAB:
                if val:
                    return ("nav", "UP" if self._shift else "DOWN")
            elif val != 1:                          # the rest fire on press only
                continue
            elif code in (_ENTER, _KPENTER):
                return ("ok", None)
            elif code == _ESC:
                return ("back", None)
            elif code == _BACKSPACE:
                return ("bksp", None)
            elif code in _CHARS:
                return ("char", _CHARS[code])

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass
