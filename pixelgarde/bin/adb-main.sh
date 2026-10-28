# Une seule main par telephone : arbitre entre agents et lots (2026-10-06).
# Source par adb-garde et par le CLI `telephone`. Ne s'execute pas seul.
#
# POURQUOI CE FICHIER EXISTE
# Le 06/10, un lot LINE (annonce dans 23 groupes, lance par un agent) et un
# agent qui reglait WhatsApp Business se sont coupe l'A07 l'un l'autre
# pendant 30 min : 10 groupes en echec, les horaires jamais poses. adb-garde
# classait les deux « pilote » (meme service claude-proxy) et ne tranchait
# qu'entre pilote et tache planifiee. USER : « si je lance une nouvelle tache,
# ca coupe l'automatisation temporairement, fait la tache, puis ca reprend,
# et les agents ne doivent pas se couper sans cesse ni tourner en rond ».
#
# LA REGLE
#   - Qui tient le telephone a un BAIL (bail-<appareil>), rafraichi a chaque
#     commande qui modifie l'ecran. Les lectures (dump, capture) passent.
#   - pilote (session d'agent, terminal) : garde la main tant qu'il agit.
#     Un autre pilote attend son tour dans la FILE, sans jamais le couper.
#     Le bail tombe si le pilote reste inactif ADB_INACTIF s (180) ou si sa
#     session est finie.
#   - lot (script detache : annonces LINE, envois en serie) : cede la main
#     a tout pilote, attend en silence, puis reprend tout seul. Un lot se
#     reconnait sans rien declarer : aucun agent ni terminal parmi ses
#     ancetres. ADB_CLASSE=lot le force.
#   - la file sert les pilotes avant les lots, puis par ordre d'arrivee.
#     Une place reste gardee 150 s entre deux essais du meme pilote.

MAIN_INACTIF=${ADB_INACTIF:-180}
MAIN_INACTIF_LOT=${ADB_INACTIF_LOT:-300}
MAIN_ATTENTE=${ADB_ATTENTE:-100}
MAIN_ATTENTE_LOT=${ADB_ATTENTE_LOT:-14400}
MAIN_PLACE=150

# Fixe MAIN_CLASSE (pilote|lot), MAIN_PROPRIO (cle stable) et MAIN_LIBELLE.
# La cle d'une session Hermes est son --resume : le proxy relance un
# processus claude a chaque message, son pid change, la session reste.
main_identite() {
  local p=$$ c cmd n=0
  if [ -n "${ADB_PROPRIO:-}" ]; then
    MAIN_PROPRIO="nom:$ADB_PROPRIO"; MAIN_CLASSE=${ADB_CLASSE:-pilote}
    MAIN_LIBELLE=${ADB_LIBELLE:-$ADB_PROPRIO}; return
  fi
  if [ "${ADB_CLASSE:-}" != lot ]; then
    while [ "$p" -gt 1 ] 2>/dev/null && [ $n -lt 40 ]; do
      n=$((n + 1))
      c=$(cat /proc/$p/comm 2>/dev/null) || break
      if [ "$c" = claude ]; then
        cmd=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
        MAIN_CLASSE=pilote
        if [[ "$cmd" =~ --resume\ ([0-9a-f-]{36}) ]]; then
          MAIN_PROPRIO="claude:${BASH_REMATCH[1]}"
          MAIN_LIBELLE="session ${BASH_REMATCH[1]:0:8} ($(basename "$(readlink /proc/$p/cwd 2>/dev/null)"))"
        else
          MAIN_PROPRIO="pid:$p"
          MAIN_LIBELLE="agent pid $p ($(basename "$(readlink /proc/$p/cwd 2>/dev/null)"))"
        fi
        return
      fi
      case "$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)" in
        *hermes_cli.main\ gateway*) MAIN_CLASSE=pilote; MAIN_PROPRIO="pid:$p"; MAIN_LIBELLE="Hermes"; return ;;
      esac
      [ "$c" = systemd ] && break
      p=$(sed 's/.*) //' /proc/$p/stat 2>/dev/null | cut -d' ' -f2)
    done
  fi
  local sid tty
  sid=$(ps -o sid= -p $$ 2>/dev/null | tr -d ' ')
  tty=$(ps -o tty= -p $$ 2>/dev/null | tr -d ' ')
  MAIN_PROPRIO="sid:$sid"
  if [ "${ADB_CLASSE:-}" != lot ] && [ -n "$tty" ] && [ "$tty" != "?" ]; then
    MAIN_CLASSE=pilote; MAIN_LIBELLE="terminal $tty"
  else
    MAIN_CLASSE=lot
    # Le libelle vient de l'ancetre le plus haut : le chef de session est
    # souvent deja mort (setsid puis &), le script du lot, lui, tourne.
    local h=$$ pp
    while pp=$(sed 's/.*) //' /proc/$h/stat 2>/dev/null | cut -d' ' -f2) && [ "${pp:-1}" -gt 1 ] \
          && [ "$(cat /proc/$pp/comm 2>/dev/null)" != systemd ]; do h=$pp; done
    MAIN_LIBELLE="$(tr '\0' ' ' < /proc/$h/cmdline 2>/dev/null | cut -c1-50)($(basename "$(readlink /proc/$h/cwd 2>/dev/null)"))"
  fi
}

# Le proprietaire est-il encore la ? Une session Hermes entre deux messages
# n'a plus de processus : elle a fini son tour, le telephone est libre.
main_vivant() {
  case "$1" in
    claude:*) pgrep -f -- "--resume ${1#claude:}" >/dev/null ;;
    pid:*) kill -0 "${1#pid:}" 2>/dev/null ;;
    sid:*) pgrep -s "${1#sid:}" >/dev/null ;;
    *) return 0 ;;
  esac
}

main_age() { echo $(( $(date +%s) - $(stat -c %Y "$1" 2>/dev/null || echo 0) )); }

# Lit le bail : B_CLASSE B_PROPRIO B_DEBUT B_LIBELLE, et dit s'il tient encore.
main_lire_bail() {
  B_CLASSE= B_PROPRIO= B_DEBUT= B_LIBELLE= B_AGE=
  [ -s "$1" ] || return 1
  IFS=$'\t' read -r B_CLASSE B_PROPRIO B_DEBUT B_LIBELLE < "$1"
  B_AGE=$(main_age "$1")
  local lim=$MAIN_INACTIF; [ "$B_CLASSE" = lot ] && lim=$MAIN_INACTIF_LOT
  [ "$B_AGE" -lt "$lim" ] && main_vivant "$B_PROPRIO"
}

# Premier ticket vivant de la file, pilotes d'abord. Nettoie les perimes.
main_tete() {
  local f t
  for f in $(ls "$1" 2>/dev/null | sort); do
    t="$1/$f"
    if [ "$(main_age "$t")" -ge "$MAIN_PLACE" ] || ! main_vivant "$(cut -f1 "$t")"; then
      rm -f "$t"; continue
    fi
    cut -f1 "$t"; return
  done
}

main_journal() { printf '%s  %s %s\n' "$(date -Is)" "$1" "$2" >> "$PRIORITE/journal.log"; }

# Prend la main sur l'appareil, ou attend son tour. Sort en 75 si un pilote
# attend trop longtemps : il garde sa place 150 s et doit reessayer.
main_prendre() {
  local app=$1 bail="$PRIORITE/bail-$1" file="$PRIORITE/file-$1" verrou="$PRIORITE/bail-$1.lock"
  local debut ticket="" rang tete annonce=0 max libre
  main_identite
  mkdir -p "$file"
  debut=$(date +%s)
  max=$MAIN_ATTENTE; [ "$MAIN_CLASSE" = lot ] && max=$MAIN_ATTENTE_LOT
  ticket=$(grep -lF -- "$MAIN_PROPRIO"$'\t' "$file"/* 2>/dev/null | head -1)
  while :; do
    exec 8>"$verrou"; flock 8
    libre=0
    if main_lire_bail "$bail"; then
      if [ "$B_PROPRIO" = "$MAIN_PROPRIO" ]; then
        touch "$bail"; flock -u 8; exec 8>&-
        [ -n "$ticket" ] && rm -f "$ticket"
        return 0
      fi
      [ "$MAIN_CLASSE" = pilote ] && [ "$B_CLASSE" = lot ] && libre=1
    else
      libre=1
    fi
    if [ "$libre" = 1 ]; then
      tete=$(main_tete "$file")
      if [ -z "$tete" ] || [ "$tete" = "$MAIN_PROPRIO" ]; then
        if [ -n "$B_PROPRIO" ] && [ "$B_CLASSE" = lot ] && main_vivant "$B_PROPRIO"; then
          main_journal "$app" "PAUSE $B_LIBELLE, la main passe a $MAIN_LIBELLE"
          echo "adb-garde : $app etait pris par $B_LIBELLE. Je le mets en pause, il reprendra seul." >&2
        fi
        printf '%s\t%s\t%s\t%s\n' "$MAIN_CLASSE" "$MAIN_PROPRIO" "$(date +%s)" "$MAIN_LIBELLE" > "$bail"
        flock -u 8; exec 8>&-
        [ -n "$ticket" ] && rm -f "$ticket"
        main_journal "$app" "MAIN $MAIN_CLASSE $MAIN_LIBELLE"
        return 0
      fi
    fi
    # Pas mon tour : je prends ou garde ma place dans la file.
    if [ -z "$ticket" ] || [ ! -e "$ticket" ]; then
      rang=1; [ "$MAIN_CLASSE" = lot ] && rang=2
      ticket="$file/$rang-$(date +%s%N)"
      printf '%s\t%s\n' "$MAIN_PROPRIO" "$MAIN_LIBELLE" > "$ticket"
    else
      touch "$ticket"
    fi
    flock -u 8; exec 8>&-
    if [ "$annonce" = 0 ]; then
      annonce=1
      local qui=${B_LIBELLE:-$(cut -f2 "$file/$(ls "$file" | sort | head -1)" 2>/dev/null)}
      if [ "$MAIN_CLASSE" = lot ]; then
        echo "adb-garde : $app pris par $qui. Le lot se met en pause et reprendra seul." >&2
        main_journal "$app" "ATTENTE lot $MAIN_LIBELLE derriere $qui"
      else
        echo "adb-garde : $app pris par $qui. J'attends mon tour (${max} s max), sans le couper..." >&2
        main_journal "$app" "ATTENTE $MAIN_LIBELLE derriere $qui"
      fi
    fi
    if [ $(( $(date +%s) - debut )) -ge "$max" ]; then
      main_journal "$app" "REFUS $MAIN_LIBELLE apres ${max} s"
      cat >&2 <<MSG
adb-garde : $app toujours pris par ${B_LIBELLE:-un autre agent}. Commande NON executee (code 75).
Ta place dans la file est gardee $MAIN_PLACE s. NE PAS contourner : pas d'appel au vrai
adb, pas de kill de l'autre tache. Attendre la main : \`telephone attendre $app\`.
Voir qui tient quoi : \`telephone etat\`.
MSG
      exit 75
    fi
    sleep 1
  done
}

# Rend la main tout de suite (fin de pilotage), si on la tient.
main_rendre() {
  local bail="$PRIORITE/bail-$1"
  main_identite
  exec 8>"$PRIORITE/bail-$1.lock"; flock 8
  if main_lire_bail "$bail" || [ -s "$bail" ]; then
    if [ "$B_PROPRIO" = "$MAIN_PROPRIO" ] || [ "${2:-}" = --force ]; then
      rm -f "$bail"; main_journal "$1" "RENDU par $MAIN_LIBELLE"
      echo "$1 rendu."
    else
      echo "$1 tenu par $B_LIBELLE, pas par toi : rien rendu (--force pour forcer)."
    fi
  else
    echo "$1 deja libre."
  fi
  flock -u 8; exec 8>&-
}
