#!/usr/bin/env bash
# Rabbit Blaster installer for the M5 Cardputer Zero.
#
# Run it on the device, from a clone of this repo:
#     ./install.sh
#
# It installs the app and its boot-screen tile, downloads the IR code
# databases, and adds the IR overlays to /boot/firmware/config.txt (the old
# file is kept as config.txt.rabbit-blaster.bak). Safe to run again.
#
# Options:
#   --keep-uart   leave enable_uart alone and skip the IR receiver overlay
#                 (transmit only; keeps the header UART for other add-ons)
#   --no-irdb     don't download the irdb code database (~24 MB)
#   --force       install even if this doesn't look like a Cardputer Zero
set -euo pipefail

KEEP_UART=0; WITH_IRDB=1; FORCE=0
for arg in "$@"; do
  case "$arg" in
    --keep-uart) KEEP_UART=1 ;;
    --no-irdb)   WITH_IRDB=0 ;;
    --force)     FORCE=1 ;;
    -h|--help)   sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX=/usr/share/rabbit-blaster
APPROOT=/usr/share/APPLaunch
CFG="${RB_CONFIG_TXT:-/boot/firmware/config.txt}"
TX_GPIO=26      # EXT header pad G3
RX_GPIO=15      # EXT header pad G15
TV_URL=https://raw.githubusercontent.com/flipperdevices/flipperzero-firmware/dev/applications/main/infrared/resources/infrared/assets/tv.ir
IRDB_URL=https://github.com/probonopd/irdb.git

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
say() { printf '\n[*] %s\n' "$*"; }

# --- is this a Cardputer Zero? ------------------------------------------------
problems=""
grep -qi "compute module" /proc/device-tree/model 2>/dev/null \
  || problems="$problems not a Raspberry Pi Compute Module;"
[ -d "$APPROOT/applications" ] || problems="$problems no APPLaunch launcher at $APPROOT;"
grep -qE '^dtoverlay=cardputerzero' "$CFG" 2>/dev/null \
  || problems="$problems no cardputerzero overlay in $CFG;"
if [ -n "$problems" ]; then
  echo "This does not look like an M5 Cardputer Zero:$problems" >&2
  [ "$FORCE" -eq 1 ] || { echo "Stopping. Use --force to install anyway." >&2; exit 1; }
fi

# --- packages -------------------------------------------------------------------
need=""
for pkg in v4l-utils python3-pil python3-numpy python3-evdev git curl; do
  dpkg -s "$pkg" >/dev/null 2>&1 || need="$need $pkg"
done
if [ -n "$need" ]; then
  say "installing packages:$need"
  $SUDO apt-get update -q
  $SUDO apt-get install -y $need
fi

# --- app ----------------------------------------------------------------------
say "app -> $PREFIX"
$SUDO mkdir -p "$PREFIX/rabbitblaster" "$PREFIX/remotes"
$SUDO install -o root -g root -m 644 "$HERE"/rabbitblaster/*.py "$PREFIX/rabbitblaster/"
$SUDO install -o root -g root -m 755 "$HERE/bin/rabbit-blaster-root" "$PREFIX/rabbit-blaster-root"
for f in "$HERE"/share/remotes/*.ir; do
  [ -e "$f" ] && $SUDO cp -n "$f" "$PREFIX/remotes/"
done

if [ ! -e "$PREFIX/remotes/TV_Universal.ir" ]; then
  say "universal TV remote (Flipper Zero firmware tv.ir)"
  tmp="$(mktemp)"
  if curl -fsSL -o "$tmp" "$TV_URL" && grep -q "IR library file" "$tmp"; then
    $SUDO install -m 644 "$tmp" "$PREFIX/remotes/TV_Universal.ir"
  else
    echo "    download failed; skipping (the app works without it)"
  fi
  rm -f "$tmp"
fi

if [ "$WITH_IRDB" -eq 1 ] && [ ! -d "$PREFIX/irdb/codes" ]; then
  say "irdb code database (~24 MB download)"
  $SUDO git clone --depth 1 "$IRDB_URL" "$PREFIX/irdb" \
    || echo "    clone failed; the app still works with .ir remotes. Re-run to retry."
fi

# --- launcher tile ------------------------------------------------------------
say "boot-screen tile -> $APPROOT"
$SUDO install -m 755 "$HERE/bin/rabbit-blaster" "$APPROOT/bin/rabbit-blaster"
$SUDO python3 "$HERE/tools/make_icon.py" "$APPROOT/share/images/rabbit-blaster.png"
$SUDO install -m 644 "$HERE/share/applications/rabbit-blaster.desktop" \
     "$APPROOT/applications/rabbit-blaster.desktop"

# --- let the launcher start the app as root without a password ------------------
say "sudo rule for the app runner"
tmp="$(mktemp)"
{
  echo "# Rabbit Blaster: the app needs root to switch the EXT header's 5V."
  echo "%gpio ALL=(root) NOPASSWD: $PREFIX/rabbit-blaster-root \"\""
  if [ "$(id -u)" -ne 0 ]; then
    echo "$(id -un) ALL=(root) NOPASSWD: $PREFIX/rabbit-blaster-root \"\""
  fi
} > "$tmp"
$SUDO visudo -cf "$tmp" >/dev/null
$SUDO install -o root -g root -m 440 "$tmp" /etc/sudoers.d/rabbit-blaster
rm -f "$tmp"

# --- config.txt: IR overlays ----------------------------------------------------
say "IR overlays in $CFG"
[ -e "$CFG.rabbit-blaster.bak" ] || $SUDO cp -p "$CFG" "$CFG.rabbit-blaster.bak"
changed=0
block=""

other="$(grep -nE '^dtoverlay=.*gpio_pin='"$TX_GPIO"'([^0-9]|$)' "$CFG" | grep -v 'gpio-ir-tx' || true)"
[ -z "$other" ] || echo "    WARNING: another overlay already uses GPIO$TX_GPIO: $other"

if ! grep -qE '^dtoverlay=gpio-ir-tx,gpio_pin='"$TX_GPIO"'([^0-9]|$)' "$CFG"; then
  block="${block}dtoverlay=gpio-ir-tx,gpio_pin=$TX_GPIO"$'\n'
fi
if [ "$KEEP_UART" -eq 0 ]; then
  if ! grep -qE '^dtoverlay=gpio-ir,gpio_pin='"$RX_GPIO"'([^0-9]|$)' "$CFG"; then
    block="${block}dtoverlay=gpio-ir,gpio_pin=$RX_GPIO,gpio_pull=up"$'\n'
  fi
  if grep -qE '^enable_uart=1' "$CFG"; then
    $SUDO sed -i 's/^enable_uart=1.*/enable_uart=0  # was 1; changed by rabbit-blaster/' "$CFG"
    changed=1
  elif ! grep -qE '^enable_uart=' "$CFG"; then
    block="${block}enable_uart=0"$'\n'
  fi
fi
if [ -n "$block" ]; then
  printf '\n# >>> rabbit-blaster (COBRA Commander on the EXT header: IR TX = pad G3 = GPIO%s, IR RX = pad G15 = GPIO%s)\n[all]\n%s# <<< rabbit-blaster\n' \
    "$TX_GPIO" "$RX_GPIO" "$block" | $SUDO tee -a "$CFG" >/dev/null
  changed=1
fi
grep -nE '^(dtoverlay=gpio-ir|enable_uart)' "$CFG" | sed 's/^/    /'

# --- done -----------------------------------------------------------------------
live=0
[ -e "/proc/device-tree/gpio-ir-transmitter@$(printf '%x' "$TX_GPIO")" ] && live=1
say "Installed."
if [ "$changed" -eq 1 ] || [ "$live" -eq 0 ]; then
  echo "    REBOOT NOW (sudo reboot): the IR overlays only load at boot, and the app"
  echo "    refuses to power the board until the transmitter is on GPIO$TX_GPIO."
else
  echo "    Reboot (or restart the launcher) to see the Rabbit Blaster tile."
fi
echo "    Your own Flipper .ir files go in $PREFIX/remotes"
