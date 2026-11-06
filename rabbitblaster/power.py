"""External IR-board power control for the Cardputer Zero.

The Rabbit Labs IR board draws VCC from the ADV-compatible connector's
switched 5V. Powering it requires: ext_usb_gpio_fun=0, ext_5v_out=1,
grove_5v_out=1, and GPIO26 driven HIGH and held.

SAFETY INTERLOCK: the board's IR LED is active-low. If gpio-ir-tx is NOT
configured active-low (invert=1), the idle-low line holds the LED on and it
overheats. enable() therefore reads the *running* device tree and refuses to
power the board unless the IR transmitter is confirmed active-low. It fails
safe: any uncertainty -> no power.
"""

from __future__ import annotations

import glob
import struct
import sys

_PWR_GPIO = 26
_RAILS_ON = (
    ("/sys/class/leds/ext_usb_gpio_fun/brightness", "0"),
    ("/sys/class/leds/ext_5v_out/brightness", "1"),
    ("/sys/class/leds/grove_5v_out/brightness", "1"),
)
_RAILS_OFF = ("/sys/class/leds/ext_5v_out/brightness",
              "/sys/class/leds/grove_5v_out/brightness")

_req = None
_chip = None


def ir_is_active_low() -> bool:
    """True only if the running gpio-ir-tx uses GPIO_ACTIVE_LOW (invert=1).

    The gpios property is <phandle pin flags>; flags bit0 = active-low.
    Fail-safe: returns False on anything unexpected.
    """
    nodes = glob.glob("/proc/device-tree/gpio-ir-transmitter*/gpios")
    nodes += glob.glob("/proc/device-tree/*/gpio-ir-transmitter*/gpios")
    for node in nodes:
        try:
            data = open(node, "rb").read()
            if len(data) < 12 or len(data) % 4:
                continue
            cells = struct.unpack(">%dI" % (len(data) // 4), data)
            if cells[-1] & 1:
                return True
        except Exception:
            continue
    return False


def _write(path, val):
    try:
        with open(path, "w") as f:
            f.write(val)
        return True
    except Exception as e:
        print("power: write %s failed: %s" % (path, e), file=sys.stderr)
        return False


def enable() -> bool:
    """Power the board, but only if the IR line is confirmed active-low."""
    global _req, _chip
    if not ir_is_active_low():
        print("power: REFUSING to power board - gpio-ir-tx is not active-low "
              "(invert=1 not active in the running config). Set invert=1 and "
              "reboot first. Board left unpowered (safe).", file=sys.stderr)
        return False
    for path, val in _RAILS_ON:
        _write(path, val)
    try:
        import gpiod
        from gpiod.line import Direction, Value
        _chip = gpiod.Chip("/dev/gpiochip0")
        s = gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE)
        _req = _chip.request_lines(config={_PWR_GPIO: s}, consumer="rabbit-blaster")
        print("power: board enabled (rails on, GPIO26 high, IR active-low).")
        return True
    except Exception as e:
        print("power: GPIO26 request failed: %s" % e, file=sys.stderr)
        # back the rails off if we couldn't hold the enable line
        disable()
        return False


def disable():
    """Cut board power: release GPIO26 and switch the 5V rails off."""
    global _req, _chip
    try:
        if _req is not None:
            _req.release()
    except Exception:
        pass
    _req = None
    _chip = None
    for path in _RAILS_OFF:
        _write(path, "0")
