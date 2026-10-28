#!/usr/bin/env python3
"""Journal des skills : chaque chargement, puis ce qui suit (temps 1 de la boucle d'amelioration).

Pose le 2026-10-06. Sans ce journal, aucune boucle ne sait si une skill a rendu
service : `Retro agent hebdo` modifiait les skills sans mesure avant et apres.

3 evenements, un seul script :
- PostToolUse (Skill, skill_view, Read d'un SKILL.md) : note le chargement ;
- PostToolUseFailure : note l'echec d'outil qui suit une skill ;
- UserPromptSubmit : note les 3 messages de USER qui suivent une skill,
  avec un drapeau `correction` quand il corrige ou redemande.

Journal : ~/.claude/journal-skills/AAAA-MM.jsonl. Lecture : `~/.claude/outils/issue-skills.py`.
Contrat : ne bloque jamais, ne parle jamais (exit 0, stdout vide), et se tait
en cas d'erreur. Ne s'execute que s'il y a quelque chose a noter.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

RACINE = Path.home() / ".claude/journal-skills"
ACTIVES = RACINE / "actives"
SUIVI = 3  # messages de USER notes apres le dernier chargement
CORRECTION = re.compile(
    r"c'?est faux|pas (ça|ca) que|tu t'?es tromp|"
    r"recommence|encore (un |une )?(bug|erreur)|"
    r"je t'?ai (déjà |deja )?dit|n'importe quoi|je (ne )?voulais pas|"
    r"\bnon,? (je|tu) (veux|voulais|dois)|"
    r"doesn'?t work|not working|wrong|ผิด",
    re.I,
)
# Messages envoyes par la machine, pas par USER (revue de skills d'Hermes, etc.)
MACHINE = re.compile(r"^(Review the conversation above|<command-|<local-command|Caveat:|"
                     r"This session is being continued|\[Request interrupted|<task-notification)")
COUPE = re.compile(r"<(memory-context|regles-apprises|system-reminder)>", re.I)


def nettoyer(texte):
    texte = COUPE.split(texte or "", maxsplit=1)[0]
    texte = re.sub(r"^\s*Gateway message origin[^\n]*\n", "", texte)  # en-tete Hermes
    texte = re.sub(r'^\s*\{"platform".*?Do not guess a reply destination[^.]*\.\s*', "",
                   texte, flags=re.S)  # bloc d'adressage Hermes
    texte = re.sub(r"^\s*\[[^\]]{1,30}\]\s*", "", texte)  # prefixe « [Vin] »
    return " ".join(texte.split())


def nom_skill(outil, entree):
    if outil == "Skill":
        return (entree.get("skill") or "").split(":")[-1].split("/")[-1] or None
    if outil == "skill_view":
        return (entree.get("name") or "").split("/")[-1] or None
    if outil == "Read":
        p = entree.get("file_path") or ""
        if p.endswith("/SKILL.md"):
            return Path(p).parent.name
    return None


def ecrire(evt):
    RACINE.mkdir(parents=True, exist_ok=True)
    with open(RACINE / time.strftime("%Y-%m.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(evt, ensure_ascii=False) + "\n")


def main():
    d = json.load(sys.stdin)
    session = d.get("session_id") or ""
    if not session:
        return
    etat_f = ACTIVES / f"{session}.json"
    evt_nom = d.get("hook_event_name")
    base = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": session,
            "cwd": d.get("cwd", ""), "source": "hook"}
    if os.environ.get("HERMES_TOPIC_DIR"):
        base["topic"] = Path(os.environ["HERMES_TOPIC_DIR"]).name

    if evt_nom == "PostToolUse":
        skill = nom_skill(d.get("tool_name"), d.get("tool_input") or {})
        if not skill:
            return
        ACTIVES.mkdir(parents=True, exist_ok=True)
        try:
            etat = json.loads(etat_f.read_text())
        except (OSError, ValueError):
            etat = {"skills": []}
        if skill not in etat["skills"]:
            etat["skills"].append(skill)
        etat["reste"] = SUIVI
        etat_f.write_text(json.dumps(etat))
        ecrire({**base, "type": "charge", "skill": skill})
        return

    if not etat_f.exists():
        return  # aucune skill dans cette session : rien a noter
    etat = json.loads(etat_f.read_text())

    if evt_nom == "PostToolUseFailure":
        err = d.get("error") or d.get("tool_response") or ""
        ecrire({**base, "type": "echec", "skills": etat["skills"],
                "outil": d.get("tool_name"), "extrait": str(err)[:200]})
        return

    if evt_nom == "UserPromptSubmit" and etat.get("reste", 0) > 0:
        texte = nettoyer(d.get("prompt"))
        if not texte or MACHINE.match(texte):
            return
        etat["reste"] -= 1
        etat_f.write_text(json.dumps(etat))
        ecrire({**base, "type": "prompt", "skills": etat["skills"],
                "rang": SUIVI - etat["reste"], "extrait": texte[:300],
                "correction": bool(CORRECTION.search(texte))})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
