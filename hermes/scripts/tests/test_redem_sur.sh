#!/usr/bin/env bash
# Preuve du correctif de redem-sur.sh : un tour plus vieux que TOUR_MAX ne compte
# que si SA session a un pouls vivant, pas n'importe quel CLI.
#
# Cas du 2026-10-11 : la session fantome test-relais-qg-1791656981 (tour oublie)
# a bloque un redemarrage, parce qu'un AUTRE CLI avait un pouls recent.
#
# Tout se passe dans un dossier temporaire : ni qg.db ni le gateway ne sont touches.
set -uo pipefail
ICI=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d /tmp/test-redem-XXXXXX)
ECHECS=0
verifie() { # libelle attendu obtenu
  if [ "$2" = "$3" ]; then echo "OK  $1"; else echo "KO  $1 : attendu $2, obtenu $3"; ECHECS=$((ECHECS + 1)); fi
}

# --- 1. Le script : base factice, aucun redemarrage ---------------------------
sqlite3 "$T/qg.db" "CREATE TABLE tours_actifs (session_id TEXT PRIMARY KEY, debut REAL, modele TEXT, cible TEXT, pouls REAL);
  CREATE TABLE topics (session_id TEXT PRIMARY KEY, thread_id TEXT, nom_infere TEXT);"
sqlite3 "$T/exe.db" "CREATE TABLE executions (job_id TEXT, status TEXT, claimed_at TEXT);"
NOW=$(date +%s)
# Tour fantome : demarre il y a 50 min, plus vieux que TOUR_MAX (35 min).
sqlite3 "$T/qg.db" "INSERT INTO tours_actifs (session_id, debut) VALUES ('test-relais-qg-fantome', $((NOW - 3000)));"
# Tour long mais reel : 50 min aussi.
sqlite3 "$T/qg.db" "INSERT INTO tours_actifs (session_id, debut) VALUES ('entreprise-a-reel', $((NOW - 3000)));"

compte() { # $1 = sessions vivantes (une par ligne, via une commande factice)
  printf '#!/bin/bash\nprintf "%%s" "%s"\n' "$1" >"$T/vivantes.sh"; chmod +x "$T/vivantes.sh"
  REDEM_DB="$T/qg.db" REDEM_EXE="$T/exe.db" REDEM_DEMARRAGE=$((NOW - 7200)) \
    REDEM_VIVANTES_CMD="$T/vivantes.sh" "$ICI/redem-sur.sh" --compte
}
verifie "aucun pouls vivant : les 2 vieux tours ne comptent pas" 0 "$(compte '')"
verifie "pouls de entreprise-a-reel seulement : 1 seul tour compte" 1 "$(compte 'entreprise-a-reel')"
verifie "le fantome n'est pas sauve par le pouls d'une autre session" 1 "$(compte 'entreprise-a-reel')"
verifie "pouls des 2 sessions : les 2 comptent" 2 "$(compte $'entreprise-a-reel\ntest-relais-qg-fantome')"
sqlite3 "$T/qg.db" "INSERT INTO tours_actifs (session_id, debut) VALUES ('recent', $((NOW - 60)));"
verifie "un tour recent compte toujours, pouls ou non" 1 "$(compte '')"

# --- 2. L'appariement : le pouls d'un autre CLI ne sauve pas le fantome -------
RES=$(python3 - "$ICI" <<'PY'
import sys, time
sys.path.insert(0, sys.argv[1])
from redem_pouls import sessions_vivantes
now = time.time()
tours = [("fantome", now - 3000), ("reel", now - 3000 + 400)]
# Un seul CLI vivant, parti 20 s apres le tour "reel" : celui de "reel".
travaux = [{"uuid": "u1", "depart": now - 3000 + 420, "pouls": now - 30}]
v1 = sessions_vivantes(tours, travaux, {}, now, 600)
# Meme CLI, mais appris comme lie a "reel" : "fantome" ne le recoit pas.
v2 = sessions_vivantes(tours, travaux, {"reel": "u1"}, now, 600)
# Pouls trop vieux : plus rien de vivant.
v3 = sessions_vivantes(tours, [dict(travaux[0], pouls=now - 900)], {"reel": "u1"}, now, 600)
# Deux candidats dans la fenetre : ambigu, personne n'est declare vivant.
t2 = [{"uuid": "a", "depart": now - 3000 + 100, "pouls": now - 5}, {"uuid": "b", "depart": now - 3000 + 110, "pouls": now - 5}]
v4 = sessions_vivantes([("fantome", now - 3000)], t2, {}, now, 600)
print(sorted(v1), sorted(v2), sorted(v3), sorted(v4))
PY
)
verifie "apparier : le CLI de 'reel' ne profite pas au fantome" "['reel'] ['reel'] [] []" "$RES"

if [ "$ECHECS" -eq 0 ]; then echo "TOUT OK"; exit 0; fi
echo "$ECHECS echec(s)"; exit 1
