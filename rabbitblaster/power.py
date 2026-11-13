"""External IR-board power control: Cardputer Zero + Rabbit Labs COBRA Commander.

Driven the way the Cardputer ADV drives it (see docs/how-ir-works.md): the
board is 5 V plus ONE modulated IR data line on the header's "G3" pad. Its LEDs
run straight off 5 V, gated by that line, so the line must idle LOW.

On the Zero the G3 pad is BCM GPIO26 (ADV header: G3=RESET, G4=INT, G6=BUSY,
G13/G15=UART; M5's Zero cap drivers use GPIO23=IRQ, GPIO22=CS2, GPIO14/15=UART
and hold GPIO26 HIGH, which they call "power"). GPIO26 therefore belongs to the
kernel gpio-ir-tx driver and this module must never drive it: holding it HIGH
lights the whole ring at DC and overheats the board.

Power is only the switched header 5 V, the same recipe M5's cap drivers use:
ext_usb_gpio_fun=0, ext_5v_out=1 (grove_5v_out=1 is kept on as before).

SAFETY INTERLOCK: enable() reads the running device tree and refuses to switch
5 V on unless gpio-ir-tx is on the expected pin and active-high (idle LOW).
RB_IR_TX_GPIO overrides the expected pin.
"""

from __future__ import annotations

import glob
import os
import struct
import sys

IR_TX_GPIO = int(os.environ.get("RB_IR_TX_GPIO", "26"))

_RAILS_ON = (
    ("/sys/class/leds/ext_usb_gpio_fun/brightness", "0"),
    ("/sys/class/leds/ext_5v_out/brightness", "1"),
    ("/sys/class/leds/grove_5v_out/brightness", "1"),
)
_RAILS_OFF = ("/sys/class/leds/ext_5v_out/brightness",
              "/sys/class/leds/grove_5v_out/brightness")


def ir_tx_configs():
    """Return [(pin, active_low)] for every running gpio-ir-tx node. A unit with
    built-in IR has its own transmitter node besides the header one."""
    nodes = glob.glob("/proc/device-tree/gpio-ir-transmitter*/gpios")
    nodes += glob.glob("/proc/device-tree/*/gpio-ir-transmitter*/gpios")
    out = []
    for node in nodes:
        try:
            data = open(node, "rb").read()
            if len(data) < 12 or len(data) % 4:
                continue
            cells = struct.unpack(">%dI" % (len(data) // 4), data)
            out.append((cells[-2], bool(cells[-1] & 1)))
        except Exception:
            continue
    return out


def ir_tx_config():
    """Return (pin, active_low) of the gpio-ir-tx on IR_TX_GPIO, or None."""
    for cfg in ir_tx_configs():
        if cfg[0] == IR_TX_GPIO:
            return cfg
    return None


def ir_tx_safe() -> bool:
    """True only if gpio-ir-tx is on IR_TX_GPIO and active-high (idle low)."""
    cfg = ir_tx_config()
    return cfg is not None and cfg[0] == IR_TX_GPIO and not cfg[1]


def _write(path, val):
    try:
        with open(path, "w") as f:
            f.write(val)
        return True
    except Exception as e:
        print("power: write %s failed: %s" % (path, e), file=sys.stderr)
        return False


def enable() -> bool:
    """Switch the header 5 V on, only if the IR line is confirmed idle-low."""
    if not ir_tx_safe():
        print("power: REFUSING to power the board - gpio-ir-tx is not on GPIO%d "
              "active-high (found %s). The ring could be held on and overheat. "
              "Fix config.txt and reboot. Board left unpowered (safe)."
              % (IR_TX_GPIO, ir_tx_configs()), file=sys.stderr)
        return False
    for path, val in _RAILS_ON:
        _write(path, val)
    print("power: 5V on (IR line GPIO%d idles low)." % IR_TX_GPIO)
    return True


def disable():
    """Switch the header 5 V off."""
    for path in _RAILS_OFF:
        _write(path, "0")
