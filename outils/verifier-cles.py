"""Aucune cle renseignee dans un fichier de configuration du depot.

Parcourt les .yaml / .yml / .json suivis sous hermes/, claude/, pixelgarde/, install/.
Toute valeur d'une cle sensible doit etre vide, "local" ou un trou __X__.
Usage : python3 outils/verifier-cles.py [fichiers...]   (sans argument : tout le depot)
"""

import json
import re
import subprocess
import sys
from pathlib import Path

SENSIBLES = re.compile(
    r"(api_key|record_key|token|secret|password|bot_token|webhook_secret)$", re.I
)
TOLEREES = {"", "local", "~", "none", "null"}
TROU = re.compile(r"^__[A-Z_]+__$")
RACINES = ("hermes/", "claude/", "pixelgarde/", "install/")


def valeur_ok(v):
    if v is None or isinstance(v, (bool, int, float)):
        return True
    s = str(v).strip()
    return s.lower() in TOLEREES or TROU.match(s) is not None


def parcourir(obj, chemin, fautes):
    if isinstance(obj, dict):
        for k, v in obj.items():
            sensible = (
                isinstance(k, str) and SENSIBLES.search(k) and not isinstance(v, (dict, list))
            )
            if sensible and not valeur_ok(v):
                fautes.append(f"{chemin}: {k} = {str(v)[:6]}...")
            parcourir(v, chemin, fautes)
    elif isinstance(obj, list):
        for x in obj:
            parcourir(x, chemin, fautes)


def charger(p):
    texte = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix == ".json":
        return json.loads(texte)
    try:
        import yaml  # noqa
    except ImportError:
        # Sans pyyaml : lecture ligne a ligne, suffisante pour "cle: valeur"
        d = {}
        for ligne in texte.splitlines():
            m = re.match(r"^\s*([A-Za-z_]+)\s*:\s*(.*?)\s*(#.*)?$", ligne)
            if m:
                d[m.group(1)] = m.group(2).strip("\"'")
        return d
    return yaml.safe_load(texte)


def fichiers_cibles(args):
    if args:
        return [Path(a) for a in args]
    out = subprocess.run(  # noqa: S603  git du PATH, arguments fixes
        [  # noqa: S607
            "git",
            "ls-files",
            "-z",
            "--others",
            "--cached",
            "--exclude-standard",
            *[r.rstrip("/") for r in RACINES],
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return [Path(x) for x in out.split("\0") if x]


def main():
    fautes = []
    for p in fichiers_cibles(sys.argv[1:]):
        if p.suffix not in (".json", ".yaml", ".yml") or not p.exists():
            continue
        if not str(p).startswith(RACINES):
            continue
        try:
            parcourir(charger(p), str(p), fautes)
        except Exception as e:  # fichier illisible : verifier-formats.sh s'en charge
            print(f"non lu : {p} ({e.__class__.__name__})")
    if fautes:
        print("cles renseignees :")
        for f in fautes:
            print("  " + f)
        sys.exit(1)
    print("cles : aucune renseignee")


if __name__ == "__main__":
    main()
