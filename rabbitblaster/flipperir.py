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
from typing import List, Optional

from . import irproto


@dataclass
class Signal:
    name: str
    type: str                      # "parsed" or "raw"
    protocol: str = ""
    address: List[int] = field(default_factory=list)
    command: List[int] = field(default_factory=list)
    frequency: int = 38000
    duty_cycle: float = 0.33
    data: List[int] = field(default_factory=list)

    def transmittable(self) -> bool:
        if self.type == "raw":
            return len(self.data) >= 2
        return self.protocol in irproto._PROTOCOLS

    def render(self):
        """Return (carrier_hz, durations[us]). Raises if not transmittable."""
        if self.type == "raw":
            durs = list(self.data)
            if len(durs) % 2 == 0:      # ir-ctl wants pulse-terminated
                durs = durs[:-1]
            return int(self.frequency), durs
        return irproto.encode(self.protocol, self.address, self.command)


def _hexbytes(s: str) -> List[int]:
    out = []
    for tok in s.split():
        try:
            out.append(int(tok, 16))
        except ValueError:
            pass
    return out


def _ints(s: str) -> List[int]:
    out = []
    for tok in s.split():
        try:
            out.append(int(tok))
        except ValueError:
            pass
    return out


def parse(path) -> List[Signal]:
    signals: List[Signal] = []
    cur: Optional[dict] = None

    def flush():
        nonlocal cur
        if cur and cur.get("name"):
            signals.append(Signal(
                name=cur.get("name", "?"),
                type=cur.get("type", "parsed"),
                protocol=cur.get("protocol", ""),
                address=_hexbytes(cur.get("address", "")),
                command=_hexbytes(cur.get("command", "")),
                frequency=int(cur.get("frequency", "38000") or 38000),
                duty_cycle=float(cur.get("duty_cycle", "0.33") or 0.33),
                data=_ints(cur.get("data", "")),
            ))
        cur = None

    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#"):
                flush()
                continue
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key in ("filetype", "version"):
                continue
            if key == "name":
                flush()
                cur = {}
            if cur is None:
                cur = {}
            cur[key] = val
    flush()
    return signals
