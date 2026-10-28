#!/usr/bin/env bash
# Audit complet du depot : identites privees, cles, fichiers interdits, secrets.
# Usage : outils/audit.sh            (tout l'arbre, suivi et non suivi)
#         outils/audit.sh --staged   (ce qui va etre commite)
set -u
cd "$(dirname "$0")/.."
code=0
if [ "${1:-}" = "--staged" ]; then
  mapfile -d '' fichiers < <(git diff --cached --name-only -z --diff-filter=ACMR)
  if [ "${#fichiers[@]}" -gt 0 ]; then
    python3 hermes_kit/audit.py "${fichiers[@]}" || code=1
    python3 outils/verifier-cles.py "${fichiers[@]}" || code=1
    python3 outils/verifier-interdits.py "${fichiers[@]}" || code=1
  fi
  gitleaks git --pre-commit --staged --redact --no-banner . || code=1
else
  python3 hermes_kit/audit.py || code=1
  python3 outils/verifier-cles.py || code=1
  python3 outils/verifier-interdits.py || code=1
  gitleaks dir . --redact --no-banner || code=1
fi
[ "$code" = 0 ] && echo "audit : vert" || echo "audit : ROUGE, commit refuse"
exit "$code"
