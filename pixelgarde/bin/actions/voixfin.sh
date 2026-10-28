#!/usr/bin/env bash
# Le telephone annonce qu'il a raccroche.
set -euo pipefail
PIXEL_TMP="${PIXEL_TMP:-/tmp}"
rm -f "$PIXEL_TMP/pixel-voix" "$PIXEL_TMP/pixel-voix-etat"
# Un tour en cours n'a plus personne a qui parler : la file reprend la main.
# Une LECTURE reste : le telephone dira lui-meme rapportfini ou rapportcoupe.
"$(dirname "$0")/../qg-lecture" finir TOUR >/dev/null 2>&1 || true
# Raccroche en pleine seance du Conseil : ce qui a ete dit est note quand meme.
if [ -e /tmp/pixel-conseil ]; then
  setsid nohup python3 "$HOME/Bureau/Projets/contexte/bin/qg/qg-conseil.py" clore \
    >/dev/null 2>>"$HOME/.hermes/logs/qg-conseil.log" < /dev/null &
fi
# Un tour en cours de traitement n'a plus de destinataire : sa reponse
# arriverait dans le vide, et le service la jouerait au prochain reveil, hors
# contexte. Le marqueur suffit a l'annuler, voixtour.sh le relit avant d'agir.
echo "voix : conversation fermee" >&2
