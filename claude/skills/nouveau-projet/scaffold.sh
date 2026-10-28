#!/usr/bin/env bash
# scaffold.sh : pose le socle projet sur le disque, en une commande.
#
# La doctrine est dans ~/Bureau/Projets/contexte/methodes/socle-projet.md.
# Ce script en est l'exécution : arborescence de la section 8, filet de la
# section 2, hooks de la section 3, tests de la section 4, permissions de la
# section 7, CLAUDE.md de la section 1.
#
# Usage : scaffold.sh <chemin-du-projet> <type>
#   type : python-api | python-cli | js-web | mixte
#
# Refuse un dossier existant non vide, parce qu'un socle ne se pose pas sur un
# projet dont on ne sait rien. SOCLE_FORCE=1 lève ce refus pour compléter un
# projet déjà commencé : dans les deux cas, aucun fichier existant n'est jamais
# écrasé, il est seulement signalé. Relancer le script est donc sans effet de bord.

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TPL="$SKILL_DIR/templates"
SOCLE="$HOME/Bureau/Projets/contexte/methodes/socle-projet.md"

usage() {
  echo "Usage : $0 <chemin-du-projet> <python-api|python-cli|js-web|mixte>" >&2
  exit 1
}

[ $# -eq 2 ] || usage
DEST="$1"
TYPE="$2"

case "$TYPE" in
  python-api|python-cli|js-web|mixte) ;;
  *) echo "Type inconnu : $TYPE" >&2; usage ;;
esac

[ -d "$TPL" ] || { echo "Templates introuvables : $TPL" >&2; exit 1; }

# ── Un projet vit dans une famille, sous un univers, jamais a la racine (2026-10-24) ──
RACINE_PROJETS="$HOME/Bureau/Projets"
PARENT="$(cd "$(dirname "$DEST")" 2>/dev/null && pwd || dirname "$DEST")"
# Depuis le 2026-10-24 : <univers>/<famille>/<nom>, univers = business ou perso.
if [ "$PARENT" = "$RACINE_PROJETS" ] || [ "$PARENT" = "$RACINE_PROJETS/business" ] || [ "$PARENT" = "$RACINE_PROJETS/perso" ]; then
  echo "x $DEST n'est pas dans une famille." >&2
  echo "  Un projet vit sous ~/Bureau/Projets/<univers>/<famille>/$(basename "$DEST")" >&2
  echo "  Familles : $(cd "$RACINE_PROJETS" && find business perso -mindepth 1 -maxdepth 1 -type d ! -name '.*' -printf '%p ')" >&2
  echo "  Carte : ~/Bureau/Projets/INDEX.md" >&2
  exit 1
fi

# ── Refus d'un dossier non vide ──────────────────────────────────────────────
if [ -e "$DEST" ]; then
  if [ ! -d "$DEST" ]; then
    echo "x $DEST existe et n'est pas un dossier." >&2
    exit 1
  fi
  if [ -n "$(ls -A "$DEST" 2>/dev/null)" ] && [ "${SOCLE_FORCE:-0}" != "1" ]; then
    echo "x $DEST existe et n'est pas vide." >&2
    echo "  Le socle part TOUJOURS d'un dossier vide : jamais la copie d'un projet existant." >&2
    echo "  Choisir un autre chemin, ou vider celui-ci volontairement." >&2
    echo "  Pour compléter un projet déjà commencé, sans jamais écraser un fichier" >&2
    echo "  existant : SOCLE_FORCE=1 $0 \"$DEST\" $TYPE" >&2
    exit 1
  fi
fi

mkdir -p "$DEST"
DEST="$(cd "$DEST" && pwd)"
PROJET="$(basename "$DEST")"
PKG="$(printf '%s' "$PROJET" | tr '[:upper:]-' '[:lower:]_' | tr -cd '[:alnum:]_')"
PYPROD="${PY_PROD_VERSION:-3.11}"

CREES=(); EXISTANTS=()

# pose_copie <source> <chemin relatif> : copie sans jamais écraser.
# Pas de pipeline ici : un « ... | pose » ferait tourner la fonction dans un
# sous-shell, et le décompte des fichiers créés se perdrait avec lui.
pose_copie() {
  local src="$1" rel="$2" abs="$DEST/$2"
  if [ -e "$abs" ]; then EXISTANTS+=("$rel"); return 0; fi
  mkdir -p "$(dirname "$abs")"
  cp "$src" "$abs"
  CREES+=("$rel")
}

# pose_rendu <template> <chemin relatif> : substitue les marqueurs puis pose.
pose_rendu() {
  local tpl="$1" rel="$2" abs="$DEST/$2"
  if [ -e "$abs" ]; then EXISTANTS+=("$rel"); return 0; fi
  mkdir -p "$(dirname "$abs")"
  rendre "$tpl" >"$abs"
  CREES+=("$rel")
}

rendre() {  # rendre <fichier template> : substitue les marqueurs sur stdout
  PROJET="$PROJET" PKG="$PKG" PYPROD="$PYPROD" COMMANDES="$COMMANDES" \
  DESCRIPTION="$DESCRIPTION" REMOTE="$REMOTE" USAGE="$USAGE" \
  BLOC_PY="$BLOC_PY" BLOC_WEB="$BLOC_WEB" BLOC_DEPS="$BLOC_DEPS" LIGNE_DEPS="$LIGNE_DEPS" \
  python3 -c '
import os, sys
t = open(sys.argv[1]).read()
cles = ("BLOC_PY","BLOC_WEB","BLOC_DEPS","LIGNE_DEPS","PROJET","PKG","PYPROD","COMMANDES","DESCRIPTION","REMOTE","USAGE")
for _ in range(2):   # les blocs insérés portent eux-mêmes des marqueurs
    for k in cles:
        t = t.replace("@@%s@@" % k, os.environ.get(k, ""))
sys.stdout.write(t)
' "$1"
}

# ── Variables selon le type ──────────────────────────────────────────────────
REMOTE="aucun pour l'instant (dépôt local). Tant qu'il n'y a pas de push, ce script est la seule protection."
BLOC_PY=""; BLOC_WEB=""; BLOC_DEPS=""; LIGNE_DEPS=""; USAGE=""
case "$TYPE" in
  python-api)
    DESCRIPTION="API Python."
    COMMANDES=".venv/bin/python -m uvicorn $PKG.main:app --reload   # servir en local
scripts/check.sh                                    # vérifier
"
    BLOC_PY="$(cat "$TPL/check.py.part")"$'\n'
    USAGE="#   scripts/check.sh py         Python seulement
"
    ;;
  python-cli)
    DESCRIPTION="Outil Python en ligne de commande."
    COMMANDES=".venv/bin/python -m $PKG --help   # lancer
scripts/check.sh                  # vérifier
"
    BLOC_PY="$(cat "$TPL/check.py.part")"$'\n'
    USAGE="#   scripts/check.sh py         Python seulement
"
    ;;
  js-web)
    DESCRIPTION="Application web."
    COMMANDES="pnpm install --frozen-lockfile   # installer
pnpm dev                          # servir en local
scripts/check.sh   # vérifier
"
    BLOC_WEB="$(cat "$TPL/check.web.part")"$'\n'
    BLOC_DEPS="$(cat "$TPL/claude.deps.part")"$'\n'
    LIGNE_DEPS="| Installer une dépendance JS | \`pnpm add\` (jamais npm/yarn/npx) | contourner \`pnpm-workspace.yaml\` |"$'\n'
    USAGE="#   scripts/check.sh web        front seulement
"
    ;;
  mixte)
    DESCRIPTION="Back Python et front web."
    COMMANDES=".venv/bin/python -m $PKG   # back
pnpm dev                   # front
scripts/check.sh           # vérifier les deux
"
    BLOC_PY="$(cat "$TPL/check.py.part")"$'\n'
    BLOC_WEB="$(cat "$TPL/check.web.part")"$'\n'
    BLOC_DEPS="$(cat "$TPL/claude.deps.part")"$'\n'
    LIGNE_DEPS="| Installer une dépendance JS | \`pnpm add\` (jamais npm/yarn/npx) | contourner \`pnpm-workspace.yaml\` |"$'\n'
    USAGE="#   scripts/check.sh py         Python seulement
#   scripts/check.sh web        front seulement
"
    ;;
esac

# ── Arborescence, section 8 du socle ─────────────────────────────────────────
for d in .claude/rules .claude/skills .claude/commands .claude/hooks .claude/prompts \
         scripts tests/unit tests/integration tests/regression tests/data \
         docs artifacts reports archive; do
  mkdir -p "$DEST/$d"
done
# git ne suit pas un dossier vide : un .gitkeep dit que la place est réservée.
for d in .claude/rules .claude/skills .claude/commands .claude/prompts \
         tests/unit tests/integration tests/regression tests/data \
         docs reports archive; do
  [ -e "$DEST/$d/.gitkeep" ] || { : >"$DEST/$d/.gitkeep"; }
done

# ── Fichiers racine ──────────────────────────────────────────────────────────
pose_rendu "$TPL/CLAUDE.md.tpl" "CLAUDE.md"
pose_rendu "$TPL/README.md.tpl" "README.md"
pose_rendu "$TPL/gitignore.tpl" ".gitignore"

# ── Le filet ─────────────────────────────────────────────────────────────────
pose_rendu "$TPL/check.base.sh" "scripts/check.sh"
chmod +x "$DEST/scripts/check.sh"
pose_copie "$TPL/scripts/no_long_dashes.py" "scripts/no_long_dashes.py"
chmod +x "$DEST/scripts/no_long_dashes.py"

# ── Réglages et hooks, sections 3 et 7 ───────────────────────────────────────
pose_copie "$TPL/settings.json.tpl" ".claude/settings.json"
for h in bash_guard.py stuck_detector.py deploy_report.sh; do
  pose_copie "$TPL/hooks/$h" ".claude/hooks/$h"
  chmod +x "$DEST/.claude/hooks/$h" 2>/dev/null || true
done

# playwright_cleanup.sh ne se pose QUE là où un navigateur est piloté, et il
# se branche en SessionStart + Stop : il ne parle que s'il a nettoyé quelque
# chose. Un hook bavard à vide coûte du contexte à chaque message.
if [ "$TYPE" = "js-web" ] || [ "$TYPE" = "mixte" ]; then
  pose_copie "$TPL/hooks/playwright_cleanup.sh" ".claude/hooks/playwright_cleanup.sh"
  chmod +x "$DEST/.claude/hooks/playwright_cleanup.sh"
  python3 - "$DEST/.claude/settings.json" <<'PYEOF'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
entry = {"type": "command",
         "command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/playwright_cleanup.sh"',
         "timeout": 10}
h = s.setdefault("hooks", {})
for ev, matcher in (("SessionStart", "startup"), ("Stop", None)):
    bloc = {"hooks": [entry]}
    if matcher:
        bloc = {"matcher": matcher, "hooks": [entry]}
    if json.dumps(bloc) not in json.dumps(h.get(ev, [])):
        h.setdefault(ev, []).append(bloc)
json.dump(s, open(p, "w"), indent=2, ensure_ascii=False)
open(p, "a").write("\n")
PYEOF
fi

# ── Tests et outillage, section 4 ────────────────────────────────────────────
case "$TYPE" in
  python-api|python-cli|mixte)
    pose_rendu "$TPL/pyproject.toml.tpl" "pyproject.toml"
    pose_copie "$TPL/conftest.py.tpl" "tests/conftest.py"
    mkdir -p "$DEST/$PKG"
    [ -e "$DEST/$PKG/__init__.py" ] || { : >"$DEST/$PKG/__init__.py"; CREES+=("$PKG/__init__.py"); }
    ;;
esac
case "$TYPE" in
  js-web|mixte)
    pose_rendu "$TPL/package.json.tpl" "package.json"
    pose_copie "$TPL/pnpm-workspace.yaml.tpl" "pnpm-workspace.yaml"
    ;;
esac

# ── git ──────────────────────────────────────────────────────────────────────
if [ -d "$DEST/.git" ]; then
  GIT_ETAT="dépôt git déjà présent, laissé tel quel"
else
  git -C "$DEST" init -q
  GIT_ETAT="git init fait (aucun commit, aucun remote)"
fi

# ── Résumé ───────────────────────────────────────────────────────────────────
GRAS=$'\033[1m'; VERT=$'\033[32m'; RAZ=$'\033[0m'
printf '\n%s%sSocle posé : %s (%s)%s\n' "$GRAS" "$VERT" "$PROJET" "$TYPE" "$RAZ"
printf '%s\n\n' "$DEST"
printf '%sCréés (%d) :%s\n' "$GRAS" "${#CREES[@]}" "$RAZ"
for f in "${CREES[@]}"; do printf '  %s\n' "$f"; done
if [ "${#EXISTANTS[@]}" -gt 0 ]; then
  printf '\n%sDéjà présents, non écrasés (%d) :%s\n' "$GRAS" "${#EXISTANTS[@]}" "$RAZ"
  for f in "${EXISTANTS[@]}"; do printf '  %s\n' "$f"; done
fi
printf '\n%sÉtat git :%s %s\n' "$GRAS" "$RAZ" "$GIT_ETAT"
printf '\n%sÀ faire maintenant :%s\n' "$GRAS" "$RAZ"
printf '  1. Ouvrir CLAUDE.md et remplir « Projet et commandes ».\n'
printf '  2. Lancer scripts/check.sh : il doit être vert avant le premier commit.\n'
case "$TYPE" in
  python-api|python-cli|mixte)
    printf '  3. python3 -m venv .venv && .venv/bin/pip install ruff pytest\n' ;;
  js-web|mixte)
    printf '  3. Poser pnpm si absent : npm install -g pnpm@11.22.0\n'
    printf '     puis  pnpm add -D eslint typescript vitest\n'
    printf '     (npm/yarn/npx sont bloqués par bash_guard.py : voir section 10 du socle)\n' ;;
esac
printf '  4. Doctrine complète : %s\n' "$SOCLE"
[ -f "$SOCLE" ] || printf '     (introuvable sur cette machine : la fiche contexte est absente)\n'

# Index des projets : le projet neuf apparait dans Projets/INDEX.md et le LISEZMOI de sa famille.
case "$DEST" in "$HOME/Bureau/Projets/"*)
  python3 "$HOME/Bureau/Projets/contexte/bin/index-projets.py" >/dev/null && echo "+ index des projets regenere (Projets/INDEX.md)" ;;
esac
