"""Rabbit Blaster main app: framebuffer UI + Cardputer keyboard to browse
the irdb database (648 brands) and Flipper .ir remotes, and transmit on
/dev/lirc0.

    python3 -m rabbitblaster.app
    python3 -m rabbitblaster.app --screenshot /tmp/rb.png --screen brands --filter sony
"""

from __future__ import annotations

import argparse
import glob
import os
import time

from . import flipperir, irdb, irsend, power, ui


# --------------------------------------------------------------------------
# Flipper .ir remote discovery
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Generic list page with optional type-to-filter
# --------------------------------------------------------------------------

class Page:
    def __init__(self, title, items, on_select, subtitle="", enabled=None,
                 filterable=False):
        self.title = title
        self.items = items
        self.on_select = on_select          # idx(into self.items) -> action|None
        self.base_subtitle = subtitle
        self.enabled = enabled
        self.filterable = filterable
        self.sel = 0
        self.filter = ""

    def view(self):
        if self.filterable and self.filter:
            idx = [i for i, it in enumerate(self.items)
                   if self.filter.lower() in it.lower()]
        else:
            idx = list(range(len(self.items)))
        items = [self.items[i] for i in idx]
        enabled = [self.enabled[i] for i in idx] if self.enabled else None
        return items, enabled, idx

    def subtitle(self):
        if self.filterable and self.filter:
            return "/" + self.filter
        return self.base_subtitle


class App:
    # The COBRA Commander's 10-LED driver latches on if sends are fired
    # back-to-back; enforce a cooldown so the ring is never held on.
    MIN_SEND_GAP = 1.5
    SETTLE_S = 0.3   # power-on -> send delay so inrush and LED burst don't coincide

    def __init__(self, fb, keypad, remotes, device=irsend.DEFAULT_DEVICE, repeats=1):
        self.fb = fb
        self.kp = keypad
        self.remotes = remotes
        self.device = device
        self.repeats = repeats
        self._last_send = 0.0

    # -- page builders --
    def home(self):
        entries = []
        if irdb.available():
            n = len(irdb.list_brands())
            entries.append(("IRDB  (%d brands)" % n, lambda: ("push", self.brands_page())))
        for name, path in self.remotes:
            entries.append((".ir  " + name,
                            (lambda p: (lambda: ("push", self.buttons_page(os.path.splitext(os.path.basename(p))[0], p))))(path)))
        labels = [e[0] for e in entries]
        cbs = [e[1] for e in entries]
        if not labels:
            labels = ["(no IRDB and no .ir remotes found)"]
            cbs = [lambda: None]
        return Page("RABBIT BLASTER", labels, lambda i: cbs[i](),
                    subtitle="%d sources" % len(entries))

    def brands_page(self):
        brands = irdb.list_brands()
        return Page("IRDB brands", brands,
                    lambda i: ("push", self.devices_page(brands[i])),
                    subtitle="%d" % len(brands), filterable=True)

    def devices_page(self, brand):
        devs = irdb.list_devices(brand)
        labels = [d[0] for d in devs]
        return Page(brand[:20], labels,
                    lambda i: ("push", self.functions_page(brand, devs[i][1])),
                    subtitle="%d" % len(labels), filterable=len(labels) > 8)

    def functions_page(self, brand, path):
        rows = irdb.read_csv(path)
        labels = [r.name for r in rows]
        enabled = [irdb.supported(r.protocol) for r in rows]

        def on_select(i):
            res = irdb.render_row(rows[i])
            if not res:
                return None
            c, d = res
            return ("transmit", (c, d, rows[i].name))

        return Page(brand[:20], labels, on_select, subtitle="%d keys" % len(labels),
                    enabled=enabled, filterable=len(labels) > 8)

    def buttons_page(self, name, path):
        sigs = flipperir.parse(path)
        labels = [s.name for s in sigs]
        enabled = [s.transmittable() for s in sigs]

        def on_select(i):
            if not sigs[i].transmittable():
                return None
            c, d = sigs[i].render()
            return ("transmit", (c, d, sigs[i].name))

        return Page(name[:20], labels, on_select, subtitle="%d keys" % len(labels),
                    enabled=enabled, filterable=len(labels) > 8)

    # -- main loop --
    def run(self):
        stack = [self.home()]
        while stack:
            page = stack[-1]
            items, enabled, idx = page.view()
            if page.sel >= len(items):
                page.sel = max(0, len(items) - 1)
            hint = ("type=filter  Tab move  OK  ESC back" if page.filterable
                    else "Tab/arrows move  OK pick  ESC back")
            self.fb.show(ui.list_screen(page.title, items, page.sel,
                                        subtitle=page.subtitle(), enabled=enabled,
                                        hint=hint))
            kind, val = self.kp.wait()
            if kind == "nav":
                if val == "UP" and items:
                    page.sel = (page.sel - 1) % len(items)
                elif val == "DOWN" and items:
                    page.sel = (page.sel + 1) % len(items)
                elif val == "LEFT":
                    if len(stack) > 1:
                        stack.pop()
                elif val == "RIGHT":
                    self._activate(page, items, idx, stack)
            elif kind == "ok":
                self._activate(page, items, idx, stack)
            elif kind == "back":
                stack.pop()
            elif kind == "bksp":
                if page.filterable and page.filter:
                    page.filter = page.filter[:-1]
                    page.sel = 0
                else:
                    stack.pop()
            elif kind == "char" and page.filterable:
                page.filter += val
                page.sel = 0

    def _activate(self, page, items, idx, stack):
        if not items:
            return
        action = page.on_select(idx[page.sel])
        if not action:
            return
        if action[0] == "push":
            stack.append(action[1])
        elif action[0] == "transmit":
            carrier, durs, label = action[1]
            if time.time() - self._last_send < self.MIN_SEND_GAP:
                self._flash("Wait", "cooling down", ui.ACCENT)
                return
            # The board is powered ONLY for the duration of a send, never at
            # idle: enable (interlock-checked) -> transmit -> cut power.
            try:
                if not power.enable():
                    raise irsend.IRError("board power refused by interlock")
                try:
                    # Let the 5V rail / board caps charge before the LED burst;
                    # inrush + burst together sag the supply and reset the Pi.
                    time.sleep(self.SETTLE_S)
                    irsend.send(carrier, durs, device=self.device, repeats=self.repeats)
                finally:
                    power.disable()
                self._last_send = time.time()
                self._flash("SENT", label, ui.ACCENT2)
            except irsend.IRError as e:
                self._flash("TX ERROR", str(e), ui.ACCENT)

    def _flash(self, big, sub, color):
        self.fb.show(ui.message_screen(big, sub, color))
        time.sleep(0.7)


# --------------------------------------------------------------------------
# Screenshot preview (no hardware)
# --------------------------------------------------------------------------

def _screenshot(args):
    remotes = collect_remotes(args.remotes)
    app = App(None, None, remotes)
    if args.screen == "brands":
        page = app.brands_page()
    elif args.screen == "devices":
        page = app.devices_page(args.brand or (irdb.list_brands() or ["?"])[0])
    elif args.screen == "functions":
        brand = args.brand or (irdb.list_brands() or ["?"])[0]
        devs = irdb.list_devices(brand)
        page = app.functions_page(brand, devs[0][1]) if devs else app.home()
    else:
        page = app.home()
    if args.filter:
        page.filter = args.filter
    items, enabled, _ = page.view()
    img = ui.list_screen(page.title, items, args.select, subtitle=page.subtitle(),
                         enabled=enabled)
    img.save(args.screenshot)
    print("wrote %s (%dx%d), %d rows" % (args.screenshot, img.width, img.height, len(items)))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rabbitblaster.app")
    ap.add_argument("--fb", default="/dev/fb0")
    ap.add_argument("--keyboard", default=None)
    ap.add_argument("--device", default=irsend.DEFAULT_DEVICE)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--remotes", default=None)
    ap.add_argument("--screenshot", default=None)
    ap.add_argument("--screen", choices=["home", "brands", "devices", "functions"],
                    default="home")
    ap.add_argument("--brand", default=None)
    ap.add_argument("--filter", default="")
    ap.add_argument("--select", type=int, default=0)
    args = ap.parse_args(argv)

    if args.screenshot:
        _screenshot(args)
        return 0

    from .framebuffer import Framebuffer
    from .keypad import Keypad
    fb = Framebuffer(args.fb)
    kp = Keypad(args.keyboard)
    try:
        App(fb, kp, collect_remotes(args.remotes), device=args.device,
            repeats=args.repeats).run()
    finally:
        kp.close()
        fb.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
