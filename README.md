# Rabbit Blaster

An IR-blaster app for the **M5 Cardputer Zero** (Raspberry Pi Compute Module 0,
Debian 13, 320×170 LCD). Appears on the APPLaunch boot screen and transmits
consumer IR codes from Flipper Zero `.ir` files through the on-board IR LED.

## Device facts (discovered)

- **IR transmit:** kernel `gpio-ir-tx` on **GPIO12** → `/dev/lirc0` (TX).
  Receiver is `gpio-ir` on GPIO13 → `/dev/lirc1`. `ir-ctl` 1.30.1 is installed.
  `/dev/lirc0` is `root:video` (app needs the `video` group or root).
- **Display:** `/dev/fb0` = `panel-mipi-dbid`, **320×170, 16bpp RGB565**, stride 640.
- **Keyboard:** `tca8418c` matrix at `/dev/input/cardputer-zero-internal`
  (event3), read via evdev. (`input` group needed.)
- **Launcher:** drop a `.desktop` in `/usr/share/APPLaunch/applications/`
  pointing at an `Exec=` (a script is fine); icon under `share/images/`.
- Python 3.13 with PIL, numpy, evdev, gpiod, pyyaml all preinstalled.

## Architecture

- `rabbitblaster/irproto.py` — protocol encoders → microsecond pulse trains.
  Implemented: NEC, NECext, Samsung32, Sony SIRC 12/15/20, RC5, RC6(mode0).
- `rabbitblaster/flipperir.py` — parse Flipper `.ir` files (`parsed` + `raw`).
- `rabbitblaster/irsend.py` — transmit via `ir-ctl --send` on `/dev/lirc0`.
- `rabbitblaster/sendcli.py` — headless CLI for testing the engine.
- `rabbitblaster/ui.py`, `app.py` — framebuffer UI + evdev input (in progress).

## Status

- [x] IR engine, tested on hardware: NEC / Samsung32 / SIRC / RC5 / raw all
      transmit via `/dev/lirc0`.
- [ ] Framebuffer UI + keyboard navigation.
- [ ] APPLaunch boot-screen entry + install (group perms, icon).
- [ ] RC6 / Kaseikyo validation; bundled remote database.

## CLI usage

    python3 -m rabbitblaster.sendcli share/remotes/sample.ir --list
    sudo python3 -m rabbitblaster.sendcli share/remotes/sample.ir --name Power --repeats 2

Override the TX device with `RABBIT_BLASTER_TX=/dev/lircN`.
