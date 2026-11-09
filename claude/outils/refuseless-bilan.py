#!/usr/bin/env python3
"""Usage du provider refuseless, lu dans les logs agent (hors proxy).

Les topics sur refuseless appellent api.refuseless.com en direct : le proxy
ne les voit pas. Chaque appel laisse pourtant une ligne `API call #N` dans
~/.hermes/logs/agent.log* avec tokens, cache et latence. Cet outil les agrege.

  refuseless-bilan.py [jours]      bilan par jour, modele et topic (defaut 7)
  refuseless-bilan.py --cles       soldes vivants des cles du pool (API /v1/credits)
  refuseless-bilan.py --profil X   instance de profil dediee (ex. hunter, groupe Opsec)
                                   : logs et base du profil ~/.hermes/profiles/X/

Prix non expose par l'API refuseless : le bilan est en tokens, pas en dollars.
"""
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request

LOGS = os.path.expanduser("~/.hermes/logs/agent.log*")
QG = os.path.expanduser("~/.hermes/qg.db")
NOMS = os.path.expanduser("~/.hermes/qg-noms.json")
AUTH = os.path.expanduser("~/.hermes/auth.json")

LIGNE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}.*API call #\d+: model=(\S+) "
    r"provider=refuseless in=(\d+) out=(\d+) total=(\d+) latency=([\d.]+)s"
    r"(?: cache=(\d+)/(\d+) \((\d+)%\))?")


def topics_connus():
    """session_id -> nom lisible du topic (qg.db + qg-noms.json)."""
    noms = {}
    try:
        for cle, nom in json.load(open(NOMS)).items():
            noms[cle] = nom
    except Exception:
        pass
    out = {}
    try:
        c = sqlite3.connect(f"file:{QG}?mode=ro", uri=True, timeout=5.0)
        c.row_factory = sqlite3.Row
        for r in c.execute("SELECT session_id, thread_id, chat_id FROM topics"):
            cle = f'{r["chat_id"]}:{r["thread_id"]}' if r["chat_id"] else ""
            out[r["session_id"]] = noms.get(cle) or (f"topic {r['thread_id']}" if r["thread_id"] else "hors telegram")
        c.close()
    except Exception:
        pass
    return out


def appels():
    """Toutes les lignes d'appel refuseless des logs (rotations comprises)."""
    for f in sorted(glob.glob(LOGS), key=os.path.getmtime):
        for l in open(f, errors="ignore"):
            m = LIGNE.match(l)
            if m:
                yield m


def bilan(jours):
    t = topics_connus()
    limite = time.time() - jours * 86400
    # Les dates des logs n'ont pas l'annee de fichier : on garde tout ce que
    # les rotations couvrent, filtre par jour civil si les logs debordent.
    par_jour, par_modele, par_topic = {}, {}, {}
    tot = {"appels": 0, "in": 0, "out": 0, "cache_in": 0, "lat": 0.0}
    for m in appels():
        jour, modele, entree, sortie, total, lat = m.group(1), m.group(2), \
            int(m.group(3)), int(m.group(4)), int(m.group(5)), float(m.group(6))
        cache_in = int(m.group(7) or 0)
        # session = l'id entre crochets du log, s'il est present sur la ligne
        sid = None
        s = re.search(r"\[(\d{8}_\d{6}_[0-9a-f]+)\]", lorigine := m.string)
        sid = s.group(1) if s else None
        nom = t.get(sid, "session inconnue")
        d = {"appels": 0, "in": 0, "out": 0, "cache_in": 0, "lat": 0.0}
        for cible in (par_jour.setdefault(jour, d.copy()),
                      par_modele.setdefault(modele, d.copy()),
                      par_topic.setdefault(nom, d.copy()), tot):
            cible["appels"] += 1
            cible["in"] += entree
            cible["out"] += sortie
            cible["cache_in"] += cache_in
            cible["lat"] += lat
    print(f"Appels refuseless des logs disponibles ({jours} j demandes, couverture log : "
          f"{min(par_jour) if par_jour else '?'} -> {max(par_jour) if par_jour else '?'})\n")
    if not tot["appels"]:
        print("Aucun appel trouve.")
        return
    cache_pc = 100 * tot["cache_in"] / tot["in"] if tot["in"] else 0
    print(f"TOTAL : {tot['appels']} appels · in {tot['in']/1e6:.1f} M · out {tot['out']/1e3:.0f} k · "
          f"cache {cache_pc:.0f}% · latence moy {tot['lat']/tot['appels']:.1f} s\n")
    print("Par jour :")
    for jour in sorted(par_jour):
        d = par_jour[jour]
        print(f"  {jour} : {d['appels']:4} appels · in {d['in']/1e6:6.1f} M · out {d['out']/1e3:5.0f} k · "
              f"lat moy {d['lat']/d['appels']:5.1f} s")
    print("\nPar modele :")
    for modele, d in sorted(par_modele.items(), key=lambda x: -x[1]["in"]):
        print(f"  {modele:32} {d['appels']:4} appels · in {d['in']/1e6:6.1f} M · out {d['out']/1e3:5.0f} k")
    print("\nTop topics (tokens entrants) :")
    for nom, d in sorted(par_topic.items(), key=lambda x: -x[1]["in"])[:10]:
        print(f"  {nom[:40]:42} {d['appels']:4} appels · in {d['in']/1e6:6.1f} M · out {d['out']/1e3:5.0f} k · "
              f"lat moy {d['lat']/d['appels']:5.1f} s")


def cles():
    try:
        pool = json.load(open(AUTH))["credential_pool"]["custom:refuseless"]
    except Exception as e:
        print("pool illisible :", e)
        return 1
    for e in pool:
        cle = e.get("access_token") or ""
        try:
            req = urllib.request.Request("https://api.refuseless.com/v1/credits",
                                         headers={"Authorization": "Bearer " + cle})
            with urllib.request.urlopen(req, timeout=15) as r:
                c = json.loads(r.read())
            print(f'  {e["label"]:24} {e["id"]} · solde {c.get("available"):10.3f} $ '
                  f'· pool: {e.get("last_status") or "ok"}')
        except Exception as ex:
            print(f'  {e["label"]:24} {e["id"]} · erreur {getattr(ex, "code", ex)}')
    return 0


def main():
    a = sys.argv[1:]
    if "--cles" in a:
        return cles()
    global LOGS, QG, NOMS, AUTH
    for i, x in enumerate(a):
        if x == "--profil" and i + 1 < len(a):
            racine = os.path.expanduser(f"~/.hermes/profiles/{a[i + 1]}")
            LOGS = f"{racine}/logs/agent.log*"
            QG = f"{racine}/qg.db"
            NOMS = f"{racine}/qg-noms.json"
            AUTH = f"{racine}/auth.json"
    jours = 7
    for x in a:
        if x.isdigit():
            jours = int(x)
    bilan(jours)
    return 0


if __name__ == "__main__":
    sys.exit(main())
