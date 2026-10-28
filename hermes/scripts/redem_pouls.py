#!/usr/bin/env python3
"""Sessions dont le tour est vieux mais vivant, pour redem-sur.sh.

Un tour de plus de TOUR_MAX n'est pas forcement mort : un tour EntrepriseA de 49 min
(envois LINE en serie) a deja ete coupe a tort. Mais le pouls doit etre CELUI DE
SA SESSION. Avant, redem-sur.sh demandait « un CLI quelconque a-t-il un pouls
recent ? » : le 2026-10-11, la session fantome test-relais-qg-1791656981 (tour
oublie dans tours_actifs) a bloque un redemarrage parce qu'une AUTRE session
travaillait. Ici, chaque tour est apparie a son propre CLI (veilleur.apparier),
et un appariement absent ou ambigu ne compte pas.

Lecture seule : ni qg.db ni l'etat du veilleur ne sont modifies.

  redem_pouls.py [--db CHEMIN] [--pouls-max S]    une session vivante par ligne
"""
import argparse
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


FENETRE = (-60, 420)  # comme veilleur.FENETRE_APPARIEMENT : un CLI nait peu apres son tour


def sessions_vivantes(tours, travaux, liens, now, pouls_max):
    """Ensemble des session_id dont le CLI apparie a battu depuis moins de pouls_max.

    tours : [(session_id, debut)] ; travaux : sortie de veilleur.travaux_en_cours() ;
    liens : {session_id: uuid} appris par le veilleur (copie, jamais modifie).

    Meme regle que veilleur.apparier, avec une difference voulue : les paires sont
    prises par ecart de depart croissant, pas dans l'ordre de la table. Dans l'ordre
    de la table, un tour fantome pouvait voler le CLI d'un tour reel parti 7 min
    apres lui. Un tour a plusieurs candidats mal separes reste non apparie.
    """
    libres = {t["uuid"]: t for t in travaux}
    pris = {}
    for sid, uuid in liens.items():  # 1. liens deja appris, tant que leur CLI vit
        if uuid in libres:
            pris[sid] = libres.pop(uuid)
    restants = [(sid, debut) for sid, debut in tours if sid not in pris and debut is not None]

    ambigus = set()
    paires = []
    for sid, debut in restants:  # 2. candidats par proximite de depart
        cands = sorted(((abs(t["depart"] - debut), t["uuid"]) for t in libres.values()
                        if FENETRE[0] <= t["depart"] - debut <= FENETRE[1]))
        if len(cands) > 1 and not (cands[0][0] <= 15 and cands[1][0] >= 30):
            ambigus.add(sid)
            continue
        paires += [(ecart, sid, uuid) for ecart, uuid in cands[:1]]
    for ecart, sid, uuid in sorted(paires):  # 3. les ecarts les plus petits d'abord
        if sid not in pris and uuid in libres:
            pris[sid] = libres.pop(uuid)
    return {sid for sid, t in pris.items() if sid not in ambigus and now - t["pouls"] < pouls_max}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.path.expanduser("~/.hermes/qg.db"))
    p.add_argument("--pouls-max", type=float, default=600)
    a = p.parse_args()
    try:
        import veilleur
        c = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True, timeout=3)
        tours = c.execute("SELECT session_id, debut FROM tours_actifs").fetchall()
        c.close()
        liens = (veilleur.etat_lu().get("liens") or {})
        vivantes = sessions_vivantes(tours, veilleur.travaux_en_cours(), liens, time.time(), a.pouls_max)
    except Exception as exc:  # noqa: BLE001
        print(f"redem_pouls : {exc}", file=sys.stderr)
        return 0  # en cas de doute, aucun tour vieux ne compte (comme avant)
    for sid in sorted(vivantes):
        print(sid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
