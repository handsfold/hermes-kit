#!/usr/bin/env bash
# Branche l'audit sur chaque commit du clone courant.
set -e
cd "$(dirname "$0")/.."
cat > .git/hooks/pre-commit <<'H'
#!/usr/bin/env bash
exec "$(git rev-parse --show-toplevel)/outils/audit.sh" --staged
H
chmod +x .git/hooks/pre-commit
echo "hook pre-commit pose"
