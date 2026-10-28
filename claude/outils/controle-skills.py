#!/usr/bin/python3
"""Controle hebdomadaire des skills : n'ecrit au QG que s'il trouve un ecart.

Lance les outils deja ecrits et resume ce qui demande une action :
  1. audit-skills.py --perso : format (longueur, sommaire, description)
  2. liens casses dans ~/.claude/skills, ~/.hermes/skills, ~/.agents/skills
  3. usage-skills.py 30 : noms presents a la fois chez Claude et Hermes
  4. usage-skills.py 7 --rates : skills ratees dans plus de 50 % des cas (3 sessions mini)
  5. issue-skills.py 7 : skills corrigees par USER dans plus de 25 % des sessions suivies

Usage : controle-skills.py [--sec]   (--sec : affiche sans deposer au QG)
Timer : controle-skills.timer (systemd utilisateur), lundi 8 h.
Ne le 2026-10-06 (revue des skills, point 5).
"""
import re
import subprocess
import sys
from pathlib import Path

OUTILS = Path.home() / ".claude/outils"
PY = "/usr/bin/python3"
# Doublons de nom voulus par USER (2026-10-24, rapport 4290) : jamais signales.
HOMONYMES_VOULUS = {"computer-use"}


def lancer(*args):
    try:
        r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True, timeout=600)
        return r.returncode, r.stdout
    except Exception as e:
        return 1, str(e)


def main():
    ecarts = []

    _, sortie = lancer(OUTILS / "audit-skills.py", "--perso")
    m = re.search(r": (\d+) avec au moins un ecart", sortie)
    if m and int(m.group(1)):
        ecarts.append(f"**Format** : {m.group(1)} skills hors guide.\n"
                      + "\n".join(l for l in sortie.splitlines() if l.startswith("[")))

    casses = []
    for d in ("~/.claude/skills", "~/.hermes/skills", "~/.agents/skills"):
        r = subprocess.run(["find", str(Path(d).expanduser()), "-maxdepth", "3", "-xtype", "l"],
                           capture_output=True, text=True)
        casses += r.stdout.split()
    if casses:
        ecarts.append(f"**Liens casses** : {len(casses)}\n" + "\n".join(f"- `{c}`" for c in casses[:10]))

    _, sortie = lancer(OUTILS / "usage-skills.py", "30")
    m = re.search(r"(\d+) noms presents chez Claude ET Hermes : (.*)", sortie)
    restants = [n.strip() for n in m.group(2).split(",") if n.strip()] if m else []
    restants = [n for n in restants if n not in HOMONYMES_VOULUS]
    if restants:
        ecarts.append(f"**Doublons de nom** : {', '.join(restants)}")

    code, sortie = lancer(OUTILS / "usage-skills.py", "7", "--rates")
    if code == 0:
        lignes = []
        for l in sortie.splitlines():
            m = re.match(r"\s*(\d+) · (\d+) · (\d+) % · (\S+)$", l)
            if m and int(m.group(1)) >= 3 and int(m.group(3)) > 50:
                lignes.append(f"- `{m.group(4)}` : {m.group(3)} % rate "
                              f"({m.group(2)} chargee sur {m.group(1)} declenchees)")
        if lignes:
            ecarts.append("**Declenchement rate** (plus de 50 %) :\n" + "\n".join(lignes))

    code, sortie = lancer(OUTILS / "issue-skills.py", "7")
    if code == 0:
        lignes = []
        for l in sortie.splitlines():
            m = re.match(r"\s*\d+ ·\s+\d+ ·\s+(\d+) ·\s+\d+ \(\s*(\d+) %\).*· (\S+)$", l)
            if m and int(m.group(1)) >= 3 and int(m.group(2)) > 25:
                lignes.append(f"- `{m.group(3)}` : corrigee dans {m.group(2)} % des sessions")
        if lignes:
            ecarts.append("**Skills souvent corrigees** :\n" + "\n".join(lignes))

    if not ecarts:
        print("Aucun ecart.")
        return
    texte = "\n\n".join(ecarts)
    print(texte)
    if "--sec" not in sys.argv:
        subprocess.run(["qg-attente", "add", f"Controle des skills : {len(ecarts)} point(s)",
                        "--resume", texte, "--source", "controle-skills"], check=False)


if __name__ == "__main__":
    main()
