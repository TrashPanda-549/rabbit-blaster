"""CLI for testing the Rabbit Blaster IR engine without the UI.

  python3 -m rabbitblaster.sendcli FILE.ir --list
  python3 -m rabbitblaster.sendcli FILE.ir --name Power [--repeats 2] [--device /dev/lirc0]
  python3 -m rabbitblaster.sendcli FILE.ir --name Power --dry-run   # print durations only
"""

from __future__ import annotations

import argparse
import sys

from . import flipperir, irsend


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rabbitblaster.sendcli")
    ap.add_argument("file", help="Flipper .ir file")
    ap.add_argument("--name", help="signal (button) name to send")
    ap.add_argument("--list", action="store_true", help="list signals and exit")
    ap.add_argument("--device", default=irsend.DEFAULT_DEVICE)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true",
                    help="render and print the pulse train, do not transmit")
    args = ap.parse_args(argv)

    signals = flipperir.parse(args.file)
    if not signals:
        print("no signals parsed from %s" % args.file, file=sys.stderr)
        return 2

    if args.list or not args.name:
        for s in signals:
            flag = " " if s.transmittable() else "!"
            extra = s.protocol if s.type == "parsed" else "raw/%dHz/%dsym" % (s.frequency, len(s.data))
            print("%s %-20s %s" % (flag, s.name, extra))
        if not args.name:
            print("\n(use --name NAME to transmit; '!' = unsupported, carry as raw)")
        return 0

    matches = [s for s in signals if s.name == args.name]
    if not matches:
        print("no signal named %r" % args.name, file=sys.stderr)
        return 2
    sig = matches[0]
    if not sig.transmittable():
        print("signal %r (%s) is not transmittable by this build"
              % (sig.name, sig.protocol or sig.type), file=sys.stderr)
        return 3

    carrier, durs = sig.render()
    print("rendering %r: %s, carrier=%dHz, %d symbols"
          % (sig.name, sig.protocol or "raw", carrier, len(durs)))
    if args.dry_run:
        print(" ".join(str(d) for d in durs))
        return 0

    try:
        irsend.send(carrier, durs, device=args.device, repeats=args.repeats)
    except irsend.IRError as e:
        print("TX failed: %s" % e, file=sys.stderr)
        return 1
    print("sent %r via %s (x%d)"
          % (sig.name, args.device or irsend.find_tx_device(), args.repeats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
