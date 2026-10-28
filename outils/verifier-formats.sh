#!/usr/bin/env bash
# Apres la desidentification : chaque JSON et YAML du depot doit encore se lire.
# Une regle sed qui glisse une apostrophe dans une chaine YAML casse la config.
set -eu
cd "$(git rev-parse --show-toplevel)"
PY=python3
if ! $PY -c "import yaml" 2>/dev/null; then
  for c in "$HOME/.hermes/hermes-agent/venv/bin/python" "$HOME/.hermes/venv/bin/python"; do
    [ -x "$c" ] && "$c" -c "import yaml" 2>/dev/null && PY="$c" && break
  done
fi
fautes=0
while IFS= read -r -d '' f; do
  [ -f "$f" ] || continue
  case "$f" in
    *.json) $PY -c "import json,sys; json.load(open(sys.argv[1]))" "$f" || { echo "JSON invalide : $f"; fautes=$((fautes+1)); } ;;
    *.yaml|*.yml) $PY -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" "$f" 2>/dev/null \
        || { if $PY -c "import yaml" 2>/dev/null; then echo "YAML invalide : $f"; fautes=$((fautes+1)); else echo "YAML non verifie (pyyaml absent) : $f"; fi; } ;;
  esac
done < <(git ls-files -z --others --cached --exclude-standard claude hermes pixelgarde install)
[ "$fautes" -eq 0 ] && echo "formats : ok" || { echo "formats : $fautes fichier(s) casse(s)"; exit 1; }
