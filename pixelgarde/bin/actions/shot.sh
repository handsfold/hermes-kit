#!/usr/bin/env bash
# Bouton « Capture » : range une capture datee dans ~/Images/Pixel.
set -euo pipefail
ADDR="${1:-$(adb devices | awk '/device$/{print $1; exit}')}"
DEST="$HOME/Images/Pixel"
mkdir -p "$DEST"
F="$DEST/pixel-$(date +%Y%m%d-%H%M%S).png"
adb -s "$ADDR" exec-out screencap -p > "$F"
# L'eclair rouge APRES la prise : pose avant, il serait dans l'image. C'est le
# seul retour visuel d'un declic instantane, la vibration ne se voit pas.
adb -s "$ADDR" shell am broadcast -n com.poste.pixelgarde/.Recepteur \
  -a com.poste.pixel.CADRE --es on flash >/dev/null 2>&1 || true
adb -s "$ADDR" shell cmd vibrator_manager synced oneshot 120 >/dev/null 2>&1 || true
echo "$F"
