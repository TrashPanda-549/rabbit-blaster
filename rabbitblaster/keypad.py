"""Map Cardputer Zero keyboard (tca8418c) evdev events to logical buttons."""

from __future__ import annotations

import glob

from evdev import InputDevice, ecodes

UP, DOWN, LEFT, RIGHT, OK, BACK, QUIT = "UP", "DOWN", "LEFT", "RIGHT", "OK", "BACK", "QUIT"

_MAP = {
    ecodes.KEY_UP: UP,
    ecodes.KEY_DOWN: DOWN,
    ecodes.KEY_LEFT: LEFT,
    ecodes.KEY_RIGHT: RIGHT,
    ecodes.KEY_ENTER: OK,
    ecodes.KEY_KPENTER: OK,
    ecodes.KEY_SPACE: OK,
    ecodes.KEY_ESC: BACK,
    ecodes.KEY_BACKSPACE: BACK,
    ecodes.KEY_Q: QUIT,
}

_DEFAULT_PATHS = [
    "/dev/input/cardputer-zero-internal",
]


def find_keyboard() -> str:
    for p in _DEFAULT_PATHS:
        try:
            InputDevice(p)
            return p
        except Exception:
            pass
    for p in sorted(glob.glob("/dev/input/event*")):
        try:
            d = InputDevice(p)
            if "tca8418" in (d.name or "").lower():
                return p
        except Exception:
            continue
    raise RuntimeError("Cardputer keyboard not found under /dev/input")


class Keypad:
    def __init__(self, path: str | None = None):
        self.dev = InputDevice(path or find_keyboard())

    def wait(self):
        """Block until a mapped button is pressed; return its logical name.

        Navigation keys repeat (auto-repeat held key); OK/BACK/QUIT fire on
        the initial press only.
        """
        for event in self.dev.read_loop():
            if event.type != ecodes.EV_KEY:
                continue
            btn = _MAP.get(event.code)
            if btn is None:
                continue
            if btn in (UP, DOWN, LEFT, RIGHT):
                if event.value in (1, 2):   # press or auto-repeat
                    return btn
            elif event.value == 1:          # press only
                return btn

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass
