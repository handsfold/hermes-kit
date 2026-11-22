#!/usr/bin/env python3
"""Exposition du vocabulaire sensible envoye a Claude (2026-11-08).

  sensibles-bilan.py [jours]     remplacements du filtre + exposition brute

Le filtre du proxy claude (server.js, `nettoyer`) reformule jailbreak, malware,
botnet, ransomware, virus, infection, phishing, payload, backdoor, stealer,
trojan, hack, pirate, attaque, exploit avant l'envoi. Ce bilan lit ses
remplacements (~/.hermes/logs/sensibles.log, depuis le 2026-11-08) et mesure
l'exposition brute dans les transcripts des jours passes.
"""
import collections
import glob
import json
import os
import re
import sys
import time

LOG = os.path.expanduser("~/.hermes/logs/sensibles.log")
PROJETS = os.path.expanduser("~/.claude/projects")
MOTS = ["jailbreak", "malware", "botnet", "ransom", "virus", "infect", "phishing",
        "payload", "backdoor", "stealer", "trojan", "hack", "pirate", "attaque",
        "attack", "exploit", "red team", "red-team"]


def bilan(jours):
    limite = time.time() - jours * 86400
    filtre = collections.Counter()
    if os.path.exists(LOG):
        for l in open(LOG, errors="ignore"):
            m = re.match(r"(\S+)T\S+ n=(\d+)", l)
            if m and time.time() - time.mktime(time.strptime(m.group(1), "%Y-%m-%d")) < (jours + 1) * 86400:
                filtre[m.group(1)[:10]] += int(m.group(2))
    print(f"Filtre du proxy : {sum(filtre.values())} mots reformules sur {jours} j")
    for j in sorted(filtre):
        print(f"  {j} : {filtre[j]}")
    # Exposition brute : ce qui partait avant le filtre, transcripts des N jours.
    brut = collections.Counter()
    n_sessions = 0
    for f in glob.glob(os.path.join(PROJETS, "*", "*.jsonl")):
        if os.path.getmtime(f) < limite:
            continue
        touche = False
        try:
            for l in open(f, errors="ignore"):
                bas = l.lower()
                for k in MOTS:
                    if k in bas:
                        brut[k] += bas.count(k)
                        touche = True
        except Exception:
            continue
        if touche:
            n_sessions += 1
    print(f"\nExposition brute dans {n_sessions} sessions des {jours} derniers jours :")
    for k, v in brut.most_common(8):
        print(f"  {k:12} {v}")
    return 0


if __name__ == "__main__":
    jours = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
    sys.exit(bilan(jours))
