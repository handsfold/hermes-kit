#!/usr/bin/env python3
"""L'etat du bouclier Claude, en une commande (2026-11-08).

  claude-bouclier.py [jours]     refus, replis Opus, mots filtrees, lecons, config

Centralise tout ce qui protege le compte Claude depuis le ban du 2026-11-08 :
fichier de config des mots, filtre du proxy, lecons injectees, journaux.
"""
import collections
import glob
import json
import os
import re
import subprocess
import sys
import time

LOG_SENSIBLES = os.path.expanduser("~/.hermes/logs/sensibles.log")
DISPATCH = os.path.expanduser("~/.hermes/qg-dispatch.log")
LECONS = os.path.expanduser("~/.claude/lecons-refus.md")
CONFIG = os.path.expanduser("~/.config/claude-proxy/mots-sensibles.json")
PROJETS = os.path.expanduser("~/.claude/projects")


def refus_transcripts(jours):
    """(total, par jour, sessions touchees) depuis les transcripts Claude."""
    limite = time.time() - jours * 86400
    motif = re.compile(
        r"(?i)je ne peux pas|impossible de|cannot verify|can't (verify|access)|"
        r"peux-tu (me )?(confirmer|preciser)|il me manque|besoin d'acces|pas acces|"
        r"hors (du )?(perimetre|champ)|out of scope")
    par_jour, sessions, total = collections.Counter(), set(), 0
    for f in glob.glob(os.path.join(PROJETS, "*", "*.jsonl")):
        if os.path.getmtime(f) < limite:
            continue
        n = 0
        try:
            for l in open(f, errors="ignore"):
                if '"type":"assistant"' not in l and '"type": "assistant"' not in l:
                    continue
                try:
                    d = json.loads(l)
                except Exception:
                    continue
                m = d.get("message") or {}
                c = m.get("content")
                txt = c if isinstance(c, str) else " ".join(
                    x.get("text", "") for x in (c or [])
                    if isinstance(x, dict) and x.get("type") == "text") if isinstance(c, list) else ""
                if txt and motif.search(txt):
                    n += 1
        except Exception:
            continue
        if n:
            total += n
            par_jour[time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(f)))] += n
            sessions.add(os.path.basename(os.path.dirname(f)))
    return total, par_jour, len(sessions)


def compte_journal(chemin, motif, jours):
    limite = time.time() - jours * 86400
    n = 0
    try:
        for l in open(chemin, errors="ignore"):
            if motif.search(l) and time.time() - os.path.getmtime(chemin) < jours * 86400 + 3600:
                n += 1
    except OSError:
        pass
    return n


def main():
    jours = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    maintenant = time.strftime("%Y-%m-%d %H:%M")
    print(f"BOUCLIER CLAUDE · {maintenant} · fenetre {jours} j\n")

    try:
        n_mots = len(json.load(open(CONFIG)).get("mots", []))
        print(f"Config mots sensibles : {CONFIG} ({n_mots} mots, relu a chaud, 30 s)")
    except Exception as e:
        print(f"Config : ILLEISIBLE ({e})")

    n_filtre = compte_journal(LOG_SENSIBLES, re.compile(r"n=\d+"), jours)
    print(f"Filtre du proxy : {n_filtre} mots reformules sur {jours} j")

    total, par_jour, sessions = refus_transcripts(jours)
    print(f"Refus dans les reponses de Claude : {total} ({sessions} sessions)")
    for j in sorted(par_jour):
        print(f"  {j} : {par_jour[j]}")

    n_repli = compte_journal(DISPATCH, re.compile(r"repli opus"), jours)
    n_refus_topic = compte_journal(DISPATCH, re.compile(r"refus detecte"), jours)
    print(f"Replis Opus 4.8 : {n_repli} · refus attrapes avant repli : {n_refus_topic}")

    try:
        n_lecons = len([l for l in open(LECONS) if l.startswith("- ")])
        print(f"Lecons injectees a Claude : {n_lecons} ({LECONS})")
    except OSError:
        print("Lecons : fichier absent (aucune lecons en core)")

    seuil = 30
    if total > seuil:
        print(f"\nANOMALIE : {total} refus > seuil {seuil} sur {jours} j : regarder refus-apprendre.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
