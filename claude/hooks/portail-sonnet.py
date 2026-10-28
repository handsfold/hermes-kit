#!/usr/bin/env python3
"""Impose la navigation web par le sous-agent `portail` (Sonnet, contexte vide).

Mesure du 2026-10-04 (conso-hermes.py 2) : les tours qui ont chargé opencli-browser
relisent 2,2 M de tokens en moyenne. Chaque étape de navigation relit tout
l'historique du topic, plus les arbres de page déjà lus. Un sous-agent repart
d'environ 20 k et rend seulement sa conclusion.

Refuse `opencli browser` dans la session principale. Laisse passer :
- les appels faits DANS un sous-agent (`agent_id` présent dans l'entrée du hook) ;
- les commandes préfixées `PORTAIL_DIRECT=1 ` (un seul coup d'oeil, assumé).
"""
import json
import re
import sys

# Seulement en position de commande : pas dans un texte cité (prompt, grep, commit).
NAVIGUE = re.compile(
    r"(^|[;&|(`]\s*|\$\(\s*|\b(?:then|do|timeout\s+\d+)\s+)(\w+=\S*\s+)*opencli\s+browser\b",
    re.M,
)
# Les commandes qui parlent du hook lui-même (tests, édition).
EXEMPT = re.compile(r"portail-sonnet\.py|agents/portail\.md")
# Sans navigation : aide, etat du pont, fermeture (15 faux refus, 2026-10-28).
SANS_NAVIGATION = re.compile(r"opencli\s+browser\s+(--help|-h|help|list|tabs|sessions|close|chrome|status|doctor)\b")

MOTIF = """Refus : la navigation web passe par le sous-agent `portail` (Sonnet, contexte vide).

Ici, chaque étape de navigation relit tout l'historique du topic : 2,2 M de tokens
par tour en moyenne (mesure du 2026-10-04). Le sous-agent repart de 20 k.

Fais : outil Agent, subagent_type "portail", model "sonnet". Le brief dit le site,
le but, les identifiants à utiliser (référence, jamais la valeur), et ce qu'il doit rendre.
Une seule commande, assumée : préfixer `PORTAIL_DIRECT=1 `."""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if (not NAVIGUE.search(cmd) or data.get("agent_id")
            or "PORTAIL_DIRECT=1" in cmd or EXEMPT.search(cmd)
            or (SANS_NAVIGATION.search(cmd) and len(NAVIGUE.findall(cmd)) == 1)):
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": MOTIF,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
