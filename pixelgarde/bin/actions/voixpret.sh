#!/usr/bin/env bash
# Le telephone annonce que la reponse a fini de se jouer et attend un appui.
#
# La conversation reste ouverte (le marqueur /tmp/pixel-voix n'est pas
# touche) : seul le micro est en attente. USER tape le bouton "voix" pour
# reprendre la parole, ou "voixannuler" pour raccrocher sans reparler.
set -euo pipefail
PIXEL_TMP="${PIXEL_TMP:-/tmp}"
echo "pret" > "$PIXEL_TMP/pixel-voix-etat"
# Le tour est joue : la file des rapports peut repartir. Pas pendant un
# compte a rebours (sous-etat compte) : c'est envoiconfirme qui le clot.
"$(dirname "$0")/../qg-lecture" finir TOUR compte >/dev/null 2>&1 || true
echo "voix : reponse jouee, en attente d'un appui" >&2
