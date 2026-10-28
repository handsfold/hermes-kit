#!/usr/bin/env bash
# Bouton « Enregistrer l'ecran » : un seul bouton pour les deux sens.
#
# Le defaut d'avant (signale le 2026-08-26) : « Capture ecran » etait un
# declic instantane, sans le moindre retour. USER ne savait ni qu'elle avait eu
# lieu, ni qu'elle etait finie, et croyait l'ecran filme en continu. Ici on
# assume la duree : le liser rouge tient tant que l'enregistrement tient, et
# ne s'eteint qu'au second appui.
#
# screenrecord tourne SUR le telephone, pas ici : couper le lien adb ne coupe
# donc pas la prise. Le fichier est rapatrie a l'arret.
set -euo pipefail
ADDR="${1:-$(adb devices | awk '/device$/{print $1; exit}')}"
TEL=/sdcard/pixel-rec.mp4
MARQUE=/tmp/pixel-rec
DEST="$HOME/Images/Pixel"
mkdir -p "$DEST"

cadre() { adb -s "$ADDR" shell am broadcast -n com.poste.pixelgarde/.Recepteur \
    -a com.poste.pixel.CADRE --es on "$1" >/dev/null 2>&1 || true; }
peindre() { "$(dirname "$0")/../pixel" bulle >/dev/null 2>&1 || true; }

if [ -f "$MARQUE" ]; then
    # SIGINT et pas SIGKILL : screenrecord ferme proprement son conteneur MP4
    # sur SIGINT. Tue net, le fichier est illisible, sans un mot d'erreur.
    adb -s "$ADDR" shell pkill -INT screenrecord >/dev/null 2>&1 || true
    rm -f "$MARQUE"
    cadre 0
    # Laisser le mux se terminer avant de tirer le fichier.
    sleep 1.5
    F="$DEST/pixel-$(date +%Y%m%d-%H%M%S).mp4"
    adb -s "$ADDR" pull "$TEL" "$F" >/dev/null 2>&1 || true
    adb -s "$ADDR" shell rm -f "$TEL" >/dev/null 2>&1 || true
    adb -s "$ADDR" shell cmd vibrator_manager synced oneshot 200 >/dev/null 2>&1 || true
    peindre
    echo "$F"
    exit 0
fi

adb -s "$ADDR" shell rm -f "$TEL" >/dev/null 2>&1 || true
# --time-limit 1800 : le plafond dur d'Android. Sans lui, screenrecord s'arrete
# tout seul a 180 s, et USER croirait le bouton casse.
adb -s "$ADDR" shell "screenrecord --bit-rate 12M --time-limit 1800 $TEL" \
    >/dev/null 2>&1 &
: > "$MARQUE"
cadre 1
adb -s "$ADDR" shell cmd vibrator_manager synced oneshot 120 >/dev/null 2>&1 || true
peindre
echo "enregistrement en cours"
