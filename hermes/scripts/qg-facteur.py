#!/usr/bin/env python3
"""Le facteur : porte chaque rapport au QG, que le telephone reponde ou non.

La file `attente` se remplit toute seule, le hook `qg-collecter` s'en charge.
Jusqu'au 2026-10-03, le texte n'arrivait au QG que par la bulle du Pixel
(rapport.sh, lance par le garde), et ce script ne parlait que si l'ADB etait
mort. Resultat : ADB coupe ou a moitie vivant, plus aucun rapport au QG.

Desormais c'est lui qui poste le texte, toutes les 30 s, des qu'un rapport
est stable depuis GRACE_S. La bulle ne garde que la voix. Un rapport n'est
poste qu'une fois : la colonne `notifie` le grave, et rapport.sh la lit et
l'ecrit aussi. USER repond dans le QG, et le QG relaie avec
`qg-attente relais <id> "<sa phrase>"`.
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from qg_adresse import adresse

DB = os.path.expanduser("~/.hermes/qg.db")
ENV = os.path.expanduser("~/.hermes/.env")
CHAT = adresse()[0]
THREAD = adresse()[1]
# Un rapport doit etre stable (aucun nouveau tour du topic) depuis ce delai.
GRACE_S = int(os.environ.get("QG_FACTEUR_GRACE", "90"))
LOT_MAX = 5


def env(cle):
    try:
        with open(ENV) as f:
            for ligne in f:
                if ligne.startswith(cle + "="):
                    return ligne.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def cx():
    c = sqlite3.connect(DB, timeout=10.0)
    c.row_factory = sqlite3.Row
    try:
        c.execute("ALTER TABLE attente ADD COLUMN notifie REAL")
        c.commit()
    except sqlite3.OperationalError:
        pass  # deja la
    return c


def envoyer(texte):
    jeton = env("TELEGRAM_BOT_TOKEN")
    if not jeton:
        print("pas de TELEGRAM_BOT_TOKEN", file=sys.stderr)
        return False
    data = urllib.parse.urlencode({
        "chat_id": CHAT,
        "message_thread_id": THREAD,
        "text": texte,
        "disable_web_page_preview": "true",
    }).encode()
    url = "https://api.telegram.org/bot{}/sendMessage".format(jeton)
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            return json.load(r).get("ok", False)
    except Exception as e:
        print("envoi impossible : {}".format(e), file=sys.stderr)
        return False


def sujet_de(cible):
    """'telegram:-100...:1230' -> le nom lisible du topic, si on le connait."""
    thread = (cible or "").rsplit(":", 1)[-1]
    if not thread:
        return ""
    c = sqlite3.connect("file:{}?mode=ro".format(DB), uri=True, timeout=5.0)
    r = c.execute("SELECT nom FROM noms WHERE thread_id = ?", (thread,)).fetchone()
    if not r:
        r = c.execute(
            "SELECT nom_infere FROM topics WHERE thread_id = ? AND nom_infere IS NOT NULL"
            " ORDER BY derniere_activite DESC LIMIT 1", (thread,)).fetchone()
    c.close()
    return (r[0] if r else "") or ""


QG_ATTENTE = "/usr/local/bin/qg-attente"
VERROU_LECTURE = "/tmp/qg-rapport.lock"


def lecture_en_cours():
    """rapport.sh tient-il son verrou ? Alors c'est lui qui poste, on attend."""
    import fcntl
    try:
        f = open(VERROU_LECTURE, "a")
    except OSError:
        return False
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        f.close()


def qg(*args, timeout=90):
    try:
        r = subprocess.run([QG_ATTENTE] + list(args), capture_output=True,
                           text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def main():
    """Tout rapport stable part au QG, que le telephone reponde ou non.

    USER, 2026-10-03 : « tous les rapports doivent arriver dans le QG ». Le
    texte ne depend donc plus de la bulle : c'est hote-1 qui le poste, une
    fois le rapport stable depuis GRACE_S (un topic qui enchaine les tours
    rafraichit sa ligne, on ne poste pas chaque tour). La bulle ne garde que
    la voix : quand elle lit un rapport deja poste, rapport.sh saute le texte.
    Si la bulle l'a lu avant nous, statut passe a « lu » et rien ne part ici.
    """
    c = cx()
    lignes = c.execute(
        "SELECT id, cible FROM attente"
        " WHERE statut = 'nouveau' AND notifie IS NULL"
        " AND cree < ? ORDER BY cree LIMIT ?",
        (time.time() - GRACE_S, LOT_MAX)).fetchall()
    if not lignes or lecture_en_cours():
        c.close()
        print("CR: resume {} rapport(s) en attente, rien a porter".format(len(lignes)), flush=True)
        print("CR: donnee en_attente={}".format(len(lignes)), flush=True)
        return 0
    portes = 0
    sans_texte = 0
    echec_envoi = False
    for r in lignes:
        texte = qg("voix", str(r["id"])) or qg("texte", str(r["id"]))
        if not texte:
            sans_texte += 1
            continue
        # Relu juste avant l'envoi : la bulle a pu le poster pendant le resume.
        deja = c.execute("SELECT statut, notifie FROM attente WHERE id = ?",
                         (r["id"],)).fetchone()
        if not deja or deja["statut"] != "nouveau" or deja["notifie"]:
            continue
        nom = sujet_de(r["cible"])
        if not envoyer("Rapport{}\n{}".format(" " + nom if nom else "", texte)[:4000]):
            echec_envoi = True
            break
        c.execute("UPDATE attente SET notifie = ? WHERE id = ?",
                  (time.time(), r["id"]))
        c.commit()
        portes += 1
    c.close()
    if portes:
        print("porte {} rapport(s)".format(portes))
    print("CR: resume {} rapport(s) portes sur {}".format(portes, len(lignes)), flush=True)
    if sans_texte:
        print("CR: service qg-attente=ko texte vide pour {} rapport(s)".format(sans_texte), flush=True)
    else:
        print("CR: service qg-attente=ok", flush=True)
    if echec_envoi:
        print("CR: service telegram=ko envoi refuse ou injoignable", flush=True)
    elif portes:
        print("CR: service telegram=ok", flush=True)
    if (echec_envoi or sans_texte) and not portes:
        print("CR: etat warn", flush=True)
    print("CR: donnee portes={}".format(portes), flush=True)
    print("CR: donnee en_attente={}".format(len(lignes)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
