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

ip = irproto


def _sony20(d, s, f):
    return ip.sirc((d & 0x1F) | (((s & 0xFF) << 5) if s >= 0 else 0), f, 20)


# irdb protocol name (lower-case) -> encoder(device, subdevice, function).
_ENCODERS = {
    "nec": ip.build_nec, "nec1": ip.build_nec, "nec2": ip.build_nec,
    "necx1": ip.necx, "necx2": ip.necx,
    "nec1-y1": lambda d, s, f: ip.nec_yamaha(d, s, f, 1),
    "nec1-y2": lambda d, s, f: ip.nec_yamaha(d, s, f, 2),
    "nec1-y3": lambda d, s, f: ip.nec_yamaha(d, s, f, 3),
    "pioneer": ip.pioneer,
    "tivo unit=0": lambda d, s, f: ip.tivo(f, 0),
    "tivo unit=1": lambda d, s, f: ip.tivo(f, 1),
    "aiwa": ip.aiwa,
    "dgtec": lambda d, s, f: ip.dgtec(d, f),
    "proton": lambda d, s, f: ip.proton(d, f),
    "panasonic": ip.panasonic,
    "jvc-48": ip.jvc48,
    "denon-k": ip.denon_k,
    "fujitsu": ip.fujitsu,
    "denon": lambda d, s, f: ip.denon(d, f),
    "denon{1}": lambda d, s, f: ip.denon(d, f),
    "sharp": lambda d, s, f: ip.sharp(d, f),
    "sharp{1}": lambda d, s, f: ip.sharp(d, f),
    "mitsubishi": lambda d, s, f: ip.mitsubishi(d, f),
    "akai": lambda d, s, f: ip.akai(d, f),
    "thomson": lambda d, s, f: ip.thomson(d, f),
    "recs80": lambda d, s, f: ip.recs80(d, f),
    "velleman": lambda d, s, f: ip.velleman(d, f),
    "panasonic_old": lambda d, s, f: ip.panasonic_old(d, f),
    "emerson": lambda d, s, f: ip.emerson(d, f),
    "scatl-6": lambda d, s, f: ip.scatl6(d, f),
    "rca": lambda d, s, f: ip.rca(d, f),
    "rca-38": lambda d, s, f: ip.rca(d, f, carrier=38700),
    "rca(old)": lambda d, s, f: ip.rca(d, f, old=True),
    "rca-38(old)": lambda d, s, f: ip.rca(d, f, carrier=38700, old=True),
    "g.i.cable": lambda d, s, f: ip.gi_cable(d, f),
    "dish_network": ip.dish_network,
    "directv": lambda d, s, f: ip.directv(d, f),
    "mce": ip.mce,
    "rc5": lambda d, s, f: ip.rc5(d, f),
    "rc6": lambda d, s, f: ip.rc6(d, f),
    "sony12": lambda d, s, f: ip.sirc(d, f, 12),
    "sony15": lambda d, s, f: ip.sirc(d, f, 15),
    "sony20": _sony20,
    "jvc": lambda d, s, f: ip.jvc(d, f),
    "jvc{2}": lambda d, s, f: ip.jvc(d, f),
}


def base_dir():
    for d in BASE_CANDIDATES:
        if d and os.path.isdir(d):
            return d
    return None


def available():
    return base_dir() is not None


def supported(protocol) -> bool:
    return (protocol or "").strip().lower() in _ENCODERS


def render(protocol, device, subdevice, function):
    """Return (carrier_hz, durations[us]) or None if unsupported."""
    enc = _ENCODERS.get((protocol or "").strip().lower())
    if enc is None:
        return None
    return enc(int(device), int(subdevice), int(function))


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
