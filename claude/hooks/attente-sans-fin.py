#!/usr/bin/env python3
"""Refuse une boucle d'attente qui se trouve elle-meme.

Ne le 2026-10-09 : EntrepriseA 2 attendait la fin d'un script par
`until ! pgrep -f 15_cross_marche.py; do sleep 15; done`. Le script avait fini
depuis 30 min, mais `pgrep -f` cherche dans la ligne de commande complete, et
celle du `bash -c` qui porte la boucle contient le meme nom. La boucle se
trouvait elle-meme et ne finissait jamais. Le veilleur a vu juste (tour mort),
l'agent semblait occupe.

Le hook refuse `pgrep -f` dans une boucle `until` / `while`, sauf avec la
parade des crochets (`pgrep -f '[1]5_cross'`), qui ne se reconnait pas.
Sortie d'urgence : prefixer la commande de `ATTENTE_ASSUMEE=1 `.
"""
import json
import re
import sys

BOUCLE = re.compile(r"\b(until|while)\b")
PGREP = re.compile(r"\bpgrep\s+(?:-\w+\s+)*-\w*f\w*\s+(?:-\w+\s+)*(['\"]?)([^\s'\";|&)]+)\1")

MOTIF = """Refus : cette boucle d'attente ne finira jamais.

`pgrep -f` lit la ligne de commande COMPLETE. Celle du bash qui porte ta boucle
contient le meme nom : la boucle se trouve elle-meme. Le 2026-10-09, EntrepriseA 2
a attendu 30 min un script deja fini, et le tour a ete declare mort.

Attendre plutot :
  - par PID : `while kill -0 <PID> 2>/dev/null; do sleep 15; done`
  - ou avec des crochets, qui ne se reconnaissent pas : `pgrep -f '[1]5_cross_marche.py'`
  - ou lancer le script avec `run_in_background` et attendre sa notification.

Si la boucle est vraiment voulue : prefixe de `ATTENTE_ASSUMEE=1 `."""


def fautif(cmd: str) -> bool:
    if "ATTENTE_ASSUMEE=1" in cmd or not BOUCLE.search(cmd):
        return False
    return any("[" not in m.group(2) for m in PGREP.finditer(cmd))


def main():
    try:
        entree = json.load(sys.stdin).get("tool_input") or {}
    except Exception:
        return
    if fautif(str(entree.get("command") or "")):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": MOTIF}}))


if __name__ == "__main__":
    main()
