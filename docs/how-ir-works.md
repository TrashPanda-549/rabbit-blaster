# How IR Works at Its Core — and what it means for Rabbit Blaster

Research notes on consumer infrared (the kind a Flipper Zero / Cardputer blasts),
written to settle *why* the COBRA Commander wasn't transmitting and what the
correct drive scheme is. Sources are linked at the bottom.

---

## 1. Physical layer: it's a flashing LED, not steady light

An IR remote never shines a steady beam. It **flashes an IR LED at a carrier
frequency** — almost always **38 kHz** (the band runs ~30–58 kHz; RC5 uses
36 kHz, Sony 40 kHz). The receiver in the TV is a *tuned demodulator*
(TSOP-style): it only "hears" light that is blinking at its carrier frequency
and ignores everything else (sunlight, room lights, your hand). That carrier is
the whole reason IR is robust.

Two states carry all the information:

- **Mark** (a.k.a. pulse / burst) = carrier present → LED flashing at 38 kHz.
- **Space** = carrier absent → LED dark.

The **data is in the pattern and length of marks and spaces**, *not* in the
carrier. The carrier is just the "ink"; the marks/spaces are the writing.

**Carrier duty cycle** (how much of each 26 µs carrier period the LED is lit) is
typically **33 %**, not 50 %. 33 % still decodes fine and cuts LED current/heat
by a third — which matters a lot for a 10-LED blaster. We already send at 33 %.

## 2. Data layer: the encodings

Every protocol is just a different way of turning bits into mark/space timings:

| Protocol | Scheme | Notes |
|----------|--------|-------|
| **NEC** | pulse-distance | 9 ms leader + 4.5 ms space; fixed 562 µs marks; short space = 0, 3× space = 1; addr, ~addr, cmd, ~cmd; LSB first; repeat frame ~40 ms |
| **RC5** (Philips) | bi-phase / Manchester | fixed bit time, data in the mid-bit transition, 36 kHz |
| **Sony SIRC** | pulse-width | fixed space, mark length encodes the bit, 40 kHz |
| Samsung32, RC6, Kaseikyo (Panasonic), Denon… | variations | same idea, different timings/headers |

**Parsed vs raw** — the only two ways a code is ever stored:

- **Parsed**: you know the protocol, so you store `(protocol, address, command)`
  and *generate* the timings on the fly. Compact, and you can change a button.
- **Raw**: you just store the list of microsecond mark/space durations and
  replay them. Works for anything, even unknown remotes, but it's a fixed
  recording.

Both end up as the *identical* modulated waveform on the wire. This is exactly
what Rabbit Blaster's `irproto.py` (parsed encoders) and `flipperir.py` /
`irdb.py` (raw + table lookups) produce.

## 3. How the Flipper Zero does it (the reference design)

- **Hardware:** three IR LEDs driven *directly from the MCU* (STM32), plus a
  **TSOP-75338** demodulating receiver. No fancy driver IC on the Flipper itself.
- **Carrier:** an STM32 **hardware timer runs a 38 kHz / 33 % PWM** — that PWM
  *is* the carrier. (`furi_hal_infrared_async_tx_start` literally takes `freq`
  and `duty_cycle` for the PWM.)
- **Timing:** a **second timer (with DMA)** walks the mark/space timing table and
  **gates the carrier PWM on during marks, off during spaces**. Carrier PWM AND
  timing envelope → the modulated waveform. One pin out.
- **`.ir` files:** parsed (`NEC`, `Samsung32`, `RC5`, `RC6`, `SIRC`, `Kaseikyo`
  + `address`/`command`) or raw (`frequency: 38000`, `duty_cycle: 0.330000`,
  `data:` = µs timings, max 1024). Decoding is in software, which is why it can
  learn and replay almost anything.
- **Universal remote = brute force:** it iterates an entire dictionary of known
  codes and fires each one. That's why "turn the TV off" takes a few seconds.
- **External blaster (Rabbit Labs etc.):** the Flipper routes **the same
  modulated signal out a GPIO (pin "A7")** instead of / alongside the internal
  LEDs, turns on the **5 V rail**, and the add-on board's LEDs blast. The board
  is *"ONLY a transmitter."*

**Takeaway:** carrier + data are combined *before* they leave the host, on **one
modulated line**. The add-on board does not generate a carrier.

## 4. How our Linux / Raspberry Pi stack does it

- **`gpio-ir-tx` is a kernel bit-banger** — **no hardware PWM.** For each mark it
  toggles the GPIO at 38 kHz *in software* (it disables local interrupts during
  transmit so the timing holds); for each space it holds the line low. Default
  38 kHz / 50 %; `ir-ctl` / LIRC can override carrier and duty (we use 33 %). It
  accepts carriers up to 500 kHz.
- **`/dev/lircN`** is the char device; `ir-ctl --send <file>` sends a
  `pulse`/`space` list or a raw capture. `carrier 0` in the file = **no carrier**
  (envelope only — for boards that make their own carrier; *ours doesn't*).
- **500 ms cap:** LIRC rejects a single transmission longer than ~500 ms, which
  is why `flipperir.render()` truncates long raw captures to the first frame.
- So on the Zero, just like the Flipper's A7, **the full modulated waveform
  (carrier + data) comes out of ONE GPIO** — the "IR TX pin."

## 5. What the COBRA Commander actually needs (the unlock)

From Rabbit Labs' own listings, the board — Flipper version (7 LEDs) and the
COBRA Commander (10 LEDs, for Cardputer ADV + Zero) — is electrically just:

> **5 V supply + ONE modulated IR data line.** The high-intensity LEDs are
> *"driven directly from the 5 V rail"*, gated by the data line (through a
> transistor/MOSFET). It **does not generate its own carrier** and has **no
> separate "PWM-power" input.** The modulation must already be on the data line.

That single fact explains everything we saw:

1. **Why it stayed cool on a real remote but cooked for us:** on a genuine IR
   frame the carrier is present only during marks, at 33 % duty, so the LEDs are
   actually lit only a *small fraction* of the time → the board self-limits and
   stays cool. **Hold the data line DC-high and the LEDs are full-on 100 % →
   overheat.**
2. **Why the ring was a solid, hot, non-flickering light:** the data line was
   held **high and un-modulated**. The old config had `gpio-ir-tx` on **GPIO14**
   (the mini-UART TX, which *idles high*), and the board's real IR-in pad was
   additionally held high by the **`gpio-ir` RX overlay's pull-up**. Constant
   drive = no flicker, maximum heat.
3. **Why nothing reached the TV:** our nicely modulated 38 kHz was coming out a
   pin the board doesn't read, while the pin it *does* read just sat high.

### The correct drive scheme (what the research says to do)

- Put the **modulated `gpio-ir-tx`** on the **exact header pad the board uses for
  IR-in**, **idling LOW**, at **38 kHz / 33 %**.
- Keep **5 V steady** during the send.
- Result: the ring fires only during carrier bursts → it **blasts the TV and
  stays cool at the same time**, with **no need to PWM the power rail.**

### About "PWM the power pin"

The board's design doesn't use a PWM power input. PWMing the 5 V/enable line
would **chop the LED supply**, amplitude-modulating and distorting the carrier
bursts — at worst it breaks the TV's decode, at best it just dims the blast.
The instinct came from the overheating, but the overheating's real cause is the
**DC-high data line on the wrong pin**, not the power rail. **Recommendation:**
steady 5 V + the correct idle-low modulated data pin *first*; only consider a
power-side current limit if it still runs hot (it shouldn't).

## 6. The one open question: which Pi GPIO is the board's IR-in

This is the only thing left to nail, and it must be *read*, not guessed:

- **Vendor docs (Cardputer ADV):** transmit on header pad **"G3"**, receive on
  **"G15"**, 5 V. On the ADV (an ESP32) those silk labels equal ESP32 GPIO
  numbers.
- **The Zero is a Raspberry Pi.** The *same physical header pads* map to
  *different BCM GPIO numbers*. So **"G3" on the Zero is not necessarily BCM
  GPIO3**, and "G15" is not necessarily BCM GPIO15.
- "TX = 15" (from testing) and the vendor's "G3 transmit / G15 receive" only
  reconcile once we have the Zero's **pad → BCM map**. That is readable straight
  off the device — `gpioinfo` line names, the `cardputerzero` overlay, and
  `pinctrl` — with **no board power and no guessing.** (TODO: capture this; the
  device was rebooting at the time of writing.)

Once the pad→BCM map is in hand: set `dtoverlay=gpio-ir-tx,gpio_pin=<that BCM>`,
remove any `gpio-ir` RX pull-up from the *same* pad, send a known NEC code at
38 kHz/33 % with 5 V steady, and confirm on the **front/selfie camera** (rear
cameras have an IR filter) that the ring flickers, plus that the TV responds.

---

### Sources

- IR basics / NEC / RC5 / SIRC: [Altium — NEC protocol](https://techdocs.altium.com/display/FPGA/NEC%20Infrared%20Transmission%20Protocol),
  [SB-Projects IR notes via hobbyist pages], [keyestudio IR project](https://docs.keyestudio.com/projects/KS0069-KS0072-KS0073/en/latest/docs/2.%20Arduino/Project/Project14.html)
- Flipper IR hardware/firmware: [Flipper docs — Infrared](https://docs.flipper.net/infrared),
  [Flipper blog — Taking over TVs](https://blog.flipper.net/infrared/),
  [furi_hal_infrared_async_tx_start (freq+duty PWM)](https://docs.rs/flipper0/latest/flipper0/ffi/fn.furi_hal_infrared_async_tx_start.html),
  [Wikipedia — Flipper Zero](https://en.wikipedia.org/wiki/Flipper_Zero)
- `.ir` file format: [Flipper firmware — InfraredFileFormats.md](https://code.popov.link/mirrors/flipperzero-firmware/src/branch/dev/documentation/file_formats/InfraredFileFormats.md),
  [forum.flipper.net — IR data field](https://forum.flipper.net/t/ir-file-format-what-is-the-encoding-for-the-data-field/3166)
- Linux `gpio-ir-tx` bit-banger: [kernel driver gpio-ir-tx.c](https://git.zx2c4.com/wireguard-linux/plain/drivers/media/rc/gpio-ir-tx.c),
  [kernel DT binding](https://www.kernel.org/doc/Documentation/devicetree/bindings/leds/irled/gpio-ir-tx.txt)
- Rabbit Labs boards: [Flipper IR blaster (Tindie)](https://www.tindie.com/products/tehrabbitt/flipper-zero-ir-blaster-by-rabbit-labstm/),
  [COBRA Commander (rabbit-labs.com)](https://rabbit-labs.com/product/rabbit-labs-cobra-commander-ir-blaster/),
  [COBRA Commander (Lectronz)](https://www.lectronz.com/products/rabbit-labs-cobra-commander-ir-blaster)
- M5 Bruce IR + Cardputer IR pin: [Bruce firmware](https://github.com/pr3y/Bruce),
  [M5Stack Cardputer IR_NEC example (IR_TX_PIN 44)](https://docs.m5stack.com/en/arduino/m5cardputer/ir_nec)
