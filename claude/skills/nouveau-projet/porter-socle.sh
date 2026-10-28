#!/usr/bin/env bash
# porter-socle.sh : pose le socle de garde-fous sur un projet qui EXISTE DÉJÀ.
#
# scaffold.sh part d'un dossier vide. Celui-ci fait l'inverse : il arrive sur un
# projet vivant, avec sa dette, sa prod et ses habitudes, et il y greffe le même
# filet sans rien casser.
#
# Pourquoi il existe (principe 14 du socle, mesuré le 2026-08-26) : sur 60 jours,
# 17 demandes de USER formulées « comme dans les autres projets ». Il ne demandait
# rien de neuf, il constatait un écart. Un garde-fou qui existe sur un projet et
# pas sur les autres est une dette, pas un acquis. Tant que la propagation est
# manuelle, elle repose sur lui, un rappel à la fois. Elle est donc ici.
#
# Trois règles absolues :
#   1. AUCUN fichier existant n'est écrasé. Il est signalé, jamais remplacé.
#      settings.json et .gitignore font exception : ils sont FUSIONNÉS, avec
#      copie de sauvegarde. Relancer le script est donc sans effet de bord.
#   2. Le filet posé dit la vérité sur ce qu'il vérifie. Un projet sans test
#      voit écrit « aucun test », il ne voit pas un vert.
#   3. La dette héritée est figée, pas nettoyée. Le cliquet échoue quand un
#      compteur monte, jamais sur l'existant.
#
# Usage : porter-socle.sh <chemin-du-projet> [options]
#   --pm npm|pnpm|aucun   gestionnaire de paquets (auto)
#   --py-prod X.Y         version de Python en PRODUCTION (défaut 3.11)
#   --pkg "a b"           dossiers Python à compiler et formater (auto)
#   --tests "tests/unit"  chemins pytest (auto ; vide = aucun test)
#   --ui                  ce projet pilote un navigateur (pose le nettoyage)
#   --no-ui               force l'inverse
#   --dry-run             dit ce qu'il ferait, n'écrit rien

set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TPL="$SKILL_DIR/templates"
PTPL="$TPL/porter"

GRAS=$'\033[1m'; VERT=$'\033[32m'; JAUNE=$'\033[33m'; ROUGE=$'\033[31m'; RAZ=$'\033[0m'

usage() { sed -n '25,35p' "${BASH_SOURCE[0]}" >&2; exit 1; }

[ $# -ge 1 ] || usage
DEST="$1"; shift
PM=""; PYPROD="3.11"; PKG=""; TESTS=""; UI=""; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pm)      PM="$2"; shift 2 ;;
    --py-prod) PYPROD="$2"; shift 2 ;;
    --pkg)     PKG="$2"; shift 2 ;;
    --tests)   TESTS="$2"; shift 2 ;;
    --ui)      UI=1; shift ;;
    --no-ui)   UI=0; shift ;;
    --dry-run) DRY=1; shift ;;
    *) echo "Option inconnue : $1" >&2; usage ;;
  esac
done

[ -d "$DEST" ] || { echo "${ROUGE}x $DEST n'existe pas.${RAZ}" >&2; exit 1; }
DEST="$(cd "$DEST" && pwd)"
if [ -z "$(ls -A "$DEST" 2>/dev/null)" ]; then
  echo "${ROUGE}x $DEST est vide.${RAZ}" >&2
  echo "  Un dossier vide, c'est scaffold.sh : $SKILL_DIR/scaffold.sh" >&2
  exit 1
fi
PROJET="$(basename "$DEST")"
SLUG="$(printf '%s' "$PROJET" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]_')"

# ── Détection ────────────────────────────────────────────────────────────────
# Rien n'est deviné en silence : tout ce qui est détecté est imprimé, et toute
# détection se corrige par une option. Un socle qui devine mal sans le dire
# poserait un filet qui ment, ce qui est pire que pas de filet.
A_PY=0
if [ -n "$(find "$DEST" -maxdepth 3 -name '*.py' -not -path '*/node_modules/*' \
        -not -path '*/.venv/*' -not -path '*/archive/*' -print -quit 2>/dev/null)" ]; then
  A_PY=1
fi
A_JS=0
[ -f "$DEST/package.json" ] && A_JS=1

if [ -z "$PM" ]; then
  if   [ -f "$DEST/pnpm-lock.yaml" ];    then PM=pnpm
  elif [ -f "$DEST/package-lock.json" ]; then PM=npm
  elif [ "$A_JS" = "1" ];                then PM=npm
  else PM=aucun; fi
fi

if [ -z "$PKG" ] && [ "$A_PY" = "1" ]; then
  # Les dossiers Python de premier niveau qui portent du code, hors outillage.
  for d in "$DEST"/*/; do
    n="$(basename "$d")"
    case "$n" in
      .*|node_modules|archive|artifacts|reports|docs|tests|test|.venv|venv|__pycache__|data|logs|public|static) continue ;;
    esac
    if [ -n "$(find "$d" -maxdepth 2 -name '*.py' -print -quit 2>/dev/null)" ]; then
      PKG="${PKG:+$PKG }$n"
    fi
  done
  # Du Python à la racine et nulle part ailleurs : c'est la racine qu'on compile.
  if [ -z "$PKG" ] && ls "$DEST"/*.py >/dev/null 2>&1; then PKG="."; fi
fi

if [ -z "$TESTS" ]; then
  for t in tests/unit tests/integration tests test; do
    if [ -d "$DEST/$t" ] && [ -n "$(find "$DEST/$t" -name 'test_*.py' -o -name '*_test.py' -print -quit 2>/dev/null)" ]; then
      TESTS="${TESTS:+$TESTS }$t"
      [ "$t" = "tests" ] && break
      [ "$t" = "test" ] && break
    fi
  done
  # tests/ pris en entier rend tests/unit redondant.
  case "$TESTS" in *"tests/unit"*|*"tests/integration"*) TESTS="${TESTS// tests/}" ;; esac
fi

if [ -z "$UI" ]; then
  UI=0
  if [ "$A_JS" = "1" ] || [ -d "$DEST/static" ] || [ -d "$DEST/public" ]; then UI=1; fi
fi

REMOTE="$(git -C "$DEST" remote get-url origin 2>/dev/null || true)"
if [ -z "$REMOTE" ]; then
  REMOTE="aucun (dépôt local). Tant qu'il n'y a pas de push, ce script est la seule protection."
fi
CI="aucune. Le jour où il y en a une, elle lance EXACTEMENT ce script."
if [ -d "$DEST/.github/workflows" ] && [ -n "$(ls -A "$DEST/.github/workflows" 2>/dev/null)" ]; then
  CI="des workflows existent dans .github/workflows : VÉRIFIER qu'ils tournent vraiment et qu'ils lancent ce script. Une CI qui ne voit pas le code ne vérifie pas le code."
fi

printf '\n%sPortage du socle sur %s%s\n' "$GRAS" "$PROJET" "$RAZ"
printf '  %s\n' "$DEST"
printf '  Python : %s   paquets : %s\n' "$([ "$A_PY" = 1 ] && echo oui || echo non)" "${PKG:-aucun}"
printf '  Tests  : %s\n' "${TESTS:-AUCUN}"
printf '  Front  : %s   gestionnaire : %s   UI pilotée : %s\n' \
       "$([ "$A_JS" = 1 ] && echo oui || echo non)" "$PM" "$([ "$UI" = 1 ] && echo oui || echo non)"
printf '  Python de prod visé : %s\n\n' "$PYPROD"

CREES=(); EXISTANTS=(); FUSIONNES=()

rendre() {  # rendre <fichier> : substitue les marqueurs sur stdout
  PROJET="$PROJET" SLUG="$SLUG" PYPROD="$PYPROD" PKG="$PKG" TESTS="$TESTS" \
  REMOTE="$REMOTE" CI="$CI" USAGE="$USAGE" INSTALL="$INSTALL" \
  BLOC_PY="$BLOC_PY" BLOC_WEB="$BLOC_WEB" BLOC_TESTS="$BLOC_TESTS" \
  BLOC_LOCK="$BLOC_LOCK" BLOC_DEPS="$BLOC_DEPS" \
  python3 -c '
import os, sys
t = open(sys.argv[1], encoding="utf-8").read()
cles = ("BLOC_PY","BLOC_WEB","BLOC_TESTS","BLOC_LOCK","BLOC_DEPS",
        "PROJET","SLUG","PYPROD","PKG","TESTS","REMOTE","CI","USAGE","INSTALL")
for _ in range(3):   # les blocs insérés portent eux-mêmes des marqueurs
    for k in cles:
        t = t.replace("@@%s@@" % k, os.environ.get(k, ""))
sys.stdout.write(t)
' "$1"
}

pose() {   # pose <source> <rel> [--rendu]
  local src="$1" rel="$2" mode="${3:-}" abs="$DEST/$2"
  if [ -e "$abs" ]; then EXISTANTS+=("$rel"); return 0; fi
  if [ "$DRY" = "1" ]; then CREES+=("$rel"); return 0; fi
  mkdir -p "$(dirname "$abs")"
  if [ "$mode" = "--rendu" ]; then rendre "$src" >"$abs"; else cp "$src" "$abs"; fi
  CREES+=("$rel")
}

# ── Le filet ─────────────────────────────────────────────────────────────────
USAGE=""; INSTALL=""; BLOC_PY=""; BLOC_WEB=""; BLOC_TESTS=""; BLOC_LOCK=""; BLOC_DEPS=""

if [ "$A_PY" = "1" ]; then
  USAGE="$USAGE#   scripts/check.sh py         Python seulement
"
  if [ -n "$TESTS" ]; then BLOC_TESTS="$(cat "$PTPL/check.tests.part")"
  else BLOC_TESTS="$(cat "$PTPL/check.sans_tests.part")"; fi
  BLOC_TESTS="$BLOC_TESTS"$'\n'
  BLOC_PY="$(cat "$PTPL/check.py.part")"$'\n'
fi
if [ "$A_JS" = "1" ]; then
  USAGE="$USAGE#   scripts/check.sh web        front seulement
"
  if [ "$PM" = "pnpm" ]; then
    INSTALL="pnpm install --frozen-lockfile"
    BLOC_LOCK="$(cat "$PTPL/lock.pnpm.part")"
    BLOC_DEPS="$(cat "$PTPL/guard.pnpm.part")"
  else
    INSTALL="npm ci"
    BLOC_LOCK="$(cat "$PTPL/lock.npm.part")"
    BLOC_DEPS="$(cat "$PTPL/guard.npm.part")"
  fi
  BLOC_WEB="$(cat "$PTPL/check.web.part")"$'\n'
fi

pose "$TPL/check.base.sh" "scripts/check.sh" --rendu
[ "$DRY" = "0" ] && chmod +x "$DEST/scripts/check.sh" 2>/dev/null
pose "$TPL/scripts/no_long_dashes.py" "scripts/no_long_dashes.py"
pose "$PTPL/cliquet.py" "scripts/cliquet.py"

# ── Hooks ────────────────────────────────────────────────────────────────────
pose "$PTPL/bash_guard.base.py" ".claude/hooks/bash_guard.py" --rendu
pose "$TPL/hooks/stuck_detector.py" ".claude/hooks/stuck_detector.py"
pose "$TPL/hooks/deploy_report.sh" ".claude/hooks/deploy_report.sh"
[ "$UI" = "1" ] && pose "$TPL/hooks/playwright_cleanup.sh" ".claude/hooks/playwright_cleanup.sh"
if [ "$DRY" = "0" ]; then
  chmod +x "$DEST"/.claude/hooks/* 2>/dev/null
  chmod +x "$DEST"/scripts/no_long_dashes.py "$DEST"/scripts/cliquet.py 2>/dev/null
fi

# ── settings.json : fusion, jamais écrasement ────────────────────────────────
if [ "$DRY" = "0" ]; then
  RES=$(UI="$UI" python3 - "$DEST/.claude/settings.json" "$TPL/settings.json.tpl" <<'PYEOF'
import json, os, shutil, sys
from pathlib import Path

cible, modele = Path(sys.argv[1]), Path(sys.argv[2])
neuf = json.loads(modele.read_text(encoding="utf-8"))
ui = os.environ.get("UI") == "1"

def entree(chemin, timeout=10, shell="python3"):
    return {"type": "command",
            "command": f'{shell} "$CLAUDE_PROJECT_DIR/.claude/hooks/{chemin}"',
            "timeout": timeout}

voulus = {
    "PreToolUse": [{"matcher": "Bash", "hooks": [entree("bash_guard.py")]}],
    "UserPromptSubmit": [{"hooks": [entree("stuck_detector.py")]}],
}
if ui:
    pw = entree("playwright_cleanup.sh", shell="bash")
    voulus["SessionStart"] = [{"matcher": "startup", "hooks": [pw]}]
    voulus["Stop"] = [{"hooks": [pw]}]

if not cible.exists():
    cible.parent.mkdir(parents=True, exist_ok=True)
    neuf["hooks"] = voulus
    cible.write_text(json.dumps(neuf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("cree")
    raise SystemExit(0)

try:
    actuel = json.loads(cible.read_text(encoding="utf-8"))
except json.JSONDecodeError as e:
    print(f"illisible:{e}")
    raise SystemExit(1)

avant = json.dumps(actuel, sort_keys=True)
shutil.copy(cible, str(cible) + ".avant-socle")

perms = actuel.setdefault("permissions", {})
for cle in ("allow", "ask", "deny"):
    existant = perms.setdefault(cle, [])
    for v in neuf["permissions"].get(cle, []):
        if v not in existant:
            existant.append(v)
for cle in ("_commentaire", "_ask_pourquoi", "_hooks_pourquoi"):
    src = neuf.get(cle) or neuf.get("permissions", {}).get(cle)
    if src is None:
        continue
    if cle == "_ask_pourquoi":
        perms.setdefault(cle, src)
    else:
        actuel.setdefault(cle, src)
actuel.setdefault("respectGitignore", True)

hooks = actuel.setdefault("hooks", {})
ajoutes = 0
for ev, blocs in voulus.items():
    presents = json.dumps(hooks.get(ev, []))
    for b in blocs:
        # Le nom du fichier suffit à reconnaître un hook déjà branché, même si
        # la commande a été réécrite à la main entre-temps.
        marqueur = b["hooks"][0]["command"].split("/")[-1].rstrip('"')
        if marqueur in presents:
            continue
        hooks.setdefault(ev, []).append(b)
        ajoutes += 1

if json.dumps(actuel, sort_keys=True) == avant:
    Path(str(cible) + ".avant-socle").unlink(missing_ok=True)
    print("inchange")
else:
    cible.write_text(json.dumps(actuel, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"fusionne:{ajoutes}")
PYEOF
)
  case "$RES" in
    cree)       CREES+=(".claude/settings.json") ;;
    inchange)   EXISTANTS+=(".claude/settings.json (déjà conforme)") ;;
    fusionne:*) FUSIONNES+=(".claude/settings.json (${RES#fusionne:} hook(s) branché(s), copie dans .claude/settings.json.avant-socle)") ;;
    illisible:*) printf '%sx settings.json illisible : %s%s\n' "$ROUGE" "${RES#illisible:}" "$RAZ" ;;
  esac

  # ── .gitignore : les fichiers d'état du socle ──────────────────────────────
  GI="$DEST/.gitignore"
  AJOUT=""
  for l in ".claude/deploy_status.json" ".claude/.deploy_reported" ".claude/settings.local.json" ".claude/*.log" ".claude/settings.json.avant-socle"; do
    grep -qxF "$l" "$GI" 2>/dev/null || AJOUT="${AJOUT}${l}"$'\n'
  done
  if [ -n "$AJOUT" ]; then
    { [ -s "$GI" ] && printf '\n'; printf '# État local du socle de garde-fous, jamais commité\n%s' "$AJOUT"; } >>"$GI"
    FUSIONNES+=(".gitignore ($(printf '%s' "$AJOUT" | grep -c . ) ligne(s) ajoutée(s))")
  fi
fi

# ── Résumé ───────────────────────────────────────────────────────────────────
printf '%sCréés (%d)%s\n' "$GRAS" "${#CREES[@]}" "$RAZ"
for f in "${CREES[@]:-}"; do [ -n "$f" ] && printf '  + %s\n' "$f"; done
if [ "${#FUSIONNES[@]}" -gt 0 ]; then
  printf '\n%sFusionnés (%d)%s\n' "$GRAS" "${#FUSIONNES[@]}" "$RAZ"
  for f in "${FUSIONNES[@]}"; do printf '  ~ %s\n' "$f"; done
fi
if [ "${#EXISTANTS[@]}" -gt 0 ]; then
  printf '\n%sDéjà présents, NON écrasés (%d)%s\n' "$GRAS" "${#EXISTANTS[@]}" "$RAZ"
  for f in "${EXISTANTS[@]}"; do printf '  = %s\n' "$f"; done
fi

printf '\n%sÀ faire maintenant, dans cet ordre :%s\n' "$GRAS" "$RAZ"
printf '  1. python3 scripts/cliquet.py --baseline   fige la dette héritée\n'
printf '     puis  scripts/cliquet.py --detail       et REGARDER : un compteur\n'
printf '     absurde est un faux positif, il se corrige AVANT d'\''être figé.\n'
printf '  2. scripts/check.sh                        doit finir vert\n'
printf '  3. Ouvrir .claude/hooks/bash_guard.py, section « Règles propres au\n'
printf '     projet » : y écrire ce qui coupe CETTE prod, avec date et incident.\n'
printf '  4. Citer scripts/check.sh dans les 10 premières lignes du CLAUDE.md.\n'
[ "$DRY" = "1" ] && printf '\n%s(--dry-run : rien n'\''a été écrit)%s\n' "$JAUNE" "$RAZ"
exit 0
