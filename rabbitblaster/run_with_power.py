"""Launch wrapper: power the external IR board for the app's lifetime only.

Enables board power (guarded by the active-low interlock in power.enable),
runs the app, and cuts power on exit no matter how the app ends.
"""

from __future__ import annotations

import sys

from . import power
from .app import main


def run(argv=None):
    powered = power.enable()
    if not powered:
        print("run_with_power: board not powered (see above); the UI still "
              "runs but sends won't reach the board until invert=1 is active.",
              file=sys.stderr)
    try:
        return main(sys.argv[1:] if argv is None else argv)
    finally:
        power.disable()


if __name__ == "__main__":
    raise SystemExit(run())
