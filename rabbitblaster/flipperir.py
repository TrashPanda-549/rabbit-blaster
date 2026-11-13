"""Parse Flipper Zero `.ir` files into transmittable signals.

A Flipper .ir file is a header followed by signal blocks separated by `#`:

    Filetype: IR signals file
    Version: 1
    #
    name: Power
    type: parsed
    protocol: NEC
    address: 04 00 00 00
    command: 08 00 00 00
    #
    name: Vol_up
    type: raw
    frequency: 38000
    duty_cycle: 0.330000
    data: 9000 4500 560 560 ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from . import irproto


@dataclass
class Signal:
    name: str
    type: str                      # "parsed" or "raw"
    protocol: str = ""
    address: List[int] = field(default_factory=list)
    command: List[int] = field(default_factory=list)
    frequency: int = 38000
    data: List[int] = field(default_factory=list)

    def transmittable(self) -> bool:
        if self.type == "raw":
            return len(self.data) >= 2
        return self.protocol in irproto._PROTOCOLS

    def render(self):
        """Return (carrier_hz, durations[us]). Raises if not transmittable."""
        if self.type == "raw":
            durs = [max(1, int(v)) for v in self.data]
            # LIRC refuses transmissions over 500 ms total, and Flipper raw
            # captures often hold several repeated frames separated by long
            # gaps. Keep only the first frame: cut at the first inter-frame
            # gap (a space > 20 ms). Repeats are added by irsend if wanted.
            for i in range(1, len(durs), 2):        # spaces sit at odd indices
                if durs[i] > 20000:
                    durs = durs[:i]                 # ends on the pulse before it
                    break
            total, keep = 0, len(durs)              # hard cap well under 500 ms
            for i, v in enumerate(durs):
                total += v
                if total > 450000:
                    keep = i
                    break
            durs = durs[:keep]
            if len(durs) % 2 == 0:                  # ir-ctl wants pulse-terminated
                durs = durs[:-1]
            return int(self.frequency), durs
        return irproto.encode(self.protocol, self.address, self.command)


def _ints(s: str, base: int = 10) -> List[int]:
    """Whitespace-separated integers, skipping anything unparseable."""
    out = []
    for tok in s.split():
        try:
            out.append(int(tok, base))
        except ValueError:
            pass
    return out


def parse(path) -> List[Signal]:
    signals: List[Signal] = []
    cur: dict = {}

    def flush():
        if cur.get("name"):
            signals.append(Signal(
                name=cur["name"],
                type=cur.get("type", "parsed"),
                protocol=cur.get("protocol", ""),
                address=_ints(cur.get("address", ""), 16),
                command=_ints(cur.get("command", ""), 16),
                frequency=int(cur.get("frequency") or 38000),
                data=_ints(cur.get("data", "")),
            ))
        cur.clear()

    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith("#"):
                flush()
                continue
            key, sep, val = line.partition(":")
            key = key.strip().lower()
            if not sep or key in ("filetype", "version"):
                continue
            if key == "name":
                flush()
            cur[key] = val.strip()
    flush()
    return signals
