#!/usr/bin/env bash
# Remove Rabbit Blaster from the Cardputer Zero and undo its config.txt block.
#     ./uninstall.sh            keeps your .ir files in /usr/share/rabbit-blaster/remotes
#     ./uninstall.sh --purge    removes those too
set -euo pipefail
PURGE=0; [ "${1:-}" = "--purge" ] && PURGE=1

PREFIX=/usr/share/rabbit-blaster
APPROOT=/usr/share/APPLaunch
CFG="${RB_CONFIG_TXT:-/boot/firmware/config.txt}"
if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

$SUDO rm -f "$APPROOT/bin/rabbit-blaster" \
            "$APPROOT/applications/rabbit-blaster.desktop" \
            "$APPROOT/share/images/rabbit-blaster.png" \
            /etc/sudoers.d/rabbit-blaster
if [ "$PURGE" -eq 1 ]; then
  $SUDO rm -rf "$PREFIX"
else
  $SUDO rm -rf "$PREFIX/rabbitblaster" "$PREFIX/irdb" "$PREFIX/rabbit-blaster-root"
fi

if grep -q '^# >>> rabbit-blaster' "$CFG"; then
  $SUDO sed -i '/^# >>> rabbit-blaster/,/^# <<< rabbit-blaster/d' "$CFG"
fi
$SUDO sed -i 's/^enable_uart=0  # was 1; changed by rabbit-blaster.*/enable_uart=1/' "$CFG"

echo "Rabbit Blaster removed. Reboot to unload the IR overlays."
if grep -qE '^dtoverlay=gpio-ir(-tx)?,gpio_pin=(26|15)' "$CFG"; then
  echo "Note: $CFG still has IR overlay lines that this script did not add:"
  grep -nE '^dtoverlay=gpio-ir(-tx)?,gpio_pin=(26|15)' "$CFG" | sed 's/^/    /'
fi
echo "The config.txt from before the first install is at $CFG.rabbit-blaster.bak"
