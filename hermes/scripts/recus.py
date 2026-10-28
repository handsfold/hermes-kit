#!/usr/bin/env python3
"""Recus des actions de l'agent : debut, fin ou echec. Alerte au QG si pas de fin.

Ne le 2026-10-03, demande de USER : « un recu pour chaque action, avec une
alerte chez moi s'il n'y a pas de fin ». Avant, un tour coupe par un
redemarrage disparaissait sans trace : veilleur.py effacait sa ligne de
tours_actifs sans rien dire.

Qui ecrit quoi, dans qg.db, table recus :
  debut   injecter-regles.py (hook pre_llm_call), action « tour »
  fin     qg-collecter.py (hook post_llm_call)
  echec   ce script, quand un recu reste ouvert alors que le tour ne peut plus
          finir, ou quand une execution cron finit en failed ou unknown
  redem-sur.sh ecrit aussi les siens, action « redemarrage »

Tourne hors du gateway (par surveillance.py, timer surveillance.timer, toutes les 3 min) : il doit
survivre a ce qu'il surveille. Usage :
  recus.py            controle, et alerte au QG par echec nouveau
  recus.py --liste    les 15 derniers recus
"""
import os
import sqlite3
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from veilleur import poster, _demarrage_gateway, a_repondu  # noqa: E402
from qg_adresse import adresse

DB = os.path.expanduser("~/.hermes/qg.db")
EXE = os.path.expanduser("~/.hermes/cron/executions.db")
QG = adresse()
# gateway_timeout vaut 1800 s : un tour ne peut pas vivre au-dela. Marge de 5 min.
TOUR_MAX = 2100
# Un recu de redemarrage sans fin apres ce delai : le gateway n'est pas revenu.
REDEM_MAX = 15 * 60
SCHEMA = ("CREATE TABLE IF NOT EXISTS recus (id INTEGER PRIMARY KEY, session_id TEXT, "
          "action TEXT, debut REAL, fin REAL, statut TEXT, detail TEXT, "
          "ref TEXT UNIQUE, alerte REAL)")


def hm(t):
    return datetime.fromtimestamp(t).strftime("%H:%M") if t else "?"


def nom_topic(c, sid):
    r = c.execute("SELECT COALESCE(NULLIF(nom_infere,''), thread_id) FROM topics "
                  "WHERE session_id = ?", (sid,)).fetchone()
    if r and r[0]:
        return str(r[0])
    if sid.startswith("cron_"):
        return "cron " + sid.split("_")[1]
    return sid


def echouer(c, rid, detail):
    c.execute("UPDATE recus SET statut = 'echec', fin = ?, detail = ? WHERE id = ?",
              (time.time(), detail, rid))


def controler(c, now):
    g = _demarrage_gateway()
    for rid, sid, action, debut in c.execute(
            "SELECT id, session_id, action, debut FROM recus "
            "WHERE statut = 'debut'").fetchall():
        if action == "redemarrage":
            if now - debut > REDEM_MAX:
                echouer(c, rid, "gateway pas revenu {} min apres l'ordre".format(int((now - debut) / 60)))
            continue
        coupe = g is not None and debut < g - 5
        trop_vieux = now - debut > TOUR_MAX
        if not (coupe or trop_vieux):
            continue
        # Le hook de fin a pu rater son ecriture alors que le tour a repondu.
        # Le transcript fait foi : on ferme le recu sans alerter.
        if a_repondu(sid, debut):
            c.execute("UPDATE recus SET statut = 'fin', fin = ?, detail = ? WHERE id = ?",
                      (now, "fin lue dans le transcript", rid))
            continue
        if coupe:
            echouer(c, rid, "coupe par le redemarrage du gateway de {}".format(hm(g)))
        else:
            echouer(c, rid, "aucune fin apres {} min".format(int((now - debut) / 60)))

    # Executions cron mortes : le scheduler les marque failed ou unknown.
    if os.path.exists(EXE):
        x = sqlite3.connect(EXE, timeout=3)
        rows = x.execute(
            "SELECT id, job_id, status, COALESCE(started_at, claimed_at), COALESCE(error,'') "
            "FROM executions WHERE status IN ('failed','unknown') "
            "AND claimed_at > datetime('now','-1 day')").fetchall()
        x.close()
        for eid, job, statut, debut_txt, err in rows:
            try:
                debut = datetime.fromisoformat(debut_txt).timestamp()
            except Exception:
                debut = now
            detail = "cron {} : {}{}".format(job, statut, (" · " + err[:140]) if err else "")
            # Si le tour de ce cron a deja son recu ouvert ou en echec, on le complete.
            r = c.execute(
                "SELECT id FROM recus WHERE session_id LIKE ? AND debut BETWEEN ? AND ? "
                "AND ref IS NULL ORDER BY debut LIMIT 1",
                ("cron_{}_%".format(job), debut - 120, debut + 900)).fetchone()
            if c.execute("SELECT 1 FROM recus WHERE ref = ?", (eid,)).fetchone():
                continue
            if r:
                c.execute("UPDATE recus SET statut = 'echec', fin = COALESCE(fin, ?), "
                          "detail = ?, ref = ? WHERE id = ?", (now, detail, eid, r[0]))
            else:
                c.execute("INSERT INTO recus (session_id, action, debut, fin, statut, detail, ref) "
                          "VALUES (?, 'cron', ?, ?, 'echec', ?, ?)",
                          ("cron_" + job, debut, now, detail, eid))


def alerter(c):
    for rid, sid, debut, detail in c.execute(
            "SELECT id, session_id, debut, detail FROM recus "
            "WHERE statut = 'echec' AND alerte IS NULL").fetchall():
        texte = ("*Action sans fin* · {}\nDebut {} · {}\nRecu {}".format(
            nom_topic(c, sid), hm(debut), detail or "cause inconnue", rid))
        if poster(QG, texte):
            c.execute("UPDATE recus SET alerte = ? WHERE id = ?", (time.time(), rid))


def liste(c):
    for r in c.execute("SELECT id, session_id, action, debut, fin, statut, COALESCE(detail,'') "
                       "FROM recus ORDER BY id DESC LIMIT 15"):
        print("{:>5} {:<10} {:<6} {} -> {} {:<38} {}".format(
            r[0], r[2], r[5], hm(r[3]), hm(r[4]), r[1][:38], r[6][:60]))


def main():
    c = sqlite3.connect(DB, timeout=10)
    c.execute(SCHEMA)
    if "--liste" in sys.argv:
        liste(c)
        return 0
    now = time.time()
    controler(c, now)
    c.commit()
    alerter(c)
    c.commit()
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
