#!/usr/bin/env bash
# Verification apres redemarrage : lance hermes-verif.sh et ne parle au QG que s'il y a un KO.
#
# Le gateway met du temps a reconnecter Telegram : jusqu'a 3 essais, 60 s d'ecart,
# et seul le dernier compte. Silence complet si tout est OK.
#
#   hermes-verif-apres.sh [--attente SECONDES]   (defaut 60, 0 pour les tests)
#
# Variables de test : QG_ATTENTE (commande de depot), VERIF (script de verification).
set -uo pipefail

ATTENTE=60
[ "${1:-}" = "--attente" ] && ATTENTE=${2:-60}
VERIF=${VERIF:-$HOME/.hermes/scripts/hermes-verif.sh}
QG=${QG_ATTENTE:-qg-attente}
SORTIE=/tmp/hermes-verif-apres.log

for essai in 1 2 3; do
  sleep "$ATTENTE"
  if "$VERIF" >"$SORTIE" 2>&1; then
    echo "verification OK (essai $essai)" >>"$SORTIE"
    exit 0
  fi
done

"$QG" add "Hermes redemarre mais la verification est KO" \
  --source hermes-verif --origine hermes-maj-sure --resume - <"$SORTIE"
exit 1
