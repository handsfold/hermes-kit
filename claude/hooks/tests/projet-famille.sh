#!/usr/bin/env bash
# Eprouve projet-sans-famille.py : un projet neuf vit dans <univers>/<famille>/, jamais plus haut.
# Usage : ~/.claude/hooks/tests/projet-famille.sh   (sortie 1 si un cas echoue)
cd "$(dirname "$0")/.." || exit 2
H=projet-sans-famille.py
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

cas REFUS Bash 'mkdir -p ~/Bureau/Projets/zz-neuf-test'
cas REFUS Bash "mkdir $P/zz-neuf-test/src"
cas REFUS Bash 'git clone https://github.com/a/b.git ~/Bureau/Projets/zz-neuf-test'
cas REFUS Bash 'cd ~/Bureau/Projets && git clone git@github.com:a/zz-neuf-test.git'
cas REFUS Bash 'mkdir zz-neuf-test' "$P"
cas REFUS Bash 'cp -r /tmp/x $HOME/Bureau/Projets/zz-neuf-test'
cas REFUS Bash 'echo a > ~/Bureau/Projets/zz-notes.md'
cas REFUS Bash 'bash ~/.claude/skills/nouveau-projet/scaffold.sh ~/Bureau/Projets/zz-neuf-test js-web'
cas REFUS Write "$P/zz-neuf-test/README.md"
cas REFUS Write "$P/zz-notes.md"
cas REFUS Bash 'mkdir -p ~/Bureau/Projets/perso/zz-neuf-test'
cas REFUS Bash 'mkdir -p ~/Bureau/Projets/business/zz-neuf-test'
cas REFUS Bash 'mkdir zz-neuf-test' "$P/business"
cas REFUS Bash 'mkdir business/zz-neuf-test' "$P"
cas REFUS Write "$P/perso/zz-notes.md"
cas PASSE Bash 'mkdir -p ~/Bureau/Projets/perso/vie/zz-neuf-test'
cas PASSE Bash 'mkdir -p ~/Bureau/Projets/archives/zz-neuf-test'
cas PASSE Bash 'git clone https://github.com/a/b.git ~/Bureau/Projets/perso/outils/zz-neuf-test'
cas PASSE Bash 'mkdir zz-neuf-test' "$P/perso/vie"
cas PASSE Bash 'ls ~/Bureau/Projets/zz-neuf-test'
cas PASSE Bash 'cat ~/Bureau/Projets/INDEX.md'
cas PASSE Bash 'NOUVELLE_FAMILLE=1 mkdir ~/Bureau/Projets/zz-famille'
cas PASSE Bash 'touch ~/Bureau/Projets/contexte/projets/zz.md'
cas PASSE Write "$P/perso/agent/claude-proxy/zz.txt"
cas PASSE Write "$P/business/sites/projet-a/zz.txt"
cas PASSE Bash 'cat ~/Bureau/Projets/perso/LISEZMOI.md'
cas PASSE Write "$P/INDEX.md"
cas PASSE Write "/tmp/zz-neuf-test/a.txt"

echo "$ECHECS echec(s)"
[ "$ECHECS" -eq 0 ]
