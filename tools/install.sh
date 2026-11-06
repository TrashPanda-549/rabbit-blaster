#!/usr/bin/env bash
# Install Rabbit Blaster onto the Cardputer Zero: python package, launcher,
# APPLaunch .desktop entry + icon, and device-access groups.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX=/usr/share/rabbit-blaster
APPROOT=/usr/share/APPLaunch

echo "[*] python package -> $PREFIX"
sudo mkdir -p "$PREFIX/rabbitblaster" "$PREFIX/remotes"
sudo cp "$HERE"/rabbitblaster/*.py "$PREFIX/rabbitblaster/"
for f in "$HERE"/share/remotes/*.ir; do
  [ -e "$f" ] && sudo cp -n "$f" "$PREFIX/remotes/" || true
done

echo "[*] launcher + desktop entry -> $APPROOT"
sudo install -m 755 "$HERE/bin/rabbit-blaster" "$APPROOT/bin/rabbit-blaster"
sudo python3 "$HERE/tools/make_icon.py" "$APPROOT/share/images/rabbit-blaster.png"
sudo install -m 644 "$HERE/share/applications/rabbit-blaster.desktop" \
     "$APPROOT/applications/rabbit-blaster.desktop"

echo "[*] device access for $(id -un): video, input groups"
sudo usermod -aG video,input "$(id -un)"

echo "[*] installed."
echo "    User remotes: drop .ir files in ~/.rabbit-blaster/remotes or $PREFIX/remotes"
echo "    If it can't open the screen on first launch, reboot (groups apply at login)."
