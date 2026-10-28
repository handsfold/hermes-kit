#!/usr/bin/env python3
"""qg-pouls : le pouls des tours en vol. Repere l'agent mort en silence.

Jusqu'ici le QG ne voyait que les agents qui parlent. Celui qui meurt sans un
mot n'existait pas : il ne deposait aucun rapport, donc rien ne s'allumait, et
USER decouvrait des heures plus tard qu'un chantier n'avait jamais avance.

Le proxy tient desormais un registre des tours en vol (GET /encours). Ce script
le lit, et ne parle que dans deux cas :

  - un tour s'est termine anormalement (coupure, erreur, timeout) ;
  - un tour vivant n'a rien emis depuis trop longtemps.

Regle de conduite, tiree de l'alarm management : un incident ne se signale
qu'UNE fois. Un veilleur qui repete est un veilleur qu'on eteint.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

ICI = os.path.dirname(os.path.abspath(__file__))
PROXY = os.environ.get("QG_PROXY", "http://127.0.0.1:8000")
# Les deux surcharges servent aux tests : sans elles, verifier le veilleur
# imposerait de deposer de vrais rapports, donc de faire parler le telephone.
MEMOIRE = os.environ.get("QG_POULS_MEMOIRE") or os.path.expanduser("~/.hermes/qg-pouls.json")
ATTENTE = os.environ.get("QG_POULS_ATTENTE") or os.path.join(ICI, "qg-attente.py")

_spec = importlib.util.spec_from_file_location(
    "qgconfig", os.path.join(ICI, "qg-config.py"))
_cfg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cfg)
reglage = _cfg.reglage

import qg_coupures

LOG_AGENT = os.environ.get("QG_POULS_LOG_AGENT") or os.path.expanduser("~/.hermes/logs/agent.log")
MOTIF_INTERRUPTION = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ .*"
                                r"(Interrupt requested|Turn ended: reason=interrupted)")


def interruptions_hermes():
    """Instants ou Hermes a annule lui-meme son appel en cours.

    Cas vus du 06 au 13/10/2026 : USER ecrit pendant un tour, ou une relecture de
    fond est remplacee (« background review superseded »). Le proxy voit alors
    le client partir et note une coupure. Ce n'est pas une panne : 6 alertes
    sur 6 etaient de ce type.
    """
    instants = []
    try:
        with open(LOG_AGENT, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 2_000_000))
            for l in f.read().decode("utf-8", "replace").splitlines():
                m = MOTIF_INTERRUPTION.match(l)
                if m:
                    instants.append(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp())
    except OSError:
        pass
    return instants


def memoire():
    try:
        with open(MEMOIRE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ecrire(m):
    # Le fichier grossirait sans fin : on ne garde que ce qui a moins d'un jour.
    limite = time.time() - 86400
    m = {k: v for k, v in m.items() if v > limite}
    tmp = MEMOIRE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(m, f)
    os.replace(tmp, MEMOIRE)
    return m


def signaler(titre, resume):
    subprocess.run([sys.executable, ATTENTE, "add", titre,
                    "--source", "pouls", "--resume", resume],
                   check=False, capture_output=True)


def lire_encours():
    with urllib.request.urlopen(PROXY + "/encours", timeout=8) as r:
        return json.load(r)


def main():
    silence_max = int(reglage("pouls_silence_min")) * 60
    m = memoire()
    vu = 0

    try:
        etat = lire_encours()
    except urllib.error.HTTPError as e:
        # 404 : le proxy tourne, mais dans une version qui ne tient pas encore
        # le registre des tours. Ce n'est pas une panne, c'est un proxy qui n'a
        # pas ete recharge. Le veilleur se tait jusque-la.
        if e.code == 404:
            return 0
        raise
    except (urllib.error.URLError, OSError, ValueError) as e:
        # Le proxy injoignable est un incident a part entiere, mais un seul :
        # sans cette memoire, une panne d'une heure remplirait douze fois la file.
        if "proxy-muet" not in m:
            m["proxy-muet"] = time.time()
            ecrire(m)
            signaler("Le proxy ne repond plus",
                     "GET {}/encours a echoue : {}.\n\nAucun tour ne peut plus "
                     "etre suivi tant que le proxy est muet. Verifier "
                     "`systemctl --user status claude-proxy`.".format(PROXY, e))
        return 1
    m.pop("proxy-muet", None)

    # Les morts : un arret planifie de la passerelle les explique (on se tait),
    # sinon UNE alerte par fenetre de 2 min (qg_coupures, partage avec
    # tours-veilleur.py : le premier des deux qui passe la dit, l'autre se tait).
    morts = [t for t in etat.get("tours", [])
             if t.get("issue") in qg_coupures.MORTS
             and "{}-{}".format(t.get("id"), t["issue"]) not in m]
    interruptions = interruptions_hermes() if morts else []
    # Coupure voulue par Hermes (60 s avant, 15 s apres) : on se tait.
    muets, groupes = qg_coupures.trier(
        morts, voulue=lambda fin: any(-60 <= a - fin <= 15 for a in interruptions))
    a_noter = list(muets)
    for cles, texte in groupes:
        vu += 1
        a_noter += cles
        signaler("Agents arrêtés net" if len(cles) > 1 else "Un agent s'est arrêté net", texte)
    qg_coupures.noter(a_noter)
    for k in a_noter:
        m[k.replace(":", "-", 1)] = time.time()

    for t in etat.get("tours", []):
        cle = "{}-{}".format(t.get("id"), t.get("issue") or "vol")
        if cle in m:
            continue
        issue = t.get("issue")
        apercu = (t.get("apercu") or "").strip() or "(sans apercu)"
        age = int(t.get("ageS", 0))

        if issue and issue != "fini" and issue not in qg_coupures.MORTS:
            # Autre fin que les trois morts connues (ex. interrompu) : dite telle quelle.
            m[cle] = time.time()
            vu += 1
            signaler(
                "Un tour s'est arrete net ({})".format(issue),
                "Le tour {} a fini en `{}`.\n\nDebut du prompt : {}\n\nDetail : {}".format(
                    t.get("id"), issue, apercu, t.get("detail") or "aucun"))
            continue

        if not issue and int(t.get("silenceS", 0)) >= silence_max:
            m[cle] = time.time()
            vu += 1
            signaler(
                "Un agent se tait depuis {} min".format(
                    int(t.get("silenceS", 0)) // 60),
                "Le tour {} tourne depuis {} s et n'a plus rien émis depuis "
                "{} s.\n\nDemande : {}.\n\n"
                "Il réfléchit peut-être longuement, ou il est bloqué. "
                "Le proxy le laissera vivre jusqu'à son timeout.".format(
                    t.get("id"), age, t.get("silenceS"), qg_coupures.demande(t)))

    ecrire(m)
    if os.environ.get("QG_POULS_BAVARD"):
        print("{} tours en vol, {} signales".format(
            len(etat.get("tours", [])), vu))
    return 0


if __name__ == "__main__":
    sys.exit(main())
