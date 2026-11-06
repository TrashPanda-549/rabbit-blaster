"""Rabbit Blaster main app: framebuffer UI + Cardputer keyboard to browse
Flipper .ir remotes and transmit codes on /dev/lirc0.

Run on the device (needs access to /dev/fb0, the keyboard, and /dev/lirc0):
    python3 -m rabbitblaster.app

Preview a screen without hardware:
    python3 -m rabbitblaster.app --screenshot /tmp/rb.png --screen buttons --remote sample
"""

from __future__ import annotations

import argparse
import glob
import os
import time

from . import flipperir, irsend, ui


def remote_dirs(extra=None):
    dirs = []
    if extra:
        dirs.append(extra)
    env = os.environ.get("RABBIT_BLASTER_REMOTES")
    if env:
        dirs.extend(env.split(os.pathsep))
    dirs += [
        os.path.expanduser("~/.rabbit-blaster/remotes"),
        os.path.expanduser("~/Documents/IR"),
        "/usr/share/rabbit-blaster/remotes",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "share", "remotes"),
    ]
    out, seen = [], set()
    for d in dirs:
        d = os.path.abspath(os.path.expanduser(d))
        if d not in seen and os.path.isdir(d):
            out.append(d)
            seen.add(d)
    return out


def collect_remotes(extra=None):
    found = {}
    for d in remote_dirs(extra):
        for f in sorted(glob.glob(os.path.join(d, "*.ir"))):
            name = os.path.splitext(os.path.basename(f))[0]
            found.setdefault(name, f)
    return sorted(found.items())


class App:
    def __init__(self, fb, keypad, remotes, device=irsend.DEFAULT_DEVICE, repeats=2):
        self.fb = fb
        self.kp = keypad
        self.remotes = remotes            # [(name, path)]
        self.device = device
        self.repeats = repeats

    def _draw(self, img):
        self.fb.show(img)

    def run(self):
        if not self.remotes:
            self._draw(ui.message_screen("No remotes", "Drop .ir files in ~/.rabbit-blaster/remotes",
                                         color=ui.ACCENT))
            while self.kp.wait() not in ("QUIT", "BACK"):
                pass
            return

        sel = 0
        while True:
            names = [r[0] for r in self.remotes]
            self._draw(ui.list_screen("RABBIT BLASTER", names, sel,
                                      subtitle="%d remotes" % len(names),
                                      hint="↑↓ pick   OK open   Q quit"))
            btn = self.kp.wait()
            if btn == "QUIT":
                return
            elif btn == "UP":
                sel = (sel - 1) % len(names)
            elif btn == "DOWN":
                sel = (sel + 1) % len(names)
            elif btn == "OK":
                self._buttons_screen(self.remotes[sel][0], self.remotes[sel][1])

    def _buttons_screen(self, name, path):
        try:
            signals = flipperir.parse(path)
        except Exception as e:
            self._flash("LOAD ERR", str(e), ui.ACCENT)
            return
        if not signals:
            self._flash("Empty", "no signals in file", ui.ACCENT)
            return

        labels = [s.name for s in signals]
        enabled = [s.transmittable() for s in signals]
        sel = 0
        while True:
            self._draw(ui.list_screen(name, labels, sel, subtitle="%d keys" % len(labels),
                                      enabled=enabled))
            btn = self.kp.wait()
            if btn in ("BACK", "QUIT"):
                return
            elif btn == "UP":
                sel = (sel - 1) % len(labels)
            elif btn == "DOWN":
                sel = (sel + 1) % len(labels)
            elif btn == "OK":
                self._transmit(signals[sel])

    def _transmit(self, sig):
        if not sig.transmittable():
            self._flash("Unsupported", "%s not encodable yet" % (sig.protocol or sig.type), ui.ACCENT)
            return
        try:
            irsend.send_signal(sig, device=self.device, repeats=self.repeats)
            self._flash("SENT", sig.name, ui.ACCENT2)
        except irsend.IRError as e:
            self._flash("TX ERROR", str(e), ui.ACCENT)

    def _flash(self, big, sub, color):
        self._draw(ui.message_screen(big, sub, color))
        time.sleep(0.7)


def _screenshot(args):
    remotes = collect_remotes(args.remotes)
    if args.screen == "buttons":
        path = dict(remotes).get(args.remote) or (remotes[0][1] if remotes else None)
        if not path:
            img = ui.message_screen("No remotes", "nothing to preview", ui.ACCENT)
        else:
            sigs = flipperir.parse(path)
            img = ui.list_screen(args.remote or os.path.basename(path),
                                 [s.name for s in sigs], args.select,
                                 subtitle="%d keys" % len(sigs),
                                 enabled=[s.transmittable() for s in sigs])
    else:
        names = [r[0] for r in remotes] or ["(none)"]
        img = ui.list_screen("RABBIT BLASTER", names, args.select,
                             subtitle="%d remotes" % len(remotes),
                             hint="↑↓ pick   OK open   Q quit")
    img.save(args.screenshot)
    print("wrote %s (%dx%d)" % (args.screenshot, img.width, img.height))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rabbitblaster.app")
    ap.add_argument("--fb", default="/dev/fb0")
    ap.add_argument("--keyboard", default=None)
    ap.add_argument("--device", default=irsend.DEFAULT_DEVICE, help="LIRC TX device")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--remotes", default=None, help="extra remotes directory")
    ap.add_argument("--screenshot", default=None, help="render a screen to PNG and exit")
    ap.add_argument("--screen", choices=["remotes", "buttons"], default="remotes")
    ap.add_argument("--remote", default=None, help="remote name for --screen buttons")
    ap.add_argument("--select", type=int, default=0)
    args = ap.parse_args(argv)

    if args.screenshot:
        _screenshot(args)
        return 0

    from .framebuffer import Framebuffer
    from .keypad import Keypad

    remotes = collect_remotes(args.remotes)
    fb = Framebuffer(args.fb)
    kp = Keypad(args.keyboard)
    try:
        App(fb, kp, remotes, device=args.device, repeats=args.repeats).run()
    finally:
        kp.close()
        fb.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
