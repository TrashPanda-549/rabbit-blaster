"""Cardputer Zero keyboard (tca8418c) -> UI events via evdev.

wait() returns a (kind, value) tuple:
    ("nav", "UP"|"DOWN"|"LEFT"|"RIGHT")   arrow keys (auto-repeat)
    ("ok", None)                          Enter
    ("back", None)                        Esc
    ("bksp", None)                        Backspace
    ("char", "<c>")                       a printable key (for type-to-filter)
"""

from __future__ import annotations

import glob

from evdev import InputDevice, ecodes

_NAV = {
    ecodes.KEY_UP: "UP",
    ecodes.KEY_DOWN: "DOWN",
    ecodes.KEY_LEFT: "LEFT",
    ecodes.KEY_RIGHT: "RIGHT",
}

_CHARS = {}
for _ch in "abcdefghijklmnopqrstuvwxyz":
    _code = getattr(ecodes, "KEY_" + _ch.upper(), None)
    if _code is not None:
        _CHARS[_code] = _ch
for _d in "0123456789":
    _code = getattr(ecodes, "KEY_" + _d, None)
    if _code is not None:
        _CHARS[_code] = _d
_CHARS[ecodes.KEY_SPACE] = " "
_CHARS[ecodes.KEY_MINUS] = "-"
_CHARS[ecodes.KEY_DOT] = "."

_DEFAULT_PATHS = ["/dev/input/cardputer-zero-internal"]


def find_keyboard() -> str:
    for p in _DEFAULT_PATHS:
        try:
            InputDevice(p)
            return p
        except Exception:
            pass
    for p in sorted(glob.glob("/dev/input/event*")):
        try:
            if "tca8418" in (InputDevice(p).name or "").lower():
                return p
        except Exception:
            continue
    raise RuntimeError("Cardputer keyboard not found under /dev/input")


class Keypad:
    def __init__(self, path: str | None = None):
        self.dev = InputDevice(path or find_keyboard())
        self._shift = False

    def wait(self):
        # On this keyboard the arrows are an Fn layer we can't see as KEY_UP,
        # so base-layer Tab / Shift+Tab drive up/down with no Fn needed.
        for event in self.dev.read_loop():
            if event.type != ecodes.EV_KEY:
                continue
            code, val = event.code, event.value
            if code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                self._shift = val != 0
                continue
            if code in _NAV:
                if val in (1, 2):           # press or auto-repeat
                    return ("nav", _NAV[code])
                continue
            if code == ecodes.KEY_TAB:
                if val in (1, 2):
                    return ("nav", "UP" if self._shift else "DOWN")
                continue
            if val != 1:                    # the rest fire on press only
                continue
            if code in (ecodes.KEY_ENTER, ecodes.KEY_KPENTER):
                return ("ok", None)
            if code == ecodes.KEY_ESC:
                return ("back", None)
            if code == ecodes.KEY_BACKSPACE:
                return ("bksp", None)
            if code in _CHARS:
                return ("char", _CHARS[code])

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass
