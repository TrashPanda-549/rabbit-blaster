"""Use the probonopd/irdb database (CSV codes) as a transmit source.

irdb layout:  codes/<Brand>/<DeviceType>/<device>,<subdevice>.csv
CSV columns:  functionname,protocol,device,subdevice,function

Codes are parametric (a protocol name + device/subdevice/function numbers),
so we render them to pulses with irproto. Protocols we don't encode yet are
reported as unsupported (shown with a mark, not transmitted).
"""

from __future__ import annotations

import csv
import os
from collections import namedtuple

from . import irproto

Row = namedtuple("Row", "name protocol device subdevice function")

BASE_CANDIDATES = [
    os.environ.get("RABBIT_BLASTER_IRDB"),
    os.path.expanduser("~/irdb/codes"),
    "/usr/share/rabbit-blaster/irdb/codes",
    "/usr/share/irdb/codes",
]

_NEC = ("nec", "nec1", "nec2", "necx1", "necx2")


def base_dir():
    for d in BASE_CANDIDATES:
        if d and os.path.isdir(d):
            return d
    return None


def available():
    return base_dir() is not None


def supported(protocol) -> bool:
    pl = (protocol or "").strip().lower()
    return pl in _NEC or pl in ("rc5", "rc6", "sony12", "sony15", "sony20", "jvc")


def render(protocol, device, subdevice, function):
    """Return (carrier_hz, durations[us]) or None if unsupported."""
    pl = (protocol or "").strip().lower()
    D, S, F = int(device), int(subdevice), int(function)
    if pl in _NEC:
        return irproto.build_nec(D, S, F)
    if pl == "rc5":
        return irproto.rc5(D, F)
    if pl == "rc6":
        return irproto.rc6(D, F)
    if pl == "sony12":
        return irproto.sirc(D, F, 12)
    if pl == "sony15":
        return irproto.sirc(D, F, 15)
    if pl == "sony20":
        addr = (D & 0x1F) | (((S & 0xFF) << 5) if S >= 0 else 0)
        return irproto.sirc(addr, F, 20)
    if pl == "jvc":
        return irproto.jvc(D, F)
    return None


def render_row(row: Row):
    return render(row.protocol, row.device, row.subdevice, row.function)


# --------------------------------------------------------------------------
# Tree navigation
# --------------------------------------------------------------------------

def list_brands():
    base = base_dir()
    if not base:
        return []
    return sorted((n for n in os.listdir(base)
                   if os.path.isdir(os.path.join(base, n))), key=str.lower)


def list_devices(brand):
    """Return [(label, csv_path)] for a brand, across its device-type dirs."""
    base = base_dir()
    out = []
    bdir = os.path.join(base, brand)
    if not os.path.isdir(bdir):
        return out
    for typ in sorted(os.listdir(bdir), key=str.lower):
        tdir = os.path.join(bdir, typ)
        if not os.path.isdir(tdir):
            continue
        for name in sorted(os.listdir(tdir)):
            if name.endswith(".csv"):
                label = "%s  [%s]" % (typ.replace("_", " "), name[:-4])
                out.append((label, os.path.join(tdir, name)))
    return out


def read_csv(path):
    rows = []
    try:
        with open(path, newline="", errors="replace") as f:
            r = csv.reader(f)
            next(r, None)  # header
            for rec in r:
                if len(rec) < 5:
                    continue
                try:
                    rows.append(Row(rec[0], rec[1], int(rec[2]),
                                    int(rec[3]), int(rec[4])))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


# --------------------------------------------------------------------------
# Coverage report (python3 -m rabbitblaster.irdb)
# --------------------------------------------------------------------------

def _coverage():
    base = base_dir()
    if not base:
        print("irdb not found; checked:", [c for c in BASE_CANDIDATES if c])
        return
    total = 0
    supp = 0
    by_proto = {}
    for root, _dirs, files in os.walk(base):
        for fn in files:
            if not fn.endswith(".csv"):
                continue
            for row in read_csv(os.path.join(root, fn)):
                total += 1
                ok = supported(row.protocol)
                supp += 1 if ok else 0
                key = row.protocol.strip()
                d = by_proto.setdefault(key, [0, ok])
                d[0] += 1
    print("irdb base: %s" % base)
    print("total codes: %d   transmittable now: %d (%.1f%%)"
          % (total, supp, 100.0 * supp / max(1, total)))
    print("top unsupported protocols:")
    uns = sorted(((n, c) for n, (c, ok) in by_proto.items() if not ok),
                 key=lambda x: -x[1])
    for n, c in uns[:15]:
        print("  %6d  %s" % (c, n))


if __name__ == "__main__":
    _coverage()
