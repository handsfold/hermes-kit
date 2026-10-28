#!/usr/bin/env python3
"""Refuse la creation d'un projet a la racine de ~/Bureau/Projets ou directement sous un univers.

Ne le 2026-10-24, au rangement des projets par famille, puis par univers le meme jour.
Avant, 56 dossiers vivaient a la racine et aucun agent ne savait ou chercher.
Desormais un projet neuf vit dans `~/Bureau/Projets/<univers>/<famille>/<nom>`
(univers business et perso), et `Projets/INDEX.md` dit ou vit quoi.

Regle : une commande Bash qui cree (mkdir, git clone, cp, mv, rsync, touch, ln,
tee, redirection, init d'outil) un nom NEUF directement sous Projets/ ou sous
Projets/<univers>/, ou un Write/Edit dont le chemin passe par un tel nom, est
refusee. Les noms deja presents (univers, familles, contexte, INDEX.md, liens de
transition) passent. Sous archives/ et dans une famille, tout passe.

Laissez-passer : `NOUVELLE_FAMILLE=1` dans la commande, pour creer une famille
voulue par USER. L'ajouter ensuite a UNIVERS dans `contexte/bin/index-projets.py`.

Hermes et Prime n'ont pas ce hook : `index-projets.py --verifier` sert de filet.
"""
import json
import os
import re
import shlex
import sys

RACINE = os.path.expanduser("~/Bureau/Projets")
UNIVERS = ("business", "perso")
HOME = os.path.expanduser("~")

# Un chemin absolu ou relatif au HOME qui pointe sous Projets/<X>.
CHEMIN = re.compile(r"""(?:~|\$HOME|\$\{HOME\}|""" + re.escape(HOME) + r""")/Bureau/Projets/([^/\s"'`;|&()<>]+)(?:/([^/\s"'`;|&()<>]+))?""")
CREATION = re.compile(
    r"""(^|\s|/)(mkdir|git\s+clone|cp|mv|rsync|touch|tee|ln|install|unzip|tar|uv\s+init|npm\s+init|
        npx\s+create-\S+|pnpm\s+create|cargo\s+new|django-admin\s+startproject|scaffold\.sh)(\s|$)""",  # « > » retire le 2026-10-28 : 31 faux refus sur 31
    re.X)
SEGMENTS = re.compile(r"&&|\|\||;|\n|\|")

MOTIF = """Refus : cette commande cree `Projets/{nom}`, hors de toute famille.

Depuis le 2026-10-24, chaque projet vit dans un univers, puis une famille :
  ~/Bureau/Projets/<univers>/<famille>/<nom>
{familles}.
Carte de ce qui existe : ~/Bureau/Projets/INDEX.md (fiche contexte/methodes/socle-projet.md).

Choisis la famille, refais la commande avec le chemin long, puis lance
  python3 ~/Bureau/Projets/contexte/bin/index-projets.py
Creer une famille neuve, sur demande de USER seulement : prefixer NOUVELLE_FAMILLE=1."""


def existe(nom: str) -> bool:
    return os.path.lexists(os.path.join(RACINE, nom))


def neuf(parts):
    """Nom neuf mal place (1er niveau, ou 2e niveau sous un univers), sinon None."""
    parts = [x for x in parts if x and x != "."]
    # Un motif (*, ?, [) ne cree rien : c'est une lecture (2026-10-28).
    if any(c in "".join(parts) for c in "*?["):
        return None
    if not parts:
        return None
    if not existe(parts[0]):
        return parts[0]
    if parts[0] in UNIVERS and len(parts) >= 2 and not existe(parts[0] + "/" + parts[1]):
        return parts[0] + "/" + parts[1]
    return None


def familles() -> str:
    out = []
    for u in UNIVERS:
        try:
            fams = sorted(e.name for e in os.scandir(os.path.join(RACINE, u))
                          if e.is_dir(follow_symlinks=False) and not e.name.startswith("."))
        except OSError:
            fams = ["?"]
        out.append(f"{u}/ : {', '.join(fams)}")
    return "Familles :\n  " + "\n  ".join(out) + "\nArchives : archives/<nom>"


def base_de(cwd: str):
    """Prefixe relatif si cwd est la racine ou un univers, sinon None."""
    rp, rr = os.path.realpath(cwd or ""), os.path.realpath(RACINE)
    if rp == rr:
        return []
    if os.path.dirname(rp) == rr and os.path.basename(rp) in UNIVERS:
        return [os.path.basename(rp)]
    return None


def nom_depuis_git_clone(segment: str):
    """Nom cree par `git clone <url> [dossier]` lance depuis la racine."""
    try:
        mots = shlex.split(segment)
    except ValueError:
        return None
    if "clone" not in mots:
        return None
    args = [m for m in mots[mots.index("clone") + 1:] if not m.startswith("-")]
    if not args:
        return None
    if len(args) >= 2:
        return args[1].rstrip("/").split("/")[:2]
    return [re.sub(r"\.git$", "", args[0].rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1])]


def nom_relatif(segment: str, base):
    """Nom cree par mkdir/touch/cp/mv a chemin relatif, lance depuis la racine ou un univers."""
    try:
        mots = shlex.split(segment)
    except ValueError:
        return None
    if not mots:
        return None
    verbe = os.path.basename(mots[0])
    args = [m for m in mots[1:] if not m.startswith("-")]
    if verbe in ("mkdir", "touch") and args:
        cibles = args
    elif verbe in ("cp", "mv", "rsync", "ln") and len(args) >= 2:
        cibles = [args[-1]]
    else:
        return None
    for c in cibles:
        if c.startswith(("/", "~", "$", ".")):
            continue
        nom = neuf(base + c.split("/")[:2])
        if nom:
            return nom
    return None


def verifier_bash(cmd: str, cwd: str):
    if "NOUVELLE_FAMILLE=1" in cmd:
        return None
    base = base_de(cwd)
    for seg in SEGMENTS.split(cmd):
        seg = seg.strip()
        if seg.startswith("cd "):
            base = base_de(os.path.expanduser(seg[3:].strip().strip("\"'").replace("$HOME", HOME)))
            continue
        if not seg:
            continue
        if not CREATION.search(seg):
            # « > » ne cree que sa CIBLE, pas les chemins lus avant lui
            # (2026-10-28 : 31 faux refus sur `ls Projets/* > ailleurs`).
            for cible in re.findall(r">>?\s*(\S+)", seg):
                for p1, p2 in CHEMIN.findall(cible):
                    nom = neuf([p1, p2])
                    if nom:
                        return nom
            continue
        for p1, p2 in CHEMIN.findall(seg):
            nom = neuf([p1, p2])
            if nom:
                return nom
        if base is not None:
            if re.search(r"\bgit\s+clone\b", seg):
                parts = nom_depuis_git_clone(seg)
                nom = neuf(base + parts) if parts else None
            else:
                nom = nom_relatif(seg, base)
            if nom:
                return nom
    return None


def verifier_chemin(chemin: str):
    chemin = os.path.abspath(os.path.expanduser(chemin or ""))
    if not chemin.startswith(RACINE + os.sep):
        return None
    parts = chemin[len(RACINE) + 1:].split(os.sep)
    # Un fichier pose directement sous un univers (business/notes.md) est aussi mal range.
    return neuf(parts)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    entree = data.get("tool_input") or {}
    outil = data.get("tool_name") or ("Bash" if "command" in entree else "")
    if outil == "Bash":
        nom = verifier_bash(entree.get("command") or "", data.get("cwd") or os.getcwd())
    else:
        nom = verifier_chemin(entree.get("file_path") or entree.get("notebook_path") or "")
    if not nom:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": MOTIF.format(nom=nom, familles=familles()),
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
