"""External IR-board power control: Cardputer Zero + Rabbit Labs COBRA Commander.

Driven the SAME way the Cardputer ADV drives it (see docs/how-ir-works.md):
the board is just 5 V + ONE modulated IR data line. The ADV turns the header's
5 V on and routes the modulated 38 kHz/33 % IR signal out the "G3" transmit pad;
the board's 10 LEDs are driven straight off 5 V, gated by that line. It makes no
carrier of its own and has NO PWM-power input, so we do NOT PWM the rail.

On the Zero that means:
  - switched 5 V on: ext_usb_gpio_fun=0, ext_5v_out=1, grove_5v_out=1
  - GPIO26 held HIGH as the board enable (steady, not PWM)
  - the modulated gpio-ir-tx on the BCM pin wired to the G3 pad, idling LOW

Because the IR line idles LOW and the carrier is present only during marks (at
33 % duty), the LEDs are lit only a small fraction of the time -> the board
stays cool even with 5 V on. The old overheating came from the IR line being
held DC-HIGH on the wrong pin (GPIO14 = mini-UART, idles high), not from the
power rail.

SAFETY INTERLOCK: enable() reads the *running* device tree and refuses to power
the board unless gpio-ir-tx is active-high (so idle = LOW = ring off). Set
RB_IR_TX_GPIO=<bcm> to also pin it to a specific pad. Fails safe: any
uncertainty -> no power.
"""

from __future__ import annotations

import glob
import os
import struct
import sys

_PWR_GPIO = 26
# Optional: the BCM pin wired to the board's G3 transmit pad. When set, the
# interlock also checks gpio-ir-tx is on exactly this pin. Leave unset to accept
# any active-high gpio-ir-tx (the real safety property).
_EXPECT_TX_GPIO = os.environ.get("RB_IR_TX_GPIO")
_EXPECT_TX_GPIO = int(_EXPECT_TX_GPIO) if _EXPECT_TX_GPIO else None

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
    """True only if gpio-ir-tx is active-high (idle low), and on the expected
    pin when RB_IR_TX_GPIO is set."""
    cfg = ir_tx_config()
    if cfg is None or cfg[1]:            # missing, or active-low -> unsafe
        return False
    if _EXPECT_TX_GPIO is not None and cfg[0] != _EXPECT_TX_GPIO:
        return False
    return True


def _write(path, val):
    try:
        with open(path, "w") as f:
            f.write(val)
        return True
    except Exception as e:
        print("power: write %s failed: %s" % (path, e), file=sys.stderr)
        return False


def enable() -> bool:
    """Power the board (5 V on + GPIO26 high), only if the IR line idles low."""
    global _req, _chip
    if not ir_tx_safe():
        print("power: REFUSING to power the board - gpio-ir-tx is not confirmed "
              "active-high (idle low) %s(cfg=%s). The ring could be held on and "
              "overheat. Fix config.txt (gpio-ir-tx on the G3-pad BCM, "
              "enable_uart=0) and reboot. Board left unpowered (safe)."
              % ("on GPIO%s " % _EXPECT_TX_GPIO if _EXPECT_TX_GPIO else "",
                 ir_tx_config()), file=sys.stderr)
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
    print("power: board enabled (5V rails on, GPIO26 high; IR idles low) - "
          "ADV-style steady 5V, no PWM.")
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
