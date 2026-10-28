#!/usr/bin/env python3
"""Teste si une skill se charge sur un jeu de requetes, en conditions reelles.

Usage :
    tester-declenchement.py <dossier-skill> [--fois 1] [--tours 1] [--modele claude-sonnet-4-6]

--tours N : laisse N etapes au modele et regarde tous ses appels d'outil, pas le 1er.
Pour une skill qui se charge en 2e (ex. entreprise-a-analyse-distributeurs apres entreprise-a-index).

Lit <dossier-skill>/evals/declenchement.json : [{"query": ..., "should_trigger": bool}].
Chaque requete part en `claude -p --max-turns 1` depuis un dossier vide : la memoire
de session (claude-mem) n'y injecte aucun contexte. On lit le 1er appel d'outil.

Pourquoi pas run_eval du skill-creator (2026-10-24) : sur hote-1 il rend 0 declenchement
sur tout, alors que le modele charge bien la skill (vu dans le flux stream-json).
Et lance depuis ~, claude-mem injecte le travail du jour : 2 faux positifs sur 3.
"""
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def premier_outil(requete, modele, neutre, tours=1):
    try:
        sortie = subprocess.run(
            ["claude", "-p", requete, "--output-format", "stream-json", "--verbose",
             "--model", modele, "--max-turns", str(tours)],
            cwd=neutre, capture_output=True, text=True, timeout=180).stdout
    except subprocess.TimeoutExpired:
        return "delai"
    vus = []
    for ligne in sortie.splitlines():
        try:
            e = json.loads(ligne)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            for c in e["message"].get("content", []):
                if c.get("type") == "tool_use":
                    cible = c["input"].get("skill") or c["input"].get("file_path", "")
                    vus.append(f"{c['name']}:{cible}")
                    if tours == 1:
                        return vus[0]
    return " > ".join(vus) or "aucun"


def main(args):
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    dossier = Path(args[0]).expanduser().resolve()
    fois = int(args[args.index("--fois") + 1]) if "--fois" in args else 1
    tours = int(args[args.index("--tours") + 1]) if "--tours" in args else 1
    modele = args[args.index("--modele") + 1] if "--modele" in args else "claude-sonnet-4-6"
    nom = dossier.name
    jeu = json.loads((dossier / "evals/declenchement.json").read_text(encoding="utf-8"))
    taches = [(q, k) for q in jeu for k in range(fois)]
    with tempfile.TemporaryDirectory() as neutre, ThreadPoolExecutor(8) as pool:
        res = list(pool.map(lambda t: premier_outil(t[0]["query"], modele, neutre, tours), taches))
    bons = 0
    for i, q in enumerate(jeu):
        vus = res[i * fois:(i + 1) * fois]
        charge = sum(nom in v for v in vus)
        ok = (charge * 2 >= fois) == q["should_trigger"]
        bons += ok
        attendu = "doit" if q["should_trigger"] else "ne doit pas"
        print(f"{'OK' if ok else 'KO'} {charge}/{fois} ({attendu}) {q['query'][:60]}  [{vus[0][:90]}]")
    print(f"== {nom} : {bons}/{len(jeu)} justes")
    return 0 if bons == len(jeu) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
