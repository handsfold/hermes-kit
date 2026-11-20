#!/usr/bin/env python3
"""Runner pour le hook bounded-build-output : execute une commande tests/build
en conservant TOUT (code de sortie, cwd, stdout, stderr) dans un journal brut
mode 600 sous scratch, puis n'affiche au plus que 100 lignes TOTALES
(debut/fin intelligents + lignes d'erreur + chemin du journal).

La commande tourne via /bin/bash avec `set -o pipefail` prefixed : les codes
de sortie des pipelines ne sont plus masques par le dernier maillon. La
commande elle-meme n'est jamais reecrite ni coupee : elle est passee entiere.

Usage : bounded-build-run.py [--cwd DIR] <commande...>
"""
import json
import os
import re
import subprocess
import sys
import time

MAX_AFFICHAGE = 100          # lignes TOTALES affichees, chemin du journal inclus
MAX_BLOC_ERREURS = 30        # plafond des lignes d'erreur mises en avant
MAX_FIN_STDERR = 10          # fin de stderr toujours montree si tres longue
MOTIFS_ERREUR = re.compile(
    r"error|fail|assert|exception|traceback|panic|fatal|"
    r"FAILED|ERROR|\bE\s+\d|✗|✘", re.IGNORECASE)

# Scratch de USER (jamais /tmp) : $HOME/.hermes/cache/scratch
SCRATCH = os.environ.get("CLAUDE_BOUNDED_DIR",
                         "$HOME/.hermes/cache/scratch/bounded-build")


def ecrire_journal(cwd, commande, code, sortie, erreurs):
    """Journal brut complet, mode 600, sous scratch. Retourne le chemin."""
    os.makedirs(SCRATCH, exist_ok=True)
    chemin = os.path.join(
        SCRATCH, "bounded-%s-%d.log" % (time.strftime("%Y%m%d-%H%M%S"),
                                        os.getpid()))
    fd = os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("date: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("cwd: %s\n" % cwd)
        f.write("code_sortie: %d\n" % code)
        f.write("commande: %s\n" % commande)
        f.write("=== STDOUT ===\n")
        f.write(sortie)
        if sortie and not sortie.endswith("\n"):
            f.write("\n")
        f.write("=== STDERR ===\n")
        f.write(erreurs)
        if erreurs and not erreurs.endswith("\n"):
            f.write("\n")
    os.chmod(chemin, 0o600)
    return chemin


def lignes(texte):
    return texte.splitlines() if texte else []


def affichage_limite(commande, code, sortie, erreurs, journal):
    """Au plus MAX_AFFICHAGE lignes TOTALES : erreurs d'abord, puis debut et
    fin de stdout, puis fin de stderr, puis une seule ligne de journal.
    Sortie <= 100 lignes : passee telle quelle (stdout/stderr separement)."""
    ls, le = lignes(sortie), lignes(erreurs)
    if len(ls) + len(le) <= MAX_AFFICHAGE:
        return sortie, erreurs  # petites sorties : strictement inchangees

    budget = MAX_AFFICHAGE - 1  # la derniere ligne = chemin du journal
    out = []
    # 1. lignes d'erreur (stderr seulement : un echo "error" dans stdout
    #    n'est pas forcement une erreur, stderr l'est par convention)
    errs = [l for l in le + ls if MOTIFS_ERREUR.search(l)][:MAX_BLOC_ERREURS]
    if errs:
        out.append("[Erreurs detectees (%d) :]" % len(errs))
        out.extend(errs)
    # 2. fin de stderr
    reste = budget - len(out)
    if le:
        fin_stderr = le[-min(MAX_FIN_STDERR, max(reste - 4, 0)):]
        if fin_stderr:
            out.append("[Fin de stderr :]")
            out.extend(fin_stderr)
    # 3. debut et fin de stdout avec le reste, moitie/moitie
    reste = budget - len(out)
    if ls and reste > 2:
        tete = reste // 2 - 1
        queue = reste - tete - 2
        tete = max(tete, 1)
        out.append("[Debut de stdout :]")
        out.extend(ls[:tete])
        if len(ls) > tete + queue:
            out.append("[... %d lignes omises ...]" % (len(ls) - tete - queue))
        out.extend(ls[-queue:] if queue > 0 else [])
    elif ls:
        out.append("[stdout : %d lignes, voir journal]" % len(ls))
    out.append("[code de sortie : %d] Journal complet : %s" % (code, journal))
    # Filet de securite : jamais plus de MAX_AFFICHAGE lignes.
    if len(out) > MAX_AFFICHAGE:
        garde = out[-1]
        out = out[:MAX_AFFICHAGE - 1] + [garde]
    return "\n".join(out) + "\n", ""


def main():
    args = sys.argv[1:]
    cwd = os.getcwd()
    if args and args[0] == "--cwd":
        cwd = args[1]
        args = args[2:]
    commande = " ".join(args)

    # pipefail en tete : la commande originale n'est pas modifiee, on ajoute
    # seulement un reglage du shell. Ordre des pipelines preserve.
    resultat = subprocess.run(
        ["bash", "-c", "set -o pipefail; " + commande],
        cwd=cwd if os.path.isdir(cwd) else None,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    journal = ecrire_journal(cwd, commande, resultat.returncode,
                             resultat.stdout or "", resultat.stderr or "")
    sortie, erreurs = affichage_limite(commande, resultat.returncode,
                                       resultat.stdout or "",
                                       resultat.stderr or "", journal)
    sys.stdout.write(sortie)
    if erreurs:
        sys.stderr.write(erreurs)
    sys.exit(resultat.returncode)


if __name__ == "__main__":
    main()
