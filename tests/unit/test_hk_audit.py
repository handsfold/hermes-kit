"""hk-audit : photo avant, migration puis annulation, sur un faux HOME en desordre."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
SCRIPT = RACINE / "install" / "hk-audit.py"


def skill(dossier: Path, description: str, corps: str = "corps") -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    texte = f"---\nname: {dossier.name}\ndescription: {description}\n---\n{corps}\n"
    (dossier / "SKILL.md").write_text(texte)


def desordre(home: Path) -> None:
    c, h = home / ".claude" / "skills", home / ".hermes" / "skills"
    skill(c / "alpha", "Alpha : fait A.")
    skill(c / "beta", "Beta : fait B.", "version ancienne")
    os.utime(c / "beta" / "SKILL.md", (1577836800, 1577836800))  # 2020
    skill(h / "productivity" / "alpha", "Alpha : fait A.")  # copie identique
    skill(h / "research" / "beta", "Beta : fait B.", "version neuve")  # divergente, plus recente
    skill(h / "misc" / "gamma", "Gamma : seulement dans Hermes.")
    skill(h / "c" / "mort", "Mort : lien casse cote Claude.")
    (c / "mort").symlink_to(home / "nulle-part")  # lien mort, une copie existe ailleurs
    (home / ".claude" / "settings.json").write_text("{}")


def photo(home: Path) -> list:
    etat = []
    for p in sorted(home.rglob("*")):
        if ".config" in p.parts:
            continue
        r = str(p.relative_to(home))
        if p.is_symlink():
            etat.append(("L", r, os.readlink(p)))
        elif p.is_file():
            etat.append(("F", r, hashlib.sha1(p.read_bytes(), usedforsecurity=False).hexdigest()))
    return etat


def lancer(home: Path, *args: str) -> str:
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "HK_LANG": "fr"}
    r = subprocess.run(  # noqa: S603  (script du depot, arguments fixes)
        [sys.executable, "-I", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout


def test_avant_migrer_annuler(tmp_path):
    home = tmp_path / "home"
    desordre(home)
    initial = photo(home)
    audit = home / ".config" / "hermes-kit" / "audit"

    lancer(home, "--avant", "--sans-historique")
    avant = json.loads((audit / "avant.json").read_text())
    assert avant["skills"]["eparpillees"] == 4
    assert avant["skills"]["doublons"] == 2
    assert list(audit.glob("sauvegarde-*.tar.gz"))

    lancer(home, "--migrer")
    c = home / ".claude" / "skills"
    assert (c / "gamma" / "SKILL.md").is_file()  # entree dans la source
    assert "version neuve" in (c / "beta" / "SKILL.md").read_text()  # la plus recente gagne
    assert (home / ".hermes" / "skills" / "research" / "beta").is_symlink()
    assert (c / "mort" / "SKILL.md").is_file()  # lien mort remplace par la copie

    lancer(home, "--sans-historique")
    apres = json.loads((audit / "apres.json").read_text())
    assert apres["skills"]["eparpillees"] == 0
    assert apres["skills"]["doublons"] == 0
    assert apres["gain"]["score"]["apres"] > apres["gain"]["score"]["avant"]

    lancer(home, "--annuler")
    assert photo(home) == initial
