"""Launch wrapper (runs as root via the launcher's sudo).

Board power is applied by the app itself only for the ~100 ms around each
send (see App._activate) and is never held while idle. This wrapper just runs
the app and, as a belt-and-braces measure, forces the board unpowered on exit
no matter how the app ends.
"""

from __future__ import annotations

import sys

from . import power
from .app import main


def run(argv=None):
    try:
        return main(sys.argv[1:] if argv is None else argv)
    finally:
        power.disable()


if __name__ == "__main__":
    raise SystemExit(run())
