#!/usr/bin/env python3
"""Les reglages du QG, en un seul endroit.

Ils etaient eparpilles : la voix dans deux scripts bash, le modele dans deux
fonctions Python, le salon Telegram en dur, les delais en constantes de module.
Changer la voix demandait de savoir ou chercher, et une valeur oubliee quelque
part suffisait a rendre le comportement incoherent.

Les valeurs par defaut vivent ICI, dans le code : le QG marche sans aucun
fichier de configuration. Qui veut en changer une ecrit un JSON partiel dans
~/.hermes/qg-config.json ; seules les cles presentes sont surchargees. C'est ce
qui rendra ce projet publiable sans que personne ait a editer du code pour
l'essayer.

    qg-config.py                 tous les reglages, avec leur origine
    qg-config.py get voix        une valeur, brute, pour un script
    qg-config.py env             de quoi faire `eval` en bash
    qg-config.py chemin          ou ecrire pour surcharger
"""
import io
import json
import os
import sys
# Charge par spec_from_file_location depuis qg-pouls : son dossier n'est pas
# toujours dans sys.path (casse du 2026-10-04 10:41, pouls muet 2 h 30).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qg_adresse import adresse

FICHIER = os.path.expanduser("~/.hermes/qg-config.json")

DEFAUTS = {
    # Le modele qui resume les rapports. JAMAIS haiku : USER l'a tranche le
    # 2026-08-29, ses resumes ratent le fond du rapport. Sonnet est en prime
    # deux fois plus rapide ici (4,6 s contre 12).
    "modele": "sonnet",
    # Une voix francaise NON multilingue. Les voix « Multilingual » changent de
    # langue selon ce qu'elles croient lire : un rapport plein de mots anglais
    # partait en espagnol.
    "voix": "fr-FR-HenriNeural",
    "debit": "+8%",
    # Debit de la bulle vocale envoyee dans le QG. Toujours naturel : USER
    # accelere deja lui-meme dans Telegram, un audio pre-accelere l'etait deux
    # fois (2026-09-25). « debit » ne regle que la lecture sur le telephone.
    "debit_telegram": "+0%",
    # Debit des boutons « Lire l'ecran » et « Lire le presse-papier » de la
    # pastille : USER les veut en accelere, independamment du debit du QG.
    # Au-dela de tant de caracteres, le rapport est resume avant d'etre livre.
    # En dessous, il part tel quel : resumer trois lignes ne gagne rien.
    "resume_seuil": 150,
    "resume_phrases": 3,
    # Le salon ou atterrissent les rapports.
    "telegram_chat": adresse()[0],
    "telegram_thread": adresse()[1],
    # Le garde attend que la file soit stable avant de lire, puis attend que la
    # voix prefabriquee soit prete, sans depasser cette limite.
    "regroupe_s": 8,
    "attente_voix_s": 45,
    # Combien de rapports on prepare d'avance. C'est le prix a payer pour un
    # appui instantane : au-dela, on fabrique des voix jamais ecoutees.
    "prefabrique_max": 5,
    "differe_max_min": 120,
    # Silence toleré avant que le veilleur ne signale un agent peut-etre mort.
    # Un tour qui reflechit longuement reste muet plusieurs minutes : en dessous
    # de 15, le veilleur crierait au loup sur des agents en pleine sante.
    "pouls_silence_min": 15,
}


def charge():
    """Les defauts, ecrases par le fichier de l'utilisateur s'il existe."""
    v = dict(DEFAUTS)
    try:
        with io.open(FICHIER, encoding="utf-8") as f:
            perso = json.load(f)
        if isinstance(perso, dict):
            for k in perso:
                # Une cle inconnue est ignoree en silence plutot que de faire
                # planter le garde : une faute de frappe ne doit pas couper
                # la lecture des rapports.
                if k in DEFAUTS:
                    v[k] = perso[k]
    except (OSError, ValueError):
        pass
    return v


def reglage(cle):
    return charge().get(cle, DEFAUTS.get(cle))


def main():
    a = sys.argv[1:]
    if a and a[0] == "get":
        v = reglage(a[1])
        print("" if v is None else v)
        return 0
    if a and a[0] == "env":
        # Un seul appel Python plutot qu'un par reglage : `eval` en bash.
        for k, v in sorted(charge().items()):
            print("QGC_{}='{}'".format(k.upper(), str(v).replace("'", "'\\''")))
        return 0
    if a and a[0] == "chemin":
        print(FICHIER)
        return 0
    perso = os.path.exists(FICHIER)
    v = charge()
    for k in sorted(DEFAUTS):
        marque = " (perso)" if perso and v[k] != DEFAUTS[k] else ""
        print("{:18} {}{}".format(k, v[k], marque))
    print()
    print("Pour changer : {}".format(FICHIER))
    return 0


if __name__ == "__main__":
    sys.exit(main())
