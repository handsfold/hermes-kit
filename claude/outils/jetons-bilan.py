#!/usr/bin/env python3
"""Bilan du veilleur des jetons : etat de chaque jeton au dernier passage et pannes sur n jours.

Lit ~/.local/state/veilleur-jetons/journal.jsonl (une ligne par passage). Aucun secret.
Usage : jetons-bilan.py [jours=14]
"""
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

J = Path.home() / ".local/state/veilleur-jetons/journal.jsonl"
jours = int(sys.argv[1]) if len(sys.argv) > 1 else 14
if not J.exists():
    sys.exit("journal absent : veilleur-jetons n'a jamais tourne")
lim = datetime.now(timezone.utc) - timedelta(days=jours)
lignes = [json.loads(l) for l in J.read_text().splitlines() if l.strip()]
lignes = [l for l in lignes if datetime.fromisoformat(l["ts"].replace("Z", "+00:00")) >= lim]
if not lignes:
    sys.exit(f"aucun passage depuis {jours} j")
der = lignes[-1]
print(f"{len(lignes)} passage(s) en {jours} j, dernier {der['ts']} : "
      f"{der['ok']} ok, {der['warn']} warn, {der['ko']} ko, {der['inconnu']} inconnu, {der.get('alertes', 0)} alerte(s)")
pannes = Counter()
for l in lignes:
    for nom, etat in l["jetons"].items():
        if etat != "ok":
            pannes[(nom, etat)] += 1
for (nom, etat), n in pannes.most_common():
    print(f"  {etat:8} {nom:32} {n} passage(s)")
if not pannes:
    print("  tous les jetons ok sur la periode")
