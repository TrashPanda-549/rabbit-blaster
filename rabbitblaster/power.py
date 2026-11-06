"""External IR-board power control: Cardputer Zero + Rabbit Labs COBRA Commander.

The COBRA Commander is a 5V board (10 high-power IR LEDs). It draws power from
the expansion header's switched 5V: ext_usb_gpio_fun=0, ext_5v_out=1,
grove_5v_out=1, and GPIO26 driven HIGH and held for the app's lifetime.

Its IR-TX line is Pi GPIO14 and is ACTIVE-HIGH: the LED ring is ON while the
line is high. Anything that leaves GPIO14 high at idle (the mini-UART idles
high, for one) holds the ring at full 5V and overheats it.

SAFETY INTERLOCK: enable() reads the *running* device tree and refuses to power
the board unless gpio-ir-tx is on GPIO14 and active-high (idle LOW = ring off).
It fails safe: any uncertainty -> no power.
"""

from __future__ import annotations

import glob
import struct
import sys

_PWR_GPIO = 26
_IR_TX_GPIO = 14
_RAILS_ON = (
    ("/sys/class/leds/ext_usb_gpio_fun/brightness", "0"),
    ("/sys/class/leds/ext_5v_out/brightness", "1"),
    ("/sys/class/leds/grove_5v_out/brightness", "1"),
)
_RAILS_OFF = ("/sys/class/leds/ext_5v_out/brightness",
              "/sys/class/leds/grove_5v_out/brightness")

_req = None
_chip = None


def ir_tx_config():
    """Return (pin, active_low) of the running gpio-ir-tx, or None."""
    nodes = glob.glob("/proc/device-tree/gpio-ir-transmitter*/gpios")
    nodes += glob.glob("/proc/device-tree/*/gpio-ir-transmitter*/gpios")
    for node in nodes:
        try:
            data = open(node, "rb").read()
            if len(data) < 12 or len(data) % 4:
                continue
            cells = struct.unpack(">%dI" % (len(data) // 4), data)
            return cells[-2], bool(cells[-1] & 1)
        except Exception:
            continue
    return None


def ir_tx_safe() -> bool:
    """True only if gpio-ir-tx is on GPIO14 and active-high (idle low)."""
    cfg = ir_tx_config()
    return cfg is not None and cfg[0] == _IR_TX_GPIO and not cfg[1]


def _write(path, val):
    try:
        with open(path, "w") as f:
            f.write(val)
        return True
    except Exception as e:
        print("power: write %s failed: %s" % (path, e), file=sys.stderr)
        return False


def enable() -> bool:
    """Power the board, but only if the IR line is confirmed safe at idle."""
    global _req, _chip
    if not ir_tx_safe():
        print("power: REFUSING to power the board - gpio-ir-tx is not on GPIO14 "
              "active-high (cfg=%s). The ring would be held on and overheat. "
              "Fix config.txt and reboot. Board left unpowered (safe)."
              % (ir_tx_config(),), file=sys.stderr)
        return False
    # Claim the enable line FIRST. If another instance already owns board
    # power, this fails and we must not touch the rails it depends on.
    try:
        import gpiod
        from gpiod.line import Direction, Value
        _chip = gpiod.Chip("/dev/gpiochip0")
        s = gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE)
        _req = _chip.request_lines(config={_PWR_GPIO: s}, consumer="rabbit-blaster")
    except Exception as e:
        print("power: GPIO26 unavailable (%s) - another instance likely owns board "
              "power; rails left untouched." % e, file=sys.stderr)
        _req = None
        _chip = None
        return False
    for path, val in _RAILS_ON:
        _write(path, val)
    print("power: board enabled (5V rails on, GPIO26 high; IR idles low).")
    return True


def disable():
    """Cut board power: drive GPIO26 low, release it, switch the 5V rails off."""
    global _req, _chip
    try:
        if _req is not None:
            from gpiod.line import Value
            _req.set_value(_PWR_GPIO, Value.INACTIVE)
            _req.release()
    except Exception:
        pass
    _req = None
    _chip = None
    for path in _RAILS_OFF:
        _write(path, "0")
