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
- `rabbitblaster/irdb.py` — read the probonopd/irdb CSV tree (brand -> device ->
  function) and render parametric codes via `irproto`.
- `rabbitblaster/ui.py` — PIL screens (320x170).
- `rabbitblaster/keypad.py` — evdev -> nav + type-to-filter characters.
- `rabbitblaster/app.py` — navigation stack: Home -> IRDB brands -> devices ->
  functions, plus Flipper `.ir` remotes; transmit on select.
- `rabbitblaster/sendcli.py` — headless CLI for testing `.ir` files.

## Code sources

- **irdb** (probonopd/irdb): ~114k codes across 648 brands, stored parametrically
  (protocol + device/subdevice/function). Rendered on the fly. **73% (83.5k codes)
  transmittable now** — NEC family, RC5, RC6, Sony 12/15/20, JVC. The rest
  (Mitsubishi, Aiwa, MCE, Panasonic/Kaseikyo, Denon, Pioneer, …) are shown with a
  `!` until their encoders are added. `python3 -m rabbitblaster.irdb` prints coverage.
- **Flipper `.ir` files**: dropped in `~/.rabbit-blaster/remotes` or
  `/usr/share/rabbit-blaster/remotes` (a universal TV remote is bundled).

## Status

- [x] IR engine: NEC / NECext / Samsung32 / SIRC / RC5 / RC6 / raw all
      transmit via `/dev/lirc0` without error on real hardware.
- [x] Framebuffer UI (320x170) + Cardputer keyboard navigation (evdev).
- [x] APPLaunch boot-screen entry + `install.sh` (icon, `video`/`input` groups).
- [x] Universal TV remote installed (`TV_Universal`, 752 transmittable codes).
- [x] Full irdb integration: Home -> brand -> device -> function browser with
      type-to-filter; 83.5k/114k codes renderable; real power codes for
      Sony/Samsung/LG/Philips/Panasonic/Vizio/Toshiba verified transmitting.
- [ ] Confirm a real appliance responds (needs a device + its codes in front of it).
- [ ] Add encoders for the long tail (Mitsubishi, Aiwa, MCE/RC6A, Panasonic/Kaseikyo,
      Denon, Pioneer, RECS80, Proton, RCA, Sharp, …) to raise coverage past 73%.

## Install (on the device)

    git clone / copy this tree to the Cardputer, then:
    bash tools/install.sh
    # reboot so it appears on the boot screen and group access activates

Add your own remotes: drop Flipper `.ir` files in `~/.rabbit-blaster/remotes`
or `/usr/share/rabbit-blaster/remotes`.

## CLI usage

    python3 -m rabbitblaster.sendcli share/remotes/sample.ir --list
    sudo python3 -m rabbitblaster.sendcli share/remotes/sample.ir --name Power --repeats 2

Override the TX device with `RABBIT_BLASTER_TX=/dev/lircN`.
