#!/usr/bin/python3
"""Audit des skills de USER contre le guide Anthropic des skills (modeles 5.5).

Regles mesurables (video RoboNuggets VQyYzLJ6xos, 2026-10-05) :
  1. SKILL.md sous 500 lignes, references a un seul niveau.
  2. Tout fichier de plus de 100 lignes commence par un sommaire.
  5. Description courte, a la 3e personne.

Perimetre : skills actives de Claude Code (~/.claude/skills, hors skillOverrides
"off"), d'Hermes (~/.hermes/skills, hors skills.disabled, liens exclus pour ne
pas compter deux fois) et de Prime (~/.agents/skills, vrais dossiers seulement).

Usage : audit-skills.py [--tout] [--perso]
  --tout  : liste chaque skill, sinon seulement celles en ecart
  --json  : tout le catalogue en JSON (alimente la page web skills-audit)
  --perso : seulement les skills de USER, classees par leur source (parc_skills.py), pas par la langue
"""
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # python de linuxbrew en tete du PATH : relancer sous /usr/bin
    if sys.executable != "/usr/bin/python3" and Path("/usr/bin/python3").exists():
        os.execv("/usr/bin/python3", ["/usr/bin/python3", *sys.argv])
    raise

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parc_skills import est_de_vj  # noqa: E402

HOME = Path.home()
SEUIL_SOMMAIRE = 100
SEUIL_SKILL = 500
SEUIL_DESC = 500
PREMIERE_PERSONNE = re.compile(r"^\s*(je |j'|i |i'm|i can|me |nous )", re.I)
REF_MD = re.compile(r"[\w./-]+\.md\b")


def desactivees_claude():
    try:
        s = json.loads((HOME / ".claude/settings.json").read_text())
    except Exception:
        return set()
    return {k for k, v in (s.get("skillOverrides") or {}).items() if v == "off"}


def desactivees_hermes():
    try:
        c = yaml.safe_load((HOME / ".hermes/config.yaml").read_text())
        return set((c.get("skills") or {}).get("disabled") or [])
    except Exception:
        return set()


def skills():
    vus = set()
    off = desactivees_claude()
    for d in sorted((HOME / ".claude/skills").iterdir()):
        f = d / "SKILL.md"
        if f.exists() and d.name not in off:
            vus.add(f.resolve())
            yield "claude", d.name, f
    off = desactivees_hermes()
    racine = HOME / ".hermes/skills"
    trouves = []
    for dossier, sous, _ in os.walk(racine, followlinks=True):
        sous[:] = [s for s in sous if not s.startswith(".")]
        if Path(dossier).relative_to(racine).parts.__len__() >= 3:
            sous[:] = []
        if (Path(dossier) / "SKILL.md").exists():
            trouves.append(Path(dossier) / "SKILL.md")
    # Une skill de USER deplacee vers ~/.claude/skills (lien en retour) reste une skill
    # d'Hermes : on la compte ici si Claude ne l'a pas deja comptee (skillOverrides "off").
    for f in sorted(trouves):
        d = f.parent
        if d.name in off:
            continue
        if f.resolve() not in vus and "/.archive" not in str(f):
            vus.add(f.resolve())
            yield "hermes", d.name, f
    for d in sorted((HOME / ".agents/skills").iterdir()):
        f = d / "SKILL.md"
        if not d.is_symlink() and f.exists() and f.resolve() not in vus:
            vus.add(f.resolve())
            yield "prime", d.name, f


def corps(texte):
    """Texte sans le frontmatter, et la description."""
    m = re.match(r"^---\n(.*?)\n---\n?", texte, re.S)
    if not m:
        return texte, ""
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        fm = {}
    return texte[m.end():], str(fm.get("description") or "")


def a_sommaire(texte):
    """Vrai si les 30 premieres lignes nomment au moins 3 des titres ## du fichier."""
    lignes = texte.splitlines()
    titres = [l.lstrip("#").strip().lower() for l in lignes if re.match(r"^#{2,3} ", l)]
    if len(titres) < 3:
        return True  # fichier sans vraies sections : rien a sommairiser
    tete = "\n".join(lignes[:30]).lower()
    tete = "\n".join(l for l in tete.splitlines() if not re.match(r"^#{2,3} ", l))
    trouves = sum(1 for t in titres if t[:25] and t[:25] in tete)
    return trouves >= 3 or re.search(r"\b(sommaire|contents|table des mati)", tete)


def auditer(f):
    texte = f.read_text(errors="ignore")
    texte_corps, desc = corps(texte)
    n = texte.count("\n") + 1
    ecarts = []
    if n > SEUIL_SKILL:
        ecarts.append(f"SKILL.md {n} lignes (> {SEUIL_SKILL})")
    elif n > SEUIL_SOMMAIRE and not a_sommaire(texte_corps):
        ecarts.append(f"SKILL.md {n} lignes sans sommaire")
    if len(desc) > SEUIL_DESC:
        ecarts.append(f"description {len(desc)} car.")
    if PREMIERE_PERSONNE.search(desc):
        ecarts.append("description a la 1re personne")
    d = f.parent
    for r in sorted(d.rglob("*.md")):
        if r == f or {".git", "node_modules", ".agents", "fixtures"} & set(r.parts):
            continue
        t = r.read_text(errors="ignore")
        nr = t.count("\n") + 1
        rel = r.relative_to(d)
        if nr > SEUIL_SOMMAIRE and not a_sommaire(t):
            ecarts.append(f"{rel} {nr} lignes sans sommaire")
        imbriques = [m for m in set(REF_MD.findall(t))
                     if (r.parent / m).exists() and (r.parent / m) != r]
        if imbriques:
            ecarts.append(f"{rel} renvoie a {', '.join(sorted(imbriques)[:3])} (2e niveau)")
    return n, ecarts, est_de_vj(f.parent.name) and not any(
        x in str(f) for x in ("gstack", "/synced/", "/openclaw-imports/"))


def main():
    tout = "--tout" in sys.argv
    perso = "--perso" in sys.argv
    if "--json" in sys.argv:
        lignes = []
        for agent, nom, f in skills():
            n, ecarts, de_vj = auditer(f)
            desc = corps(f.read_text(errors="ignore"))[1]
            lignes.append({"agent": agent, "nom": nom, "lignes": n, "desc": len(desc),
                           "ecarts": ecarts, "perso": de_vj})
        print(json.dumps(lignes, ensure_ascii=False))
        return
    total = avec = 0
    par_agent = {}
    en_ecart = {}
    for agent, nom, f in skills():
        n, ecarts, de_vj = auditer(f)
        if perso and not de_vj:
            continue
        total += 1
        par_agent[agent] = par_agent.get(agent, 0) + 1
        if ecarts:
            avec += 1
            en_ecart[agent] = en_ecart.get(agent, 0) + 1
        if ecarts or tout:
            print(f"[{agent}] {nom} ({n} l.)")
            for e in ecarts[:6]:
                print(f"    {e}")
            if len(ecarts) > 6:
                print(f"    ... {len(ecarts) - 6} autres")
    detail = ", ".join(f"{a} {c}" for a, c in par_agent.items())
    print(f"\nConformite au guide, par agent :")
    for a, c in par_agent.items():
        ok = c - en_ecart.get(a, 0)
        barre = "█" * round(20 * ok / c) + "░" * (20 - round(20 * ok / c))
        print(f"  {a:<7} {barre} {ok}/{c} conformes")
    print(f"\n{total} skills actives ({detail}) : {avec} avec au moins un ecart.")


if __name__ == "__main__":
    main()
