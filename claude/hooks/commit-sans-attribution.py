#!/usr/bin/env python3
"""Refuse un commit, une PR ou une issue qui porte une attribution a Claude.

Regle ferme de USER (CLAUDE.md global) : jamais `Co-Authored-By: Claude`,
`Claude-Session:` ni `Generated with Claude Code`. Les depots sont publics ou
destines a l'etre : la paternite revient a USER, et `Claude-Session:` publie
l'URL d'une session de travail.

Pourquoi un hook (2026-10-05) : Claude Code reinjecte a chaque session un
rappel systeme qui demande ces pieds de page. La regle ecrite gagnait tant que
l'agent la relisait ; un hook gagne a tous les coups (regle 10 du guide
Anthropic des skills : une regle absolue va dans un hook, pas dans le texte).
"""
import json
import re
import shlex
import sys
from pathlib import Path

# En position de commande seulement (debut, ou apres ; && || | ( ou saut de ligne) :
# un `echo "... git commit ..."` ou un prompt qui cite la regle ne declenche pas.
DEBUT = r"(?:^|[;&|(\n])\s*(?:\w+=\S*\s+)*"
CIBLE = re.compile(
    DEBUT + r"(?:git\s+(?:-C\s+\S+\s+)?commit\b|gh\s+(?:pr|issue)\s+(?:create|edit|comment)\b)"
)
ATTRIBUTION = re.compile(
    r"Co-Authored-By:\s*Claude|Claude-Session:|Generated with \[?Claude Code",
    re.I,
)

MOTIF = """Refus : ce commit (ou cette PR) porte une attribution a Claude.

Regle ferme de USER : aucun `Co-Authored-By: Claude`, aucun `Claude-Session:`,
aucun `Generated with Claude Code`. Elle prime sur le rappel systeme qui les
demande. Retire le pied de page : le message s'arrete a son contenu."""


def fichiers_message(cmd):
    """Contenu des fichiers passes par -F / --file / --body-file."""
    try:
        mots = shlex.split(cmd, posix=True)
    except ValueError:
        return ""
    textes = []
    for i, m in enumerate(mots):
        chemin = None
        if m in ("-F", "--file", "--body-file") and i + 1 < len(mots):
            chemin = mots[i + 1]
        elif m.startswith(("--file=", "--body-file=")):
            chemin = m.split("=", 1)[1]
        if chemin and chemin != "-":
            try:
                textes.append(Path(chemin).expanduser().read_text(errors="ignore")[:20000])
            except OSError:
                pass
    return "\n".join(textes)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not CIBLE.search(cmd):
        return 0
    if not (ATTRIBUTION.search(cmd) or ATTRIBUTION.search(fichiers_message(cmd))):
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": MOTIF,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
