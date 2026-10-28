#!/usr/bin/env bash
# Routine du lundi : essai de mise a jour vers le prochain palier, sans rien changer
# au Hermes en service (l'essai vit dans un worktree jetable).
#
# Depot au QG seulement dans 2 cas :
#   - palier PRET : 0 conflit et tests OK ;
#   - probleme NOUVEAU : une signature (cible + resultat) jamais vue.
# Sinon : silence (une ligne dans le journal).
#
# Variables de test : MAJ_SURE, QG_ATTENTE, ETAT_FICHIER, JOURNAL.
set -uo pipefail

MAJ_SURE=${MAJ_SURE:-$HOME/.hermes/scripts/hermes-maj-sure.sh}
QG=${QG_ATTENTE:-qg-attente}
ETAT=${ETAT_FICHIER:-$HOME/.hermes/maj/hebdo-etat.txt}
JOURNAL=${JOURNAL:-$HOME/.hermes/maj/hebdo.log}
mkdir -p "$(dirname "$ETAT")" "$(dirname "$JOURNAL")"

note() { echo "$(date '+%F %H:%M') $*" >> "$JOURNAL"; }

cible=$("$MAJ_SURE" prochain 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$cible" ]; then
  note "aucun palier plus recent : silence"
  exit 0
fi

sortie=$("$MAJ_SURE" essai --cible "$cible" 2>&1)
code=$?
resume=$(echo "$sortie" | grep -E ' retouches reposées, [0-9]+ à revoir$' | tail -1)
tests=$(echo "$sortie" | grep -m1 '^Tests : ')
rapport=$(echo "$sortie" | sed -n 's/^Rapport : //p' | tail -1)

if [ "$code" -eq 0 ] && [ -n "$resume" ] && [[ "$tests" == "Tests : OK"* ]]; then
  statut=PRET
elif [ "$code" -eq 3 ]; then
  statut="CONFLIT $(echo "$resume" | sed -n 's/.*, \([0-9]\+\) à revoir$/\1/p')"
elif [ "$code" -eq 0 ]; then
  statut="TESTS ${tests:-absents}"
else
  statut="ERREUR code $code"
fi

signature="$cible|$statut"
deja=$(cat "$ETAT" 2>/dev/null || true)
note "$signature (rapport ${rapport:-aucun})"

deposer() {
  # $1 titre, texte sur stdin
  "$QG" add "$1" --source hermes-maj-hebdo --origine hermes-maj-sure --resume - \
    || note "ECHEC du depot au QG"
}

if [ "$statut" = PRET ]; then
  if [ "$signature" != "$deja" ]; then
    deposer "Hermes : le palier $cible est pret" <<EOF
Essai du lundi : $resume. $tests.
Rapport : ${rapport:-inconnu}
Rien n'a ete change. Pour basculer : hermes-maj-sure.sh bascule --oui (apres accord de USER).
EOF
  fi
elif [ "$signature" != "$deja" ]; then
  deposer "Hermes : l'essai du palier $cible pose probleme ($statut)" <<EOF
Essai du lundi : ${resume:-pas de resume}. ${tests:-Tests : absents}.
Rapport : ${rapport:-inconnu}
Rien n'a ete change.
EOF
fi

echo "$signature" > "$ETAT"
exit 0
