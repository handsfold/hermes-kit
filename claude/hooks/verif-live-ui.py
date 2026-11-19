#!/usr/bin/env python3
"""Stop : refuse « c'est en ligne / corrige » apres un changement d'interface web sans preuve sur le LIVE.

Cree le 2026-11-19 (demande de USER). Regle : contexte/INDEX.md:71, « aucune UI livree sans
preuve visuelle prise sur l'adresse de production » (bin/verif-ui.sh). Elle n'etait que du
texte : verif-avant-annonce accepte un simple curl local.

Declencheur (les 3 ensemble) : le tour modifie un fichier d'interface (web/, static/, public/,
.css, .html) ; la reponse annonce une reussite ; apres la derniere modification, aucun outil ne
touche une adresse non locale AVEC une capture ou un test navigateur (verif-ui.sh, opencli,
agent portail, playwright, screenshot). Echappatoire : annoncer « non verifie sur le live »
sans dire que c'est livre, ou VERIF_LIVE_OFF=1. Un refus par tour, fail-open, journal refus.log.
"""
import importlib.util
import json
import os
import re
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
_s = importlib.util.spec_from_file_location("va", os.path.join(ICI, "verif-avant-annonce.py"))
va = importlib.util.module_from_spec(_s)
_s.loader.exec_module(va)

UI = re.compile(r"/(?:web|static|public|templates)/|\.(?:css|html)$")
NAVIGATEUR = re.compile(r"verif-ui\.sh|opencli|playwright|screenshot|chromium|chrome.*--headless|portail", re.I)
LIVE = re.compile(r"https?://(?!(?:127\.0\.0\.1|localhost|0\.0\.0\.0)\b)[\w.-]+\.[a-z]{2,}", re.I)


def decision(texte, outils):
    if not texte or not va.ANNONCE.search(texte):
        return None
    idx, fichiers = va._modifs(outils)
    ui = [i for i, f in zip(idx, fichiers)
          if UI.search(f) and not any(j in f for j in va.JETABLE)]
    if not ui:
        return None
    if va.AVEU.search(texte) and not va.REPARE.search(texte):
        return None
    for nom, entree in outils[ui[-1] + 1:]:
        blob = json.dumps(entree, ensure_ascii=False)
        if NAVIGATEUR.search(blob) and (LIVE.search(blob) or "verif-ui" in blob or "portail" in blob):
            return None
    return va.ANNONCE.search(texte).group(0), fichiers[idx.index(ui[-1])]


def main():
    if os.environ.get("VERIF_LIVE_OFF"):
        return 0
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    if d.get("stop_hook_active"):
        return 0
    try:
        from _tour import lire_tour
        texte, outils, _ = lire_tour(d.get("transcript_path", ""), {})
        r = decision(d.get("last_assistant_message") or texte, outils)
    except Exception:
        return 0
    if not r:
        return 0
    annonce, fichier = r
    try:
        with open(os.path.join(ICI, "refus.log"), "a") as j:
            j.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} verif-live-ui {annonce!r} {fichier}\n")
    except OSError:
        pass
    sys.stderr.write(
        f"Tu annonces « {annonce} » apres avoir modifie l'interface ({os.path.basename(fichier)}), "
        "mais aucune preuve n'a ete prise sur la version LIVE (adresse de production).\n"
        "Remede : bin/verif-ui.sh <url-live> (captures 1440 et 390), ou le sous-agent portail, "
        "puis regarde les captures et dis laquelle tu as vue. Sinon ecris « non verifie sur le live » "
        "et ne dis pas que c'est livre.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
