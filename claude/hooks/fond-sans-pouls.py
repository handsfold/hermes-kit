#!/usr/bin/env python3
"""PreToolUse Bash : sous le proxy Hermes, un Bash lance en fond (run_in_background)
n'a aucun point d'etape automatique et meurt avec le tour. On ne bloque pas
(USER, 2026-10-28 : trop de refus), on rappelle la voie qui a un pouls.
Ne se declenche pas si la commande passe deja par agent-fond.
Ne repond que sous le proxy (HERMES_TOPIC_DIR / CLAUDE_TIMEOUT_MS)."""
import json, os, sys
if not (os.environ.get("HERMES_TOPIC_DIR") or os.environ.get("CLAUDE_TIMEOUT_MS")):
    sys.exit(0)
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if d.get("tool_name") != "Bash":
    sys.exit(0)
e = d.get("tool_input") or {}
if not e.get("run_in_background") or "agent-fond" in (e.get("command") or ""):
    sys.exit(0)
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "Rappel : cette tache de fond n'a pas de point d'etape automatique "
        "et peut mourir avec le tour. Si elle depasse 3 minutes : ~/bin/agent-fond lancer, "
        "USER recevra un pouls toutes les 10 min dans son topic. Sinon, donne-lui toi-meme "
        "un point d'etape spontane (methodes/agents-detaches.md)."}}))
