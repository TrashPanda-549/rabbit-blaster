"""IR protocol encoders: turn (protocol, address, command) into a carrier
frequency and a list of microsecond durations (pulse, space, pulse, ... )
suitable for raw transmission via ir-ctl / LIRC.

The duration list always starts with a pulse (mark) and ends with a pulse,
so it is valid for `ir-ctl --send` (which requires pulse-terminated data).

Implemented: NEC, NECext, Samsung32, SIRC (Sony 12/15/20), RC5, RC6 (mode 0).
Everything else should be carried as a `raw` Flipper entry (see flipperir.py).
"""

from __future__ import annotations

# Inter-frame gap (us) inserted between repeated frames.
_GAP = 40000


def _finish(durs):
    """Ensure the sequence ends on a pulse (odd length)."""
    if len(durs) % 2 == 0:
        durs = durs[:-1]
    return [int(round(d)) for d in durs]


def _lsb_bits(byte, n=8):
    return [(byte >> i) & 1 for i in range(n)]


def _msb_bits(value, n):
    return [(value >> (n - 1 - i)) & 1 for i in range(n)]


def _segments_to_durations(segs):
    """Merge consecutive same-level segments and emit a pulse-first list.

    segs: list of (level, duration_us), level 1 = pulse (mark), 0 = space.
    Idle is low, so any leading space is dropped.
    """
    merged = []
    for level, dur in segs:
        if merged and merged[-1][0] == level:
            merged[-1][1] += dur
        else:
            merged.append([level, dur])
    while merged and merged[0][0] == 0:
        merged.pop(0)
    return [d for _, d in merged]


# --------------------------------------------------------------------------
# Pulse-distance protocols (NEC family, Samsung)
# --------------------------------------------------------------------------

def _pulse_distance(header, bits, one, zero, mark, trailer_mark=True):
    durs = list(header)
    for b in bits:
        durs.append(mark)
        durs.append(one if b else zero)
    if trailer_mark:
        durs.append(mark)
    return durs


def nec(address, command):
    bits = (_lsb_bits(address & 0xFF) + _lsb_bits((~address) & 0xFF)
            + _lsb_bits(command & 0xFF) + _lsb_bits((~command) & 0xFF))
    durs = _pulse_distance([9000, 4500], bits, 1690, 560, 560)
    return 38000, _finish(durs)


def necext(address, command):
    # 16-bit address (not complemented) + command + ~command
    bits = (_lsb_bits(address & 0xFF) + _lsb_bits((address >> 8) & 0xFF)
            + _lsb_bits(command & 0xFF) + _lsb_bits((~command) & 0xFF))
    durs = _pulse_distance([9000, 4500], bits, 1690, 560, 560)
    return 38000, _finish(durs)


def samsung32(address, command):
    bits = (_lsb_bits(address & 0xFF) + _lsb_bits(address & 0xFF)
            + _lsb_bits(command & 0xFF) + _lsb_bits((~command) & 0xFF))
    durs = _pulse_distance([4500, 4500], bits, 1690, 560, 560)
    return 38000, _finish(durs)


def build_nec(device, subdevice, function):
    """NEC with explicit device/subdevice/function (irdb semantics).
    subdevice < 0 means 'not given' -> use ~device as the second byte."""
    s = subdevice if (subdevice is not None and subdevice >= 0) else (~device) & 0xFF
    bits = (_lsb_bits(device & 0xFF) + _lsb_bits(s & 0xFF)
            + _lsb_bits(function & 0xFF) + _lsb_bits((~function) & 0xFF))
    durs = _pulse_distance([9000, 4500], bits, 1690, 560, 560)
    return 38000, _finish(durs)


def jvc(device, function):
    bits = _lsb_bits(device & 0xFF) + _lsb_bits(function & 0xFF)
    durs = _pulse_distance([8400, 4200], bits, 1578, 526, 526)
    return 38000, _finish(durs)


# --------------------------------------------------------------------------
# Sony SIRC (pulse-width coded, 40 kHz, send 3 frames)
# --------------------------------------------------------------------------

def sirc(address, command, nbits=12, frames=3):
    if nbits == 12:
        cmd_n, addr_n = 7, 5
    elif nbits == 15:
        cmd_n, addr_n = 7, 8
    elif nbits == 20:
        cmd_n, addr_n = 7, 13  # 5 addr + 8 extended, packed together LSB-first
    else:
        raise ValueError("SIRC nbits must be 12/15/20")

    bits = _lsb_bits(command, cmd_n) + _lsb_bits(address, addr_n)

    one_frame = [2400, 600]  # header mark, space
    for b in bits:
        one_frame.append(1200 if b else 600)
        one_frame.append(600)
    # one_frame currently ends with a space; frame period is ~45 ms.
    used = sum(one_frame)
    gap = max(_GAP, 45000 - used)

    durs = []
    for i in range(frames):
        durs.extend(one_frame)
        if i != frames - 1:
            # extend the trailing space to make up the 45 ms period
            durs[-1] += gap
    return 40000, _finish(durs)


# --------------------------------------------------------------------------
# Manchester protocols (RC5 / RC6)
# --------------------------------------------------------------------------

def rc5(address, command):
    """Standard 14-bit RC5. field bit = 1 for commands 0..63."""
    half = 889
    toggle = 0
    field = 1 if command < 64 else 0
    cmd6 = command & 0x3F
    frame = [1, field, toggle] + _msb_bits(address & 0x1F, 5) + _msb_bits(cmd6, 6)
    segs = []
    for b in frame:
        # IEEE Manchester: 1 = space then mark, 0 = mark then space
        if b:
            segs.append((0, half)); segs.append((1, half))
        else:
            segs.append((1, half)); segs.append((0, half))
    return 36000, _finish(_segments_to_durations(segs))


def rc6(address, command):
    """RC6 mode 0 (customer/command), 36 kHz. Toggle bit is double width."""
    u = 444
    segs = [(1, 6 * u), (0, 2 * u)]  # leader
    # start bit = 1, then 3 mode bits = 000
    frame = [1, 0, 0, 0]
    widths = [1, 1, 1, 1]
    # toggle bit (double width)
    frame.append(0)
    widths.append(2)
    # 8-bit address + 8-bit command, MSB first, normal width
    for b in _msb_bits(address & 0xFF, 8) + _msb_bits(command & 0xFF, 8):
        frame.append(b)
        widths.append(1)
    for b, w in zip(frame, widths):
        half = u * w
        # RC6 Manchester: 1 = mark then space, 0 = space then mark
        if b:
            segs.append((1, half)); segs.append((0, half))
        else:
            segs.append((0, half)); segs.append((1, half))
    return 36000, _finish(_segments_to_durations(segs))


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------

_PROTOCOLS = {
    "NEC": lambda a, c: nec(a[0], c[0]),
    "NECext": lambda a, c: necext(a[0] | (a[1] << 8), c[0]),
    "NEC42": lambda a, c: necext(a[0] | (a[1] << 8), c[0]),
    "NEC42ext": lambda a, c: necext(a[0] | (a[1] << 8), c[0]),
    "Samsung32": lambda a, c: samsung32(a[0], c[0]),
    "SIRC": lambda a, c: sirc(a[0], c[0], 12),
    "SIRC15": lambda a, c: sirc(a[0], c[0], 15),
    "SIRC20": lambda a, c: sirc(a[0] | (a[1] << 8), c[0], 20),
    "RC5": lambda a, c: rc5(a[0], c[0]),
    "RC5X": lambda a, c: rc5(a[0], c[0]),
    "RC6": lambda a, c: rc6(a[0], c[0]),
}

SUPPORTED = sorted(_PROTOCOLS)


def encode(protocol, address_bytes, command_bytes):
    """Return (carrier_hz, durations[us]) for a parsed protocol signal.

    address_bytes / command_bytes are little-endian byte lists as they appear
    in a Flipper .ir file. Raises KeyError for unsupported protocols.
    """
    key = protocol.strip()
    if key not in _PROTOCOLS:
        raise KeyError(protocol)
    a = list(address_bytes) + [0, 0, 0, 0]
    c = list(command_bytes) + [0, 0, 0, 0]
    return _PROTOCOLS[key](a, c)
