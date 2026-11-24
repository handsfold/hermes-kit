#!/usr/bin/env bash
# Rapport local a J+15, aucun message externe ni appel LLM.
set -uo pipefail
OUT="$HOME/.claude/rapports/skills-pi/$(date +%F-%H%M%S)"
mkdir -p "$OUT"
status=0
run() {
  local name="$1"; shift
  if timeout 300 "$@" >"$OUT/$name.txt" 2>&1; then
    printf '%s : OK\n' "$name"
  else
    printf '%s : ECHEC (voir le rapport)\n' "$name"
    status=1
  fi
}
run profil node "$HOME/.pi/agent/tests/skills-profile.test.mjs"
run routage python3 "$HOME/.claude/outils/test-routeur-skills.py"
run usage python3 "$HOME/.claude/outils/usage-skills.py" 15
run aiguilleur python3 "$HOME/.claude/outils/aiguilleur-bilan.py" 15
printf 'Rapports : %s\n' "$OUT"
printf 'Limite : usage-skills.py ne compte pas encore les sessions Pi.\n'
printf 'Le profil mesure des caracteres, pas un gain de cout ou de reussite.\n'
exit "$status"
