#!/usr/bin/env bash
# Le compte a rebours de la bulle est arrive au bout : la demande part.
#
# Depose par Voix.java a la fin du compte (duree de la phrase lue + 5 s). C'est
# le telephone qui decide de la fin, hote-1 n'a aucune minuterie : deux horloges
# qui se recalent, c'est ce qui avait jete une phrase de USER le 2026-10-01.
# Rien en attente (deja annule, deja parti) : le standard ne rend rien, on se tait.
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
LIGNE="$(python3 "$STANDARD" confirmer 2>>"$HOME/.hermes/logs/qg-standard.log")"
echo "envoi : ${LIGNE:-rien en attente}" >&2
[ -n "$LIGNE" ] || exit 0
"$QG_BIN/qg-trace.sh" "$LIGNE"
