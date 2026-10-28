#!/usr/bin/env python3
"""hk-aiguilleur: pick the skill a message needs BEFORE the model sees it.

Left to choose, a model loads a skill about once in two (Vercel, 01/2026: 53 %,
same as no doc at all; here: 3 loads out of 18 runs, 112 out of 211 trigger hits
in 30 days of Claude Code). The router removes that decision: it reads the
message, picks at most 2 skills, and its injection text carries the SKILL.md
body, so the model has nothing left to decide.

Choice, in this order:
  1. keywords: the regex of declencheurs.json (HK_DECLENCHEURS);
  2. meaning: cosine between the message and each skill's hook and quoted user
     phrases (« ... »), multilingual MiniLM; kept only above a threshold AND
     with a margin over the runner-up. In doubt, nothing is injected: a wrong
     skill costs 4 000 to 15 000 tokens and can lower the score.

  hk-aiguilleur.py choisir "message"           JSON: choice, route, scores
  hk-aiguilleur.py injection "message" [--json] the text a pre_llm_call hook appends
  hk-aiguilleur.py corpus [--jours 60]         labelled history (message -> skill loaded)
  hk-aiguilleur.py eval [--ecrire]             precision / recall, threshold grid search

Meaning needs sentence-transformers (HK_EMBED_PYTHON points to a python that
has it). Without it the router runs on keywords only and says so.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

HOME = Path.home()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", HOME / ".hermes"))
RACINES = [HERMES_HOME / "skills", HOME / ".claude" / "skills"]
DECLENCHEURS = Path(os.environ.get("HK_DECLENCHEURS", HOME / ".claude/outils/declencheurs.json"))
CONFIG = HOME / ".config" / "hermes-kit" / "aiguilleur.json"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "hermes-kit" / "aiguilleur"
PIEGES = Path(__file__).with_name("aiguilleur-pieges.jsonl")
MODELE = os.environ.get(
    "HK_EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
MODELE_CACHE = os.environ.get(
    "HK_EMBED_CACHE", str(HOME / "Bureau/Projets/business/entreprise-a/index/modeles")
)
DEFAUT = {
    "seuil": 0.9,
    "marge": 0.05,
    "z_complement": 4.0,
    "max_skills": 2,
    "max_chars": 9000,
    "min_mots": 3,
}
QUOTE = re.compile(r"«\s*([^«»]{3,120}?)\s*»")
BLOCS = re.compile(
    r"<(memory-context|regles-apprises|system-reminder|task-notification)>.*?</\1>", re.S
)
ENTETE = re.compile(r"^Gateway message origin \(JSON data.*?\n\n", re.S)


# ---------------------------------------------------------------- index


def frontmatter(texte):
    if not texte.startswith("---"):
        return {}, texte
    fin = texte.find("\n---", 3)
    if fin < 0:
        return {}, texte
    tete, corps = texte[3:fin], texte[fin + 4 :].lstrip("\n")
    try:
        import yaml

        meta = yaml.safe_load(tete) or {}
    except Exception:
        meta = {}
        for lg in tete.splitlines():
            k, _, v = lg.partition(":")
            if v and not lg.startswith(" "):
                meta[k.strip()] = v.strip().strip("'\"")
    return (meta if isinstance(meta, dict) else {}), corps


def desactivees():
    """skills.disabled of the Hermes config: Hermes never offers them."""
    noms, dans, dedans = set(), False, False
    try:
        lignes = (HERMES_HOME / "config.yaml").read_text().splitlines()
    except OSError:
        return noms
    for lg in lignes:
        b = lg.strip()
        if not b or b.startswith("#"):
            continue
        if not lg[0].isspace():
            dans, dedans = b == "skills:", False
        elif dans and b == "disabled:":
            dedans = True
        elif dedans and b.startswith("- "):
            noms.add(b[2:].split(" #")[0].strip().strip("'\""))
        else:
            dedans = False
    return noms


def skills():
    """{name: {path, desc, when, body, units}} for every installed skill, first root wins."""
    off, out = desactivees(), {}
    for i, racine in enumerate(RACINES):
        if not racine.exists():
            continue
        # os.walk with followlinks: rglob skips linked folders, and a skill
        # shared from ~/.agents/skills is a link (10 skills were missing,
        # opencli-browser and coffre-identifiants among them, 2026-10-25).
        fichiers = []
        for dossier, sous, noms in os.walk(racine, followlinks=True):
            sous[:] = sorted(
                d
                for d in sous
                if not d.startswith(".") and d not in ("tests", "references", "assets")
            )
            if "SKILL.md" in noms:
                fichiers.append(Path(dossier) / "SKILL.md")
        for f in sorted(fichiers):
            try:
                meta, corps = frontmatter(f.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            nom = str(meta.get("name") or f.parent.name)
            if nom in out or (i == 0 and nom in off):
                continue
            desc = " ".join(str(meta.get("description") or "").split())
            when = " ".join(str(meta.get("when_to_use") or "").split())
            if not desc:
                continue
            accroche = re.split(r"(?<=[.!?])\s", desc, maxsplit=1)[0]
            units = [accroche, desc[:300]] + [
                q for q in QUOTE.findall(desc + " " + when) if len(q.split()) >= 2
            ]
            out[nom] = {
                "path": str(f.parent.resolve()),
                "desc": desc,
                "when": when,
                "body": corps,
                "units": list(dict.fromkeys(units)),
            }
    return out


# ---------------------------------------------------------------- meaning

_modele = None


def modele():
    global _modele
    if _modele is None:
        if Path(MODELE_CACHE, "hub").exists() or any(Path(MODELE_CACHE).glob("models--*")):
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("HF_HOME", MODELE_CACHE)
        from sentence_transformers import SentenceTransformer

        _modele = SentenceTransformer(MODELE, device="cpu", cache_folder=MODELE_CACHE)
    return _modele


def sens_dispo():
    try:
        import sentence_transformers  # noqa: F401

        return True
    except Exception:
        return False


def encoder(textes):
    import numpy as np

    v = modele().encode(textes, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(v, dtype="float32")


class Index:
    def __init__(self):
        self.skills = skills()
        self.noms, self.units = [], []
        for n, s in self.skills.items():
            for u in s["units"]:
                self.noms.append(n)
                self.units.append(u)
        self.vec = None
        if sens_dispo():
            import numpy as np

            cle = hashlib.sha1(
                json.dumps([MODELE, self.noms, self.units]).encode(), usedforsecurity=False
            ).hexdigest()[:16]
            f = CACHE / f"index-{cle}.npy"
            if f.exists():
                self.vec = np.load(f)
            else:
                self.vec = encoder(self.units)
                CACHE.mkdir(parents=True, exist_ok=True)
                for vieux in CACHE.glob("index-*.npy"):
                    vieux.unlink()
                np.save(f, self.vec)
        try:
            table = json.loads(DECLENCHEURS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            table = {}
        self.motifs = {
            n: [re.compile(m, re.I) for m in r.get("motifs", [])]
            for n, r in table.items()
            if not n.startswith("_") and n in self.skills
        }

    def scores(self, texte):
        """{skill: best cosine over its units}."""
        if self.vec is None:
            return {}
        q = encoder([texte])[0]
        sims = self.vec @ q
        best = {}
        for n, s in zip(self.noms, sims.tolist(), strict=True):
            if s > best.get(n, -1):
                best[n] = s
        return best


def nettoyer(texte):
    if not isinstance(texte, str):
        texte = (
            " ".join(b.get("text", "") for b in texte if isinstance(b, dict))
            if isinstance(texte, list)
            else str(texte)
        )
    texte = ENTETE.sub("", texte)
    texte = BLOCS.sub(" ", texte)
    texte = re.split(r"\n\[System:|\n\[(?:OUT-OF-BAND|Note: model)", texte, maxsplit=1)[0]
    texte = re.sub(r"^\s*\[[^\]\n]{1,40}\]\s*", "", texte)  # "[Vin] " sender prefix
    return texte.strip()


def config():
    c = dict(DEFAUT)
    with contextlib.suppress(OSError, ValueError):
        c.update(json.loads(CONFIG.read_text()))
    return c


def decider(hits, top, z, mots, conf):
    """The rule, shared by choisir and eval.

    Keywords win. Meaning may add the skill it ranks first as the 2nd one when
    its peak stands out (z-score over all skills >= z_complement): measured on
    the bench, that fixes a mail task whose keywords only named entreprise-a-index.
    Meaning alone needs top1 >= seuil and a margin; with MiniLM it stays off
    (seuil 0.9): a trap like "Oui" scores 0.89 and z 3.9, a real task 0.65.
    """
    if hits:
        ch = list(hits)
        if top and top[0][0] not in ch and z >= conf["z_complement"]:
            ch = [ch[0], top[0][0]]
        return ch[: conf["max_skills"]]
    if mots < conf["min_mots"] or not top:
        return []
    s1, s2 = top[0][1], (top[1][1] if len(top) > 1 else 0.0)
    return [top[0][0]] if s1 >= conf["seuil"] and s1 - s2 >= conf["marge"] else []


def profil(idx, texte):
    """(hits, top3, z) of a cleaned message."""
    sc = idx.scores(texte)
    top = [[n, round(v, 4)] for n, v in sorted(sc.items(), key=lambda kv: -kv[1])[:3]]
    z = 0.0
    if sc:
        import numpy as np

        v = np.array(list(sc.values()))
        z = float((top[0][1] - v.mean()) / (v.std() + 1e-6))
    hits = sorted(
        [n for n, ms in idx.motifs.items() if any(m.search(texte) for m in ms)],
        key=lambda n: -sc.get(n, 0),
    )
    return hits, top, round(z, 2)


def choisir(idx, message, conf=None):
    conf = conf or config()
    texte = nettoyer(message)
    res = {"message": texte[:200], "choix": [], "voie": None, "sens": idx.vec is not None}
    if not texte:
        return res
    hits, top, z = profil(idx, texte)
    res.update(top=top, z=z, mots_cles=hits)
    res["choix"] = decider(hits, top, z, len(texte.split()), conf)
    if res["choix"]:
        res["voie"] = "mots" if hits and res["choix"][0] in hits else "sens"
        if hits and len(res["choix"]) > 1 and res["choix"][1] not in hits:
            res["voie"] = "mots+sens"
    return res


def injection(idx, res, racine_vue=None, conf=None):
    """Text appended to the user message: the SKILL.md bodies, already loaded."""
    conf = conf or config()
    morceaux, budget = [], conf["max_chars"]
    # A companion (USER's rules for a third-party skill) keeps its room: the long
    # third-party body would otherwise eat the whole budget and drop it.
    reserve = {
        n: min(len(idx.skills[n]["body"].strip()), conf["max_chars"] * 2 // 3)
        for n in res["choix"]
        if n in COMPAGNES.values() and n in idx.skills
    }
    for n in res["choix"]:
        s = idx.skills[n]
        corps = s["body"].strip()
        dispo = reserve.pop(n, None)
        if dispo is None:
            dispo = max(0, budget - sum(reserve.values()))
        coupe = len(corps) > dispo
        corps = corps[:dispo] + (
            f"\n\n[... truncated: skill_view(name='{n}') for the rest]" if coupe else ""
        )
        budget = max(0, budget - len(corps))
        lieu = f"{racine_vue}/{n}" if racine_vue else s["path"]
        morceaux.append(
            f"[Skill router: the skill '{n}' matches this message (route: {res['voie']}). "
            f"Its SKILL.md is below, already loaded: follow it, no skill_view needed. "
            f"Its other files (references/, scripts/) are in {lieu}. "
            f"If it does not apply to this message, ignore it.]\n\n{corps}"
        )
        if not budget:
            break
    return "\n\n".join(morceaux)


# ---------------------------------------------------------------- corpus


def corpus_hermes(depuis):
    out = []
    db = HERMES_HOME / "state.db"
    if not db.exists():
        return out
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    lignes = c.execute(
        """select m.session_id, m.id, m.tool_calls from messages m join sessions s on
        s.id=m.session_id
                          where m.role='assistant' and m.tool_calls like '%skill_view%' and
                          m.timestamp > ?
                          and s.source in ('telegram','api_server')""",
        (depuis,),
    ).fetchall()
    for sid, mid, tc in lignes:
        try:
            noms = [
                json.loads((t.get("function") or {}).get("arguments") or "{}").get("name", "")
                for t in json.loads(tc)
                if (t.get("function") or {}).get("name") == "skill_view"
            ]
        except (ValueError, TypeError, AttributeError):
            continue
        u = c.execute(
            "select content from messages where session_id=? and id<? and role='user' order by "
            "id desc limit 1",
            (sid, mid),
        ).fetchone()
        if u and u[0]:
            for n in noms:
                out.append((u[0], n.split("/")[-1], "hermes"))
    return out


def corpus_claude(depuis):
    out = []
    for f in (HOME / ".claude" / "projects").glob("*/*.jsonl"):
        if f.stat().st_mtime < depuis:
            continue
        brut = f.read_bytes()
        if b'"Skill"' not in brut:
            continue
        dernier, vu = None, set()
        for lg in brut.splitlines():
            try:
                d = json.loads(lg)
            except ValueError:
                continue
            if d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary"):
                continue
            msg = d.get("message") if isinstance(d.get("message"), dict) else {}
            contenu = msg.get("content")
            if d.get("type") == "user" and d.get("promptSource") != "system":
                textes = (
                    [contenu]
                    if isinstance(contenu, str)
                    else [
                        b.get("text", "")
                        for b in contenu or []
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                )
                textes = [
                    t
                    for t in textes
                    if t
                    and not t.startswith(
                        (
                            "This session is being continued",
                            "<command",
                            "<task-notification",
                            "Base directory for this skill",
                        )
                    )
                ]
                if textes:
                    dernier, vu = textes[0], set()
            elif d.get("type") == "assistant" and dernier and isinstance(contenu, list):
                for b in contenu:
                    if (
                        isinstance(b, dict)
                        and b.get("type") == "tool_use"
                        and b.get("name") == "Skill"
                    ):
                        n = (
                            str((b.get("input") or {}).get("skill") or "")
                            .split(":")[-1]
                            .split("/")[-1]
                        )
                        if n and n not in vu:
                            vu.add(n)
                            out.append((dernier, n, "claude"))
    return out


def faire_corpus(jours):
    depuis = time.time() - jours * 86400
    noms = set(skills())
    lignes, vus = [], set()
    for brut, n, src in corpus_hermes(depuis) + corpus_claude(depuis):
        t = nettoyer(brut)
        if n not in noms or not t or len(t) > 1500 or (t, n) in vus:
            continue
        vus.add((t, n))
        lignes.append({"message": t, "skill": n, "source": src})
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / "corpus.jsonl"
    f.write_text(
        "".join(json.dumps(lg, ensure_ascii=False) + "\n" for lg in lignes), encoding="utf-8"
    )
    par = {}
    for lg in lignes:
        par[lg["skill"]] = par.get(lg["skill"], 0) + 1
    print(f"{len(lignes)} pairs (message -> skill loaded) over {jours} days: {f}")
    print("  " + " · ".join(f"{n} {k}" for n, k in sorted(par.items(), key=lambda kv: -kv[1])[:15]))


# ---------------------------------------------------------------- eval


def jeux(idx):
    """positives: bench tasks + history; negatives: traps (must choose nothing)."""
    pos = []
    for n, s in idx.skills.items():
        f = Path(s["path"]) / "tests" / "taches.jsonl"
        if f.exists():
            for lg in f.read_text(encoding="utf-8").splitlines():
                if lg.strip():
                    pos.append({"message": json.loads(lg)["consigne"], "skill": n, "jeu": "banc"})
    f = CACHE / "corpus.jsonl"
    if f.exists():
        pos += [
            dict(json.loads(lg), jeu="histo")
            for lg in f.read_text(encoding="utf-8").splitlines()
            if lg.strip()
        ]
    neg = (
        [
            dict(json.loads(lg), jeu="piege")
            for lg in PIEGES.read_text(encoding="utf-8").splitlines()
            if lg.strip()
        ]
        if PIEGES.exists()
        else []
    )
    return pos, neg


def mesurer(pos_res, neg_res, conf):
    """Counts with a given threshold, from cached profiles (no re-encoding)."""

    def decide(r):
        return decider(r["hits"], r["top"], r["z"], r["mots"], conf)

    m = {}
    for jeu in ("banc", "histo"):
        rs = [r for r in pos_res if r["jeu"] == jeu]
        bon = sum(r["skill"] in decide(r) for r in rs)
        rien = sum(not decide(r) for r in rs)
        m[jeu] = {"n": len(rs), "bon": bon, "faux": len(rs) - bon - rien, "rien": rien}
    m["piege"] = {"n": len(neg_res), "injecte": sum(bool(decide(r)) for r in neg_res)}
    return m


def evaluer(a):
    idx = Index()
    if idx.vec is None:
        sys.exit(
            "meaning unavailable: run with HK_EMBED_PYTHON (a python with sentence-transformers)"
        )
    pos, neg = jeux(idx)

    def brut(e):
        t = nettoyer(e["message"])
        hits, top, z = profil(idx, t)
        return {**e, "top": top, "hits": hits, "z": z, "mots": len(t.split())}

    t0 = time.time()
    pos_res, neg_res = [brut(e) for e in pos], [brut(e) for e in neg]
    print(
        f"{len(idx.skills)} skills, {len(idx.units)} units indexed · {len(pos_res)} positives, "
        f"{len(neg_res)} traps · scored in {time.time() - t0:.1f} s"
    )
    grille = []
    for seuil in [x / 100 for x in range(50, 92, 2)]:
        for marge in (0.0, 0.04, 0.08):
            for zc in (3.5, 4.0, 4.5, 5.0, 99):
                conf = {**DEFAUT, "seuil": seuil, "marge": marge, "z_complement": zc}
                m = mesurer(pos_res, neg_res, conf)
                h = m["histo"]
                # a trap that injects costs 3, a wrong skill 2, a right one gains 1
                val = (
                    (h["bon"] + m["banc"]["bon"])
                    - 2 * (h["faux"] + m["banc"]["faux"])
                    - 3 * m["piege"]["injecte"]
                )
                grille.append((val, seuil, marge, zc, m))
    grille.sort(key=lambda g: (-g[0], -g[1], -g[3]))
    print("\nbest thresholds (value = right - 2 x wrong - 3 x trap)")
    for val, seuil, marge, zc, m in grille[:5]:
        print(
            f"  seuil {seuil:.2f} marge {marge:.2f} z {zc} · value {val} · banc {m['banc']} · "
            f"histo {m['histo']} · traps {m['piege']}"
        )
    mots = mesurer(pos_res, neg_res, {**DEFAUT, "seuil": 9, "marge": 9, "z_complement": 99})
    print(f"\nkeywords only: banc {mots['banc']} · histo {mots['histo']} · traps {mots['piege']}")
    val, seuil, marge, zc, m = grille[0]
    conf = {**DEFAUT, "seuil": seuil, "marge": marge, "z_complement": zc}
    print("\nbench tasks with the best thresholds:")
    for r in pos_res:
        if r["jeu"] == "banc":
            d = mesurer([r], [], conf)["banc"]
            print(
                f"  {r['skill']:<22} "
                f"{'RIGHT' if d['bon'] else 'nothing' if d['rien'] else 'WRONG'} "
                f"· top {r['top'][0]} z {r['z']} · keywords {r['hits'] or '-'}"
            )
    print("\ntraps:")
    for r in neg_res:
        d = mesurer([], [r], conf)["piege"]["injecte"]
        print(
            f"  {'INJECTS' if d else 'ok':<8} {r['message'][:60]!r} · top {r['top'][0]} · "
            f"keywords {r['hits'] or '-'}"
        )
    if a.ecrire:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(
            json.dumps(
                {
                    "seuil": seuil,
                    "marge": marge,
                    "z_complement": zc,
                    "date": dt.date.today().isoformat(),
                    "mesure": m,
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n"
        )
        print(f"\nwritten: {CONFIG}")
    if a.detail:
        f = CACHE / "eval-detail.jsonl"
        f.write_text(
            "".join(
                json.dumps(
                    {**r, "choix": decider(r["hits"], r["top"], r["z"], r["mots"], conf)},
                    ensure_ascii=False,
                )
                + "\n"
                for r in pos_res + neg_res
            ),
            encoding="utf-8",
        )
        print(f"detail: {f}")


# ---------------------------------------------------------------- model router

LLM_URL = os.environ.get("HK_LLM_URL", "http://localhost:8000/anthropic/v1/messages")
LLM_MODELE = os.environ.get("HK_LLM_MODEL", "claude-sonnet-5-5")
LLM_CLE = os.environ.get("HK_LLM_KEY", "x")
# Name given to the proxy (proxy-usage.jsonl "appelant"): one per caller, so each is measured.
LLM_APPELANT = os.environ.get("HK_LLM_APPELANT", "hk-aiguilleur")
CONSIGNE_LLM = (
    "You route user messages to skills. A skill is a playbook the assistant loads before working.\n"
    "For each numbered message, return the skills (at most 2, best first) that the assistant "
    "should load "
    "to do what the message asks. Return an empty list when no skill clearly applies: small "
    "talk, thanks, "
    "a bare yes/no or 'continue', a plain system command (install, restart, disk space), "
    "arithmetic, "
    "a translation, or a question any assistant answers without a playbook. A wrong skill costs "
    "more "
    "than no skill.\n"
    "charte-ux (USER's interface rules) goes with any work on a screen, page, button, menu or "
    "layout, "
    "even when another skill is picked first.\n"
    "A message may come after the end of the assistant's previous reply, marked CONTEXT. Use it "
    "only to "
    "understand what a short message (yes, go, test it) refers to, then route the user's "
    "message: the skill "
    "that the assistant needs to do what the user now asks, in that context.\n"
    'Answer with JSON only, no prose: {"1": ["skill-name"], "2": [], ...}\n\nSKILLS\n'
)


# What the router reads of each skill. Until 2026-10-25 the description was cut at 220
# characters: 63 of 217 were truncated, the "Not for" line (22 skills) and the
# when_to_use phrases (19 skills) were never seen.
CATALOGUE_DESC, CATALOGUE_WHEN = 600, 400


# Skills kept out of the router's catalogue: installed, still loadable by hand, but never
# offered. One name per line. On 2026-10-25, 125 of 217 skills (imported, English,
# never loaded in 90 days) sat next to the used ones and stole their choice.
HORS_CATALOGUE = Path(
    os.environ.get("HK_HORS_CATALOGUE", CONFIG.with_name("aiguilleur-hors-catalogue.txt"))
)


def hors_catalogue():
    try:
        return {
            lg.strip()
            for lg in HORS_CATALOGUE.read_text().splitlines()
            if lg.strip() and not lg.startswith("#")
        }
    except OSError:
        return set()


def catalogue(idx, desc_max=None, when_max=None, exclu=None):
    """Stable skill list, same order every call, so the prefix stays cacheable."""
    d = CATALOGUE_DESC if desc_max is None else desc_max
    w = CATALOGUE_WHEN if when_max is None else when_max
    x = hors_catalogue() if exclu is None else exclu
    return "\n".join(
        f"- {n}: {s['desc'][:d]}" + (f" When: {s['when'][:w]}" if w and s.get("when") else "")
        for n, s in sorted(idx.skills.items())
        if n not in x
    )


# A skill that must come with another one, whatever the model picked (a third slot
# is allowed for it). opencli-browser is a third-party package, USER's rules sit in
# opencli-browser-poste; on the bench the pair was split 2 times out of 2.
COMPAGNES = {"opencli-browser": "opencli-browser-poste"}


def avec_compagnes(choix, connus):
    out = list(choix)
    parents = {v: k for k, v in COMPAGNES.items()}
    for c in choix:
        k = COMPAGNES.get(c)
        if k and k in connus and k not in out:
            out.append(k)
        # A companion never comes alone ("jamais seule" in its own text): its parent
        # goes in front of it (bench 2026-10-25: "essaye sur seller central" got the
        # rules without the opencli-browser commands).
        p = parents.get(c)
        if p and p in connus and p not in out:
            out.insert(out.index(c), p)
    return out


CONTEXTE_CHARS = 300


def requete(texte, precedent=""):
    """User content sent to the router: the message, after the end of the previous reply if any."""
    precedent = " ".join((precedent or "").split())[-CONTEXTE_CHARS:]
    tete = (
        f"CONTEXT (end of the assistant's previous reply): ...{precedent}\n\n" if precedent else ""
    )
    return f"{tete}1. {texte[:600]}"


def appel_llm(systeme, texte, max_tokens=1200, timeout=300):
    import urllib.request

    corps = json.dumps(
        {
            "model": LLM_MODELE,
            "max_tokens": max_tokens,
            "system": systeme,
            "metadata": {"user_id": f"systemd:{LLM_APPELANT}"},
            "messages": [{"role": "user", "content": texte}],
        }
    ).encode()
    req = urllib.request.Request(  # noqa: S310 (LLM_URL : proxy local ou https de la config)
        LLM_URL,
        corps,
        {
            "content-type": "application/json",
            "x-api-key": LLM_CLE,
            "anthropic-version": "2023-06-01",
        },
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (meme URL que plus haut)
        rep = json.loads(r.read())
    txt = "".join(b.get("text", "") for b in rep.get("content", []) if b.get("type") == "text")
    return txt, rep.get("usage", {}), time.time() - t0


def lire_choix(txt, n, connus):
    """Last JSON object of the answer that has numbered keys (models may add prose or fences "
    "around it)."""
    dec, d = json.JSONDecoder(), {}
    for i, c in enumerate(txt):
        if c != "{":
            continue
        try:
            o, _ = dec.raw_decode(txt[i:])
        except ValueError:
            continue
        if isinstance(o, dict) and any(str(k).isdigit() for k in o):
            d = o
    return [
        avec_compagnes([k for k in (d.get(str(i + 1)) or []) if k in connus][:2], connus)
        for i in range(n)
    ]


def choisir_llm(idx, messages, lot=10, travailleurs=4):
    """[{choix, ms}] per message, answers cached by (model, catalogue, message)."""
    from concurrent.futures import ThreadPoolExecutor

    systeme = CONSIGNE_LLM + catalogue(idx)
    cle = hashlib.sha1((LLM_MODELE + systeme).encode(), usedforsecurity=False).hexdigest()[:12]
    fcache = CACHE / f"llm-{cle}.jsonl"
    vu = {}
    if fcache.exists():
        for lg in fcache.read_text(encoding="utf-8").splitlines():
            if lg.strip():
                e = json.loads(lg)
                vu[e["message"]] = e
    textes = [nettoyer(m)[:600] for m in messages]
    a_faire = list(dict.fromkeys(t for t in textes if t and t not in vu))
    lots = [a_faire[i : i + lot] for i in range(0, len(a_faire), lot)]
    stats = {"appels": 0, "entree": 0, "sortie": 0, "s": []}

    def un_lot(ts):
        corps = "\n\n".join(f"[{i + 1}] {t}" for i, t in enumerate(ts))
        for _essai in range(3):
            try:
                txt, us, s = appel_llm(systeme, corps)
                return ts, lire_choix(txt, len(ts), idx.skills), us, s
            except Exception as e:  # network or proxy hiccup: retry, then give up on this batch
                err = e
                time.sleep(5)
        print(f"  batch failed: {err}", file=sys.stderr)
        return ts, None, {}, 0

    with ThreadPoolExecutor(travailleurs) as ex, fcache.open("a", encoding="utf-8") as out:
        for k, (ts, ch, us, s) in enumerate(ex.map(un_lot, lots)):
            if ch is None:
                continue
            stats["appels"] += 1
            stats["entree"] += us.get("input_tokens", 0) + us.get("cache_read_input_tokens", 0)
            stats["sortie"] += us.get("output_tokens", 0)
            stats["s"].append(s)
            for t, c in zip(ts, ch, strict=False):
                vu[t] = {"message": t, "choix": c, "ms": round(s * 1000 / len(ts))}
                out.write(json.dumps(vu[t], ensure_ascii=False) + "\n")
            print(f"  batch {k + 1}/{len(lots)} · {s:.1f} s", file=sys.stderr)
    return [vu.get(t, {"choix": []})["choix"] if t else [] for t in textes], stats


def compter(rows, choix_de):
    m = {}
    for jeu in ("banc", "histo"):
        rs = [r for r in rows if r["jeu"] == jeu]
        bon = sum(r["skill"] in choix_de(r) for r in rs)
        rien = sum(not choix_de(r) for r in rs)
        m[jeu] = {"n": len(rs), "bon": bon, "faux": len(rs) - bon - rien, "rien": rien}
    pg = [r for r in rows if r["jeu"] == "piege"]
    m["piege"] = {"n": len(pg), "injecte": sum(bool(choix_de(r)) for r in pg)}
    return m


def evaluer_llm(a):
    idx = Index()
    pos, neg = jeux(idx)
    rows = pos + neg
    t0 = time.time()
    choix, st = choisir_llm(idx, [r["message"] for r in rows], a.lot, a.travailleurs)
    for r, c in zip(rows, choix, strict=False):
        t = nettoyer(r["message"])
        r["llm"] = c
        r["hits"] = sorted(n for n, ms in idx.motifs.items() if any(m.search(t) for m in ms))[:2]
    print(
        f"model {LLM_MODELE} · {len(rows)} messages · {time.time() - t0:.0f} s · "
        f"{st['appels']} new calls, tokens in {st['entree']} out {st['sortie']}"
    )
    if st["s"]:
        print(
            f"  per call: median {sorted(st['s'])[len(st['s']) // 2]:.1f} s for a batch of {a.lot}"
        )
    voies = {
        "keywords": lambda r: r["hits"],
        "model": lambda r: r["llm"],
        "keywords, else model": lambda r: r["hits"] or r["llm"],
        "keywords where model agrees": lambda r: (
            [h for h in r["hits"] if h in r["llm"]] or r["llm"]
        ),
    }
    for nom, f in voies.items():
        m = compter(rows, f)
        val = (
            sum(m[j]["bon"] - 2 * m[j]["faux"] for j in ("banc", "histo"))
            - 3 * m["piege"]["injecte"]
        )
        print(
            f"\n{nom}: value {val}\n  banc {m['banc']}\n  histo {m['histo']}\n  traps {m['piege']}"
        )
    print("\nbench tasks:")
    for r in rows:
        if r["jeu"] == "banc":
            print(f"  {r['skill']:<22} model {r['llm'] or '-'} · keywords {r['hits'] or '-'}")
    print(
        "traps the model routes:",
        [(r["message"][:40], r["llm"]) for r in neg if r["llm"]] or "none",
    )
    f = CACHE / "eval-llm-detail.jsonl"
    f.write_text(
        "".join(
            json.dumps(
                {k: r[k] for k in ("message", "skill", "jeu", "llm", "hits") if k in r},
                ensure_ascii=False,
            )
            + "\n"
            for r in rows
        ),
        encoding="utf-8",
    )
    print(f"detail: {f}")
    if a.latence:
        print(f"\nlatency, {a.latence} single-message calls:")
        ds = []
        systeme = CONSIGNE_LLM + catalogue(idx)
        for r in pos[:: max(1, len(pos) // a.latence)][: a.latence]:
            _, us, s = appel_llm(systeme, "[1] " + nettoyer(r["message"])[:600], 200)
            ds.append(s)
            print(f"  {s:.1f} s · in {us.get('input_tokens', 0)} out {us.get('output_tokens', 0)}")
        ds.sort()
        print(f"  median {ds[len(ds) // 2]:.1f} s, max {ds[-1]:.1f} s")


def juger(a):
    """Blind second opinion on every disagreement with the history label: which skill fits the "
    "message?"""
    import random
    from concurrent.futures import ThreadPoolExecutor

    idx = Index()
    f = CACHE / "eval-llm-detail.jsonl"
    rows = [json.loads(lg) for lg in f.read_text(encoding="utf-8").splitlines() if lg.strip()]
    cas = {}
    for r in rows:
        if r["jeu"] != "histo":
            continue
        for voie in ("llm", "hits"):
            if r[voie] and r["skill"] not in r[voie] and r["skill"] in idx.skills:
                cas.setdefault((r["message"], r["skill"], r[voie][0]), []).append(voie)
    rnd = random.Random(7)  # noqa: S311 (tirage d'echantillon reproductible, pas de crypto)
    items = []
    for (msg, lab, alt), voies in cas.items():
        a_, b_ = (lab, alt) if rnd.random() < 0.5 else (alt, lab)
        items.append({"message": msg, "label": lab, "alt": alt, "voies": voies, "A": a_, "B": b_})
    systeme = (
        "You judge skill routing. Given a user message and two skills, say which skill an expert "
        "assistant should load to do what the message asks. Answer one word: A, B, BOTH (both fit "
        "equally) or NEITHER (the message alone does not call for either)."
    )

    def un(it):
        q = (
            f"Message: {it['message'][:600]}\n\nA = {it['A']}: "
            f"{idx.skills[it['A']]['desc'][:400]}\n\n"
            f"B = {it['B']}: {idx.skills[it['B']]['desc'][:400]}"
        )
        try:
            txt, _, _ = appel_llm(systeme, q, 20)
        except Exception as e:
            return it, f"ERR {e}"
        m = re.search(r"\b(BOTH|NEITHER|A|B)\b", txt.upper())
        return it, m.group(1) if m else "?"

    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(un, items))
    tally = {}
    for it, v in res:
        verdict = (
            {"BOTH": "both", "NEITHER": "neither"}.get(v)
            or ("label" if it[v] == it["label"] else "router")
            if v in ("A", "B", "BOTH", "NEITHER")
            else "error"
        )
        it["verdict"] = verdict
        for voie in it["voies"]:
            tally.setdefault(voie, {}).setdefault(verdict, 0)
            tally[voie][verdict] += 1
    print(f"judge {LLM_MODELE} · {len(items)} disagreements")
    for voie, t in tally.items():
        print(f"  {'model' if voie == 'llm' else 'keywords'}: {t}")
    (CACHE / "juge-detail.jsonl").write_text(
        "".join(json.dumps(it, ensure_ascii=False) + "\n" for it, _ in res), encoding="utf-8"
    )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("choisir", "injection"):
        p = sub.add_parser(c)
        p.add_argument("message")
        p.add_argument("--json", action="store_true")
        p.add_argument("--racine-vue", help="where the injected skills will live (bench sandbox)")
    p = sub.add_parser("corpus")
    p.add_argument("--jours", type=int, default=60)
    p = sub.add_parser("eval")
    p.add_argument("--ecrire", action="store_true", help="save the best thresholds to the config")
    p.add_argument("--detail", action="store_true")
    p = sub.add_parser("eval-llm", help="same sets, routed by a model through HK_LLM_URL")
    p.add_argument("--lot", type=int, default=10)
    p.add_argument("--travailleurs", type=int, default=4)
    p.add_argument("--latence", type=int, default=0, help="also time N single-message calls")
    sub.add_parser("juger", help="blind judge on disagreements of eval-llm (set HK_LLM_MODEL)")
    a = ap.parse_args()
    if a.cmd == "juger":
        return juger(a)
    if a.cmd == "eval-llm":
        return evaluer_llm(a)
    if a.cmd == "corpus":
        return faire_corpus(a.jours)
    if a.cmd == "eval":
        return evaluer(a)
    idx = Index()
    res = choisir(idx, a.message)
    if a.cmd == "choisir":
        print(json.dumps(res, ensure_ascii=False, indent=None if a.json else 1))
        return
    texte = injection(idx, res, a.racine_vue)
    if a.json:
        print(
            json.dumps(
                {
                    **res,
                    "injection": texte,
                    "chemins": {n: idx.skills[n]["path"] for n in res["choix"]},
                },
                ensure_ascii=False,
            )
        )
    else:
        print(texte)


if __name__ == "__main__":
    main()
