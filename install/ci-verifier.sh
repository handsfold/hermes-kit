#!/usr/bin/env bash
# Verifications apres install.sh en CI (appele par .github/workflows/installation.yml).
# Entree : HK_RC (code de sortie de install.sh). Sortie 1 au premier echec.
set -u
HERMES_HOME=${HERMES_HOME:-$HOME/.hermes}
export PATH="$HOME/.local/bin:$PATH"
echec=0
verdict() { if [ "$1" = 0 ]; then echo "OK    $2"; else echo "ECHEC $2"; echec=1; fi; }

[ "${HK_RC:-1}" = 0 ]; verdict $? "install.sh rc=${HK_RC:-?}"
PY="$HERMES_HOME/hermes-agent/venv/bin/python"
[ -x "$PY" ] || PY=python3
"$PY" -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" "$HERMES_HOME/config.yaml"; verdict $? "config.yaml : yaml valide"
sortie=$(hk doctor 2>&1); echo "$sortie"
! printf '%s' "$sortie" | grep -qiE 'command not found|syntax error|unbound variable|bad substitution|unexpected token'; verdict $? "hk doctor : aucune erreur de shell"
exit "$echec"
