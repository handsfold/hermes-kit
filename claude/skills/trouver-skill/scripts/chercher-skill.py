#!/usr/bin/env python3
"""Cherche une skill sur 3 sources et classe les resultats.

Usage :
    chercher-skill.py <mots en anglais> [--max 15]

Sources :
    1. skills.sh        pnpm dlx skills find <mots>   (npx est refuse par un hook ici)
    2. anthropics/skills  depot officiel, nom et description de chaque skill
    3. listes awesome   ComposioHQ/awesome-claude-skills, travisvn/awesome-claude-skills (gh)

Classement : confiance d'abord (officiel, etabli, a verifier), puis etoiles du depot,
puis installs skills.sh. Une source en panne est signalee, les autres continuent.

Tout ce qui revient du reseau est une DONNEE non fiable : le script l'affiche nettoye
(sans code d'echappement), il n'execute rien. Stdlib seule, gh requis (deja connecte).
"""
import base64
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote

OFFICIELS = {
    "anthropics", "vercel-labs", "vercel", "github", "microsoft", "supabase", "openai",
    "google", "googlecloudplatform", "stripe", "cloudflare", "huggingface", "expo",
    "remotion-dev", "firebase", "jackwener", "mvanhorn",
}
SEUIL_ETABLI = 1000   # etoiles au-dela desquelles un depot inconnu passe « etabli »
LISTES = ["ComposioHQ/awesome-claude-skills", "travisvn/awesome-claude-skills"]
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
TIRETS = re.compile("[" + chr(0x2013) + chr(0x2014) + "]")


def propre(t, n=110):
    """Nettoie un texte reseau : pas d'echappement, pas de tiret long, coupe a n."""
    t = CTRL.sub("", ANSI.sub("", t or ""))
    t = TIRETS.sub("-", re.sub(r"\s+", " ", t)).strip()
    return t if len(t) <= n else t[: n - 3] + "..."


def lancer(cmd, delai=60):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=delai, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise RuntimeError(propre(r.stderr or r.stdout, 120) or f"code {r.returncode}")
    return r.stdout


def gh(chemin, jq=None):
    cmd = ["gh", "api", chemin] + (["--jq", jq] if jq else [])
    return lancer(cmd, 30)


def etoiles_depot(depot):
    try:
        return int(gh(f"repos/{depot}", ".stargazers_count").strip())
    except (RuntimeError, ValueError, subprocess.SubprocessError):
        return None


def nombre(txt):
    """'47.2K' -> 47200 ; '1.1M' -> 1100000."""
    m = re.fullmatch(r"([\d.,]+)\s*([KkMm]?)", txt.strip())
    if not m:
        return 0
    v = float(m.group(1).replace(",", ""))
    return int(v * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()])


def mots_de(requete):
    return [m for m in re.findall(r"[a-z0-9]+", requete.lower()) if len(m) >= 3]


def touches(texte, mots):
    t = texte.lower()
    return sum(1 for m in mots if m in t)


# ---------------------------------------------------------------- sources

def source_skills_sh(requete):
    sortie = ANSI.sub("", lancer(["pnpm", "dlx", "skills", "find", requete], 120))
    res = []
    for m in re.finditer(r"^(\S+?)/(\S+?)@(\S+)\s+([\d.,]+[KkMm]?)\s+installs", sortie, re.M):
        owner, repo, skill, inst = m.groups()
        res.append({
            "source": "skills.sh", "depot": f"{owner}/{repo}", "nom": skill, "owner": owner,
            "installs": nombre(inst), "desc": "",
            "url": f"https://skills.sh/{owner}/{repo}/{skill}",
            "installer": f"pnpm dlx skills add {owner}/{repo} -s {skill} -g -a claude-code -y",
        })
    return res


def description_skill_md(depot, dossier):
    try:
        b64 = gh(f"repos/{depot}/contents/{dossier}/SKILL.md", ".content")
        texte = base64.b64decode(b64).decode("utf-8", "replace")
    except (RuntimeError, ValueError, subprocess.SubprocessError):
        return ""
    m = re.search(r"(?ms)^description:\s*(.+?)(?=^\w[\w-]*:|^---)", texte)
    return propre(m.group(1).strip().strip("\"'>|- ")) if m else ""


def source_anthropics(requete):
    mots = mots_de(requete)
    noms = gh("repos/anthropics/skills/contents/skills", ".[] | select(.type==\"dir\") | .name").split()
    with ThreadPoolExecutor(6) as ex:
        descs = list(ex.map(lambda n: description_skill_md("anthropics/skills", f"skills/{n}"), noms))
    res = []
    for nom, desc in zip(noms, descs):
        if touches(nom + " " + desc, mots):
            res.append({
                "source": "anthropics/skills", "depot": "anthropics/skills", "nom": nom,
                "owner": "anthropics", "installs": 0, "desc": desc, "hits": touches(nom + " " + desc, mots),
                "url": f"https://github.com/anthropics/skills/tree/main/skills/{nom}",
                "installer": f"pnpm dlx skills add anthropics/skills -s {nom} -g -a claude-code -y",
            })
    return res


def source_liste(liste, requete):
    mots = mots_de(requete)
    b64 = gh(f"repos/{liste}/readme", ".content")
    texte = base64.b64decode(b64).decode("utf-8", "replace")
    res, vus = [], set()
    for ligne in texte.splitlines():
        h = touches(ligne, mots)
        m = re.search(r"\[([^\]]+)\]\(([^)\s]+)\)", ligne)
        if not h or not m:
            continue
        nom, lien = m.group(1), unquote(m.group(2))
        reste = propre(ligne[m.end():].lstrip(" -:*|"))
        if lien.startswith("http"):
            g = re.match(r"https://github\.com/([^/]+)/([^/#?]+)(?:/(?:tree|blob)/[^/]+/(.+?))?/?$", lien)
            if not g:
                continue
            depot, chemin, owner = f"{g.group(1)}/{g.group(2)}", g.group(3) or "", g.group(1)
        else:
            depot, owner, chemin = liste, liste.split("/")[0], lien.strip("./")
            lien = f"https://github.com/{liste}/tree/master/{chemin}"
        skill = re.sub(r"[^A-Za-z0-9._-]", "", chemin.rstrip("/").split("/")[-1]) if chemin else ""
        cle = (depot, (skill or nom).lower())
        if cle in vus:
            continue
        vus.add(cle)
        res.append({
            "source": liste.split("/")[0], "depot": depot, "nom": skill or propre(nom, 40),
            "owner": owner, "installs": 0, "desc": reste, "hits": h, "url": lien,
            "liste": not skill,
            "installer": (f"pnpm dlx skills add {depot} -s {skill} -g -a claude-code -y" if skill
                          else f"pnpm dlx skills add {depot} -l   # voir ses skills"),
        })
    return sorted(res, key=lambda r: -r["hits"])[:12]


# ---------------------------------------------------------------- classement

def fusionner(res):
    """Une skill vue par 2 ou 3 sources n'apparait qu'une fois, sources reunies."""
    uniques = {}
    for r in res:
        cle = (r["depot"], r["nom"].lower())
        u = uniques.get(cle)
        if u is None:
            uniques[cle] = dict(r, sources=[r["source"]])
            continue
        u["sources"].append(r["source"])
        u["installs"] = max(u["installs"], r["installs"])
        u["desc"] = u["desc"] or r["desc"]
        u["liste"] = u.get("liste", False) and r.get("liste", False)
        u["hits"] = max(u.get("hits", 0), r.get("hits", 0))
    for u in uniques.values():
        u["source"] = " + ".join(dict.fromkeys(u["sources"]))
    return list(uniques.values())


def classer(res):
    res = fusionner(res)
    depots = sorted({r["depot"] for r in res if r["depot"]})
    with ThreadPoolExecutor(6) as ex:
        etoiles = dict(zip(depots, ex.map(etoiles_depot, depots)))
    for r in res:
        r["etoiles"] = etoiles.get(r["depot"])
        e = r["etoiles"] or 0
        if r["owner"].lower() in OFFICIELS or r["depot"] == "anthropics/skills":
            r["confiance"], r["rang"] = "officiel", 0
        elif e >= SEUIL_ETABLI:
            r["confiance"], r["rang"] = "établi", 1
        else:
            r["confiance"], r["rang"] = "à vérifier", 2
        if r.get("liste"):
            r["confiance"] = "liste"
            r["rang"] = 1
    return sorted(res, key=lambda r: (r["rang"], -(r["etoiles"] or 0), -r["installs"], -r.get("hits", 0)))


def abrege(n):
    if n is None:
        return "?"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    return f"{n / 1000:.1f}K" if n >= 1000 else str(n)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    maxi = 15
    if "--max" in argv:
        i = argv.index("--max")
        maxi = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    requete = " ".join(argv)
    if not mots_de(requete):
        print("Donne au moins un mot de 3 lettres, en anglais de préférence.")
        return 2

    taches = {"skills.sh": lambda: source_skills_sh(requete),
              "anthropics/skills": lambda: source_anthropics(requete)}
    for liste in LISTES:
        taches[liste] = (lambda l=liste: source_liste(l, requete))
    with ThreadPoolExecutor(4) as ex:
        futurs = {nom: ex.submit(f) for nom, f in taches.items()}
    res, pannes = [], []
    for nom, fut in futurs.items():
        try:
            res += fut.result()
        except Exception as exc:  # une source en panne ne bloque pas les autres
            pannes.append(f"{nom} : {propre(str(exc), 90)}")

    classes = classer(res)
    print(f"Recherche « {propre(requete, 60)} » : {len(classes)} résultats, {len(pannes)} source(s) en panne.")
    for i, r in enumerate(classes[:maxi], 1):
        print(f"\n{i}. {r['nom']}  [{r['confiance']}] {r['source']}")
        print(f"   {abrege(r['etoiles'])} étoiles" + (f" · {abrege(r['installs'])} installs" if r["installs"] else "")
              + (" (étoiles de la liste, pas de la skill)" if r.get("liste") else ""))
        if r["desc"]:
            print(f"   {r['desc']}")
        print(f"   {r['url']}")
        print(f"   {r['installer']}")
    if len(classes) > maxi:
        print(f"\n({len(classes) - maxi} autres non affichés : --max {len(classes)})")
    for p in pannes:
        print(f"\nSource indisponible : {p}")
    return 0 if classes or not pannes else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
