#!/usr/bin/env bash
# Mise a jour sure d'Hermes Agent : remplace `hermes update` pour le depot en service.
#
# Pourquoi : `hermes update` fait un autostash des fichiers non commites, puis,
# quand la branche courante (main) porte des commits locaux et ne peut pas avancer
# en fast-forward, il fait `git reset --hard origin/main` (hermes_cli/update_cmd.py,
# _reconcile_diverged_checkout). Les commits locaux quittent la branche, le stash
# est rejoue sur une base qui ne les contient plus, et s'il echoue les retouches
# restent dans `git stash list` sans que personne ne soit prevenu.
#
# Ici : les retouches vivent en commits sur une serie (poste/local), on les REJOUE
# d'abord dans un worktree jetable (essai), et on ne bascule le depot en service
# qu'apres un essai sans conflit. Chaque etape destructive est precedee d'un tag.
#
# Sous-commandes : etat | essai | prochain | bascule | retour | aide   (voir `aide`).
set -euo pipefail

DEPOT=$HOME/.hermes/hermes-agent
# Serie par defaut : la branche poste/* en service (lue apres les options). Ne le
# 2026-10-13 : figee sur poste/local, l'essai du lundi testait une vieille branche
# alors que le service tournait sur poste/palier-origin-main (9 faux conflits).
SERIE=
CIBLE=origin/main
# Chemins fixes : le worktree d'essai est le SEUL dossier que le script supprime.
# Il est jetable et reserve au script : ~/.hermes/hermes-essai (copie de travail de
# USER ou d'un agent) n'est jamais touche.
ESSAI_WT=$HOME/.hermes/hermes-essai-auto
MAJ_DIR=$HOME/.hermes/maj
SCRIPTS=$HOME/.hermes/scripts
VENV_PY="$DEPOT/venv/bin/python"

OUI=0
ABLANC=0
BRANCHE_OPT=0
POSITIONNEL=()

die() { echo "ERREUR : $*" >&2; exit 1; }
g() { git -C "$DEPOT" "$@"; }
# Meme chose dans le worktree d'essai, sans hooks git (un essai ne doit rien declencher).
wt() { git -C "$ESSAI_WT" -c core.hooksPath=/dev/null "$@"; }

aide() {
  cat <<'FIN'
hermes-maj-sure.sh <sous-commande> [options]

  etat      Version, branche, retard sur la cible, nombre de retouches de la
            serie, fichiers non commites (alerte), stashes d'autostash oublies.
  essai     git fetch, puis rejoue la serie commit par commit sur la cible dans
            $HOME/.hermes/hermes-essai-auto (jetable, branche poste/essai-AAAAMMJJ). Ecrit
            $HOME/.hermes/maj/essai-AAAAMMJJ-HHMM.md. Ne touche pas au depot
            en service (hors references git : fetch, branche d'essai).
  prochain  Imprime le prochain tag stable (v2026.M.J) apres celui en service,
            ou rien (code 1) s'il n'y en a pas. Fait un fetch des tags.
  bascule   --oui requis (ou --a-blanc pour voir sans rien faire). Tag de
            retour, poste/local := branche d'essai validee, dependances,
            migration de config, synchro des skills, greffe, redemarrage
            detache via redem-sur.sh.
  retour [tag]
            --oui requis (ou --a-blanc). Revient au tag avant-maj-* le plus
            recent (ou au tag donne), refait les dependances, redemarre.
  aide      Cet ecran.

Options : --serie NOM (defaut : la branche poste/* en service, sinon poste/local)   --cible REF (defaut origin/main)
          --branche NOM  (essai seulement) essaie cette branche au lieu de poste/local
          --oui   --a-blanc

Tout se passe en 3 temps : `etat`, `essai` (lire le rapport), `bascule --oui`.
Pour une reprise de conflit : rebaser a la main une branche de retouches sur
la cible, puis `essai --serie <cette branche>` la valide, puis
`bascule --oui --serie poste/local` pose le resultat sous le nom poste/local.
FIN
}

# --- lecture des arguments ----------------------------------------------------
[ $# -ge 1 ] || { aide; exit 1; }
SOUS=$1; shift
while [ $# -gt 0 ]; do
  case "$1" in
    --serie)   [ $# -ge 2 ] || die "--serie demande un nom"; SERIE=$2; shift 2 ;;
    --cible)   [ $# -ge 2 ] || die "--cible demande une reference"; CIBLE=$2; shift 2 ;;
    --branche) [ $# -ge 2 ] || die "--branche demande un nom"; SERIE=$2; BRANCHE_OPT=1; shift 2 ;;
    --oui)     OUI=1; shift ;;
    --a-blanc) ABLANC=1; shift ;;
    -h|--help) aide; exit 0 ;;
    -*)        die "option inconnue : $1" ;;
    *)         POSITIONNEL+=("$1"); shift ;;
  esac
done

if [ -z "$SERIE" ]; then
  SERIE=$(git -C "$DEPOT" branch --show-current 2>/dev/null || true)
  case "$SERIE" in poste/*) ;; *) SERIE=poste/local ;; esac
fi

[ "$BRANCHE_OPT" = 0 ] || [ "$SOUS" = essai ] || die "--branche ne va qu'avec essai (pour bascule, utiliser --serie)"

# --- utilitaires --------------------------------------------------------------
verifier_depot() {
  [ -d "$DEPOT/.git" ] || [ -f "$DEPOT/.git" ] || die "$DEPOT n'est pas un depot git"
}

# Fichiers modifies ou non suivis dans le depot en service, une ligne par fichier.
fichiers_non_commites() { g status --porcelain; }

# Base commune de la serie et de la cible, vide si la serie n'existe pas.
base_serie() {
  g rev-parse --verify --quiet "$SERIE^{commit}" >/dev/null 2>&1 || return 0
  g merge-base "$SERIE" "$CIBLE" 2>/dev/null || true
}

# Execution d'une etape : en mode --a-blanc elle est seulement affichee.
# Retourne 0 si l'etape doit etre executee, 1 sinon.
etape() {
  local libelle=$1 commande=${2:-}
  if [ "$ABLANC" = 1 ]; then
    echo "[a blanc] $libelle"
    [ -n "$commande" ] && echo "          commande : $commande"
    return 1
  fi
  echo "==> $libelle"
  [ -n "$commande" ] && echo "    $commande"
  return 0
}

# Refus differes : en --a-blanc on les affiche et on continue, sinon on s'arrete.
REFUS=()
refuser() { REFUS+=("$1"); }
conclure_refus() {
  [ ${#REFUS[@]} -eq 0 ] && return 0
  local r
  for r in "${REFUS[@]}"; do echo "REFUS : $r"; done
  if [ "$ABLANC" = 1 ]; then
    echo "(a blanc : les etapes suivantes sont affichees, mais une vraie execution s'arreterait ici)"
    return 0
  fi
  exit 1
}

# --- etat ---------------------------------------------------------------------
cmd_etat() {
  verifier_depot
  local version branche tete retard base nb n_dirty n_stash
  version=$(sed -n 's/^version *= *"\(.*\)"/\1/p' "$DEPOT/pyproject.toml" 2>/dev/null | head -1)
  branche=$(g branch --show-current)
  tete=$(g rev-parse --short=10 HEAD)
  echo "Version        : ${version:-inconnue} (pyproject.toml)"
  echo "Branche        : ${branche:-HEAD detache} sur $tete"
  if g rev-parse --verify --quiet "$CIBLE^{commit}" >/dev/null; then
    retard=$(g rev-list --count "HEAD..$CIBLE")
    echo "Cible          : $CIBLE ($(g rev-parse --short=10 "$CIBLE"), $(g log -1 --format=%cs "$CIBLE")), HEAD en retard de $retard commits"
    echo "                 (sans fetch : lancer la sous-commande essai pour rafraichir la cible)"
  else
    echo "Cible          : $CIBLE introuvable (git fetch origin ?)"
  fi
  if g rev-parse --verify --quiet "$SERIE^{commit}" >/dev/null 2>&1; then
    base=$(base_serie)
    nb=$(g rev-list --count --no-merges "$base..$SERIE")
    echo "Serie $SERIE : $nb retouche(s) depuis la base $(g rev-parse --short=10 "$base")"
    if [ "$(g rev-parse HEAD)" != "$(g rev-parse "$SERIE")" ]; then
      echo "                 attention : HEAD n'est pas sur la pointe de $SERIE"
    fi
  else
    echo "Serie $SERIE : la branche n'existe pas encore (retouches pas rangees en commits ?)"
  fi
  n_dirty=$(fichiers_non_commites | wc -l)
  if [ "$n_dirty" -gt 0 ]; then
    echo "Non commites   : $n_dirty fichier(s)"
    fichiers_non_commites | sed 's/^/                 /'
    echo "ALERTE : retouche non rangee : a committer sur $SERIE avant toute mise a jour"
  else
    echo "Non commites   : aucun"
  fi
  n_stash=$(g stash list | grep -c 'hermes-update-autostash' || true)
  if [ "$n_stash" -gt 0 ]; then
    echo "ALERTE : $n_stash stash(es) d'autostash de hermes update laisse(s) (git stash list) : retouches possiblement perdues dedans"
  fi
  local dernier_tag
  dernier_tag=$(g tag -l 'avant-maj-????????-????' --sort=-creatordate | head -1)
  echo "Dernier tag de retour : ${dernier_tag:-aucun}"
}

# --- essai --------------------------------------------------------------------
cmd_essai() {
  verifier_depot
  mkdir -p "$MAJ_DIR"
  [ "$ESSAI_WT" = $HOME/.hermes/hermes-essai-auto ] || die "chemin d'essai inattendu"
  g rev-parse --verify --quiet "$SERIE^{commit}" >/dev/null 2>&1 \
    || die "la serie $SERIE n'existe pas (voir --serie, ou ranger les retouches en commits d'abord)"

  echo "==> git fetch origin"
  g fetch origin
  g rev-parse --verify --quiet "$CIBLE^{commit}" >/dev/null || die "cible $CIBLE introuvable"

  local jour heure base cible_sha n_commits branche_essai retard
  jour=$(date +%Y%m%d); heure=$(date +%H%M)
  branche_essai="poste/essai-$jour-$heure"  # unique : un nouvel essai ne ressert jamais une branche deja validee
  base=$(g merge-base "$SERIE" "$CIBLE") || die "pas de base commune entre $SERIE et $CIBLE"
  cible_sha=$(g rev-parse "$CIBLE")
  retard=$(g rev-list --count "$base..$CIBLE")
  n_commits=$(g rev-list --count --no-merges "$base..$SERIE")

  # Suppression du worktree precedent (ce chemin seulement).
  if g worktree list --porcelain | grep -qx "worktree $ESSAI_WT"; then
    g worktree remove --force "$ESSAI_WT"
  fi
  g worktree prune
  if [ -e "$ESSAI_WT" ]; then rm -rf -- "${ESSAI_WT:?}"; fi
  echo "==> worktree $ESSAI_WT sur $branche_essai a $CIBLE ($(g rev-parse --short=10 "$CIBLE"))"
  g worktree add -q -B "$branche_essai" "$ESSAI_WT" "$cible_sha"

  local ok=() deja=() conflit=() sha sujet fichiers etiquette
  while read -r sha; do
    [ -n "$sha" ] || continue
    sujet=$(g log -1 --format=%s "$sha")
    etiquette="$(g rev-parse --short=10 "$sha") $sujet"
    if wt cherry-pick "$sha" >/dev/null 2>&1; then
      ok+=("$etiquette")
      echo "  OK       $etiquette"
    else
      fichiers=$(wt diff --name-only --diff-filter=U || true)
      if [ -z "$fichiers" ] && [ -z "$(wt diff --cached --name-only || true)" ]; then
        # Commit devenu vide : le meme changement existe deja en amont.
        deja+=("$etiquette")
        echo "  DEJA     $etiquette (deja dans la cible)"
      else
        conflit+=("$etiquette"$'\n'"${fichiers:-(echec sans fichier en conflit : voir git cherry-pick a la main)}")
        echo "  CONFLIT  $etiquette"
        [ -n "$fichiers" ] && echo "$fichiers" | sed 's/^/             /'
      fi
      # Chaque commit est un cherry-pick isole : l'abandon ne defait que celui-la.
      wt cherry-pick --abort >/dev/null 2>&1 || wt reset -q --hard HEAD
    fi
  done < <(g rev-list --reverse --no-merges "$base..$SERIE")

  local tete_essai
  tete_essai=$(wt rev-parse HEAD)

  # --- tests ---
  local tests_ligne tests_detail=""
  TESTS_DETAIL_FILE=$(mktemp)
  tests_ligne=$(lancer_tests "$base" "$SERIE")
  tests_detail=$(cat "$TESTS_DETAIL_FILE")
  rm -f -- "${TESTS_DETAIL_FILE:?}"
  # Avec des conflits, les tests tournent sur une serie incomplete : indicatif.
  if [ "${#conflit[@]}" -gt 0 ]; then
    tests_ligne="$tests_ligne [serie incomplete a cause des conflits : resultat indicatif]"
  fi

  # --- rapport ---
  local rapport="$MAJ_DIR/essai-$jour-$heure.md" it
  {
    echo "# Essai de mise a jour du $(date '+%F %H:%M')"
    echo
    echo "- Cible : $CIBLE ($(g rev-parse --short=10 "$CIBLE"))"
    echo "- Serie : $SERIE (base $(g rev-parse --short=10 "$base"), $n_commits retouche(s))"
    echo "- Retard de la base sur la cible : $retard commits"
    echo "- Branche d'essai : $branche_essai"
    echo "- Pointe de la branche d'essai : $tete_essai"
    echo "- Worktree : $ESSAI_WT"
    echo
    echo "## Retouches reposees (OK) : ${#ok[@]}"
    for it in "${ok[@]+"${ok[@]}"}"; do echo "- $it"; done
    echo
    echo "## Deja dans la cible : ${#deja[@]}"
    for it in "${deja[@]+"${deja[@]}"}"; do echo "- $it"; done
    echo
    echo "## A revoir (CONFLIT) : ${#conflit[@]}"
    for it in "${conflit[@]+"${conflit[@]}"}"; do
      echo "- ${it%%$'\n'*}"
      echo "${it#*$'\n'}" | sed 's/^/  - /'
    done
    echo
    echo "## Tests"
    echo "$tests_ligne"
    if [ -n "$tests_detail" ]; then
      echo; echo '```'; echo "$tests_detail"; echo '```'
    fi
    echo
    echo "## Resume"
    echo "${#ok[@]} retouches reposées, ${#conflit[@]} à revoir"
  } > "$rapport"

  echo
  echo "Rapport : $rapport"
  echo "${#ok[@]} retouches reposées, ${#conflit[@]} à revoir"
  [ "${#deja[@]}" -gt 0 ] && echo "${#deja[@]} deja dans la cible"
  echo "$tests_ligne"
  [ "${#conflit[@]}" -eq 0 ] || exit 3
}

# Prochain tag stable apres le palier en service : le plus haut tag v2026.M.J
# deja contenu dans la serie, puis le suivant dans l'ordre des versions.
cmd_prochain() {
  verifier_depot
  g fetch --tags --quiet origin 2>/dev/null || echo "ATTENTION : fetch impossible, tags locaux seulement" >&2
  local stables courant suivant
  stables=$(g tag --list 'v[0-9][0-9][0-9][0-9].[0-9]*.[0-9]*' | grep -E '^v[0-9]{4}\.[0-9]+\.[0-9]+$' | sort -V)
  courant=$(g tag --merged "$SERIE" --list 'v[0-9][0-9][0-9][0-9].[0-9]*.[0-9]*' | grep -E '^v[0-9]{4}\.[0-9]+\.[0-9]+$' | sort -V | tail -1)
  [ -n "$courant" ] || die "aucun tag stable dans l'historique de $SERIE"
  suivant=$(printf '%s\n%s\n' "$stables" "$courant" | sort -V -u | grep -A1 -Fx "$courant" | sed -n 2p)
  echo "palier en service : $courant" >&2
  if [ -z "$suivant" ]; then
    echo "aucun palier plus recent" >&2
    exit 1
  fi
  echo "$suivant"
}

# Lance pytest du worktree avec le venv du depot, sur les fichiers de test que la
# serie modifie. Imprime UNE ligne "Tests : ..." ; le detail va dans TESTS_DETAIL_FILE.
# Ne plante jamais : toute impossibilite est dite dans la ligne.
TESTS_DETAIL_FILE=/dev/null
lancer_tests() {
  local base=$1 serie=$2 fichiers=() f home_tmp sortie code
  [ -x "$VENV_PY" ] || { echo "Tests : NON LANCES (venv $VENV_PY absent)"; return 0; }
  while read -r f; do
    [ -n "$f" ] && [ -f "$ESSAI_WT/$f" ] && fichiers+=("$f")
  done < <(g diff --name-only --diff-filter=AM "$base..$serie" -- 'tests/*.py' | grep -E '/test_[^/]*\.py$|^tests/test_[^/]*\.py$' || true)
  if [ ${#fichiers[@]} -eq 0 ]; then
    echo "Tests : NON LANCES (la serie ne modifie aucun fichier de test present dans l'essai)"
    return 0
  fi
  home_tmp=$(mktemp -d)
  # HERMES_HOME jetable : les tests ne doivent pas toucher ~/.hermes. PYTHONPATH
  # place le worktree avant l'installation editable du depot en service.
  local env_essai=(env HERMES_HOME="$home_tmp" PYTHONPATH="$ESSAI_WT" PYTHONDONTWRITEBYTECODE=1)
  if ! sortie=$(cd "$ESSAI_WT" && "${env_essai[@]}" "$VENV_PY" -c 'import hermes_cli.main, run_agent' 2>&1); then
    echo "$sortie" | tail -5 > "$TESTS_DETAIL_FILE"
    rm -rf -- "${home_tmp:?}"
    echo "Tests : NON LANCES (import impossible avec le venv actuel, dependances neuves probables : $(echo "$sortie" | tail -1 | cut -c1-200))"
    return 0
  fi
  if ! (cd "$ESSAI_WT" && "${env_essai[@]}" "$VENV_PY" -m pytest --version >/dev/null 2>&1); then
    rm -rf -- "${home_tmp:?}"
    echo "Tests : NON LANCES (pytest absent du venv)"
    return 0
  fi
  code=0
  sortie=$(cd "$ESSAI_WT" && timeout 900 "${env_essai[@]}" "$VENV_PY" -m pytest -q -p no:cacheprovider \
    "${fichiers[@]}" 2>&1) || code=$?
  rm -rf -- "${home_tmp:?}"
  echo "$sortie" | tail -15 > "$TESTS_DETAIL_FILE"
  local derniere; derniere=$(echo "$sortie" | tail -1 | cut -c1-200)
  if [ "$code" = 0 ]; then
    echo "Tests : OK (${#fichiers[@]} fichiers) : $derniere"
  elif [ "$code" = 124 ]; then
    echo "Tests : NON CONCLUANTS (delai de 900 s depasse)"
  else
    echo "Tests : ECHEC (code $code, ${#fichiers[@]} fichiers) : $derniere"
  fi
}

# --- etapes communes de bascule et de retour -----------------------------------
# Effacement des __pycache__ du depot (hors venv et node_modules) : le gateway
# redemarre sinon sur du bytecode ancien (meme raison que hermes update).
etape_pycache() {
  if etape "Effacer les __pycache__ du depot" "find $DEPOT -name __pycache__ (hors venv, node_modules)"; then
    find "$DEPOT" \( -path "$DEPOT/venv" -o -path '*/node_modules' -o -path "$DEPOT/.git" \) -prune \
      -o -type d -name __pycache__ -print0 | xargs -0 -r rm -rf --
  fi
}

# Installation des dependances : meme commande que hermes update
# (`uv pip install -e ".[all]"` dans le venv, repli `-e .` si un extra casse).
etape_dependances() {
  local cmd
  if command -v uv >/dev/null 2>&1; then
    cmd="cd $DEPOT && VIRTUAL_ENV=$DEPOT/venv uv pip install -e '.[all]'"
  else
    cmd="cd $DEPOT && $VENV_PY -m pip install -e '.[all]'"
  fi
  if etape "Installer les dependances Python" "$cmd (repli : -e . si un extra echoue)"; then
    if command -v uv >/dev/null 2>&1; then
      if ! (cd "$DEPOT" && VIRTUAL_ENV="$DEPOT/venv" uv pip install -e '.[all]'); then
        echo "ATTENTION : .[all] a echoue, repli sur les dependances de base (-e .)"
        (cd "$DEPOT" && VIRTUAL_ENV="$DEPOT/venv" uv pip install -e .) || die "installation des dependances impossible"
      fi
    else
      if ! (cd "$DEPOT" && "$VENV_PY" -m pip install -e '.[all]'); then
        echo "ATTENTION : .[all] a echoue, repli sur les dependances de base (-e .)"
        (cd "$DEPOT" && "$VENV_PY" -m pip install -e .) || die "installation des dependances impossible"
      fi
    fi
  fi
}

# Les 4 modules que hermes update sonde apres l'installation. S'ils ne
# s'importent pas, on NE redemarre PAS : le gateway en marche reste sur son code.
etape_import() {
  if etape "Verifier que le code s'importe" "$VENV_PY -c 'import hermes_cli.main, run_agent, model_tools, toolsets'"; then
    local sortie
    if ! sortie=$(cd "$DEPOT" && "$VENV_PY" -c 'import hermes_cli.main, run_agent, model_tools, toolsets' 2>&1); then
      echo "$sortie" | tail -8
      die "le code ne s'importe pas : pas de redemarrage. Revenir en arriere avec : $0 retour --oui"
    fi
    echo "    import OK"
  fi
}

# Greffes locales hors git : a relancer apres chaque changement de code (idempotentes).
# Liste vide depuis le 2026-10-11 : patch-avis-arret.py est devenu la retouche R09
# (commit sur poste/local). Toute nouvelle retouche va en commit, pas en greffe.
GREFFES=()
etape_greffes() {
  local script
  [ "${#GREFFES[@]}" -eq 0 ] && { echo "(aucune greffe hors git)"; return 0; }
  for script in "${GREFFES[@]}"; do
    if [ -f "$script" ]; then
      if etape "Relancer la greffe $(basename "$script")" "python3 $script"; then
        python3 "$script" || echo "ATTENTION : la greffe $(basename "$script") a echoue (code $?), a relancer a la main"
      fi
    else
      echo "(greffe absente, ignoree : $script)"
    fi
  done
}

# Redemarrage : le SEUL script autorise, lance detache (il attend la fin de tous
# les tours en cours sans limite de temps, voir son en-tete).
etape_redemarrage() {
  if etape "Redemarrer le gateway (detache, attend la fin des tours en cours)" \
      "setsid nohup redem-sur.sh puis hermes-verif-apres.sh (QG seulement si KO)"; then
    [ -x "$SCRIPTS/redem-sur.sh" ] || die "$SCRIPTS/redem-sur.sh introuvable ou non executable"
    [ -x "$SCRIPTS/hermes-verif-apres.sh" ] || die "$SCRIPTS/hermes-verif-apres.sh introuvable ou non executable"
    # Meme processus detache : la verification part quand le redemarrage est fini.
    # Puis la voix (2026-10-14) : le pyproject epingle edge-tts==7.2.7, que Microsoft
    # refuse (403). voix-a-jour.sh remet la derniere version dans TOUTES les copies,
    # celle du gateway comprise (~/.hermes/installs/...), teste une vraie synthese,
    # et ecrit CHANGE si le gateway doit redemarrer encore une fois pour la charger.
    setsid nohup bash -c "'$SCRIPTS/redem-sur.sh'; '$SCRIPTS/hermes-verif-apres.sh'; \
      if [ -x '$SCRIPTS/voix-a-jour.sh' ]; then '$SCRIPTS/voix-a-jour.sh' >/tmp/voix-a-jour.log 2>&1; \
        tail -2 /tmp/voix-a-jour.log | grep -q '^CHANGE\$' && '$SCRIPTS/redem-sur.sh'; fi" >/dev/null 2>&1 </dev/null &
    echo "    redem-sur.sh lance (journal : /tmp/redem-sur.log), puis hermes-verif.sh (resultat : /tmp/hermes-verif-apres.log, QG seulement si KO), puis voix-a-jour.sh (/tmp/voix-a-jour.log)"
  fi
}

# Avertit si des dependances Node ont change entre deux commits (non refait ici).
avertir_node() {
  local ancien=$1 nouveau=$2 liste
  liste=$(g diff --name-only "$ancien" "$nouveau" -- package.json package-lock.json web/package.json \
    web/package-lock.json ui-tui/package.json ui-tui/package-lock.json 2>/dev/null || true)
  if [ -n "$liste" ]; then
    echo "ATTENTION : dependances Node modifiees ($(echo "$liste" | tr '\n' ' ')) : npm install et build web NON refaits par ce script"
  fi
}

# Verrou : jamais deux bascules ou retours en meme temps.
prendre_verrou() {
  exec 9>/tmp/hermes-maj-sure.lock
  flock -n 9 || die "une autre operation hermes-maj-sure est en cours"
}

# --- bascule ------------------------------------------------------------------
cmd_bascule() {
  verifier_depot
  if [ "$OUI" != 1 ] && [ "$ABLANC" != 1 ]; then
    die "bascule demande --oui (ou --a-blanc pour voir les etapes sans rien faire)"
  fi
  [ "$ABLANC" = 1 ] || prendre_verrou
  [ "$ABLANC" = 1 ] && echo "=== BASCULE A BLANC : rien n'est execute ==="

  # 1. fichiers non commites
  local n_dirty; n_dirty=$(fichiers_non_commites | wc -l)
  if [ "$n_dirty" -gt 0 ]; then
    refuser "$n_dirty fichier(s) non commite(s) dans $DEPOT : retouche non rangee, a committer sur $SERIE avant toute mise a jour ($(fichiers_non_commites | head -3 | sed 's/^...//' | tr '\n' ' ')...)"
  fi

  # 2. dernier rapport d'essai
  local rapport branche_essai tete_rapport resume conflits tests_ligne tete_reelle
  rapport=$(ls -1 "$MAJ_DIR"/essai-*.md 2>/dev/null | sort | tail -1 || true)
  branche_essai="<branche-essai>"
  if [ -z "$rapport" ]; then
    refuser "aucun rapport d'essai dans $MAJ_DIR : lancer d'abord : $0 essai"
  else
    echo "Rapport d'essai : $rapport"
    branche_essai=$(sed -n "s/^- Branche d'essai : //p" "$rapport" | head -1)
    tete_rapport=$(sed -n "s/^- Pointe de la branche d'essai : //p" "$rapport" | head -1)
    resume=$(grep -E ' retouches reposées, [0-9]+ à revoir$' "$rapport" | tail -1 || true)
    conflits=$(echo "$resume" | sed -n 's/.*, \([0-9]\+\) à revoir$/\1/p')
    tests_ligne=$(grep -m1 '^Tests : ' "$rapport" || true)
    echo "Resume          : ${resume:-introuvable}"
    echo "$tests_ligne"
    if [ -z "$conflits" ]; then
      refuser "rapport illisible (ligne de resume absente) : refaire un essai"
    elif [ "$conflits" -gt 0 ]; then
      refuser "le dernier essai a $conflits conflit(s) non resolu(s) : basculer perdrait ces retouches"
    fi
    case "$tests_ligne" in
      "Tests : ECHEC"*) refuser "les tests du dernier essai ont echoue" ;;
    esac
    if ! g rev-parse --verify --quiet "refs/heads/$branche_essai" >/dev/null; then
      refuser "la branche d'essai $branche_essai n'existe plus"
    else
      tete_reelle=$(g rev-parse "refs/heads/$branche_essai")
      [ "$tete_reelle" = "$tete_rapport" ] \
        || refuser "la branche $branche_essai a bouge depuis l'essai (rapport $tete_rapport, reel $tete_reelle) : refaire un essai"
    fi
  fi
  conclure_refus

  local stamp ancien_head ancien_serie branche_actuelle
  stamp=$(date +%Y%m%d-%H%M)
  ancien_head=$(g rev-parse HEAD)
  branche_actuelle=$(g branch --show-current)
  ancien_serie=$(g rev-parse --verify --quiet "refs/heads/$SERIE" || true)

  if etape "Instantane rapide de l'etat (comme hermes update, best effort)" \
      "$VENV_PY -c 'from hermes_cli.update_cmd_maint import _run_quick_snapshots; _run_quick_snapshots()'"; then
    (cd "$DEPOT" && "$VENV_PY" -c 'from hermes_cli.update_cmd_maint import _run_quick_snapshots; print(_run_quick_snapshots())') \
      || echo "ATTENTION : instantane impossible, on continue (le tag git reste la garantie)"
  fi

  if etape "Tag de retour avant-maj-$stamp sur HEAD (branche d'origine : ${branche_actuelle:-detachee})" \
      "git tag -a avant-maj-$stamp -m 'branche=${branche_actuelle}' HEAD"; then
    g tag -a "avant-maj-$stamp" -m "branche=${branche_actuelle}" HEAD
    if [ -n "$ancien_serie" ] && [ "$ancien_serie" != "$ancien_head" ]; then
      g tag "avant-maj-$stamp-serie" "$ancien_serie"
      echo "    tag avant-maj-$stamp-serie sur l'ancienne pointe de $SERIE"
    fi
  fi

  if etape "$SERIE := $branche_essai, et le depot passe dessus" "git checkout -B $SERIE $branche_essai"; then
    g checkout -q -B "$SERIE" "$branche_essai"
    g log -1 --format='    HEAD : %h %s'
  fi
  [ "$ABLANC" = 1 ] || avertir_node "$ancien_head" HEAD

  etape_pycache
  etape_dependances
  etape_import

  local config_avant="$MAJ_DIR/config.yaml.avant-maj-$stamp"
  if etape "Copie de la config avant migration ($config_avant)" "cp -p config.yaml $config_avant"; then
    mkdir -p "$MAJ_DIR"
    cp -p $HOME/.hermes/config.yaml "$config_avant"
  fi

  if etape "Migration de la config (non interactive)" \
      "$VENV_PY -c 'from hermes_cli.config import migrate_config; migrate_config(interactive=False, quiet=False)'"; then
    (cd "$DEPOT" && "$VENV_PY" -c 'from hermes_cli.config import migrate_config; print(migrate_config(interactive=False, quiet=False))') \
      || echo "ATTENTION : migration de config echouee, a relancer : hermes config migrate"
  fi

  # La migration a deja remis display.personality a vide une fois : on remet les
  # reglages de USER, puis on liste ce qu'elle a change d'autre.
  if etape "Reappliquer les reglages proteges ($MAJ_DIR/reglages-proteges.yaml)" \
      "hermes-reglages.py appliquer config.yaml reglages-proteges.yaml --avant $config_avant"; then
    "$SCRIPTS/hermes-reglages.py" appliquer $HOME/.hermes/config.yaml "$MAJ_DIR/reglages-proteges.yaml" \
      --avant "$config_avant" \
      || echo "ATTENTION : reglages proteges non reappliques, a faire a la main (voir $config_avant)"
  fi

  if etape "Synchro des skills embarquees (comme hermes update)" \
      "$VENV_PY -c 'from tools.skills_sync import sync_skills; sync_skills(quiet=True)'"; then
    (cd "$DEPOT" && "$VENV_PY" -c 'from tools.skills_sync import sync_skills; print(sync_skills(quiet=True))') \
      || echo "ATTENTION : synchro des skills echouee, non bloquant"
  fi

  etape_greffes
  etape_redemarrage

  if [ "$ABLANC" = 1 ]; then
    echo "=== fin du a blanc ==="
    [ ${#REFUS[@]} -eq 0 ] || exit 1
  else
    echo "Bascule terminee. Retour possible : $0 retour --oui  (tag avant-maj-$stamp)"
    if [ -n "$(fichiers_non_commites)" ]; then
      echo "NOTE : la greffe a modifie le depot (fichiers non commites) : la prochaine bascule le refusera tant que ce n'est pas commite ou defait."
    fi
  fi
}

# --- retour -------------------------------------------------------------------
cmd_retour() {
  verifier_depot
  if [ "$OUI" != 1 ] && [ "$ABLANC" != 1 ]; then
    die "retour demande --oui (ou --a-blanc pour voir les etapes sans rien faire)"
  fi
  [ "$ABLANC" = 1 ] || prendre_verrou
  [ "$ABLANC" = 1 ] && echo "=== RETOUR A BLANC : rien n'est execute ==="

  local tag=${POSITIONNEL[0]:-} branche_tag n_dirty
  if [ -z "$tag" ]; then
    tag=$(g tag -l 'avant-maj-????????-????' --sort=-creatordate | head -1)
  fi
  if [ -z "$tag" ]; then
    die "aucun tag avant-maj-* dans le depot : rien a restaurer"
  elif ! g rev-parse --verify --quiet "refs/tags/$tag^{commit}" >/dev/null; then
    refuser "le tag $tag n'existe pas"
  fi
  n_dirty=$(fichiers_non_commites | wc -l)
  [ "$n_dirty" -eq 0 ] || refuser "$n_dirty fichier(s) non commite(s) dans $DEPOT : les committer ou les mettre de cote a la main d'abord"
  conclure_refus

  # La branche d'origine est notee dans le message du tag annote.
  branche_tag=$(g tag -l --format='%(contents:subject)' "$tag" | sed -n 's/^branche=//p')
  echo "Tag : $tag ($(g rev-parse --short=10 "$tag^{commit}")), branche d'origine : ${branche_tag:-detachee ou inconnue}"
  local ancien_head; ancien_head=$(g rev-parse HEAD)

  if [ -n "$branche_tag" ]; then
    if etape "Revenir sur la branche $branche_tag au tag $tag" "git checkout -B $branche_tag $tag"; then
      g checkout -q -B "$branche_tag" "$tag"
    fi
  else
    if etape "Revenir sur le tag $tag (HEAD detache)" "git checkout --detach $tag"; then
      g checkout -q --detach "$tag"
    fi
  fi
  if g rev-parse --verify --quiet "refs/tags/$tag-serie" >/dev/null; then
    if etape "Remettre $SERIE sur son ancienne pointe ($tag-serie)" "git branch -f $SERIE $tag-serie"; then
      g branch -f "$SERIE" "$tag-serie" || echo "ATTENTION : $SERIE non remise (branche utilisee ailleurs ?)"
    fi
  fi
  [ "$ABLANC" = 1 ] || avertir_node "$ancien_head" HEAD

  etape_pycache
  etape_dependances
  etape_import
  etape_greffes
  etape_redemarrage

  if [ "$ABLANC" = 1 ]; then
    echo "=== fin du a blanc ==="
    [ ${#REFUS[@]} -eq 0 ] || exit 1
  else
    echo "Retour termine. La config migree n'est pas defaite (les cles ajoutees restent, sans effet sur l'ancien code)."
  fi
}

# --- aiguillage ---------------------------------------------------------------
case "$SOUS" in
  etat)    cmd_etat ;;
  essai)   cmd_essai ;;
  prochain) cmd_prochain ;;
  bascule) cmd_bascule ;;
  retour)  cmd_retour ;;
  aide|-h|--help|help) aide ;;
  *) echo "sous-commande inconnue : $SOUS" >&2; aide; exit 1 ;;
esac
