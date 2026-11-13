"""IR protocol encoders: turn (protocol, address, command) into a carrier
frequency and a list of microsecond durations (pulse, space, pulse, ... )
suitable for raw transmission via ir-ctl / LIRC.

The duration list always starts with a pulse (mark) and ends with a pulse,
so it is valid for `ir-ctl --send` (which requires pulse-terminated data).

Flipper-style encoders: NEC, NECext, Samsung32, SIRC (Sony 12/15/20), RC5,
RC6 (mode 0). The irdb long tail (Panasonic, Denon, Sharp, Mitsubishi, Aiwa,
MCE, Pioneer, ...) is in the second half of this file; those follow the IRP
definitions in IrpTransmogrifier's IrpProtocols.xml, which is where irdb's
protocol names come from. Anything else is carried as a `raw` Flipper entry
(see flipperir.py).
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
    # one_frame currently ends with a space; frames start every 45 ms.
    used = sum(one_frame)
    gap = max(45000 - used, 5000)

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
# irdb long tail. Each function takes irdb's (device, subdevice, function)
# numbers and returns one complete key press; subdevice < 0 means "not given".
# --------------------------------------------------------------------------

def _field_bits(fields, msb=False):
    """Flatten [(value, nbits), ...] into a bit list, LSB-first unless msb."""
    out = []
    for value, n in fields:
        value &= (1 << n) - 1
        out += _msb_bits(value, n) if msb else _lsb_bits(value, n)
    return out


def _pd(unit, lead, fields, zero=(1, 1), one=(1, 3), msb=False, tail=1):
    """One pulse-distance frame, in multiples of `unit` us, ending on a mark.

    lead: leading (mark, space, ...) multipliers; zero/one: (mark, space)
    multipliers per bit; tail: closing mark multiplier.
    """
    durs = [x * unit for x in lead]
    for b in _field_bits(fields, msb):
        m, sp = one if b else zero
        durs += [m * unit, sp * unit]
    durs.append(tail * unit)
    return durs


def _join(frames, gap=None, period=None):
    """Concatenate mark-terminated frames, separated by a fixed gap (us) or
    padded so each frame starts `period` us after the previous one."""
    out = []
    for i, fr in enumerate(frames):
        out += fr
        if i != len(frames) - 1:
            out.append(gap if gap is not None else max(period - sum(fr), 5000))
    return out


def _sub(device, subdevice):
    """NEC-style default: missing subdevice is the complement of the device."""
    return subdevice if subdevice is not None and subdevice >= 0 else (~device) & 0xFF


def necx(device, subdevice, function):
    """NECx1 / NECx2: NEC data behind a 4.5 ms / 4.5 ms header."""
    f = [(device, 8), (_sub(device, subdevice), 8), (function, 8), (~function, 8)]
    return 38400, _finish(_pd(564, (8, 8), f))


def nec_yamaha(device, subdevice, function, y):
    """NEC1-y1/y2/y3: NEC1 with two bits of the check byte altered."""
    e0 = ((~y >> 1) & 1) ^ (function & 1)
    e7 = (~y & 1) ^ ((function >> 7) & 1)
    f = [(device, 8), (_sub(device, subdevice), 8), (function, 8),
         (e0, 1), (~function >> 1, 6), (e7, 1)]
    return 38400, _finish(_pd(564, (16, 8), f))


def pioneer(device, subdevice, function):
    f = [(device, 8), (_sub(device, subdevice), 8), (function, 8), (~function, 8)]
    return 40000, _finish(_pd(564, (16, 8), f))


def tivo(function, unit=0):
    f = [(133, 8), (48, 8), (function, 8), (unit, 4), (~function >> 4, 4)]
    return 38400, _finish(_pd(564, (16, 8), f))


def aiwa(device, subdevice, function):
    s = max(subdevice, 0)
    f = [(device, 8), (s, 5), (~device, 8), (~s, 5), (function, 8), (~function, 8)]
    return 38123, _finish(_pd(550, (16, 8), f))


def dgtec(device, function):
    f = [(device, 8), (function, 8), (~function, 8)]
    return 38000, _finish(_pd(560, (16, 8), f))


def proton(device, function):
    u = 500
    durs = _pd(u, (16, 8), [(device, 8)]) + [8 * u] + _pd(u, (), [(function, 8)])
    return 38500, _finish(durs)


def _kaseikyo(fields):
    """Kaseikyo family: 37 kHz, 432 us unit, 8/4 header."""
    return 37000, _finish(_pd(432, (8, 4), fields))


def panasonic(device, subdevice, function):
    s = max(subdevice, 0)
    return _kaseikyo([(2, 8), (32, 8), (device, 8), (s, 8), (function, 8),
                      (device ^ s ^ function, 8)])


def jvc48(device, subdevice, function):
    s = max(subdevice, 0)
    return _kaseikyo([(3, 8), (1, 8), (device, 8), (s, 8), (function, 8),
                      (device ^ s ^ function, 8)])


def denon_k(device, subdevice, function):
    s = max(subdevice, 0)
    check = ((device * 16) ^ s ^ (function * 16) ^ (function >> 4)) & 0xFF
    return _kaseikyo([(84, 8), (50, 8), (0, 4), (device, 4), (s, 4),
                      (function, 12), (check, 8)])


def fujitsu(device, subdevice, function):
    s = subdevice if subdevice >= 0 else device
    return _kaseikyo([(20, 8), (99, 8), (0, 4), (0, 4), (device, 8), (s, 8),
                      (function, 8)])


def _two_part(device, function, tag1, tag2):
    """Denon / Sharp: the frame, then the same frame with F inverted, 67 ms
    apart. Receivers act only on the matching pair."""
    kw = dict(zero=(1, 3), one=(1, 7))
    a = _pd(264, (), [(device, 5), (function, 8), (tag1, 2)], **kw)
    b = _pd(264, (), [(device, 5), (~function, 8), (tag2, 2)], **kw)
    return 38000, _finish(_join([a, b], period=67000))


def denon(device, function):
    return _two_part(device, function, 0, 3)


def sharp(device, function):
    return _two_part(device, function, 1, 2)


def mitsubishi(device, function):
    fr = _pd(300, (), [(device, 8), (function, 8)], zero=(1, 3), one=(1, 7))
    return 32600, _finish(_join([fr, fr], gap=80 * 300))


def akai(device, function):
    fr = _pd(289, (), [(device, 3), (function, 7)], zero=(1, 2.6), one=(1, 6.3))
    return 38000, _finish(_join([fr, fr], period=25300))


def thomson(device, function):
    f = [(device, 4), (0, 1), (device >> 4, 1), (function, 6)]
    fr = _pd(500, (), f, zero=(1, 4), one=(1, 9))
    return 33000, _finish(fr)


def recs80(device, function):
    f = [(1, 1), (0, 1), (device, 3), (function, 6)]
    return 38000, _finish(_pd(158, (), f, zero=(1, 31), one=(1, 47), msb=True))


def velleman(device, function):
    f = [(1, 1), (0, 1), (device, 3), (function, 6)]
    fr = _pd(1, (), f, zero=(700, 5060), one=(700, 7590), msb=True, tail=700)
    return 38000, _finish(fr)


def _dfdf(carrier, unit, n, device, function):
    """Panasonic_Old / Emerson / ScAtl-6: D, F, ~D, ~F behind a 4/4 header."""
    f = [(device, n), (function, 6), (~device, n), (~function, 6)]
    return carrier, _finish(_pd(unit, (4, 4), f))


def panasonic_old(device, function):
    return _dfdf(57600, 833, 5, device, function)


def emerson(device, function):
    return _dfdf(36700, 872, 6, device, function)


def scatl6(device, function):
    return _dfdf(57600, 846, 6, device, function)


def rca(device, function, carrier=58000, old=False):
    f = [(device, 4), (function, 8), (~device, 4), (~function, 8)]
    fr = _pd(460, (40, 8) if old else (8, 8), f, zero=(1, 2), one=(1, 4),
             msb=True, tail=2 if old else 1)
    return carrier, _finish(fr)


def gi_cable(device, function):
    check = -(device + (function & 15) + ((function >> 4) & 15))
    f = [(function, 8), (device, 4), (check, 4)]
    fr = _pd(490, (18, 9), f, zero=(1, 4.5), one=(1, 9))
    return 38700, _finish(fr)


def dish_network(device, subdevice, function):
    """Lead-in, then the frame three times (receivers ignore a single frame).
    F goes out MSB-first, S and D LSB-first."""
    u = 406
    bits = (_msb_bits(function & 63, 6) + _lsb_bits(max(subdevice, 0), 5)
            + _lsb_bits(device, 5))
    fr = []
    for b in bits:
        fr += [u, (4 if b else 7) * u]
    fr.append(u)
    return 57600, _finish([u, 15 * u] + _join([fr, fr, fr], gap=15 * u))


def directv(device, function):
    """DirecTV, 38 kHz variant: two bits per mark/space pair, MSB-first."""
    u = 600
    check = (7 * ((function >> 6) & 3) + 5 * ((function >> 4) & 3)
             + 3 * ((function >> 2) & 3) + (function & 3)) & 15
    bits = _field_bits([(device, 4), (function, 8), (check, 4)], msb=True)
    durs = [10 * u, 2 * u]
    for i in range(0, len(bits), 2):
        durs += [(2 if bits[i] else 1) * u, (2 if bits[i + 1] else 1) * u]
    durs.append(u)
    return 38000, _finish(durs)


def _rc6_frame(mode, payload_bits):
    """RC6 Manchester frame: leader, start bit, 3 mode bits, double-width
    toggle (sent as 0), then the payload MSB-first. 1 = mark then space."""
    u = 444
    segs = [(1, 6 * u), (0, 2 * u)]
    frame = [(1, 1)] + [(b, 1) for b in _msb_bits(mode, 3)] + [(0, 2)]
    frame += [(b, 1) for b in payload_bits]
    for b, w in frame:
        if b:
            segs.append((1, u * w)); segs.append((0, u * w))
        else:
            segs.append((0, u * w)); segs.append((1, u * w))
    return 36000, _finish(_segments_to_durations(segs))


def mce(device, subdevice, function):
    """MCE (RC6 mode 6, 32 bits): OEM1 = 128, OEM2 = subdevice, toggle 0."""
    payload = _field_bits([(128, 8), (max(subdevice, 0), 8), (0, 1),
                           (device, 7), (function, 8)], msb=True)
    return _rc6_frame(6, payload)


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
