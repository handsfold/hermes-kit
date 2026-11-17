#!/usr/bin/env python3
"""Refus de Claude, rendus visibles (2026-11-08, apres le ban du compte contact).

  refus-bilan.py [jours]     refus par jour et sessions les plus touchees

Lit les transcripts de Claude Code (~/.claude/projects), compte les phrases de
refus de raisonnement dans les reponses. Apres le filtre de vocabulaire du
proxy, un refus n'est plus excusable par le sujet : chaque refus est une piste.
"""
import glob
import json
import os
import re
import sys
import time

PROJETS = os.path.expanduser("~/.claude/projects")
REFUS = re.compile(
    r"(?i)je ne peux pas|impossible de|ne peux (pas|pas verifier)|cannot verify|"
    r"can't (verify|access)|peux-tu (me )?(confirmer|preciser)|il me manque|"
    r"besoin d'acces|pas acces|hors (du )?(perimetre|champ)|out of scope|"
    r"je ne peux pas (verifier|lire)|refuse de")
TETE = re.compile(r"^.{0,120}")


def bilan(jours):
    limite = time.time() - jours * 86400
    par_jour, sessions = {}, []
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
                m = (d.get("message") or {})
                c = m.get("content")
                txt = c if isinstance(c, str) else " ".join(
                    x.get("text", "") for x in (c or [])
                    if isinstance(x, dict) and x.get("type") == "text") if isinstance(c, list) else ""
                if txt and REFUS.search(txt):
                    n += 1
        except Exception:
            continue
        if n:
            jour = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(f)))
            par_jour[jour] = par_jour.get(jour, 0) + n
            sessions.append((n, os.path.basename(os.path.dirname(f)), f))
    total = sum(par_jour.values())
    print(f"{total} refus detects sur {jours} j, dans {len(sessions)} sessions\n")
    for j in sorted(par_jour):
        print(f"  {j} : {par_jour[j]}")
    if sessions:
        print("\nTop sessions :")
        for n, proj, f in sorted(sessions, reverse=True)[:8]:
            print(f"  {n:3} x · {proj[:40]}")
    return 0


if __name__ == "__main__":
    jours = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
    sys.exit(bilan(jours))
