#!$HOME/.hermes/hermes-agent/venv/bin/python
"""Reglages proteges d'Hermes : reappliquer apres une migration de config, et lister le reste.

  hermes-reglages.py appliquer CONFIG PROTEGES [--avant COPIE] [--a-blanc]
      Remet dans CONFIG chaque valeur de PROTEGES (cle pointee -> valeur), sans
      toucher aux autres cles (une cle secrete de la config n'est jamais lue ici
      que pour etre comparee). Ecrit en place, commentaires conserves (ruamel).
      Avec --avant COPIE (config d'avant la migration), liste ensuite ce que la
      migration a change d'AUTRE que les reglages proteges.

  hermes-reglages.py diff AVANT APRES [--proteges PROTEGES]
      Seulement la liste des changements, sans rien ecrire.

Les valeurs des cles dont le nom contient key, token, secret ou password ne sont
jamais affichees (ni dans la liste des changements) : on dit seulement qu'elles
ont change.
"""
import argparse
import os
import re
import sys
import tempfile

from ruamel.yaml import YAML

SECRET = re.compile(r"key|token|secret|password", re.I)
MAX_LIGNES = 40


def yaml_rt():
    y = YAML()  # aller-retour : conserve commentaires et ordre
    y.preserve_quotes = True
    y.width = 4096
    return y


def charger(chemin):
    with open(chemin, encoding="utf-8") as f:
        return yaml_rt().load(f) or {}


def lire(d, chemin):
    for k in chemin.split("."):
        if not hasattr(d, "get") or k not in d:
            return KeyError
        d = d[k]
    return d


def poser(d, chemin, valeur):
    """Pose `valeur` a `chemin` ; pour un bloc, fusionne cle par cle (les cles
    absentes du fichier protege, secrets compris, restent telles quelles)."""
    morceaux = chemin.split(".")
    for k in morceaux[:-1]:
        if k not in d or not hasattr(d[k], "get"):
            d[k] = {}
        d = d[k]
    dernier = morceaux[-1]
    if hasattr(valeur, "items") and dernier in d and hasattr(d[dernier], "items"):
        for k, v in valeur.items():
            poser(d[dernier], k, v)
    else:
        d[dernier] = valeur


def aplatir(d, prefixe=""):
    """Dictionnaire imbrique -> {chemin.pointe: feuille}. Les listes sont des feuilles."""
    sortie = {}
    if hasattr(d, "items"):
        for k, v in d.items():
            chemin = f"{prefixe}.{k}" if prefixe else str(k)
            if hasattr(v, "items") and v:
                sortie.update(aplatir(v, chemin))
            else:
                sortie[chemin] = v
    return sortie


def feuille(v):
    texte = repr(v) if not hasattr(v, "items") else "{}"
    return texte if len(texte) <= 70 else texte[:67] + "..."


def changements(avant, apres, exclus):
    """Lignes lisibles des differences entre deux configs, hors chemins `exclus`
    (un chemin exclu couvre tous ses descendants)."""
    a, b = aplatir(avant), aplatir(apres)

    def exclu(c):
        return any(c == e or c.startswith(e + ".") for e in exclus)

    lignes = []
    for c in sorted(set(a) | set(b)):
        if exclu(c):
            continue
        secret = bool(SECRET.search(c.split(".")[-1]))
        if c not in a:
            lignes.append(f"+ {c} = {'(secret)' if secret else feuille(b[c])}")
        elif c not in b:
            lignes.append(f"- {c} (retire)")
        elif a[c] != b[c]:
            lignes.append(f"~ {c} : {'(secret change)' if secret else feuille(a[c]) + ' -> ' + feuille(b[c])}")
    return lignes


def afficher(lignes):
    if not lignes:
        print("    aucun autre changement")
        return
    for l in lignes[:MAX_LIGNES]:
        print("    " + l)
    if len(lignes) > MAX_LIGNES:
        print(f"    ... et {len(lignes) - MAX_LIGNES} autre(s)")


def cmd_appliquer(args):
    cfg = charger(args.config)
    prot = charger(args.proteges)
    remis = []
    for chemin, voulu in prot.items():
        courant = lire(cfg, chemin)
        # On teste la conformite sur le sous-ensemble attendu, pas sur le bloc entier.
        if courant is KeyError or sous_ensemble_different(courant, voulu):
            poser(cfg, chemin, voulu)
            remis.append(chemin)
    if remis and not args.a_blanc:
        dossier = os.path.dirname(os.path.abspath(args.config))
        fd, tmp = tempfile.mkstemp(dir=dossier, prefix=".config-reglages-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml_rt().dump(cfg, f)
            os.chmod(tmp, os.stat(args.config).st_mode & 0o777)
            os.replace(tmp, args.config)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    verbe = "a remettre" if args.a_blanc else "remis"
    print(f"    reglages proteges : {len(remis)} {verbe} sur {len(prot)}")
    for c in remis:
        print(f"    reapplique : {c}")
    if args.avant:
        print("    autres changements de la migration :")
        afficher(changements(charger(args.avant), cfg, list(prot)))
    return 0


def sous_ensemble_different(reel, voulu):
    if hasattr(voulu, "items"):
        if not hasattr(reel, "items"):
            return True
        return any(k not in reel or sous_ensemble_different(reel[k], v) for k, v in voulu.items())
    return reel != voulu


def cmd_diff(args):
    exclus = list(charger(args.proteges)) if args.proteges else []
    afficher(changements(charger(args.avant), charger(args.apres), exclus))
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("appliquer")
    a.add_argument("config")
    a.add_argument("proteges")
    a.add_argument("--avant")
    a.add_argument("--a-blanc", action="store_true")
    a.set_defaults(fn=cmd_appliquer)
    d = sp.add_parser("diff")
    d.add_argument("avant")
    d.add_argument("apres")
    d.add_argument("--proteges")
    d.set_defaults(fn=cmd_diff)
    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
