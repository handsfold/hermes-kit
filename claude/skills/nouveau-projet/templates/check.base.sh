#!/usr/bin/env bash
# Vérification complète du dépôt, en local.
# ==========================================
#
# C'est LE filet du projet, et le seul. Il se lance À LA MAIN, avant toute
# livraison et avant tout déploiement. Aucun hook git ne le cache.
#
# PROTECTION RÉELLE DE CE DÉPÔT (à tenir à jour, ne jamais décrire une
# protection qui n'existe pas) :
#   remote git  : @@REMOTE@@
#   CI          : aucune pour l'instant. Le jour où il y en a une, elle lance
#                 EXACTEMENT ce script, sinon « vert en local » et « vert en
#                 CI » cessent de vouloir dire la même chose.
#
# Usage :
#   scripts/check.sh            tout (défaut)
#   scripts/check.sh --fast     sans réseau, c'est ce que le déploiement lance
@@USAGE@@#   scripts/check.sh sec        sécurité seulement
#   scripts/check.sh --strict   les avertissements deviennent bloquants
#
# Codes de sortie : 0 vert, 1 rouge, 2 une autre vérification tourne.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

# ── Un seul check à la fois, toutes sessions confondues ──────────────────────
# Plusieurs sessions Claude Code peuvent travailler sur le dépôt en parallèle.
# Deux suites de tests simultanées ne vont pas deux fois plus vite : elles se
# volent la machine. On ATTEND plutôt que de refuser, parce qu'une session qui
# vérifie veut son résultat, pas une erreur.
#
#   CHECK_NOWAIT=1   rend la main tout de suite si un check tourne (code 2)
#   CHECK_WAIT=1800  plafond d'attente en secondes (défaut 30 min)
LOCK="${TMPDIR:-/tmp}/@@PROJET@@_check.lock"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK" 2>/dev/null
  if ! flock -n 9; then
    depuis=""
    [ -r "$LOCK.pid" ] && depuis=$(ps -o etime= -p "$(cat "$LOCK.pid")" 2>/dev/null | tr -d ' ')
    printf '\033[1m-> Une vérification tourne déjà%s\033[0m\n' "${depuis:+ (depuis $depuis)}"
    if [ "${CHECK_NOWAIT:-0}" = "1" ]; then
      printf '  Rien lancé : la lancer en double la rendrait plus lente, pas plus sûre.\n'
      exit 2
    fi
    printf '  J'\''attends qu'\''elle finisse plutôt que d'\''en lancer une deuxième.\n\n'
    if ! flock -w "${CHECK_WAIT:-1800}" 9; then
      printf '\033[31mx Toujours occupée après %s s.\033[0m Relancer plus tard.\n' "${CHECK_WAIT:-1800}"
      exit 2
    fi
  fi
  echo $$ >"$LOCK.pid" 2>/dev/null
  trap 'rm -f "$LOCK.pid" 2>/dev/null' EXIT
fi

CIBLE="all"
STRICT=0
for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=1 ;;
    *)        CIBLE="$arg" ;;
  esac
done

ROUGE=$'\033[31m'; VERT=$'\033[32m'; JAUNE=$'\033[33m'; GRAS=$'\033[1m'; RAZ=$'\033[0m'
ECHECS=0

# Ne s'arrête PAS au premier échec : on veut la liste complète en un passage.
etape() {   # etape "libellé" commande...
  local titre="$1"; shift
  printf '%s-> %s%s\n' "$GRAS" "$titre" "$RAZ"
  if "$@"; then
    printf '  %sok%s\n\n' "$VERT" "$RAZ"
  else
    printf '  %sÉCHEC%s\n\n' "$ROUGE" "$RAZ"
    ECHECS=$((ECHECS + 1))
  fi
}

avertir() {  # comme etape, mais un échec n'invalide pas la livraison
  local titre="$1"; shift
  printf '%s-> %s%s\n' "$GRAS" "$titre" "$RAZ"
  if "$@"; then
    printf '  %sok%s\n\n' "$VERT" "$RAZ"
  elif [ "$STRICT" = "1" ]; then
    printf '  %sÉCHEC (--strict)%s\n\n' "$ROUGE" "$RAZ"
    ECHECS=$((ECHECS + 1))
  else
    printf '  %sà regarder, non bloquant%s\n\n' "$JAUNE" "$RAZ"
  fi
}

@@BLOC_PY@@@@BLOC_WEB@@# ── Sécurité ─────────────────────────────────────────────────────────────────
# Instantané et hors réseau, donc présent même en --fast : c'est le contrôle
# qu'on regrette le plus d'avoir sauté.
if [ "$CIBLE" = "all" ] || [ "$CIBLE" = "sec" ] || [ "$CIBLE" = "--fast" ]; then
  secrets_propres() {
    if git grep -nIE '(sk_live_[0-9A-Za-z]{20,}|rk_live_[0-9A-Za-z]{20,}|whsec_[0-9A-Za-z]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' \
         -- . ':!scripts/check.sh'; then
      echo "  Un secret est commité dans l'arbre de travail : le révoquer, le retirer, en régénérer un."
      return 1
    fi
    return 0
  }
  etape "Aucun secret commité" secrets_propres

  # Règle ferme de USER : le tiret cadratin et le tiret demi-cadratin sont
  # interdits partout. Le remède est dans le message : le script sait corriger.
  if command -v python3 >/dev/null 2>&1 && [ -f scripts/no_long_dashes.py ]; then
    tirets_propres() {
      if ! python3 scripts/no_long_dashes.py --check; then
        echo "  Remède : python3 scripts/no_long_dashes.py"
        return 1
      fi
      return 0
    }
    etape "Aucun tiret long" tirets_propres
  fi
fi

if [ "$ECHECS" -eq 0 ]; then
  printf '%s%sTout est vert.%s\n' "$GRAS" "$VERT" "$RAZ"
  exit 0
fi
printf '%s%s%d étape(s) en échec.%s\n' "$GRAS" "$ROUGE" "$ECHECS" "$RAZ"
exit 1
