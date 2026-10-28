#!/usr/bin/env python3
"""Statistiques d'installation hermes-kit, actives par defaut (desactivables).

Lance chaque heure par un cron Hermes (script sans agent : il n'ecrit rien sur
la sortie, donc aucun appel au modele). Si HK_TELEMETRIE n'est pas a 1, ou si
aucun jeton membre n'est pose, il ne fait rien.

Liste fermee d'evenements envoyes ici, une seule fois chacun :
  premier_resultat : le bot a repondu au moins une fois dans Telegram apres l'installation ;
  actif_j7         : au 7e jour, le bot a repondu dans les 24 dernieres heures.
Ce qui part : jeton du membre, identifiant d'installation aleatoire, nom de
l'evenement, version du kit, systeme. Jamais le contenu ni la date d'un message,
jamais un identifiant Telegram. Lecture de state.db : des horodatages, rien d'autre.

Usage manuel : hk-telemetrie.py [verifier|envoyer <evenement> [etape]]
"""

import json
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ETAT = Path.home() / ".config" / "hermes-kit"
TELEM = ETAT / "telemetrie"
ENVOYES = ETAT / "evenements-envoyes"
HA = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
EVENEMENTS = {"installe", "etape", "telegram_ok", "premier_resultat", "boite_ok", "actif_j7"}
JOUR = 86400


def lire_etat() -> dict:
    d = {}
    try:
        for ligne in TELEM.read_text(encoding="utf-8").splitlines():
            if "=" in ligne:
                k, v = ligne.split("=", 1)
                d[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return d


def deja(nom: str) -> bool:
    try:
        return nom in ENVOYES.read_text(encoding="utf-8").split()
    except OSError:
        return False


def envoyer(e: dict, evenement: str, etape: str = "") -> bool:
    if e.get("HK_TELEMETRIE") != "1" or evenement not in EVENEMENTS:
        return False
    url, jeton = e.get("HK_EVENT_URL", ""), e.get("HK_MEMBER_TOKEN", "")
    if not url.startswith("https://") or not jeton:
        return False
    corps = {
        "jeton": jeton,
        "install_id": e.get("HK_INSTALL_ID", ""),
        "event": evenement,
        "step": etape,
        "version": e.get("HK_VERSION", "inconnue"),
        "os": e.get("HK_OS", ""),
    }
    req = urllib.request.Request(  # noqa: S310 (https verifie plus haut)
        url,
        data=json.dumps(corps).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 (https verifie plus haut)
            return 200 <= r.status < 300
    except Exception:
        return False


def envoyer_une_fois(e: dict, evenement: str) -> None:
    if deja(evenement):
        return
    if envoyer(e, evenement):
        with ENVOYES.open("a", encoding="utf-8") as f:
            f.write(evenement + "\n")


def derniere_reponse_telegram(apres: float):
    """Horodatage de la derniere reponse du bot dans Telegram apres `apres`, ou None."""
    db = HA / "state.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            row = con.execute(
                "SELECT MAX(m.timestamp) FROM messages m JOIN sessions s ON s.id = m.session_id "
                "WHERE s.source = 'telegram' AND m.role = 'assistant' AND m.timestamp > ?",
                (apres,),
            ).fetchone()
        finally:
            con.close()
        return row[0] if row and row[0] else None
    except sqlite3.Error:
        return None


def verifier() -> None:
    e = lire_etat()
    if e.get("HK_TELEMETRIE") != "1":
        return
    try:
        installe_le = float(e.get("HK_INSTALLE_LE") or 0)
    except ValueError:
        return
    if not installe_le:
        return
    maintenant = time.time()
    if not deja("premier_resultat") and derniere_reponse_telegram(installe_le):
        envoyer_une_fois(e, "premier_resultat")
    # actif_j7 : jugee une seule fois, a la premiere verification apres le 7e jour.
    if maintenant - installe_le >= 7 * JOUR and not deja("actif_j7") and not deja("actif_j7_vu"):
        if derniere_reponse_telegram(maintenant - JOUR):
            envoyer_une_fois(e, "actif_j7")
        if not deja("actif_j7"):
            with ENVOYES.open("a", encoding="utf-8") as f:
                f.write("actif_j7_vu\n")


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] == "verifier":
        verifier()
        return 0
    if args[0] == "envoyer" and len(args) >= 2:
        return 0 if envoyer(lire_etat(), args[1], args[2] if len(args) > 2 else "") else 1
    print(__doc__.strip().splitlines()[-1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
