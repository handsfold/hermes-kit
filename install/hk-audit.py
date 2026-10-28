#!/usr/bin/env python3
"""hk-audit : photo de la config existante, migration propre, avant/apres chiffre.

Lance par install.sh juste apres la connexion du compte Claude (photo « avant »),
puis apres la pose des fichiers (migration, photo « apres »). Se relance a la main :

  hk audit                      etat actuel, compare a la photo avant s'il y en a une
  hk audit --avant              photo avant + sauvegarde, dans ~/.config/hermes-kit/audit
  hk audit --migrer [--archiver-dormantes]   regroupe les skills eparpillees, journal pour annuler
  hk audit --annuler            defait la derniere migration
  options : --json  --jours N (defaut 30)  --sans-historique (saute la lecture des transcripts)

Ce que l'audit lit, sans rien modifier :
  - skills de Claude Code (~/.claude/skills, plugins, .claude/skills des projets),
    d'Hermes (~/.hermes/skills) et des autres agents (~/.agents, ~/.codex, ~/.openclaw, opencode) ;
  - poids fixe relu a chaque session : CLAUDE.md et ses imports, index des skills, serveurs MCP ;
  - 30 jours d'historique Claude Code (~/.claude/projects/**/*.jsonl, champ message.usage) :
    tokens, part du cache, equivalent API en dollars, skills vraiment chargees ;
  - les signaux de suivi des couts (historique garde, barre d'etat, journal du proxy, hooks).

Regle : la migration ne supprime rien. Une copie part dans audit/archive/<date>/, un lien la
remplace, et chaque geste est ecrit dans audit/migration-<date>.json pour --annuler.
"""

import functools
import hashlib
import json
import os
import shutil
import sys
import tarfile
import time
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path(os.environ.get("HOME", str(Path.home())))
HA = Path(os.environ.get("HERMES_HOME", str(HOME / ".hermes")))
ETAT = HOME / ".config" / "hermes-kit"
AUDIT = ETAT / "audit"
LANG = os.environ.get("HK_LANG", "en")


def _hk_home() -> Path:
    if os.environ.get("HK_HOME"):
        return Path(os.environ["HK_HOME"])
    try:
        return Path((ETAT / "home").read_text().strip())
    except OSError:
        return HOME / ".hermes-kit"


HK_HOME = _hk_home()
SOURCE = HOME / ".claude" / "skills"  # source unique des skills de l'utilisateur

# Lieux ou un agent range ses skills : (nom, dossier, profondeur maximale du SKILL.md)
LIEUX = [
    ("claude", SOURCE, 1),
    ("hermes", HA / "skills", 3),
    ("agents", HOME / ".agents" / "skills", 1),
    ("codex", HOME / ".codex" / "skills", 1),
    ("openclaw", HOME / ".openclaw" / "skills", 2),
    ("opencode", HOME / ".config" / "opencode" / "skill", 1),
]
IGNORES = {
    ".git",
    ".archive",
    ".hub",
    ".curator_backups",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
}
HORS_SAUVEGARDE = {".git", "node_modules", "__pycache__", ".venv", "venv"}

# $ par million de tokens (grille API) : entree, sortie, ecriture cache 5 min, lecture cache
GRILLES = {
    "opus": (5.0, 25.0, 6.25, 0.50),
    "fable": (10.0, 50.0, 12.50, 0.25),
    "sonnet": (3.0, 15.0, 3.75, 0.30),
    "haiku": (1.0, 5.0, 1.25, 0.10),
}
LIMITE_INDEX = 1536  # Claude Code coupe description + when_to_use a 1 536 caracteres
CHARS_PAR_TOKEN = 4

T = {
    "fr": {
        "titre": "Audit de ta config",
        "score": "Score",
        "skills": "skills",
        "eparp": "éparpillées hors de la source unique",
        "doublons": "en double, dont {d} avec un contenu différent",
        "dormantes": "jamais chargées en {j} jours",
        "desc": "sans description utilisable",
        "poids": "relus à chaque session (CLAUDE.md, index des skills)",
        "conso": "{j} jours : {t} tokens, {usd} $ en équivalent API, cache {c} %",
        "suivi": "suivi des coûts : {n}/5 ({manque})",
        "rien": "aucun",
        "gain": "Avant / après",
        "migration": "migration : {n} gestes, {c} conflits (l'autre version est archivée)",
        "garde": "  {s} : version gardée {g}",
        "sauvegarde": "  sauvegarde : {f}",
        "annule": "annulé : {n} gestes ({f})",
        "libelles": {
            "score": "score",
            "eparpillees": "éparpillées",
            "doublons": "doublons",
            "poids_session_tokens": "tokens par session",
            "suivi": "suivi des coûts",
            "usd_par_jour_actif": "$ par jour actif",
            "contexte_par_appel": "contexte par appel",
            "part_cache": "part du cache %",
        },
    },
    "en": {
        "titre": "Audit of your setup",
        "score": "Score",
        "skills": "skills",
        "eparp": "scattered outside the single source",
        "doublons": "duplicated, {d} of them diverging",
        "dormantes": "never loaded in {j} days",
        "desc": "without a usable description",
        "poids": "re-read every session (CLAUDE.md, skills index)",
        "conso": "{j} days: {t} tokens, ${usd} API equivalent, cache {c} %",
        "suivi": "cost tracking: {n}/5 ({manque})",
        "rien": "none",
        "gain": "Before / after",
        "migration": "migration: {n} actions, {c} conflicts (the other version is archived)",
        "garde": "  {s}: kept {g}",
        "sauvegarde": "  backup: {f}",
        "annule": "undone: {n} actions ({f})",
        "libelles": {
            "score": "score",
            "eparpillees": "scattered",
            "doublons": "duplicates",
            "poids_session_tokens": "tokens per session",
            "suivi": "cost tracking",
            "usd_par_jour_actif": "$ per active day",
            "contexte_par_appel": "context per call",
            "part_cache": "cache share %",
        },
    },
}[LANG if LANG in ("fr", "en") else "en"]


# ------------------------------------------------------------------ lecture des skills
def frontmatter(texte: str) -> dict:
    """Mini lecteur YAML : cles de premier niveau, scalaires et blocs > ou |."""
    if not texte.startswith("---"):
        return {}
    fin = texte.find("\n---", 3)
    if fin < 0:
        return {}
    res, cle, bloc = {}, None, []
    for ligne in texte[3:fin].splitlines():
        if cle and (ligne.startswith((" ", "\t")) or not ligne.strip()):
            bloc.append(ligne.strip())
            continue
        if cle:
            res[cle] = " ".join(b for b in bloc if b)
            cle, bloc = None, []
        if ":" not in ligne or ligne.startswith((" ", "#")):
            continue
        k, v = ligne.split(":", 1)
        k, v = k.strip(), v.strip()
        if v in (">", "|", ">-", "|-", ">+", "|+", ""):
            cle, bloc = k, []
        else:
            res[k] = v.strip("\"'")
    if cle:
        res[cle] = " ".join(b for b in bloc if b)
    return res


def lire_skill(dossier: Path, lieu: str) -> dict | None:
    f = dossier / "SKILL.md"
    try:
        brut = f.read_bytes()
    except OSError:
        return None
    fm = frontmatter(brut.decode("utf-8", "ignore"))
    desc, wtu = fm.get("description", ""), fm.get("when_to_use", "")
    try:
        reel = str(dossier.resolve())
    except OSError:
        reel = str(dossier)
    return {
        "nom": fm.get("name") or dossier.name,
        "dossier": dossier.name,
        "lieu": lieu,
        "chemin": str(dossier),
        "reel": reel,
        "lien": dossier.is_symlink(),
        "desc": len(desc),
        "wtu": len(wtu),
        "fm": bool(fm),
        "empreinte": hashlib.sha1(brut, usedforsecurity=False).hexdigest()[:12],
        "mtime": f.stat().st_mtime,
    }


def lister(racine: Path, lieu: str, profondeur: int) -> list[dict]:
    out = []
    if not racine.is_dir():
        return out
    try:
        enfants = sorted(racine.iterdir())
    except OSError:
        return out
    for e in enfants:
        if e.name.startswith(".") or e.name in IGNORES:
            continue
        if (e / "SKILL.md").is_file():
            s = lire_skill(e, lieu)
            if s:
                out.append(s)
        elif profondeur > 1 and e.is_dir() and not e.is_symlink():
            out += lister(e, lieu, profondeur - 1)
    return out


@functools.cache
def noms_fournis() -> dict[str, str]:
    """Skills qui ne sont pas a l'utilisateur : fournies par Hermes, le hub ou le kit."""
    noms = {}
    # Le code d'Hermes porte ses skills : elles comptent comme fournies avant meme le 1er demarrage.
    for base in (HA / "hermes-agent" / "skills", HA / "hermes-agent" / "optional-skills"):
        if base.is_dir():
            for f in base.rglob("SKILL.md"):
                noms[f.parent.name] = "hermes-fourni"
    try:
        for ligne in (HA / "skills" / ".bundled_manifest").read_text().splitlines():
            if ":" in ligne:
                noms[ligne.split(":", 1)[0].strip()] = "hermes-fourni"
    except OSError:
        pass
    try:
        for n in json.loads((HA / "skills" / ".hub" / "lock.json").read_text()).get(
            "installed", {}
        ):
            noms[n] = "hub"
    except (OSError, ValueError):
        pass
    for base in (
        HK_HOME / "hermes" / "skills",
        HK_HOME / "claude" / "skills",
        HK_HOME / "install" / "skills",
    ):
        if base.is_dir():
            for f in base.rglob("SKILL.md"):
                noms[f.parent.name] = "kit"
    return noms


def skills_plugins() -> list[dict]:
    out = []
    try:
        d = json.loads((HOME / ".claude" / "plugins" / "installed_plugins.json").read_text())
    except (OSError, ValueError):
        return out
    # Seuls les plugins actives (enabledPlugins a true) entrent dans l'index de Claude Code.
    actifs = lire_json(HOME / ".claude" / "settings.json").get("enabledPlugins") or {}
    for nom, installs in (d.get("plugins") or {}).items():
        chemins = {
            i.get("installPath", "")
            for i in (installs if isinstance(installs, list) else [installs])
        }
        for c in sorted(chemins):
            for s in lister(Path(c) / "skills", "plugin", 1):
                out.append(dict(s, lieu="plugin", plugin=nom, actif=actifs.get(nom) is True))
    return out


def inventaire(cwds: set[str]) -> dict:
    fournis = noms_fournis()
    skills = []
    for lieu, racine, prof in LIEUX:
        skills += lister(racine, lieu, prof)
    for s in skills:
        s["origine"] = fournis.get(s["dossier"], "utilisateur")
    plugins = skills_plugins()
    projets = []
    for c in sorted(cwds):
        p = Path(c) / ".claude" / "skills"
        if c.startswith(("/tmp", str(HOME / ".cache"))) or Path(c) == HOME:  # noqa: S108
            continue
        projets += [
            dict(s, lieu="projet", projet=c, origine="projet") for s in lister(p, "projet", 1)
        ]
    return {"skills": skills, "plugins": plugins, "projets": projets}


# ------------------------------------------------------------------ historique Claude Code
def famille(modele: str) -> str:
    m = (modele or "").lower()
    for f in ("opus", "fable", "haiku", "sonnet"):
        if f in m:
            return f
    return "sonnet"


def historique(jours: int, depuis: float | None = None) -> dict:
    limite = depuis or (time.time() - jours * 86400)
    iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(limite))
    vus = set()
    tok = defaultdict(int)
    usd = 0.0
    appels, sessions, jours_actifs, cwds = 0, set(), set(), set()
    chargees = Counter()
    premier = None
    racine = HOME / ".claude" / "projects"
    fichiers = [f for f in racine.rglob("*.jsonl")] if racine.is_dir() else []
    for f in fichiers:
        try:
            if f.stat().st_mtime < limite:
                continue
            with open(f, errors="ignore") as fh:
                for ligne in fh:
                    if '"assistant"' not in ligne:
                        continue
                    try:
                        o = json.loads(ligne)
                    except ValueError:
                        continue
                    ts = o.get("timestamp") or ""
                    if o.get("type") != "assistant" or ts < iso:
                        continue
                    m = o.get("message") or {}
                    if o.get("cwd"):
                        cwds.add(o["cwd"])
                    for c in m.get("content") or []:
                        if not isinstance(c, dict) or c.get("type") != "tool_use":
                            continue
                        entree = c.get("input") or {}
                        if c.get("name") == "Skill" and entree.get("skill"):
                            chargees[str(entree["skill"]).split(":")[-1]] += 1
                        elif c.get("name") == "Read" and str(entree.get("file_path", "")).endswith(
                            "/SKILL.md"
                        ):
                            chargees[Path(entree["file_path"]).parent.name] += 1
                    mid = m.get("id") or o.get("requestId")
                    u = m.get("usage") or {}
                    if not u or mid in vus:
                        continue
                    vus.add(mid)
                    appels += 1
                    sessions.add(f.stem)
                    jours_actifs.add(ts[:10])
                    premier = min(premier or ts, ts)
                    i, s_ = u.get("input_tokens", 0), u.get("output_tokens", 0)
                    cw, cr = (
                        u.get("cache_creation_input_tokens", 0),
                        u.get("cache_read_input_tokens", 0),
                    )
                    tok["entree"] += i
                    tok["sortie"] += s_
                    tok["cache_ecrit"] += cw
                    tok["cache_lu"] += cr
                    g = GRILLES[famille(m.get("model", ""))]
                    usd += (i * g[0] + s_ * g[1] + cw * g[2] + cr * g[3]) / 1e6
        except OSError:
            continue
    lu = tok["entree"] + tok["cache_ecrit"] + tok["cache_lu"]
    return {
        "jours": jours,
        "jours_actifs": len(jours_actifs),
        "premier": premier,
        "sessions": len(sessions),
        "appels": appels,
        "tokens": dict(tok),
        "tokens_total": lu + tok["sortie"],
        "usd": round(usd, 2),
        "usd_par_jour_actif": round(usd / len(jours_actifs), 2) if jours_actifs else 0,
        "contexte_par_appel": round(lu / appels) if appels else 0,
        "part_cache": round(100 * tok["cache_lu"] / lu, 1) if lu else 0,
        "skills_chargees": dict(chargees.most_common()),
        "cwds": sorted(cwds),
    }


def hermes_utilisees(depuis: float) -> set[str]:
    try:
        d = json.loads((HA / "skills" / ".usage.json").read_text())
    except (OSError, ValueError):
        return set()
    iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(depuis))
    return {n for n, v in d.items() if isinstance(v, dict) and (v.get("last_used_at") or "") >= iso}


# ------------------------------------------------------------------ poids fixe et suivi
def taille_claude_md(f: Path, vus: set, prof: int = 0) -> int:
    if prof > 4 or f in vus or not f.is_file():
        return 0
    vus.add(f)
    texte = f.read_text(errors="ignore")
    n = len(texte)
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if ligne.startswith("@") and len(ligne) > 1 and " " not in ligne:
            cible = Path(os.path.expanduser(ligne[1:]))
            if not cible.is_absolute():
                cible = f.parent / cible
            n += taille_claude_md(cible, vus, prof + 1)
    return n


def lire_json(f: Path) -> dict:
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return {}


def suivi() -> dict:
    reglages = lire_json(HOME / ".claude" / "settings.json")
    hooks = reglages.get("hooks") or {}
    commandes = json.dumps(hooks)
    journal_proxy = HA / "proxy-usage.jsonl"
    signaux = {
        "historique_garde": int(reglages.get("cleanupPeriodDays", 30)) >= 90,
        "barre_etat": bool(reglages.get("statusLine")),
        "journal_proxy": journal_proxy.is_file()
        and time.time() - journal_proxy.stat().st_mtime < 7 * 86400,
        "journal_skills": "journal-skills" in commandes,
        "outils_bilan": (HOME / ".claude" / "outils" / "cache-bilan.py").is_file(),
    }
    nb_hooks = sum(len(v) for v in hooks.values() if isinstance(v, list))
    return {
        "signaux": signaux,
        "hooks": nb_hooks,
        "historique_jours": reglages.get("cleanupPeriodDays", 30),
    }


def mcp() -> int:
    d = lire_json(HOME / ".claude.json")
    n = len(d.get("mcpServers") or {})
    for p in (d.get("projects") or {}).values():
        if isinstance(p, dict):
            n += len(p.get("mcpServers") or {})
    return n


# ------------------------------------------------------------------ analyse
def analyser(jours: int, avec_historique: bool, depuis: float | None = None) -> dict:
    h = historique(jours, depuis) if avec_historique else historique(0, time.time())
    inv = inventaire(set(h["cwds"]))
    skills = inv["skills"]
    # Une skill liee a plusieurs endroits reste une seule skill : on compte par chemin reel.
    uniques = list(
        {s["reel"]: s for s in sorted(skills, key=lambda s: s["lien"], reverse=True)}.values()
    )
    perso = [s for s in uniques if s["origine"] == "utilisateur"]

    # Eparpillees : une skill de l'utilisateur qui vit hors de ~/.claude/skills (ni lien vers elle).
    source_reelle = str(SOURCE.resolve()) if SOURCE.exists() else str(SOURCE)
    eparp = [
        s
        for s in perso
        if s["lieu"] != "claude" and not s["lien"] and not s["reel"].startswith(source_reelle)
    ]
    par_nom = defaultdict(list)
    plugins_actifs = [s for s in inv["plugins"] if s["actif"]]
    for s in skills + plugins_actifs:
        par_nom[s["dossier"]].append(s)
    doublons, divergents = [], []
    for nom, groupe in par_nom.items():
        reels = {s["reel"] for s in groupe}
        if len(reels) > 1:
            doublons.append(nom)
            if len({s["empreinte"] for s in groupe}) > 1:
                divergents.append(nom)

    # Dormantes : jamais chargees dans la fenetre, ni par Claude Code ni par Hermes.
    debut = depuis or (time.time() - jours * 86400)
    utilisees = set(h["skills_chargees"]) | hermes_utilisees(debut)
    couverture = 0
    if h["premier"]:
        couverture = (
            time.time() - time.mktime(time.strptime(h["premier"][:19], "%Y-%m-%dT%H:%M:%S"))
        ) / 86400
    noms_perso = sorted({s["dossier"] for s in perso})
    dormantes = [n for n in noms_perso if n not in utilisees]
    mauvaises = [s["chemin"] for s in perso if not s["fm"] or s["desc"] == 0 or s["desc"] > 1024]

    # Poids fixe relu a chaque session de Claude Code.
    vues_claude = [s for s in skills if s["lieu"] == "claude"] + plugins_actifs
    index = sum(min(s["desc"] + s["wtu"], LIMITE_INDEX) + len(s["nom"]) + 20 for s in vues_claude)
    claude_md = taille_claude_md(HOME / ".claude" / "CLAUDE.md", set())
    poids_tokens = (index + claude_md) // CHARS_PAR_TOKEN

    su = suivi()
    sig = su["signaux"]
    # Score sur 100 : chaque bloc compte seulement s'il est mesurable.
    blocs = {}
    if perso:
        blocs["dispersion"] = (20 * (1 - len(eparp) / len(perso)), 20)
        blocs["descriptions"] = (15 * (1 - len(mauvaises) / len(perso)), 15)
        if couverture >= 7:
            blocs["dormantes"] = (15 * (1 - len(dormantes) / len(noms_perso)), 15)
    blocs["doublons"] = (max(0, 15 - 3 * len(divergents) - (len(doublons) - len(divergents))), 15)
    blocs["poids"] = (15 * min(1, max(0, (15000 - poids_tokens) / 12000)), 15)
    blocs["suivi"] = (4 * sum(sig.values()), 20)
    score = round(100 * sum(a for a, _ in blocs.values()) / sum(m for _, m in blocs.values()))

    autres = sorted({s["lieu"] for s in skills if s["lieu"] not in ("claude",)})
    return {
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "horodatage": time.time(),
        "score": score,
        "blocs": {k: [round(a, 1), m] for k, (a, m) in blocs.items()},
        "agents": {
            "claude_code": (HOME / ".claude").is_dir(),
            "hermes": (HA / "config.yaml").is_file(),
            "autres": [lieu for lieu in autres if lieu != "hermes"],
        },
        "skills": {
            "total": len(uniques),
            "utilisateur": len(perso),
            "fournies": len(uniques) - len(perso),
            "emplacements": len(skills),
            "plugins": len(plugins_actifs),
            "plugins_inactifs": len(inv["plugins"]) - len(plugins_actifs),
            "projets": len(inv["projets"]),
            "eparpillees": len(eparp),
            "doublons": len(doublons),
            "divergents": len(divergents),
            "dormantes": len(dormantes),
            "mauvaises_descriptions": len(mauvaises),
            "couverture_jours": round(couverture, 1),
            "liste_eparpillees": [s["chemin"] for s in eparp][:200],
            "liste_divergents": divergents[:100],
            "liste_dormantes": dormantes[:300],
        },
        "poids_session_tokens": poids_tokens,
        "claude_md_tokens": claude_md // CHARS_PAR_TOKEN,
        "mcp": mcp(),
        "suivi": su,
        "historique": {k: v for k, v in h.items() if k != "cwds"},
    }


def lisible(n: float) -> str:
    for seuil, suffixe in ((1e9, " G"), (1e6, " M"), (1e3, " k")):
        if n >= seuil:
            return f"{n / seuil:.1f}{suffixe}"
    return str(int(n))


def resume(a: dict) -> str:
    s, h, su = a["skills"], a["historique"], a["suivi"]
    manque = [k for k, v in su["signaux"].items() if not v]
    lignes = [
        f"{T['titre']} : {T['score']} {a['score']}/100",
        f"  {s['total']} {T['skills']} ({s['utilisateur']} perso, "
        f"{s['fournies']} fournies, {s['plugins']} plugins)",
        f"  {s['eparpillees']} {T['eparp']}",
        f"  {s['doublons']} {T['doublons'].format(d=s['divergents'])}",
    ]
    if s["couverture_jours"] >= 7:
        lignes.append(f"  {s['dormantes']} {T['dormantes'].format(j=h['jours'])}")
    lignes += [
        f"  {s['mauvaises_descriptions']} {T['desc']}",
        f"  {lisible(a['poids_session_tokens'])} tokens {T['poids']}",
    ]
    if h["appels"]:
        lignes.append(
            "  "
            + T["conso"].format(
                j=h["jours"], t=lisible(h["tokens_total"]), usd=h["usd"], c=h["part_cache"]
            )
        )
    lignes.append(
        "  " + T["suivi"].format(n=5 - len(manque), manque=", ".join(manque) or T["rien"])
    )
    return "\n".join(lignes)


def comparer(av: dict, ap: dict) -> dict:
    def d(chemin):
        x, y = av, ap
        for k in chemin:
            x, y = x.get(k, 0), y.get(k, 0)
        return {"avant": x, "apres": y}

    g = {
        "score": d(["score"]),
        "eparpillees": d(["skills", "eparpillees"]),
        "doublons": d(["skills", "doublons"]),
        "poids_session_tokens": d(["poids_session_tokens"]),
        "suivi": {
            "avant": sum(av["suivi"]["signaux"].values()),
            "apres": sum(ap["suivi"]["signaux"].values()),
        },
    }
    # Conso : seulement quand l'apres couvre au moins 3 jours actifs, ramenee au jour actif.
    if ap["historique"]["jours_actifs"] >= 3 and av["historique"]["jours_actifs"]:
        g["usd_par_jour_actif"] = d(["historique", "usd_par_jour_actif"])
        g["contexte_par_appel"] = d(["historique", "contexte_par_appel"])
        g["part_cache"] = d(["historique", "part_cache"])
    return g


def resume_gain(g: dict) -> str:
    lignes = [T["gain"]]
    for k, v in g.items():
        nom = T["libelles"].get(k, k)
        lignes.append(f"  {nom:20s} {lisible(v['avant']):>8} -> {lisible(v['apres']):>8}")
    return "\n".join(lignes)


# ------------------------------------------------------------------ sauvegarde
A_SAUVER = [
    HOME / ".claude" / "skills",
    HOME / ".claude" / "commands",
    HOME / ".claude" / "agents",
    HOME / ".claude" / "hooks",
    HOME / ".claude" / "settings.json",
    HOME / ".claude" / "CLAUDE.md",
    HOME / ".claude" / "outils",
    HOME / ".claude.json",
    HA / "skills",
    HA / "config.yaml",
    HA / ".env",
    HA / "cron",
    HA / "SOUL.md",
    HOME / ".agents" / "skills",
    HOME / ".codex" / "skills",
    HOME / ".openclaw" / "skills",
]


def sauvegarder(stamp: str) -> Path | None:
    presents = [p for p in A_SAUVER if p.exists() or p.is_symlink()]
    if not presents:
        return None
    AUDIT.mkdir(parents=True, exist_ok=True)
    cible = AUDIT / f"sauvegarde-{stamp}.tar.gz"

    def filtre(ti):
        return None if set(Path(ti.name).parts) & HORS_SAUVEGARDE else ti

    old = os.umask(0o077)
    try:
        with tarfile.open(cible, "w:gz") as tar:
            for p in presents:
                tar.add(str(p), arcname=str(p.relative_to(HOME)), filter=filtre)
    finally:
        os.umask(old)
    return cible


# ------------------------------------------------------------------ migration
def nom_archive(p: Path) -> str:
    try:
        rel = p.relative_to(HOME).as_posix()
    except ValueError:
        rel = p.as_posix().lstrip("/")
    return rel.replace("/", "__")


def migrer(archiver: bool, jours: int) -> dict:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    archive = AUDIT / "archive" / stamp
    journal = {"date": stamp, "gestes": [], "conflits": []}

    def deplacer(src: Path, dst: Path):
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        journal["gestes"].append({"geste": "deplace", "de": str(src), "vers": str(dst)})

    def retirer_lien(lien: Path):
        cible = os.readlink(lien)
        lien.unlink()
        journal["gestes"].append({"geste": "retire_lien", "chemin": str(lien), "cible": cible})

    def lier(lien: Path, cible: Path):
        lien.parent.mkdir(parents=True, exist_ok=True)
        lien.symlink_to(cible)
        journal["gestes"].append({"geste": "lien", "chemin": str(lien), "cible": str(cible)})

    h = historique(jours)
    inv = inventaire(set(h["cwds"]))
    SOURCE.mkdir(parents=True, exist_ok=True)
    par_nom = defaultdict(list)
    for s in inv["skills"]:
        if s["origine"] == "utilisateur":
            par_nom[s["dossier"]].append(s)

    for nom, groupe in sorted(par_nom.items()):
        dans_source = SOURCE / nom
        copies = [s for s in groupe if not s["lien"] and s["lieu"] != "claude"]
        if not copies:
            continue
        if dans_source.is_symlink():
            cible = dans_source.resolve()
            if not dans_source.exists():
                retirer_lien(dans_source)  # lien mort : la place est libre
            elif any(Path(c["reel"]) == cible for c in copies):
                # Sens inverse : la source pointe vers la copie, la copie y entre.
                c = next(c for c in copies if Path(c["reel"]) == cible)
                retirer_lien(dans_source)
                deplacer(Path(c["chemin"]), dans_source)
                lier(Path(c["chemin"]), dans_source)
                copies = [x for x in copies if x is not c]
        if not (dans_source.exists() or dans_source.is_symlink()):
            # Aucune version dans la source : la plus recente y entre, un lien prend sa place.
            gagnante = max(copies, key=lambda s: s["mtime"])
            deplacer(Path(gagnante["chemin"]), dans_source)
            lier(Path(gagnante["chemin"]), dans_source)
            copies = [s for s in copies if s is not gagnante]
        reference = lire_skill(dans_source, "claude")
        for c in copies:
            p = Path(c["chemin"])
            if reference and c["empreinte"] != reference["empreinte"]:
                journal["conflits"].append(
                    {
                        "skill": nom,
                        "garde": str(dans_source),
                        "archivee": str(p),
                        "gagnante": "copie" if c["mtime"] > reference["mtime"] else "source",
                    }
                )
                if c["mtime"] > reference["mtime"]:
                    # Copie plus recente : elle devient la source, l'ancienne est archivee.
                    vraie = dans_source.resolve()
                    deplacer(vraie, archive / "source" / nom)
                    deplacer(p, vraie)
                    lier(p, dans_source)
                    reference = lire_skill(dans_source, "claude")
                    continue
            deplacer(p, archive / c["lieu"] / nom_archive(p))
            lier(p, dans_source)

    if archiver:
        # Dormantes : seulement avec 21 jours d'historique au moins, jamais une skill fournie.
        a = analyser(jours, True)
        if a["skills"]["couverture_jours"] >= 21:
            for nom in a["skills"]["liste_dormantes"]:
                p = SOURCE / nom
                if p.is_dir() and not p.is_symlink():
                    liens = [
                        s
                        for s in inventaire(set()).get("skills")
                        if s["lien"] and s["reel"] == str(p.resolve())
                    ]
                    for s in liens:
                        deplacer(
                            Path(s["chemin"]), archive / "liens" / nom_archive(Path(s["chemin"]))
                        )
                    deplacer(p, archive / "dormantes" / nom)

    if journal["gestes"]:
        AUDIT.mkdir(parents=True, exist_ok=True)
        (AUDIT / f"migration-{stamp}.json").write_text(
            json.dumps(journal, indent=1, ensure_ascii=False)
        )
    return journal


def annuler() -> int:
    journaux = sorted(AUDIT.glob("migration-*.json"))
    if not journaux:
        print("no migration to undo")
        return 1
    f = journaux[-1]
    j = json.loads(f.read_text())
    for g in reversed(j["gestes"]):
        if g["geste"] == "lien":
            p = Path(g["chemin"])
            if p.is_symlink():
                p.unlink()
        elif g["geste"] == "retire_lien":
            p = Path(g["chemin"])
            if not (p.exists() or p.is_symlink()):
                p.symlink_to(g["cible"])
        elif g["geste"] == "deplace":
            src, dst = Path(g["de"]), Path(g["vers"])
            if dst.exists() or dst.is_symlink():
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
    f.rename(f.with_suffix(".annulee"))
    print(T["annule"].format(n=len(j["gestes"]), f=f.name))
    return 0


# ------------------------------------------------------------------ entree
def main() -> int:
    args = sys.argv[1:]
    jours = int(args[args.index("--jours") + 1]) if "--jours" in args else 30
    avec_h = "--sans-historique" not in args
    en_json = "--json" in args

    if "--annuler" in args:
        return annuler()

    if "--migrer" in args:
        j = migrer("--archiver-dormantes" in args, jours)
        print(T["migration"].format(n=len(j["gestes"]), c=len(j["conflits"])))
        for c in j["conflits"][:10]:
            print(T["garde"].format(s=c["skill"], g=c["garde"]))
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    avant_f = AUDIT / "avant.json"
    if "--avant" in args:
        a = analyser(jours, avec_h)
        AUDIT.mkdir(parents=True, exist_ok=True)
        if avant_f.exists():
            # Reinstallation : la premiere photo reste la reference, celle-ci est datee a cote.
            (AUDIT / f"avant-{stamp}.json").write_text(json.dumps(a, indent=1, ensure_ascii=False))
        else:
            avant_f.write_text(json.dumps(a, indent=1, ensure_ascii=False))
        sauvegarde = sauvegarder(stamp)
        print(json.dumps(a, ensure_ascii=False) if en_json else resume(a))
        if sauvegarde:
            print(T["sauvegarde"].format(f=sauvegarde))
        return 0

    av = lire_json(avant_f)
    # Apres : la conso se mesure depuis la photo avant (jamais avant elle).
    depuis = av.get("horodatage") if av else None
    a = analyser(jours, avec_h, depuis)
    if av:
        a["gain"] = comparer(av, a)
        (AUDIT / "apres.json").write_text(json.dumps(a, indent=1, ensure_ascii=False))
    if en_json:
        print(json.dumps(a, ensure_ascii=False))
    else:
        print(resume(a))
        if av:
            print(resume_gain(a["gain"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
