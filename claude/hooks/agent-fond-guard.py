#!/usr/bin/env python3
"""PreToolUse sur `Agent` : sous le proxy Hermes, refuse un sous-agent en fond.

Cause, mesuree le 2026-09-14 : claude-proxy lance UN process `claude -p` par
tour Telegram (server.js, spawn dans runClaude). Le process sort des que la
reponse est envoyee a USER. Un sous-agent lance en fond (`run_in_background`
absent ou true) vit dans ce process : il meurt avec lui, sans trace. Deux
constructions de l'app Cash flow ont ete perdues ainsi le meme jour.

Exit 2 + stderr = appel bloque, Claude lit le remede.
"""
import json
import os
import sys

sous_proxy = bool(os.environ.get("HERMES_TOPIC_DIR") or os.environ.get("CLAUDE_TIMEOUT_MS"))
if not sous_proxy:
    sys.exit(0)

try:
    donnees = json.load(sys.stdin)
except Exception:
    sys.exit(0)

if donnees.get("tool_name") != "Agent":
    sys.exit(0)

entree = donnees.get("tool_input") or {}
if entree.get("run_in_background") is False:
    sys.exit(0)

# 2026-10-28 : au lieu de refuser (164 refus, pure friction), on bascule
# l'appel au premier plan. Le remede etait toujours le meme.
entree = dict(entree, run_in_background=False)
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Sous-agent bascule au premier plan : sous claude-proxy, "
        "un agent en fond meurt a la fin du tour. Travail long : ~/bin/agent-fond.",
    "updatedInput": entree,
}}))
sys.exit(0)
sys.stderr.write(
    "Sous-agent en fond refuse : cette session tourne sous claude-proxy, "
    "un process `claude` par tour Telegram. Il sort a la fin de la reponse "
    "et tue tout sous-agent en fond (2 constructions perdues le 2026-09-14).\n"
    "Remede, au choix :\n"
    "  1. `run_in_background: false` : le tour attend le resultat (30 min "
    "d'inactivite max, le proxy relance un keepalive).\n"
    "  2. Travail long : `~/bin/agent-fond lancer \"<consigne>\" --nom N "
    "--dossier D --modele M`, puis `agent-fond suivre <id>`. "
    "Il survit a la fin du tour (methodes/agents-detaches.md).\n"
)
sys.exit(2)
