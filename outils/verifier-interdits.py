#!/usr/bin/env python3
"""Aucun fichier ni dossier qui ne devrait pas etre publie.

Complete l'audit des identites (hermes_kit/audit.py) et gitleaks, qui lisent le
CONTENU : ici on regarde le NOM, la TAILLE et la NATURE (lien symbolique).
Usage : verifier-interdits.py            (tout l'arbre suivi et non ignore)
        verifier-interdits.py f1 f2 ...  (ces fichiers seulement)
Sortie 1 si un interdit est trouve. N'affiche que des chemins, jamais de contenu.
"""

import fnmatch
import os
import shutil
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAILLE_MAX = 3 * 1024 * 1024  # 3 Mo : au-dela, ce n'est plus de la config

# Noms de fichiers interdits (motifs fnmatch sur le nom seul).
NOMS = [
    ".env",
    ".env.*",
    "auth.json",
    "*.db",
    "*.db-*",
    "*.sqlite*",
    "*.log",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "*.kdbx",
    ".infisical.json",
    "credentials*.json",
    "token*.json",
    "*.token",
    "*.bak*",
    "*.orig",
    "*.rej",
    ".netrc",
    "*.keystore",
    "*.jks",
    "settings.local.json",
    "*.sql",
    "*.dump",
    "*.zip",
    "*.tar*",
    "*.7z",
]
# Exceptions voulues (modeles sans valeur).
EXCEPTIONS = {".env.example", ".env.exemple", "env.exemple"}
# Dossiers dont rien ne doit etre publie (composante de chemin).
DOSSIERS = {
    "sessions",
    "memories",
    "memory",
    "logs",
    "state",
    "cache",
    ".venv",
    "node_modules",
    "__pycache__",
    ".git",
    "artifacts",
    "backups",
    ".curator_backups",
    "auth",
    "secrets",
    ".ssh",
    ".gnupg",
    ".aws",
}


def fichiers(args):
    if args:
        return args
    sortie = (
        subprocess.run(  # noqa: S603
            [
                shutil.which("git") or "git",
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            cwd=RACINE,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    return [f for f in sortie if f]


def main():
    bad = []
    for f in fichiers(sys.argv[1:]):
        chemin = os.path.join(RACINE, f)
        parts = f.split("/")
        nom = parts[-1]
        if not os.path.lexists(chemin):
            continue  # supprime dans l'arbre de travail
        if os.path.islink(chemin):
            cible = os.path.realpath(chemin)
            if not cible.startswith(RACINE + os.sep):
                bad.append((f, "lien symbolique vers l'exterieur du depot"))
                continue
        if nom not in EXCEPTIONS:
            for motif in NOMS:
                if fnmatch.fnmatch(nom, motif):
                    bad.append((f, f"nom interdit ({motif})"))
                    break
        for d in parts[:-1]:
            if d in DOSSIERS:
                bad.append((f, f"dossier interdit ({d}/)"))
                break
        fichier_reel = os.path.isfile(chemin) and not os.path.islink(chemin)
        if fichier_reel and os.path.getsize(chemin) > TAILLE_MAX:
            bad.append((f, "plus de 3 Mo"))
    for f, why in bad:
        print(f"interdit : {f} : {why}")
    if bad:
        print(f"verifier-interdits : {len(bad)} fichier(s) a ne pas publier")
        return 1
    print("interdits : rien a signaler")
    return 0


if __name__ == "__main__":
    sys.exit(main())
