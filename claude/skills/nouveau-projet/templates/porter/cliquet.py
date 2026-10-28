#!/usr/bin/env python3
"""Cliquet de dette : la dette héritée est tolérée, elle ne peut plus grossir.

Pourquoi ce fichier existe
--------------------------
Poser un linter sur un projet qui n'en avait pas produit sept cents lignes
rouges le premier jour. Un filet qui crie sept cents fois est un filet qu'on
désactive, et à ce moment-là il ne protège plus rien du tout. Le grand nettoyage
préalable, lui, ne se fait jamais : il coûte des jours et ne livre rien.

Donc : on compte, on fige, et on n'échoue QUE si un compteur monte. La dette du
premier jour reste visible (`--detail`) mais ne bloque personne ; la dette du
lendemain, elle, est refusée. C'est le même principe que `audit_ui.mjs` sur DJ
et sur projet-b, généralisé aux outils standards.

Aucune dépendance : bibliothèque standard seulement. C'est ce qui lui permet de
tourner aux trois portes à la fois (check.sh --fast, hook de déploiement, CI)
sans qu'aucune ne puisse diverger des autres.

Usage
-----
    python3 scripts/cliquet.py              vérifie (0 vert, 1 un compteur monte)
    python3 scripts/cliquet.py --baseline   fige l'état courant comme référence
    python3 scripts/cliquet.py --detail     liste les occurrences, par règle
    python3 scripts/cliquet.py --only ruff  un seul outil

La référence est dans `.cliquet.json`, à la racine, et elle SE COMMITE : c'est
elle qui rend le verdict identique sur le poste, dans le hook et dans la CI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
REF = RACINE / ".cliquet.json"

ROUGE = "\033[31m"
VERT = "\033[32m"
JAUNE = "\033[33m"
GRAS = "\033[1m"
RAZ = "\033[0m"


def _python() -> str:
    """Le python du venv s'il existe, celui du poste sinon."""
    venv = RACINE / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        cmd, cwd=RACINE, capture_output=True, text=True, timeout=900, **kw
    )


# ── Les sondes ───────────────────────────────────────────────────────────────
# Chacune rend (disponible, {code: [occurrences]}). « disponible » à False veut
# dire « cet outil n'est pas installé ici » : ce n'est PAS zéro défaut, et le
# compteur correspondant est alors laissé intact plutôt que remis à zéro. Sinon
# désinstaller un outil suffirait à effacer sa dette, ce qui est exactement le
# mensonge qu'on cherche à empêcher.


def sonde_ruff() -> tuple[bool, dict[str, list[str]]]:
    py = _python()
    if _run([py, "-m", "ruff", "--version"]).returncode != 0:
        return False, {}
    p = _run([py, "-m", "ruff", "check", "--output-format", "json", "."])
    try:
        items = json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        return False, {}
    par_code: dict[str, list[str]] = {}
    for it in items:
        code = it.get("code") or "?"
        loc = f"{it.get('filename', '?')}:{(it.get('location') or {}).get('row', 0)}"
        par_code.setdefault(code, []).append(loc)
    return True, par_code


def sonde_eslint() -> tuple[bool, dict[str, list[str]]]:
    if not (RACINE / "node_modules").is_dir():
        return False, {}
    if not any(
        (RACINE / n).exists()
        for n in ("eslint.config.mjs", "eslint.config.js", "eslint.config.ts", ".eslintrc.json")
    ):
        return False, {}
    p = _run(["npx", "--no-install", "eslint", ".", "-f", "json"])
    try:
        items = json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        return False, {}
    par_code: dict[str, list[str]] = {}
    for f in items:
        for m in f.get("messages", []):
            code = m.get("ruleId") or "parse-error"
            par_code.setdefault(code, []).append(f"{f.get('filePath', '?')}:{m.get('line', 0)}")
    return True, par_code


RX_TSC = re.compile(r"^(?P<f>[^(]+)\((?P<l>\d+),\d+\): error (?P<c>TS\d+):")


def sonde_tsc() -> tuple[bool, dict[str, list[str]]]:
    if not (RACINE / "node_modules").is_dir() or not (RACINE / "tsconfig.json").exists():
        return False, {}
    p = _run(["npx", "--no-install", "tsc", "--noEmit", "--pretty", "false"])
    if p.returncode != 0 and not p.stdout and "error" not in p.stderr.lower():
        return False, {}
    par_code: dict[str, list[str]] = {}
    for ligne in (p.stdout + p.stderr).splitlines():
        m = RX_TSC.match(ligne.strip())
        if m:
            par_code.setdefault(m["c"], []).append(f"{m['f']}:{m['l']}")
    return True, par_code


SONDES = {"ruff": sonde_ruff, "eslint": sonde_eslint, "tsc": sonde_tsc}


# ── Le cliquet ───────────────────────────────────────────────────────────────
def mesurer(seulement: str | None) -> dict[str, tuple[bool, dict[str, list[str]]]]:
    return {
        nom: fn()
        for nom, fn in SONDES.items()
        if seulement is None or seulement == nom
    }


def charger_ref() -> dict:
    if not REF.exists():
        return {}
    try:
        return json.loads(REF.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def main() -> int:
    args = sys.argv[1:]
    figer = "--baseline" in args
    detail = "--detail" in args
    seulement = None
    if "--only" in args:
        i = args.index("--only")
        if i + 1 < len(args):
            seulement = args[i + 1]

    mesures = mesurer(seulement)
    ref = charger_ref()
    ref_outils = ref.get("outils", {})

    if figer:
        nouveau = dict(ref_outils)
        for nom, (dispo, par_code) in mesures.items():
            if not dispo:
                print(f"{JAUNE}. {nom} : absent, compteur laissé tel quel{RAZ}")
                continue
            nouveau[nom] = {c: len(v) for c, v in sorted(par_code.items())}
        REF.write_text(
            json.dumps(
                {
                    "_lisez_moi": (
                        "Dette figée le jour du portage du socle. Le cliquet échoue "
                        "seulement si un compteur MONTE. Baisser un compteur est "
                        "toujours permis ; refiger après une correction avec "
                        "scripts/cliquet.py --baseline."
                    ),
                    "outils": nouveau,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        total = sum(sum(v.values()) for v in nouveau.values())
        print(f"{GRAS}{VERT}Référence figée{RAZ} : {REF.name}, {total} occurrence(s) tolérée(s).")
        return 0

    if not ref_outils:
        print(f"{JAUNE}Aucune référence figée.{RAZ} Remède : python3 scripts/cliquet.py --baseline")
        return 1

    montees: list[str] = []
    baisses: list[str] = []
    for nom, (dispo, par_code) in mesures.items():
        attendu = ref_outils.get(nom)
        if attendu is None:
            continue
        if not dispo:
            if sum(attendu.values()) > 0:
                montees.append(
                    f"{nom} : outil absent alors que la référence en attend "
                    f"{sum(attendu.values())} occurrence(s). Un outil qu'on ne peut "
                    f"pas lancer n'est pas un contrôle vert."
                )
            continue
        codes = set(par_code) | set(attendu)
        for c in sorted(codes):
            avant = int(attendu.get(c, 0))
            apres = len(par_code.get(c, []))
            if apres > avant:
                lieux = ", ".join(par_code.get(c, [])[:5])
                montees.append(f"{nom}/{c} : {avant} -> {apres}   {lieux}")
            elif apres < avant:
                baisses.append(f"{nom}/{c} : {avant} -> {apres}")

    if detail:
        for nom, (dispo, par_code) in mesures.items():
            if not dispo:
                print(f"{JAUNE}. {nom} : absent{RAZ}")
                continue
            print(f"{GRAS}{nom}{RAZ}")
            for c, v in sorted(par_code.items(), key=lambda kv: -len(kv[1])):
                print(f"  {len(v):5d}  {c}")
                for loc in v[:3]:
                    print(f"           {loc}")

    if baisses:
        print(f"{VERT}Dette en baisse :{RAZ} " + " · ".join(baisses))
        print("  Refiger la référence pour la verrouiller : scripts/cliquet.py --baseline")
    if montees:
        print(f"{ROUGE}{GRAS}La dette monte :{RAZ}")
        for m in montees:
            print(f"  {m}")
        print(
            "  Un compteur qui monte est un défaut NEUF, pas de la dette héritée : "
            "le corriger. Si c'est un faux positif, le justifier dans .cliquet.json "
            "avant de refiger."
        )
        return 1
    return 0


if __name__ == "__main__":
    os.environ.setdefault("NO_COLOR", "")
    sys.exit(main())
