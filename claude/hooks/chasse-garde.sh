#!/usr/bin/env bash
# Garde de fin de tour pour la chasse : si une passe est déclarée ouverte, vérifier
# qu'elle est complète et prouvée avant de laisser conclure.
# Code 2 = Claude Code bloque la fin et relit le message sur stderr.
set -uo pipefail
ETAT="$HOME/.hermes/workspace/passe_courante"
PROPRIETAIRE="$HOME/.hermes/workspace/passe_courante.session"
[ -s "$ETAT" ] || exit 0
PASSE="$(tr -dc '0-9' < "$ETAT")"
[ -n "$PASSE" ] || exit 0
# Scope a la session qui a ouvert la passe : sinon tout autre topic Claude Code
# se fait bloquer par du travail qui n'est pas le sien (etat global, bug du 2026-11-02).
if [ -s "$PROPRIETAIRE" ]; then
  ENTREE="$(cat)"
  SID="$(printf '%s' "$ENTREE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)"
  [ "$SID" = "$(cat "$PROPRIETAIRE")" ] || exit 0
fi
SORTIE="$(python3 $HOME/.claude/skills/attaques-protocoles/scripts/couverture.py --passe "$PASSE" 2>&1)"
CODE=$?
if [ "$CODE" -eq 2 ]; then
  echo "$SORTIE" >&2
  echo "Passe $PASSE non close : terminer, importer en base, puis relancer couverture.py --passe $PASSE." >&2
  echo "Ne pas annoncer la fin tant que le garde répond INCOMPLÈTE." >&2
  exit 2
fi
exit 0
