#!/usr/bin/env python3
"""PostToolUse : un fichier de cockpit/web est modifie -> reconstruit la page publique (dashboard/static).
La page exemple.tld ne lit pas cockpit/web : sans cette etape, le changement n'est jamais visible."""
import json, re, subprocess, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
chemin = (d.get("tool_input") or {}).get("file_path", "")
if not re.search(r"/perso/outils/cockpit/web/[^ ]*\.(js|css|html)$", chemin) or re.search(r"\.(bak|avant)", chemin):
    sys.exit(0)
r = subprocess.run(["python3", "$HOME/Bureau/Projets/perso/outils/cockpit/construire-stack.py"],
                   capture_output=True, text=True, timeout=60)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
    "additionalContext": ("Page publique reconstruite (stack.html/stack.js). " if r.returncode == 0 else "ECHEC reconstruction page publique : ")
    + (r.stdout.splitlines()[0] if r.returncode == 0 and r.stdout else (r.stderr or r.stdout)[-300:])
    + " Verifier le rendu sur la route servie avant d'annoncer."}}))
