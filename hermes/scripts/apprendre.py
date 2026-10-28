#!/usr/bin/env python3
"""Passage quotidien de la boucle d'apprentissage.

Capte les nouveaux retours de USER sur la forme des reponses, puis fait tourner
les deux agents. Se tait quand rien n'a change : un rapport quotidien qui dit
« rien » tous les jours devient un bruit qu'on cesse de lire.
"""
import json
import subprocess
import sys

BIN = "$HOME/.hermes/apprentissage/bin"


def lancer(script, *args):
    r = subprocess.run([sys.executable, f"{BIN}/{script}", *args],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"{script} : {r.stderr[-300:]}")
    return json.loads(r.stdout)


def main():
    jours = sys.argv[sys.argv.index("--jours") + 1] if "--jours" in sys.argv else "5"
    capte = lancer("capter.py", "--jours", jours)
    if not capte["nouveaux"]:
        return 0  # silence voulu
    res = lancer("boucle.py", "--lot", "12")
    if not res.get("adoptees"):
        return 0  # des signaux, mais rien qui merite une regle : silence aussi
    print(f'Apprentissage : {res["traites"]} retours analyses, '
          f'{len(res["adoptees"])} regles retenues.\n')
    for a in res["adoptees"]:
        print(f"- {a}")
    if res["rejets"]:
        print(f'\n{len(res["rejets"])} proposition(s) ecartee(s) par le contradicteur.')
    print(f'\nEn vigueur : {res["actives"]} regles actives, '
          f'{res["candidates"]} en attente de confirmation.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
