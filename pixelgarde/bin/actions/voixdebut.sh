#!/usr/bin/env bash
# Le telephone annonce qu'il ecoute. On ne fait que marquer l'etat.
#
# Le marqueur sert a deux choses : la pastille passe en ambre (le garde le lit
# a chaque peinture), et voixtour.sh refuse de travailler si la conversation a
# ete coupee entre le depot du tour et sa reprise.
set -euo pipefail
PIXEL_TMP="${PIXEL_TMP:-/tmp}"
touch "$PIXEL_TMP/pixel-voix"
echo "ecoute" > "$PIXEL_TMP/pixel-voix-etat"
echo "voix : conversation ouverte" >&2
# Une conversation neuve repart sans proposition en attente : un « oui » dit
# ce matin ne doit pas envoyer ce qui a ete propose hier soir.
python3 "${QG_BIN:-$HOME/Bureau/Projets/contexte/bin/qg}/qg-standard.py" debut 2>/dev/null || true
