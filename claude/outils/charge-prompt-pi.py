#!/usr/bin/python3
"""Charge du bloc skills dans le prompt de Pi, et les plus lourdes.

Pi injecte, a chaque tour, le nom, la description et le chemin de chaque skill
visible. Les skills marquees `disable-model-invocation: true` sont chargees mais
n'apparaissent pas dans le prompt. Les .fdignore de chaque racine coupent en amont.

Le calcul suit le code de Pi (dist/core/skills.js et system-prompt.js) :
collecte par racine, arret sur un SKILL.md, dossiers caches non visites,
premier nom gagne en cas de collision.

Usage : charge-prompt-pi.py [--liste N] [--seuil V J]
  --liste N : les N skills les plus lourdes en description, avec leur fichier.
  --seuil V J : sort en code 1 si visibles > V ou jetons > J (pour un hook).

Sans option : `visibles <n> jetons <n>` sur une ligne, puis le detail.
"""
import os
import re
import sys
from pathlib import Path

RACINES = [Path.home() / ".agents/skills", Path.home() / ".hermes/skills",
           Path.home() / ".claude/skills"]
IGNORES = (".gitignore", ".ignore", ".fdignore")
PART = re.compile(r"^description:\s*(.*)$", re.M)
NOM = re.compile(r"^name:\s*(.*)$", re.M)
ENTETE = ("\n\nThe following skills provide specialized instructions for specific tasks.\n"
          "Use the read tool to load a skill's file when the task matches its description.\n"
          "Resolve relative paths against the skill's directory (parent of SKILL.md). "
          "Use absolute paths in tool calls.\n\n<available_skills>\n")
DESACTIVE = re.compile(r"^disable-model-invocation:\s*true", re.M)


def regles(racine):
    """Motifs des fichiers d'ignore d'une racine, prefixes comme Pi le fait."""
    motifs = []
    for nom in IGNORES:
        p = racine / nom
        if not p.exists():
            continue
        for ligne in p.read_text(errors="ignore").splitlines():
            l = ligne.strip()
            if not l or l.startswith("#"):
                continue
            neg = l.startswith("!")
            if neg:
                l = l[1:]
            l = l.lstrip("/")
            motifs.append(("!" if neg else "") + l)
    return motifs


def ignore(rel, motifs, est_dossier):
    """Reproduit la semantique de la librairie ignore : dernier motif gagnant."""
    cible = rel + "/" if est_dossier else rel
    nom = os.path.basename(cible.rstrip("/"))
    etat = False
    for m in motifs:
        neg = m.startswith("!")
        pat = m[1:] if neg else m
        if pat.endswith("/"):
            pat = pat[:-1]
        if pat == nom or pat == cible.rstrip("/") or pat == rel:
            etat = not neg
        elif pat.endswith("/*") and rel.startswith(pat[:-1]):
            etat = not neg
        elif pat.startswith("*/") and f"/{pat[2:]}/" in f"/{rel}/":
            etat = not neg
        elif f"**/{pat}" == f"**/{rel}" or rel.startswith(pat + "/"):
            etat = not neg
    return etat


def collecter(dossier, racine, motifs, profondeur=0):
    """Les SKILL.md d'une racine, en respectant l'arret et les exclusions."""
    sortie = []
    if not dossier.is_dir():
        return sortie
    try:
        entrees = list(dossier.iterdir())
    except OSError:
        return sortie
    rel = "." if dossier == racine else str(dossier.relative_to(racine))
    for e in entrees:
        if e.name == "SKILL.md" and e.is_file():
            if not ignore(rel + "/SKILL.md" if rel != "." else "SKILL.md", motifs, False):
                sortie.append(e)
            return sortie
    for e in sorted(entrees, key=lambda x: x.name):
        if e.name.startswith(".") or e.name == "node_modules":
            continue
        r = e.name if rel == "." else f"{rel}/{e.name}"
        if e.is_dir():
            if ignore(r, motifs, True):
                continue
            sortie.extend(collecter(e, racine, motifs, profondeur + 1))
    return sortie


def main():
    vus, visibles, jetons, lourdes, nb_chargees = set(), 0, 0, [], 0
    for racine in RACINES:
        if not racine.is_dir():
            continue
        motifs = regles(racine)
        for f in collecter(racine, racine, motifs):
            t = f.read_text(errors="ignore")
            nom = NOM.search(t)
            desc = PART.search(t)
            if not nom or not desc:
                continue
            n = nom.group(1).strip().strip('"\'')
            d = desc.group(1).strip()
            if len(d) > 1 and d[0] in "\"'" and d[-1] == d[0]:
                d = d[1:-1]
            reel = os.path.realpath(f)
            if n in vus or reel in vus:
                continue
            vus.add(n)
            vus.add(reel)
            nb_chargees += 1
            if DESACTIVE.search(t):
                continue
            visibles += 1
            # gabarit exact de formatSkillsForPrompt
            # gabarit mesure sur formatSkillsForPrompt : 98 fixes + n + desc + chemin
            jetons += 98 + len(n) + len(d) + len(str(f))
            lourdes.append((len(d), n, f))
    if visibles:
        jetons += 284 + len("</available_skills>")
    jetons //= 3.8
    jetons = int(jetons)
    print(f"visibles {visibles} jetons {jetons} sur {nb_chargees} chargees")

    if "--liste" in sys.argv:
        n = int(sys.argv[sys.argv.index("--liste") + 1]) if sys.argv.index("--liste") + 1 < len(sys.argv) else 10
        for taille, nom, f in sorted(lourdes, reverse=True)[:n]:
            print(f"{taille:5d} {nom:32s} {f}")

    if "--seuil" in sys.argv:
        i = sys.argv.index("--seuil")
        vmax, jmax = int(sys.argv[i + 1]), int(sys.argv[i + 2])
        if visibles > vmax or jetons > jmax:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
