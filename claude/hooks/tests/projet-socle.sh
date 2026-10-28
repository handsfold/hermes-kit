#!/usr/bin/env bash
# Eprouve projet-sans-socle.py : un projet neuf sous <univers>/<famille>/ nait par scaffold.sh.
# Usage : ~/.claude/hooks/tests/projet-socle.sh   (sortie 1 si un cas echoue)
cd "$(dirname "$0")/.." || exit 2
H=projet-sans-socle.py
P="$HOME/Bureau/Projets"
ECHECS=0

# cas <REFUS|PASSE> <outil> <commande ou chemin> [cwd]
cas() {
  local obtenu=PASSE
  python3 -c 'import json,sys
o,v,c=sys.argv[1:4]
e={"command":v} if o=="Bash" else {"file_path":v}
print(json.dumps({"tool_name":o,"tool_input":e,"cwd":c}))' "$2" "$3" "${4:-/tmp}" \
    | python3 "$H" | grep -q '"deny"' && obtenu=REFUS
  if [ "$obtenu" = "$1" ]; then echo "ok    $1  $2 ${3//$'\n'/ }"
  else echo "ECHEC attendu $1, obtenu $obtenu : $2 ${3//$'\n'/ }"; ECHECS=$((ECHECS+1)); fi
}

# Le cas reel du 2026-10-28 : un site neuf cree a la main
cas REFUS Bash 'mkdir -p ~/Bureau/Projets/business/sites/zz-neuf-test/public'
cas REFUS Write "$P/business/sites/zz-neuf-test/public/index.html"
cas REFUS Write "$P/business/sites/zz-neuf-test/wrangler.jsonc"
cas REFUS Bash "cd $P/business/sites && mkdir zz-neuf-test"
cas REFUS Bash 'mkdir zz-neuf-test' "$P/perso/outils"
cas REFUS Bash 'git clone https://github.com/a/b.git ~/Bureau/Projets/perso/outils/zz-neuf-test'
cas REFUS Bash 'echo x > $HOME/Bureau/Projets/perso/vie/zz-neuf-test/a.txt'
# Ce qui doit passer
cas PASSE Bash 'bash ~/.claude/skills/nouveau-projet/scaffold.sh ~/Bureau/Projets/business/sites/zz-neuf-test js-web'
cas PASSE Bash 'SANS_SOCLE=1 mkdir -p ~/Bureau/Projets/business/sites/zz-neuf-test'
cas PASSE Write "$P/business/sites/realvoxai/public/neuf.html"
cas PASSE Bash 'mkdir -p ~/Bureau/Projets/business/sites/realvoxai/zz-dossier'
cas PASSE Bash 'ls ~/Bureau/Projets/business/sites/zz-neuf-test'
cas PASSE Bash 'cat ~/Bureau/Projets/business/sites/zz-neuf-test/x > /tmp/y'
cas PASSE Bash 'mkdir -p ~/Bureau/Projets/archives/zz-x/zz-y'
cas PASSE Bash 'mkdir zz-neuf-test' "$P/business/sites/realvoxai"
cas PASSE Write "$P/business/sites/LISEZMOI-neuf.md"
cas PASSE Bash 'mkdir -p ~/Bureau/Projets/business/zz-famille/zz-neuf'

[ "$ECHECS" -eq 0 ] && echo "TOUT VERT" || { echo "$ECHECS ECHEC(S)"; exit 1; }
