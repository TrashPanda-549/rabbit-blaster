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
2. **Why the ring was a solid, hot, non-flickering light:** the board's IR
   input is the header's G3 pad, which on the Zero is **GPIO26** (section 6).
   The app was holding GPIO26 **HIGH** as a "power enable", copied from M5's cap
   drivers. For this board that is the data line held high and un-modulated:
   constant drive, no flicker, maximum heat.
3. **Why nothing reached the TV:** the modulated 38 kHz was coming out GPIO14
   (and GPIO12 before that), pins the board doesn't read, while the pin it
   *does* read just sat high.

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

## 6. The Zero's header pads: G3 = GPIO26

The vendor documents the COBRA Commander as **transmit on pad "G3", receive on
pad "G15"**, 5 V. On the ADV those labels are ESP32 GPIO numbers; the Zero is a
Raspberry Pi, so the same physical pads carry different BCM numbers. No pinout
is published for the Zero, so the map below is worked out from two sources: the
ADV header's documented pad roles, and the pins M5's own Zero cap drivers use
(`apps/raspyjack/payloads/_cc1101_driver.py`, `_st25r_driver.py`).

| ADV pad (role) | Zero BCM | Evidence on the Zero |
|----------------|----------|----------------------|
| G13 / G15 (UART TX / RX) | GPIO14 / GPIO15 | LoRa cap GPS on `/dev/ttyS0`; CC1101 uses 14 and 15 |
| G4 (INT) | GPIO23 | NFC driver IRQ pin |
| G6 (BUSY) | GPIO22 | third SPI chip-select (`spi0 CS2`) |
| G5 (CS), G40/G14/G39 (SPI) | GPIO7, GPIO11/10/9 | CC1101 on `spi0.1` |
| **G3 (RESET)** | **GPIO26** | cap drivers hold it HIGH and call it "power" |

Header power, per the same drivers: `ext_usb_gpio_fun=0` and `ext_5v_out=1`.

So on the Zero: **IR TX = GPIO26, IR RX = GPIO15.** The G3 = GPIO26 row started as an
inference (it is the pad left over, and "hold HIGH to run" is what a reset line
looks like). **Confirmed on hardware 2026-11-12:** with this setup the app
turned a TV off and the board stayed cool.

## 7. Current setup

`/boot/firmware/config.txt` (previous version saved as
`config.txt.rb.pre-gpio26.bak`):

```
enable_uart=0
dtoverlay=gpio-ir,gpio_pin=15,gpio_pull=up
dtoverlay=gpio-ir-tx,gpio_pin=26
```

`power.py` switches only the header 5 V and never drives GPIO26; its interlock
refuses unless `gpio-ir-tx` is on GPIO26 active-high (`RB_IR_TX_GPIO` overrides
the pin). `irsend.py` finds the send-capable `/dev/lircN` itself.

**Blast test:** seat the board, open the app, send a known TV power code, and
watch the ring through a **front/selfie camera** (rear cameras filter IR).
Expected: a brief flash per send, board cool, ring dark otherwise. A flash that
the TV ignores is a code problem (try another code). A ring that stays on or
gets hot means the pad map above is wrong: quit the app and unplug the board.

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
