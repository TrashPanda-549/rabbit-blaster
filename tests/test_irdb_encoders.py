"""Check the irdb encoders against reference pulse trains.

tests/irp_vectors.json holds one rendering per irdb protocol name, produced by
IrpTransmogrifier 1.2.14 (`render --raw`): the carrier and the intro + repeat
timings. Our output must be a prefix of that train, within tolerance.

Run:  python tests/test_irdb_encoders.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from rabbitblaster import irdb  # noqa: E402


def close(a, b):
    return abs(a - b) <= max(30.0, 0.025 * max(a, b))


def main():
    with open(os.path.join(HERE, "irp_vectors.json")) as f:
        vectors = json.load(f)
    failed = 0
    for name, v in sorted(vectors.items()):
        carrier, durs = irdb.render(name, v["D"], v["S"], v["F"])
        ref = v["timings"]
        ok = (abs(carrier - v["freq"]) <= 0.015 * v["freq"]
              and len(durs) <= len(ref)
              and all(close(a, b) for a, b in zip(durs, ref)))
        if not ok:
            failed += 1
            print("FAIL %s D=%d S=%d F=%d" % (name, v["D"], v["S"], v["F"]))
    missing = sorted(set(irdb._ENCODERS) - {n.lower() for n in vectors})
    print("%d protocols checked, %d failed; encoders without a vector: %s"
          % (len(vectors), failed, missing or "none"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
