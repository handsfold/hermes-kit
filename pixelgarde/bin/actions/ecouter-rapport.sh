#!/usr/bin/env bash
# Fait jouer UN rapport choisi sur le Pixel, depuis l'ecran Rapports de
# l'Accueil (USER, 2026-10-13 : en mode sans lecture, il ecoute a la demande).
# Meme voie que rapport.sh : voix prefabriquee, push, VOIXDIRE. Le telephone
# rend rapportfini a la fin du son : le garde marque alors le rapport entendu.
set -euo pipefail
ID="${1:?usage: ecouter-rapport.sh <id>}"
ICI="$(dirname "$(readlink -f "$0")")"
ADB="${ADB:-adb}"
ADDR="${PIXEL_ADDR:-__PIXEL_IP__:5555}"
TEL_VOIX="/sdcard/Android/data/com.poste.pixelgarde/files/voix"
FILE="$HOME/.hermes/scripts/qg-attente.py"
eval "$("$HOME/.hermes/scripts/qg-config.py" env)"
# Voix fabriquee ici, dans un dossier temporaire : le garde efface vite les
# voix du cache pour les rapports qui ne sont plus dans son menu.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
TXT="$("$FILE" voix "$ID" 2>/dev/null || true)"
[ -n "$TXT" ] || { echo "rapport $ID vide ou inconnu" >&2; exit 1; }
SUJET="$("$FILE" sujet "$ID" 2>/dev/null || true)"
[ -n "$SUJET" ] && TXT="Rapport $SUJET. $TXT"
edge-tts --voice "$QGC_VOIX" --rate="$QGC_DEBIT" --text "$TXT" \
  --write-media "$TMP/r.mp3" >/dev/null 2>&1
[ -s "$TMP/r.mp3" ] || { echo "synthese echouee pour $ID" >&2; exit 1; }
"$ADB" -s "$ADDR" push "$TMP/r.mp3" "$TEL_VOIX/qg-pre-$ID.mp3" >/dev/null 2>&1
# Meme garde-fou que rejouer.sh : la lecture tient la parole.
QL="$ICI/../qg-lecture"
case "$("$QL" lire 2>/dev/null)" in
  *'"LIBRE"'*|*'"FENETRE"'*) "$QL" poser LECTURE "$ID" >/dev/null 2>&1 || true ;;
esac
"$ADB" -s "$ADDR" shell am start-foreground-service \
  -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIXDIRE \
  --es fichier "qg-pre-$ID.mp3" --es rapport "$ID" >/dev/null 2>&1
echo "rapport $ID envoye au telephone"
