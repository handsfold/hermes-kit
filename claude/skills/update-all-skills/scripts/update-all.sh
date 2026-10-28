#!/usr/bin/env bash
# Met à jour toutes les sources de skills installées :
#  1. gstack (dépôt git global + skills liés régénérés par ./setup)
#  2. skills gérés par `npx skills` (~/.agents/skills)
#  3. plugins Claude Code (marketplaces + chaque plugin installé)
# Ne s'arrête pas à la première erreur : chaque section rapporte son statut.
set -u

GSTACK_DIR="$HOME/.claude/skills/gstack"

echo "=== 1/3 gstack ==="
if [ -d "$GSTACK_DIR/.git" ]; then
  CHECK=$("$GSTACK_DIR/bin/gstack-update-check" --force 2>/dev/null || true)
  if echo "$CHECK" | grep -q UPGRADE_AVAILABLE; then
    OLD_VERSION=$(cat "$GSTACK_DIR/VERSION" 2>/dev/null || echo "unknown")
    echo "gstack: mise à jour $CHECK"
    (
      cd "$GSTACK_DIR" || exit 1
      git stash >/dev/null 2>&1
      git fetch origin && git reset --hard origin/main && ./setup
    ) || { echo "gstack: ECHEC du setup"; }
    NEW_VERSION=$(cat "$GSTACK_DIR/VERSION" 2>/dev/null || echo "unknown")
    # Migrations idempotentes entre OLD_VERSION et NEW_VERSION
    MIGRATIONS_DIR="$GSTACK_DIR/gstack-upgrade/migrations"
    if [ -d "$MIGRATIONS_DIR" ]; then
      for migration in $(find "$MIGRATIONS_DIR" -maxdepth 1 -name 'v*.sh' -type f 2>/dev/null | sort -V); do
        m_ver="$(basename "$migration" .sh | sed 's/^v//')"
        if [ "$OLD_VERSION" != "unknown" ] \
           && [ "$(printf '%s\n%s' "$OLD_VERSION" "$m_ver" | sort -V | head -1)" = "$OLD_VERSION" ] \
           && [ "$OLD_VERSION" != "$m_ver" ]; then
          echo "gstack: migration $m_ver"
          bash "$migration" || echo "  avertissement: migration $m_ver en erreur (non fatal)"
        fi
      done
    fi
    mkdir -p ~/.gstack
    echo "$OLD_VERSION" > ~/.gstack/just-upgraded-from
    rm -f ~/.gstack/last-update-check ~/.gstack/update-snoozed
    echo "gstack: $OLD_VERSION -> $NEW_VERSION"
  else
    echo "gstack: déjà à jour ($(cat "$GSTACK_DIR/VERSION" 2>/dev/null || echo '?'))"
  fi
else
  echo "gstack: non installé en git, ignoré"
fi

echo ""
echo "=== 2/3 skills npx (~/.agents/skills) ==="
if [ -d "$HOME/.agents/skills" ]; then
  npx -y skills update 2>&1 | tail -20 || echo "npx skills: ECHEC"
  # Une mise à jour écrase l'en-tête FR et les retouches : on les réapplique (skill trouver-skill).
  echo ""
  echo "--- remise au format USER ---"
  FORMAT_OUT=$(cd / && python3 -I "$HOME/.claude/skills/trouver-skill/scripts/mettre-au-format.py" --tout 2>&1)
  FORMAT_STATUS=$?
  echo "$FORMAT_OUT" | tail -40
  [ $FORMAT_STATUS -eq 0 ] || echo "mise au format: erreurs restantes ou ECHEC (code $FORMAT_STATUS)"
else
  echo "aucun skill géré par npx, ignoré"
fi

echo ""
echo "=== 3/3 plugins Claude Code ==="
claude plugin marketplace update 2>&1 | tail -5 || echo "marketplaces: ECHEC"
PLUGINS=$(python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.claude/plugins/installed_plugins.json'
data = json.loads(p.read_text())
for name in data.get('plugins', {}):
    print(name)
" 2>/dev/null)
if [ -n "$PLUGINS" ]; then
  while IFS= read -r plugin; do
    OUT=$(claude plugin update "$plugin" 2>&1)
    STATUS=$?
    LAST=$(echo "$OUT" | tail -1)
    if [ $STATUS -eq 0 ]; then
      echo "plugin $plugin: $LAST"
    else
      echo "plugin $plugin: ECHEC ($LAST)"
    fi
  done <<< "$PLUGINS"
else
  echo "aucun plugin installé"
fi

echo ""
echo "=== Skills sans source de mise à jour ==="
# Dossiers simples de ~/.claude/skills qui ne viennent ni de gstack ni d'un lien :
# ils ont été copiés à la main et ne peuvent pas être mis à jour automatiquement.
for d in "$HOME"/.claude/skills/*/; do
  name=$(basename "$d")
  [ "$name" = "gstack" ] && continue
  [ "$name" = "update-all-skills" ] && continue
  [ -L "${d%/}" ] && continue
  [ -d "$d/.git" ] && continue
  [ -d "$GSTACK_DIR/$name" ] && continue
  echo "  $name"
done

echo ""
echo "Terminé. Redémarrer Claude Code pour appliquer les plugins mis à jour."
