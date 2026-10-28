#!/usr/bin/env bash
# Bouton « Non » touche au-dessus de la bulle, apres un rapport.
#
# Il fait exactement ce que ferait le mot dit a voix haute : un tour du
# standard avec ce texte. Hors conversation (rapport lu par le bouton Lire),
# l'appli a deja ouvert le service ; on ouvre la conversation ici.
set -uo pipefail
ADDR="${1:-}"
ICI="$(dirname "$0")"
PIXEL_TMP="${PIXEL_TMP:-/tmp}"
[ -e "$PIXEL_TMP/pixel-voix" ] || bash "$ICI/voixdebut.sh"
VOIX_TEXTE="Non" exec bash "$ICI/voixtour.sh" "$ADDR"
