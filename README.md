# Rabbit Blaster

An IR remote app for the **M5 Cardputer Zero** with a **Rabbit Labs COBRA
Commander** IR blaster on the expansion header. It adds a Rabbit Blaster tile
to the boot screen; open it, pick a brand and a button, and it sends the IR
code.

- About 110,000 codes for 648 brands from the [irdb](https://github.com/probonopd/irdb) database (TVs, audio, set-top boxes, projectors, air conditioners and more).
- A universal TV remote (the Flipper Zero's `tv.ir`).
- Any Flipper Zero `.ir` file you add.

## What you need

- An M5 Cardputer Zero running M5's stock system (the one with the APPLaunch boot screen), connected to Wi-Fi.
- A Rabbit Labs COBRA Commander seated on the EXT header.

## Install

On the Cardputer Zero (over SSH or its terminal):

    git clone https://github.com/OWNER/rabbit-blaster.git
    cd rabbit-blaster
    ./install.sh
    sudo reboot

After the reboot, Rabbit Blaster is on the boot screen.

The installer:

- installs the app to `/usr/share/rabbit-blaster` and the tile into APPLaunch;
- downloads the irdb code database (about 24 MB) and the universal TV remote;
- adds the IR overlays to `/boot/firmware/config.txt`, keeping the previous file as `config.txt.rabbit-blaster.bak`;
- adds a sudo rule so the launcher can start the app as root (it needs root to switch the header's 5 V).

It is safe to run again, for example after `git pull`.

**It sets `enable_uart=0`.** That frees GPIO15 for the board's IR receiver, and
it also turns off the serial port on the header's UART pads, which other
add-ons (M5's LoRa/GPS cap, a serial console) use. To keep the UART and install
transmit only, run `./install.sh --keep-uart`. Other options: `--no-irdb`,
`--force`, `--help`.

To remove everything and undo the `config.txt` changes: `./uninstall.sh`, then reboot.

## Using it

| Key | Action |
|-----|--------|
| Tab / Shift+Tab | move down / up |
| Enter | open, or send the selected code |
| Esc | back |
| letters and numbers | filter the current list |
| Backspace | delete the last filter character |

The built-in keyboard's arrow keys (the Fn layer) don't work in the app yet;
use Tab and Shift+Tab.

Home has two branches: **IRDB** (brand, then device, then button) and your
`.ir` remotes. Codes marked `!` use a protocol the app can't send yet.

Sends are limited to one every 1.5 seconds. IR is invisible to the eye and to
most rear phone cameras; a front (selfie) camera shows the ring flash.

To add remotes, copy Flipper `.ir` files to `/usr/share/rabbit-blaster/remotes`.

## Safety: GPIO26 is the IR line

The COBRA Commander's LEDs run straight off the header's 5 V and are switched
by one signal pad, G3, which on the Zero is **GPIO26**. If anything holds
GPIO26 high while the board has 5 V, all ten LEDs stay on continuously and the
board overheats within seconds.

Rabbit Blaster turns the 5 V on only for the moment of each send, and refuses
to turn it on unless the kernel IR transmitter owns GPIO26 and idles it low.
Other software is not so careful: M5's own add-on drivers drive GPIO26 high as
a "power enable". **Don't run other header add-on apps with the COBRA
Commander attached.**

## How it works

- `config.txt` loads `gpio-ir-tx` on GPIO26 (pad G3) and, unless `--keep-uart`, `gpio-ir` on GPIO15 (pad G15).
- The app encodes each code as a pulse train and sends it with `ir-ctl` through LIRC, at the protocol's carrier frequency and 33 % duty.
- Header power is M5's own recipe: `ext_usb_gpio_fun=0`, `ext_5v_out=1`.

[docs/how-ir-works.md](docs/how-ir-works.md) explains consumer IR from the
ground up and how the Zero's header pads were mapped.

Code layout:

| File | Purpose |
|------|---------|
| `rabbitblaster/irproto.py` | protocol encoders (45 irdb protocol names) |
| `rabbitblaster/irdb.py` | reads the irdb CSV tree and picks the encoder |
| `rabbitblaster/flipperir.py` | parses Flipper `.ir` files |
| `rabbitblaster/irsend.py` | transmits through `ir-ctl` |
| `rabbitblaster/power.py` | header 5 V switch and the GPIO26 safety check |
| `rabbitblaster/app.py`, `ui.py`, `keypad.py`, `framebuffer.py` | the 320×170 menu |
| `rabbitblaster/sendcli.py` | send from the command line, for testing |

Command-line sending:

    cd /usr/share/rabbit-blaster
    python3 -m rabbitblaster.sendcli remotes/sample.ir --list
    sudo python3 -m rabbitblaster.sendcli remotes/sample.ir --name Power

## What has and hasn't been tested

- Developed and tested on **one pre-production Cardputer Zero**. With the COBRA Commander it turned a TV off and the board stayed cool.
- The installer was run on that unit, and its `config.txt` edits were checked against a copy of M5's factory `config.txt`. It has **not** been run on a factory-fresh or retail unit.
- Retail units are expected to have a built-in IR LED on other pins. The app ignores that transmitter and uses the header one; this is untested.
- 96 % of irdb's codes (109,614 of 114,147) can be sent. Every encoder matches a reference rendering from [IrpTransmogrifier](https://github.com/bengtmartensson/IrpTransmogrifier) (`python tests/test_irdb_encoders.py`), and LIRC accepts all of them on the device. Only an NEC-family TV code has been confirmed on a real appliance.
- irdb's "DirecTV" entries don't say which of six variants a code uses; the app sends the 38 kHz short-gap one, so some DirecTV boxes may not respond.

## Credits and licences

- The code in this repo is MIT licensed; see [LICENSE](LICENSE).
- The Rabbit Labs hare logo (`share/images/rabbit-labs-hare.png`) belongs to Rabbit Labs and is used with their permission. It is not covered by the MIT licence.
- [irdb](https://github.com/probonopd/irdb) by probonopd and the Flipper Zero firmware's `tv.ir` are downloaded by the installer and are not part of this repo; each has its own licence.
- Protocol definitions come from IrpTransmogrifier's `IrpProtocols.xml` by Bengt Mårtensson.
