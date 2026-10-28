#!/usr/bin/env python3
"""Donne a l'agent le carnet du site qu'il ouvre, et seulement celui-la.

Demande de USER (2026-10-06) : l'agent `portail` redecouvrait chaque site a
chaque run (URLs, selecteurs, pieges) et refaisait les memes erreurs. Une
memoire dans le prompt ferait grossir le contexte pour tous les sites.

Ici : un fichier par domaine dans ~/.claude/sites/<domaine>.md. Au premier
`opencli browser ... <url>` d'un domaine qui a un carnet, le hook l'injecte
dans le contexte (additionalContext), une seule fois par session. Aucun
carnet = aucun effet. Un site jamais visite ne coute rien.
"""
import json
import os
import re
import sys

DOSSIER = os.path.expanduser("~/.claude/sites")
NAVIGUE = re.compile(r"\bopencli\s+browser\b")
URL = re.compile(r"https?://([A-Za-z0-9.-]+)")
MAX = 6000  # octets injectes au plus par carnet


def carnet_de(hote):
    for h in (hote, hote[4:] if hote.startswith("www.") else "www." + hote):
        p = os.path.join(DOSSIER, h + ".md")
        if os.path.isfile(p):
            return h, p
    return None, None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not NAVIGUE.search(cmd):
        return 0
    sid = re.sub(r"\W", "", str(data.get("agent_id") or data.get("session_id") or "x"))
    etat = f"/tmp/carnet-site-{sid}.json"
    try:
        vus = set(json.load(open(etat)))
    except Exception:
        vus = set()
    textes = []
    for hote in dict.fromkeys(URL.findall(cmd)):
        nom, chemin = carnet_de(hote.lower())
        if not nom or nom in vus:
            continue
        vus.add(nom)
        texte = open(chemin, errors="ignore").read()[:MAX]
        textes.append(f"=== Carnet du site {nom} ({chemin}) ===\n{texte}")
    if not textes:
        return 0
    json.dump(sorted(vus), open(etat, "w"))
    entete = ("Carnet de site : partir de ces URLs et de ces lectures. Si une entree "
              "echoue, la corriger dans le fichier. Ajouter ce qui est appris (format : "
              "~/.claude/sites/README.md).\n")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": entete + "\n".join(textes),
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
