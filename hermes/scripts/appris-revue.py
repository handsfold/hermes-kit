#!/usr/bin/env python3
"""Revue mensuelle des lecons apprises.

Silencieux tant qu'aucune lecon n'a survecu a deux projets differents.
Des qu'une lecon est mure, elle est proposee pour entrer dans le socle.

Lance par un cron Hermes en mode --no-agent : stdout vide = rien n'est envoye.
"""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/.hermes/scripts"))
import focus  # noqa: E402

DEJA = os.path.expanduser("~/.hermes/state/appris-promues.txt")


def cle(groupe):
    return groupe["entrees"][0]["texte"].strip().lower()[:80].strip()


def main():
    entrees = focus.charger_appris()
    if not entrees:
        return 0
    murs = [g for g in focus.grouper_appris(entrees) if len(g["projets"]) >= 2]
    if not murs:
        return 0

    os.makedirs(os.path.dirname(DEJA), exist_ok=True)
    vues = set()
    if os.path.exists(DEJA):
        vues = {l.strip() for l in open(DEJA, encoding="utf-8") if l.strip()}

    neuves = [g for g in murs if cle(g) not in vues]
    if not neuves:
        return 0

    n = len(neuves)
    print(f"Revue du socle : {n} lecon{'s' if n > 1 else ''} "
          f"{'ont' if n > 1 else 'a'} survecu a deux projets.\n")
    for g in neuves:
        projets = " + ".join(sorted(g["projets"]))
        print(f"[{projets}] {g['entrees'][0]['texte']}")
        for e in g["entrees"][1:]:
            print(f"    {e['date']} · {e['projet']} · {e['texte']}")
        print()
    print("A verser dans methodes/socle-projet.md, "
          "ou a laisser si ce n'est pas une regle generale.")

    with open(DEJA, "a", encoding="utf-8") as f:
        for g in neuves:
            f.write(cle(g) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
