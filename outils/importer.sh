#!/usr/bin/env bash
# Copie dans le depot ce que MANIFESTE.txt autorise, puis lance l'audit.
# Une ligne commentee est une ligne inactive.
set -eu
cd "$(dirname "$0")/.."
EXCL=(--exclude .git --exclude node_modules --exclude __pycache__ --exclude .venv
      --exclude '*.bak*' --exclude .curator_backups --exclude '*.pyc' --exclude '*.db' --exclude '*.log')
n=0
while IFS= read -r ligne; do
  case "$ligne" in ''|'#'*) continue;; esac
  src=$(echo "$ligne" | sed 's/ *-> .*//' | sed "s|^~|$HOME|")
  dst=$(echo "$ligne" | sed 's/.* -> *//')
  [ -e "$src" ] || { echo "absent : $src"; continue; }
  mkdir -p "$(dirname "$dst")"
  rsync -a --delete "${EXCL[@]}" "$src" "$dst"
  n=$((n+1))
done < MANIFESTE.txt
echo "importe : $n entree(s)"
bash outils/apres-import.sh
SED=${HK_DESIDENT:-$HOME/Bureau/Projets/contexte/infra/desidentification.sed}
if [ -f "$SED" ]; then
  git ls-files -z --others --cached --exclude-standard claude hermes pixelgarde install 2>/dev/null \
    | xargs -0 grep -IlZ . 2>/dev/null | xargs -0 -r sed -i -f "$SED"
  echo "desidentification appliquee"
else
  echo "regles de desidentification absentes : $SED"
fi
bash outils/verifier-formats.sh
bash outils/audit.sh
