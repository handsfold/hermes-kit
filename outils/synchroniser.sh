#!/usr/bin/env bash
# Chaine automatique : config vivante -> depot -> controles -> CI -> master.
# ========================================================================
# Lancee par le timer hermes-kit-sync (toutes les 3 h) ou a la main.
#
#   1. importer.sh        rsync du MANIFESTE, desidentification, audit complet
#   2. rien a publier ?   on s'arrete, en silence
#   3. check.sh --fast    lint, format, tests, secrets, tirets longs
#   4. branche sync/...   commit, push (depot PRIVE : ce n'est pas une publication)
#   5. CI                 audit (gitleaks + identites) puis installation
#                         ubuntu + macos + windows-wsl, qui DOIVENT etre verts
#   6. master avance      fast-forward, seulement si tout est vert
#
# Au moindre rouge : rien n'avance, le motif part au QG (une seule fois par
# motif). master ne bouge JAMAIS sur un rouge.
#
# Options : --essai    s'arrete avant le commit (aucune ecriture git)
#           --sans-ci  ne pousse rien (controles locaux seulement)
#           --force    ignore le delai de 20 h entre deux synchros
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ESSAI=0; SANS_CI=0; FORCE=0
for a in "$@"; do case "$a" in --essai) ESSAI=1;; --sans-ci) SANS_CI=1;; --force) FORCE=1;; esac; done

ETAT="${XDG_STATE_HOME:-$HOME/.local/state}/hermes-kit-sync"
mkdir -p "$ETAT"
exec 9>"$ETAT/verrou"
flock -n 9 || { echo "synchro deja en cours"; exit 0; }
J="$ETAT/dernier.log"
: > "$J"
log() { echo "$*" | tee -a "$J"; }

alerte() { # alerte "<motif>" : une seule fois par motif
  local motif="$1" h; h=$(printf '%s' "$motif" | sha1sum | cut -c1-12)
  log "ROUGE : $motif"
  [ -f "$ETAT/alerte-$h" ] && return 0
  touch "$ETAT/alerte-$h"
  command -v qg-attente >/dev/null && qg-attente add "hermes-kit : synchro bloquee" \
    --resume "$motif. Rien n'a avance sur master. Journal : $J" --source hermes-kit-sync >/dev/null 2>&1
  return 0
}
vert() { rm -f "$ETAT"/alerte-*; }

# Delai minimal : la CI d'installation coute des minutes macOS (x10) et Windows (x2).
if [ "$FORCE" = 0 ] && [ "$ESSAI" = 0 ] && [ -f "$ETAT/derniere-ci" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$ETAT/derniere-ci") ))
  [ "$age" -lt 72000 ] && { log "derniere synchro il y a $((age/3600)) h : attente (--force pour passer)"; exit 0; }
fi

# Le depot doit etre propre cote git (hors ce que l'import regenere) et sur master.
[ "$(git branch --show-current)" = "master" ] || { alerte "le depot n'est pas sur master"; exit 1; }

log "== 1. import"
bash outils/importer.sh >>"$J" 2>&1 || { alerte "import ou audit rouge : $(grep -E 'interdit|identit|leak|ROUGE' "$J" | head -3 | tr '\n' ' ' | cut -c1-300)"; exit 1; }

if [ -z "$(git status --porcelain)" ]; then log "rien a publier"; vert; exit 0; fi
log "$(git status --porcelain | wc -l) fichier(s) change(s)"

log "== 2. controles locaux"
CHECK_NOWAIT=1 bash scripts/check.sh --fast >>"$J" 2>&1 || { alerte "scripts/check.sh --fast rouge : $(grep -a -B3 'ÉCHEC' "$J" | grep -a -E -- '-->|Error|error|FAILED' | head -2 | tr '\n' ' ' | cut -c1-300)"; exit 1; }
bash outils/audit.sh >>"$J" 2>&1 || { alerte "audit final rouge"; exit 1; }
log "controles locaux : verts"
[ "$ESSAI" = 1 ] && { log "essai : arret avant commit"; exit 0; }
[ "$SANS_CI" = 1 ] && { log "sans CI : arret avant push"; exit 0; }

log "== 3. commit sur branche"
B="sync/$(date +%Y%m%d-%H%M)"
git switch -c "$B" >>"$J" 2>&1 || { alerte "branche $B impossible"; exit 1; }
git add -A
git -c core.hooksPath=.git/hooks commit -q -m "Synchro auto $(date +%F) : $(git diff --cached --shortstat | sed 's/^ *//')" >>"$J" 2>&1 \
  || { git switch -q master; alerte "commit refuse (hook pre-commit) : $(tail -3 "$J" | tr '\n' ' ' | cut -c1-250)"; exit 1; }
git push -q -u origin "$B" >>"$J" 2>&1 || { git switch -q master; alerte "push impossible"; exit 1; }
touch "$ETAT/derniere-ci"

log "== 4. CI sur $B"
sleep 20
fin() { git switch -q master 2>/dev/null; }
for wf in audit installation; do
  id=""
  for _ in 1 2 3 4 5 6; do
    id=$(gh run list -R handsfold/hermes-kit -w "$wf" -b "$B" -L 1 --json databaseId -q '.[0].databaseId' 2>/dev/null)
    [ -n "$id" ] && break; sleep 15
  done
  [ -n "$id" ] || { fin; alerte "CI $wf introuvable pour $B"; exit 1; }
  # On attend les jobs bloquants : audit ; ubuntu (executeur maison) + macos + windows-wsl
  # (sautes si l'installateur n'a pas change). Plafond : 50 min.
  jobs=""
  for _ in $(seq 1 100); do
    jobs=$(gh run view "$id" -R handsfold/hermes-kit --json jobs -q '.jobs[] | "\(.name)=\(.conclusion)"' 2>/dev/null | tr '\n' ' ')
    case "$jobs" in *=" "*|"") sleep 30;; *) break;; esac
  done
  # un job termine a une conclusion non vide : "x= " signifie encore en cours
  log "CI $wf : $jobs"
  case "$wf" in
    audit)        case "$jobs" in *audit=success*) ;; *) fin; alerte "CI audit rouge sur $B ($jobs)"; exit 1;; esac;;
    # macOS et Windows : "skipped" quand l'installateur n'a pas change (job changements).
    installation) ok=1
      case "$jobs" in *ubuntu=success*) ;; *) ok=0;; esac
      case "$jobs" in *macos=success*|*macos=skipped*) ;; *) ok=0;; esac
      case "$jobs" in *windows-wsl=success*|*windows-wsl=skipped*) ;; *) ok=0;; esac
      [ "$ok" = 1 ] || { fin; alerte "CI installation rouge sur $B ($jobs)"; exit 1; };;
  esac
done

log "== 5. master avance"
git switch -q master && git merge --ff-only -q "$B" >>"$J" 2>&1 && git push -q origin master >>"$J" 2>&1 \
  || { alerte "fast-forward de master impossible"; exit 1; }
git push -q origin --delete "$B" >>"$J" 2>&1; git branch -q -d "$B" >>"$J" 2>&1
vert
log "master a jour ($(git rev-parse --short HEAD))"
command -v qg-attente >/dev/null && qg-attente add "hermes-kit : master a jour" \
  --resume "Synchro verte (audit, ubuntu, macos et windows si installateur change). Commit $(git rev-parse --short HEAD)." --source hermes-kit-sync >/dev/null 2>&1
