#!/usr/bin/env python3
"""Hook PreToolUse/Bash : limite l'affichage des commandes tests/build a 100
lignes, sans les executer lui-meme.

Principe : le hook NE RUN jamais la commande. Il reconnait une commande
tests/build simple et repond en JSON avec `updatedInput` qui enveloppe la
commande ENTIERE dans bounded-build-run.py (bash + pipefail + journal brut
mode 600 sous scratch + affichage tronque a 100 lignes).

Reconnaissance volontairement etroite (aucune decision floue, aucun LLM) :
  - un seul niveau de chaines : segments separes par && ou || ou ;, ou une
    commande simple ; chaque segment doit etre soit `cd ...` (prefixe), soit
    une commande tests/build reconnue ci-dessous ;
  - les pipes internes | sont tolerees (le runner ajoute pipefail, l'ordre
    des pipelines n'est jamais modifie) ;
  - heredoc (<<), retour a la ligne, lancement en fond (&) : pas de rewrite ;
  - commandes deja enveloppees (bounded-build-run.py dans la ligne) ou deja
    reecrites par RTK (prefixe `rtk `) : pas de rewrite, RTK reste maitre ;
  - toute autre commande (echo, git, reseau, scripts shell) : sortie 0 sans
    output, flux normal.

Format de sortie (spec PreToolUse) :
  rewrite : {"hookSpecificOutput": {"hookEventName": "PreToolUse",
             "permissionDecision": "allow", "updatedInput": {...entier...}}}
  sinon   : rien (exit 0), convention locale des hooks de ~/.claude/hooks.
"""
import json
import os
import re
import shlex
import sys

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "bounded-build-run.py")

# Separateurs de chaines. Les pipes | restent DANS un segment (le runner
# les execute entiers avec pipefail) : on ne coupe jamais un pipeline.
CHAINES = re.compile(r"&&|\|\||;")

# Premier mot reconnu comme tests/build (basename, sans chemin).
VERBES = {
    "pytest", "py.test", "tox", "nox", "make", "cmake", "ninja", "cargo",
    "jest", "vitest", "mocha", "tsc", "vite", "gradle", "mvn", "bazel",
}

# Verbes npm-like dont le premier argument doit etre test/run/build.
NPM_LIKE = {"npm", "pnpm", "yarn", "bun"}


def segment_reconnu(seg):
    """True si le segment est une commande tests/build reconnue, ou `cd`."""
    seg = seg.strip()
    if not seg or any(c in seg for c in "\n&`"):
        return False
    try:
        mots = shlex.split(seg)
    except ValueError:
        return False
    if not mots:
        return False
    # assignments d'env en tete (FOO=1 pytest ...)
    while "=" in mots[0] and not mots[0].startswith("="):
        mots = mots[1:]
        if not mots:
            return False
    verbe = os.path.basename(mots[0])
    if verbe == "rtk":
        rest = mots[1:]
        if rest and rest[0] in ("proxy", "test"):
            rest = rest[1:]
        return bool(rest) and segment_reconnu(shlex.join(rest))
    if verbe == "cd":
        return True
    if verbe in VERBES:
        return True
    if verbe in NPM_LIKE:
        return len(mots) >= 2 and mots[1] in ("test", "run", "build") and (
            mots[1] != "run" or len(mots) >= 3)
    if verbe == "npx":
        return len(mots) >= 2 and os.path.basename(mots[1]) in (
            "jest", "vitest", "mocha", "tsc", "playwright")
    if verbe == "go":
        return len(mots) >= 2 and mots[1] == "test"
    if verbe in ("python", "python3"):
        return len(mots) >= 3 and mots[1] == "-m" and mots[2] == "pytest"
    if verbe == "uv":
        return "pytest" in mots[1:3] or (len(mots) >= 3 and mots[1] == "run"
                                         and mots[2] == "pytest")
    return False


def reconnue(cmd):
    """True si TOUTE la commande est tests/build (chaque segment)."""
    if "<<" in cmd or "\n" in cmd.strip():
        return False
    segments = [s for s in CHAINES.split(cmd) if s.strip()]
    if not segments:
        return False
    return all(segment_reconnu(s) for s in segments)


def main():
    try:
        entree = json.load(sys.stdin)
    except Exception:
        return
    if entree.get("tool_name") != "Bash":
        return
    tool_input = entree.get("tool_input") or {}
    cmd = tool_input.get("command", "")
    if not cmd:
        return
    # Deja enveloppe par ce hook, ou deja reecrit par RTK : ne pas rejouer.
    if "bounded-build-run.py" in cmd:
        return
    if not reconnue(cmd):
        return
    cwd = entree.get("cwd") or os.getcwd()
    nouvelle = "python3 %s --cwd %s %s" % (
        RUNNER, shlex.quote(cwd), shlex.quote(cmd))
    nouveau_input = dict(tool_input)
    nouveau_input["command"] = nouvelle
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "updatedInput": nouveau_input}}))


if __name__ == "__main__":
    main()
