#!/usr/bin/env bash
# Une reponse devinee par le standard, touchee au-dessus de la bulle.
#
# Appele sous le nom voixb1.sh, voixb2.sh ou voixb3.sh (liens vers ce
# fichier). Le bouton porte l'id de sa bulle (voixb1:1375, voixb1:t1759...),
# le garde le passe dans VOIX_CHOIX_ID. Le libelle est dans
# qg-voix/<id>.libelles, ecrit par qg-standard.py pour CETTE bulle. Bug du
# 2026-10-06 : un seul fichier /tmp pour toutes, le rapport suivant
# l'ecrasait et le bouton du premier disait la phrase du second.
set -uo pipefail
ADDR="${1:-}"
ICI="$(dirname "$0")"
PIXEL_TMP="${PIXEL_TMP:-/tmp}"
ID="$(basename "$0" .sh)"; ID="${ID#voix}"
POUR="${VOIX_CHOIX_ID:-}"
TEXTE=""
[ -n "$POUR" ] && TEXTE="$(awk -F'\t' -v i="$ID" '$1==i{print $2; exit}' "$HOME/.hermes/qg-voix/$POUR.libelles" 2>/dev/null)"
if [ -z "$TEXTE" ]; then
  echo "voixbouton : libelle $ID introuvable pour ${POUR:-?}" >&2
  exit 1
fi
[ -e "$PIXEL_TMP/pixel-voix" ] || bash "$ICI/voixdebut.sh"
VOIX_TEXTE="$TEXTE" exec bash "$ICI/voixtour.sh" "$ADDR"
