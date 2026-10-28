#!/usr/bin/python3
"""Hook UserPromptSubmit : impose les skills critiques quand le message de USER les appelle.

Une description de skill ne garantit pas son chargement : le modele decide.
Pour les skills marquees "forcer": true dans ~/.claude/outils/declencheurs.json,
ce hook repere un mot declencheur dans le message et ajoute au contexte la
consigne de charger la skill. Rien n'est ajoute si la skill est deja chargee
dans la session (recherche dans le transcript).

Ne bloque jamais : en cas d'erreur, il sort sans rien dire.
Né : 2026-10-06 (revue des skills, point 2).
"""
import json
import re
import sys
from pathlib import Path

DECLENCHEURS = Path.home() / ".claude/outils/declencheurs.json"
BLOCS = re.compile(
    r"<(memory-context|regles-apprises|system-reminder|task-notification)>.*?</\1>", re.S
)


SYSTEME = re.compile(r"\n\[System:.*?(?=\n\n|\Z)", re.S)


def nettoyer(texte):
    """Retire la memoire et les rappels injectes : ils citent EntrepriseA en permanence."""
    texte = BLOCS.sub(" ", texte)
    # Hermes colle "[System: The skills available ... changed" et la liste des skills
    # apres un simple saut de ligne : elle cite « PC EntrepriseA », « mot de passe »...
    return SYSTEME.sub(" ", texte)


def deja_chargee(nom, transcript):
    try:
        t = Path(transcript).read_text(errors="ignore")
    except Exception:
        return False
    return (f"{nom}/SKILL.md" in t or f'"skill":"{nom}"' in t
            or f'"skill": "{nom}"' in t or f"'name': '{nom}'" in t)


def main():
    try:
        entree = json.load(sys.stdin)
        table = json.loads(DECLENCHEURS.read_text())
    except Exception:
        return
    texte = nettoyer(entree.get("prompt") or "")
    if not texte.strip():
        return
    notes = []
    for nom, regle in table.items():
        if nom.startswith("_") or not regle.get("forcer"):
            continue
        for motif in regle.get("motifs", []):
            m = re.search(motif, texte, re.I)
            if m:
                if not deja_chargee(nom, entree.get("transcript_path") or ""):
                    notes.append(
                        f"- Skill `{nom}` (mot repere : « {m.group(0)} ») : charge-la avant de "
                        f"repondre, par l'outil Skill si elle y figure, sinon lis "
                        f"`{regle['chemin']}`."
                    )
                break
    if notes:
        contexte = ("Skills a charger pour ce message (hook skills-forcees). "
                    "Si le mot est hors sujet, ignore la ligne.\n" + "\n".join(notes))
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit", "additionalContext": contexte}},
            ensure_ascii=False))


if __name__ == "__main__":
    main()
