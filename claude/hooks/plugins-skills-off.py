#!/usr/bin/env python3
"""Applique skillOverrides aux skills de plugins, que Claude Code ignore.

Pourquoi : dans Claude Code 2.1.288, la fonction qui lit skillOverrides
renvoie "on" d'office pour toute skill de source "plugin". Les entrees
"claude-mem:make-plan": "off" de ~/.claude/settings.json restaient donc
sans effet : environ 1 900 tokens de descriptions relus a chaque session.

Ce script deplace le dossier (ou le .md) de chaque skill de plugin marquee
"off" hors du cache des plugins, dans ~/.local/share/claude-skills-masquees/.
Seul le nom complet "plugin:skill" compte : un nom nu comme "setup" viserait
aussi le "setup" d'un autre plugin (ai-editor:setup, 2026-10-05). La liste
reste la seule source de verite.

Lance au SessionStart (asynchrone) : une mise a jour de plugin qui ramene
les skills est corrigee a la session suivante.

  plugins-skills-off.py              applique, silencieux
  plugins-skills-off.py --voir       applique et liste ce qui a bouge
  plugins-skills-off.py --restaurer  remet toutes les skills masquees
"""
import json
import shutil
import sys
from pathlib import Path

ACCUEIL = Path.home()
REGLAGES = ACCUEIL / ".claude/settings.json"
CACHE = ACCUEIL / ".claude/plugins/cache"
MASQUE = ACCUEIL / ".local/share/claude-skills-masquees"


def overrides_off():
    try:
        o = json.loads(REGLAGES.read_text()).get("skillOverrides") or {}
    except (OSError, ValueError):
        return set()
    return {k for k, v in o.items() if v == "off"}


def candidats():
    """(plugin, skill, chemin) pour chaque skill ou commande de plugin en cache."""
    if not CACHE.is_dir():
        return
    for depot in CACHE.iterdir():
        if not depot.is_dir():
            continue
        for plugin in depot.iterdir():
            if not plugin.is_dir():
                continue
            for version in plugin.iterdir():
                for d in (version / "skills").glob("*/"):
                    if (d / "SKILL.md").exists():
                        yield plugin.name, d.name, d
                for f in (version / "commands").glob("*.md"):
                    yield plugin.name, f.stem, f


def appliquer(voir):
    off = overrides_off()
    bouge = []
    for plugin, skill, chemin in candidats():
        if f"{plugin}:{skill}" not in off:
            continue
        cible = MASQUE / chemin.relative_to(CACHE)
        if cible.exists():
            # Deja masquee une fois : on garde la copie la plus recente.
            shutil.rmtree(cible) if cible.is_dir() else cible.unlink()
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(chemin), str(cible))
        bouge.append(f"{plugin}:{skill}")
    if voir:
        print(f"{len(bouge)} skills de plugins masquees" + (" : " + ", ".join(bouge) if bouge else ""))


def restaurer():
    n = 0
    if MASQUE.is_dir():
        for p in sorted(MASQUE.rglob("*")):
            rel = p.relative_to(MASQUE)
            est_skill = p.is_dir() and rel.parent.name == "skills"
            est_cmd = p.is_file() and rel.parent.name == "commands"
            if not (est_skill or est_cmd):
                continue
            dest = CACHE / rel
            if dest.exists() or not dest.parent.parent.exists():
                continue  # version de plugin disparue, ou deja revenue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dest))
            n += 1
    print(f"{n} skills de plugins restaurees (effet a la prochaine session)")


if __name__ == "__main__":
    if "--restaurer" in sys.argv:
        restaurer()
    else:
        appliquer("--voir" in sys.argv)
