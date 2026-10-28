#!/usr/bin/env python3
"""Refuse de creer un projet neuf dans une famille sans passer par le socle.

Ne le 2026-10-28 : USER demande « fais une landing page » pour realvoxai.com.
Le dossier business/sites/realvoxai nait a la main (mkdir, Write), sans
scripts/check.sh, sans tests, sans garde-fous, et la zone Cloudflare garde les
reglages par defaut corriges ailleurs depuis aout. Le socle est pose apres
coup. USER : « vu qu'il etait pas dans ma liste de projets, tu aurais du en
deduire » que c'etait un projet neuf. La skill nouveau-projet ne se declenchait
que sur le mot « projet » : une consigne se rate, ce hook ne se rate pas.

Regle : un nom NEUF sous Projets/<univers>/<famille>/ (univers business ou
perso, famille deja existante) ne nait que par scaffold.sh. Toute autre
creation (mkdir, cp, git clone, Write d'un fichier dedans...) est refusee
avec la commande a lancer.

Laissez-passer : `SANS_SOCLE=1` dans la commande, sur demande de USER seulement.
Les niveaux au-dessus (univers, famille) sont l'affaire de projet-sans-famille.py.
Test : ~/.claude/hooks/tests/projet-socle.sh
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
RACINE = os.path.join(HOME, "Bureau/Projets")
UNIVERS = ("business", "perso")
SOCLE = re.compile(r"scaffold\.sh|porter-socle\.sh|SANS_SOCLE=1")
CHEMIN = re.compile(
    r"(?:~|\$HOME|\$\{HOME\}|" + re.escape(HOME) + r")/Bureau/Projets/"
    r"([^/\s\"'`;|&()<>]+)/([^/\s\"'`;|&()<>]+)/([^/\s\"'`;|&()<>]+)")
CREATION = re.compile(
    r"(^|\s|/)(mkdir|git\s+clone|cp|mv|rsync|touch|tee|ln|install|unzip|tar|"
    r"uv\s+init|npm\s+init|npx\s+create-\S+|pnpm\s+create|cargo\s+new)(\s|$)")
SEGMENTS = re.compile(r"&&|\|\||;|\n|\|")


def neuf(u: str, f: str, nom: str):
    """Le chemin relatif du projet si <nom> est neuf dans une famille existante."""
    if u not in UNIVERS or nom.startswith(("$", "*", ".")) or nom.endswith((".md", ".txt")):
        return None
    if not os.path.isdir(os.path.join(RACINE, u, f)):
        return None  # famille absente : projet-sans-famille.py s'en charge
    if os.path.exists(os.path.join(RACINE, u, f, nom)):
        return None
    return f"{u}/{f}/{nom}"


def verifier_bash(cmd: str, cwd: str):
    if SOCLE.search(cmd):
        return None
    base = cwd
    for seg in SEGMENTS.split(cmd):
        seg = seg.strip()
        if seg.startswith("cd "):
            base = os.path.expanduser(seg[3:].strip().strip("\"'").replace("$HOME", HOME))
            continue
        if not seg:
            continue
        cibles = [seg] if CREATION.search(seg) else re.findall(r">>?\s*(\S+)", seg)
        for c in cibles:
            for u, f, nom in CHEMIN.findall(c):
                p = neuf(u, f, nom)
                if p:
                    return p
        # mkdir relatif depuis une famille : `cd .../business/sites && mkdir foo`
        rel = os.path.relpath(os.path.realpath(base or "/"), os.path.realpath(RACINE))
        parts = rel.split(os.sep)
        m = re.match(r"mkdir\s+(?:-p\s+)?([^\s/;&|]+)", seg)
        if m and len(parts) == 2 and not rel.startswith(".."):
            p = neuf(parts[0], parts[1], m.group(1).strip("\"'"))
            if p:
                return p
    return None


def verifier_chemin(chemin: str):
    m = CHEMIN.search(chemin or "")
    return neuf(*m.groups()) if m else None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    entree = data.get("tool_input") or {}
    outil = data.get("tool_name") or ("Bash" if "command" in entree else "")
    if outil == "Bash":
        p = verifier_bash(entree.get("command") or "", data.get("cwd") or "")
    else:
        p = verifier_chemin(entree.get("file_path") or entree.get("notebook_path") or "")
    if not p:
        return 0
    u, f, nom = p.split("/")
    motif = f"""Refus : `Projets/{p}` n'existe pas encore, c'est un projet NEUF.

Un projet neuf nait par le socle (skill nouveau-projet), meme si USER n'a pas dit
« projet » : « fais une landing », « fais un site », « j'ai pris le domaine »
creent un projet des qu'il est absent de ~/Bureau/Projets/INDEX.md.

  bash ~/.claude/skills/nouveau-projet/scaffold.sh ~/Bureau/Projets/{p} <python-api|python-cli|js-web|mixte>

Site sur Cloudflare : lire ensuite la section « Site Cloudflare » de la skill
nouveau-projet (zone, deploiement, SEO). Ne le 2026-10-28 (realvoxai cree sans
socle). Laissez-passer, sur demande de USER seulement : SANS_SOCLE=1."""
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": motif}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
