"""Adresse du QG Telegram (chat et topic), jamais codee en dur.

Ordre : variables QG_CHAT et QG_THREAD, sinon ~/.hermes/qg-adresse.json.
En ligne de commande, affiche « chat thread » pour les scripts shell.
"""
import json
import os
from pathlib import Path

FICHIER = Path.home() / ".hermes" / "qg-adresse.json"


def adresse():
    chat = os.environ.get("QG_CHAT")
    thread = os.environ.get("QG_THREAD")
    if not (chat and thread) and FICHIER.exists():
        d = json.loads(FICHIER.read_text())
        chat = chat or str(d.get("chat", ""))
        thread = thread or str(d.get("thread", ""))
    if not (chat and thread):
        raise SystemExit("QG : adresse inconnue. Renseigner QG_CHAT et QG_THREAD, "
                         "ou " + str(FICHIER))
    return chat, thread


if __name__ == "__main__":
    print(" ".join(adresse()))
