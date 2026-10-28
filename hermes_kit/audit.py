"""Audit du depot : aucune identite privee, aucun secret.

Deux couches :
- gitleaks (secrets : cles, jetons, mots de passe) ;
- une liste de motifs d'identite tenue HORS du depot (HK_IDENTITES),
  ou passee en regex unique par HK_IDENTITES_REGEX (secret CI).

Sortie : chemin et numero de ligne seulement. Jamais le texte trouve :
les journaux d'un depot public sont publics.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

DEFAUT = Path.home() / "Bureau/Projets/contexte/infra/identites-privees.txt"
IGNORES = (".git/", "node_modules/", "__pycache__/", ".venv/")
BINAIRES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".apk",
    ".idsig",
    ".keystore",
    ".jar",
    ".zip",
    ".gz",
    ".whl",
    ".pyc",
    ".db",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp3",
    ".ogg",
    ".mp4",
)


def motifs():
    brut = os.environ.get("HK_IDENTITES_REGEX")
    if brut:
        return [re.compile(brut, re.I)]
    chemin = Path(os.environ.get("HK_IDENTITES", DEFAUT))
    if not chemin.exists():
        print(f"audit : liste d'identites introuvable : {chemin}")
        sys.exit(2)
    lignes = [ligne.strip() for ligne in chemin.read_text().splitlines()]
    return [re.compile(ligne, re.I) for ligne in lignes if ligne and not ligne.startswith("#")]


def fichiers(args):
    if args:
        return [Path(a) for a in args if Path(a).is_file()]
    sortie = subprocess.run(  # noqa: S603  git du PATH, arguments fixes
        [  # noqa: S607
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        capture_output=True,
    )
    return [Path(p) for p in sortie.stdout.decode().split("\0") if p]


def main():
    regs = motifs()
    fautes = 0
    for f in fichiers(sys.argv[1:]):
        chemin = f.as_posix()
        if chemin.startswith(IGNORES) or chemin.endswith(BINAIRES):
            continue
        try:
            texte = f.read_text(errors="replace")
        except OSError:
            continue
        for no, ligne in enumerate(texte.splitlines(), 1):
            for r in regs:
                if r.search(ligne):
                    print(f"identite : {chemin}:{no}")
                    fautes += 1
                    break
    if fautes:
        print(f"audit : {fautes} ligne(s) a corriger")
        sys.exit(1)
    print("audit identites : rien a signaler")


if __name__ == "__main__":
    main()
