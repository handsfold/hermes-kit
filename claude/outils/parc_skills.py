"""Le parc de skills de USER : les 3 dossiers, dedoublonnes, classes par leur source.

Ne en 2026-10-24 : verifier-skill.py --perso ne lisait que le 1er niveau de
~/.claude/skills et classait « de USER » par la langue de la description. Il
trouvait 49 skills sur plus de 200.

Une skill est « d'usine » si son nom figure dans une source tierce :
  - les skills livrees avec Hermes (~/.hermes/hermes-agent/skills et optional-skills,
    plus tout SKILL.md passe dans l'historique git du depot, pour les skills renommees
    ou retirees depuis) ;
  - ~/.hermes/skills/.bundled_manifest et ~/.hermes/skills/.hub/lock.json ;
  - ~/.agents/.skill-lock.json (skills installees par npx skills) ;
  - skills-tierces.txt, a cote de ce fichier (Cursor, paquets copies a la main).
Les chemins gstack, synced/ (claude.ai), openclaw-imports/, .archive et .hub sont
tiers d'office. Tout le reste est a USER, quelle que soit sa langue.

Usage : parc_skills.py   (resume)  ·  parc_skills.py --liste [poste|usine]
"""
import json
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
RACINES = [HOME / ".claude/skills", HOME / ".agents/skills", HOME / ".hermes/skills"]
TIERS_CHEMIN = ("/.archive/", "gstack", "/synced/", "/openclaw-imports/", "/.hub/",
                "/node_modules/", "/.git/")
TIERCES = Path(__file__).with_name("skills-tierces.txt")


def noms_usine():
    us = set()
    depot = HOME / ".hermes/hermes-agent"
    for b in ("skills", "optional-skills"):
        us |= {f.parent.name for f in (depot / b).rglob("SKILL.md")}
    try:
        sortie = subprocess.run(
            ["git", "-C", str(depot), "log", "--all", "--name-only", "--format=", "--", "*SKILL.md"],
            capture_output=True, text=True, timeout=30).stdout
        us |= {Path(l).parent.name for l in sortie.splitlines() if l.strip()}
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        us |= {l.split(":")[0] for l in (HOME / ".hermes/skills/.bundled_manifest").read_text().split()}
    except OSError:
        pass
    for f, cle in ((HOME / ".hermes/skills/.hub/lock.json", "installed"),
                   (HOME / ".agents/.skill-lock.json", "skills")):
        try:
            us |= set(json.loads(f.read_text()).get(cle) or {})
        except (OSError, ValueError):
            pass
    try:
        us |= {l.split("#")[0].strip() for l in TIERCES.read_text().splitlines()} - {""}
    except OSError:
        pass
    return us


def parc():
    """Liste de dicts {nom, chemin (dossier), racine, poste} : une entree par nom de skill.

    Ordre de priorite pour un nom present a plusieurs endroits : ~/.claude/skills,
    puis ~/.agents/skills, puis ~/.hermes/skills (les liens d'un dossier a l'autre
    ne comptent qu'une fois).
    """
    usine = noms_usine()
    vus = {}
    for racine in RACINES:
        for f in sorted(racine.rglob("SKILL.md")):
            p = f"{f}|{f.resolve()}"
            if any(x in p for x in TIERS_CHEMIN):
                continue
            nom = f.parent.name
            if nom not in vus:
                vus[nom] = {"nom": nom, "chemin": f.parent, "racine": racine.parent.name,
                            "poste": nom not in usine}
    return sorted(vus.values(), key=lambda s: s["nom"])


def est_de_vj(nom, _cache={}):
    if "parc" not in _cache:
        _cache["parc"] = {s["nom"]: s["poste"] for s in parc()}
    return _cache["parc"].get(nom, False)


if __name__ == "__main__":
    tout = parc()
    poste = [s for s in tout if s["poste"]]
    if "--liste" in sys.argv:
        quoi = sys.argv[-1] if sys.argv[-1] in ("poste", "usine") else "poste"
        for s in tout:
            if s["poste"] == (quoi == "poste"):
                print(f"{s['nom']:<40} {s['chemin']}")
    else:
        par = {}
        for s in poste:
            par[s["racine"]] = par.get(s["racine"], 0) + 1
        print(f"{len(tout)} skills distinctes : {len(poste)} de USER, {len(tout) - len(poste)} d'usine")
        print("de USER par dossier : " + ", ".join(f"~/{k}/skills {v}" for k, v in par.items()))
