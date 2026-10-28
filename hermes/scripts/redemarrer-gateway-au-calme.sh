#!/usr/bin/env bash
# Le SEUL script de redemarrage du gateway Hermes. Il attend la fin de TOUS les
# tours en cours, sans limite de temps, puis redemarre.
#
#   setsid nohup ~/.hermes/scripts/redem-sur.sh >/dev/null 2>&1 </dev/null &
#
# Fusion du 2026-10-03 (demande de USER) de redem-sur.sh et de
# redemarrer-gateway-au-calme.sh, devenu un lien vers ce fichier. Les deux
# anciennes versions avaient chacune un plafond (7 et 15 min) au bout duquel
# elles redemarraient quand meme ou renoncaient : un tour long etait tue.
# Ici, aucun plafond. Apres 45 min d'attente, une alerte au QG, et on attend.
#
# Le signal : la table tours_actifs de qg.db. Le hook pre_llm_call y inscrit
# chaque tour, le hook post_llm_call l'efface a la fin. L'ancien comptage des
# processus `claude -p` etait faux : leurs enfants dorment pendant les outils.
#
# La session appelante n'est PAS ignoree : son tour finit juste apres avoir
# lance ce script en tache de fond, sa reponse part, puis on redemarre.
#
# Compatibilite : `--qui-suis-je` et l'argument session_id des anciennes
# versions sont acceptes et sans effet. `--essai` fait tout sauf redemarrer.
set -uo pipefail

case "${1:-}" in
  --qui-suis-je) echo "-"; exit 0 ;;
esac
ESSAI=0; [ "${1:-}" = "--essai" ] && ESSAI=1
# --compte : imprime le nombre de tours qui feraient attendre, puis sort (sans verrou,
# sans journal, sans rien redemarrer). Sert aux tests (tests/test_redem_sur.sh).
COMPTE=0; [ "${1:-}" = "--compte" ] && COMPTE=1

# Les chemins se surchargent par l'environnement pour les tests seulement.
DB=${REDEM_DB:-$HOME/.hermes/qg.db}
EXE=${REDEM_EXE:-$HOME/.hermes/cron/executions.db}
LOG=${REDEM_LOG:-/tmp/redem-sur.log}
LOCK=${REDEM_LOCK:-/tmp/redem-sur.lock}
# Les lignes tools.tts_tool vivent dans agent.log depuis fin septembre. Ne lire
# que gateway.log rendait la garde aveugle : le 2026-10-03 a 21:50, le gateway
# a ete coupe 1 s avant la fin d'une synthese de 15 s, l'audio n'est jamais parti.
# On lit les deux, et la ligne la plus recente gagne.
TTSLOGS="$HOME/.hermes/logs/agent.log $HOME/.hermes/logs/gateway.log"
GRACE=${GRACE:-8}          # apres le dernier tour : l'audio doit avoir demarre
TOUR_MAX=2100              # gateway_timeout (1800 s) plus 5 min : au-dela, ligne morte
ALERTE_APRES=${ALERTE_APRES:-2700}
IGNORER=${IGNORER:-}       # essais seulement : session a ne pas attendre (la sienne)
VIVANTES_CMD=${REDEM_VIVANTES_CMD:-python3 $HOME/.hermes/scripts/redem_pouls.py --db $DB}
read -r QG_CHAT QG_THREAD < <(python3 "$HOME/.hermes/scripts/qg_adresse.py")

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

# Un seul redemarrage a la fois : un 2e appel pendant l'attente ne fait rien.
if [ "$COMPTE" = 0 ]; then
  exec 9>"$LOCK"
  if ! flock -n 9; then
    echo "$(date '+%F %T') deja en attente, appel ignore" >> "$LOG"
    exit 0
  fi
  : > "$LOG"
  log "depart (essai=$ESSAI)"
fi

demarrage_gateway() {
  [ -n "${REDEM_DEMARRAGE:-}" ] && { echo "$REDEM_DEMARRAGE"; return; }
  local pid; pid=$(systemctl --user show -p MainPID --value hermes-gateway 2>/dev/null)
  [ -n "$pid" ] && [ "$pid" != "0" ] && stat -c %Z "/proc/$pid" 2>/dev/null || echo 0
}

# Tours en vol. Une ligne ne compte que si elle est nee apres le demarrage du
# gateway actuel (sinon le tour est deja mort), et a moins de TOUR_MAX.
# Une ligne cron ne compte que si executions.db dit ce job « running ».
# On compte aussi les executions cron running, meme avant leur 1er appel LLM.
# Un tour de plus de TOUR_MAX n'est pas forcement mort : le 2026-10-08, un tour
# EntrepriseA de 49 min (envois LINE en serie) a ete ignore et sa voix coupee par le
# redemarrage de 17:09:56. Au-dela de TOUR_MAX, le tour compte encore si un CLI
# du proxy A SA SESSION a un transcript modifie depuis moins de POULS_MAX.
# Le 2026-10-11, la session fantome test-relais-qg-1791656981 a bloque un
# redemarrage parce que le pouls etait celui d'un CLI quelconque : redem_pouls.py
# apparie maintenant chaque tour a son propre CLI.
POULS_MAX=${POULS_MAX:-600}
# Liste SQL des sessions au pouls vivant : 'a','b' ('' si aucune, aucun id n'est vide).
vivantes_sql() {
  local liste
  liste=$($VIVANTES_CMD --pouls-max "$POULS_MAX" 2>/dev/null | sed "s/'/''/g; s/^/'/; s/\$/'/" | paste -sd, -)
  echo "${liste:-''}"
}

actifs() {
  local g; g=$(demarrage_gateway)
  local vif; vif=$(vivantes_sql)
  sqlite3 "$DB" "ATTACH '$EXE' AS x;
    SELECT (SELECT COUNT(*) FROM tours_actifs t
            WHERE t.debut > $g - 5 AND (t.debut > strftime('%s','now') - $TOUR_MAX OR t.session_id IN ($vif))
              AND t.session_id != '$IGNORER'
              AND (t.session_id NOT LIKE 'cron\_%' ESCAPE '\'
                   OR EXISTS (SELECT 1 FROM x.executions e WHERE e.status = 'running'
                              AND t.session_id LIKE 'cron\_' || e.job_id || '\_%' ESCAPE '\')))
         + (SELECT COUNT(*) FROM x.executions e WHERE e.status IN ('claimed','running')
            AND CAST(strftime('%s', e.claimed_at) AS INTEGER) > strftime('%s','now') - $TOUR_MAX
            AND NOT EXISTS (SELECT 1 FROM tours_actifs t
                            WHERE t.session_id LIKE 'cron\_' || e.job_id || '\_%' ESCAPE '\'));" \
    2>/dev/null || echo 0
}

qui() {
  local g; g=$(demarrage_gateway)
  local vif; vif=$(vivantes_sql)
  sqlite3 "$DB" "SELECT group_concat(COALESCE(NULLIF(p.nom_infere,''), p.thread_id, t.session_id), ', ')
    FROM tours_actifs t LEFT JOIN topics p USING(session_id)
    WHERE t.debut > $g - 5 AND (t.debut > strftime('%s','now') - $TOUR_MAX OR t.session_id IN ($vif));" 2>/dev/null
}

# L'audio part apres le texte (13 a 15 s d'Edge TTS) : attendre qu'il soit envoye.
attendre_audio() {
  sleep "$GRACE"
  local fin=$(( $(date +%s) + 120 )) derniere
  while [ "$(date +%s)" -lt "$fin" ]; do
    derniere=$(for f in $TTSLOGS; do tail -n 4000 "$f" 2>/dev/null | grep 'tools.tts_tool' | tail -1; done | sort | tail -1)
    case "$derniere" in
      *"Generating speech"*|*transcoding*) sleep 2 ;;
      *) break ;;
    esac
  done
  # « audio saved » n'est pas « envoye » : l'upload d'un ogg de 1 Mo prend
  # quelques secondes de plus.
  sleep 8
}

alerter() {
  local tok; tok=$(grep '^TELEGRAM_BOT_TOKEN=' "$HOME/.hermes/.env" | cut -d= -f2- | tr -d "'\"")
  [ -z "$tok" ] && return
  curl -s -m 12 -o /dev/null "https://api.telegram.org/bot$tok/sendMessage" \
    --data-urlencode "chat_id=$QG_CHAT" --data-urlencode "message_thread_id=$QG_THREAD" \
    --data-urlencode "text=$1"
}

if [ "$COMPTE" = 1 ]; then
  actifs
  exit 0
fi

debut=$(date +%s); alerte=0; dernier_n=-1
while :; do
  n=$(actifs); [ -z "$n" ] && n=0
  if [ "$n" -eq 0 ]; then
    log "plus aucun tour en vol, attente de l'envoi du texte et de l'audio"
    attendre_audio
    n=$(actifs); [ -z "$n" ] && n=0
    [ "$n" -eq 0 ] && break
    log "un tour a demarre entre-temps, on attend encore"
  fi
  if [ "$n" != "$dernier_n" ]; then
    log "attente : $n tour(s) en vol : $(qui)"
    dernier_n=$n
  fi
  if [ "$alerte" = "0" ] && [ $(( $(date +%s) - debut )) -ge "$ALERTE_APRES" ]; then
    alerter "Redemarrage du gateway en attente depuis $(( ALERTE_APRES / 60 )) min : $n tour(s) encore en vol ($(qui)). J'attends toujours, rien n'est coupe."
    log "alerte envoyee au QG apres $ALERTE_APRES s"
    alerte=1
  fi
  sleep 3
done

attendu=$(( $(date +%s) - debut ))
if [ "$ESSAI" = "1" ]; then
  log "ESSAI : aurait redemarre maintenant, apres ${attendu} s d'attente"
  exit 0
fi

# Recu de l'action, ferme par recus.py ou ci-dessous une fois le gateway revenu.
rid=$(sqlite3 "$DB" "INSERT INTO recus (session_id, action, debut, statut, detail)
  VALUES ('gateway', 'redemarrage', strftime('%s','now'), 'debut', 'apres ${attendu} s d''attente');
  SELECT last_insert_rowid();" 2>/dev/null)
log "redemarrage apres ${attendu} s d'attente (recu ${rid:-?})"
REDEMARRAGE_ASSUME=1 systemctl --user restart hermes-gateway
for _ in $(seq 1 40); do
  [ "$(systemctl --user is-active hermes-gateway)" = "active" ] && break
  sleep 3
done
etat=$(systemctl --user is-active hermes-gateway)
log "gateway $etat a $(date +%H:%M:%S)"
if [ "$etat" = "active" ] && [ -n "${rid:-}" ]; then
  sqlite3 "$DB" "UPDATE recus SET statut='fin', fin=strftime('%s','now') WHERE id=$rid;"
fi
