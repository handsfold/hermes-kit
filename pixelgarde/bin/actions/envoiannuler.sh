#!/usr/bin/env bash
# USER a touche la bulle pendant le compte a rebours : rien ne part.
#
# Le geste annule, pas un mot : « stop », « non » ou une autre phrase se
# confondent a la transcription, un appui ne se confond avec rien (USER, 2026-10-01).
set -uo pipefail
QG_BIN="${QG_BIN:-$HOME/Bureau/Projets/contexte/bin/qg}"
STANDARD="$QG_BIN/qg-standard.py"
# Le compte a rebours est clos, parti ou annule : la file des rapports reprend.
"$(dirname "$0")/../qg-lecture" finir TOUR >/dev/null 2>&1 || true
# Le tour est clos : la conversation reste ouverte mais attend USER. Sans ce
# « pret », le sous-etat restait « travaille » (pose par voixtour) et la lecture
# auto des rapports se taisait jusqu'a 10 min (USER, 2026-10-10 : « les rapports
# ne sont jamais lus automatiquement »). On ne touche pas a « ecoute ».
ETAT_VOIX="${PIXEL_TMP:-/tmp}/pixel-voix-etat"
[ "$(cat "$ETAT_VOIX" 2>/dev/null)" = "travaille" ] && echo "pret" > "$ETAT_VOIX"
LIGNE="$(python3 "$STANDARD" annuler 2>>"$HOME/.hermes/logs/qg-standard.log")"
echo "envoi : ${LIGNE:-rien a annuler}" >&2
[ -n "$LIGNE" ] || exit 0
"$QG_BIN/qg-trace.sh" "$LIGNE"
