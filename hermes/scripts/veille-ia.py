#!/usr/bin/env python3
"""Veille IA et GitHub pour le topic Coach du QG.

Script de pre-run d'un job cron Hermes. Il collecte les nouveautes, les compare
a ce qui a deja ete vu, et decide s'il y a de quoi reveiller l'agent :

- rien de marquant : derniere ligne {"wakeAgent": false}, aucun message ;
- au moins 2 signaux forts (et pas d'envoi depuis 20 h) : resume envoye ;
- sinon, resume de fond tous les 3 jours et demi s'il y a au moins 5 elements.

Options : --forcer (envoie quoi qu'il arrive), --sec (n'ecrit pas l'etat).
Sources sans cle : Hacker News (Algolia), GitHub (gh api), Hugging Face
(modeles tendance, papiers du jour), releases de Claude Code et d'Hermes.
Reddit : l'astuce `.json` repond 403 depuis hote-1 et le Pi (verifie le
2026-09-25). On passe donc par opencli, qui lit Reddit dans le Chrome de hote-1.
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ETAT = Path.home() / ".local" / "state" / "veille-ia" / "etat.json"
UA = {"User-Agent": "veille-poste/1.0"}
MOTS_IA = re.compile(
    r"\b(ai|llm|llms|gpt|claude|anthropic|openai|gemini|deepseek|qwen|llama|mistral|"
    r"agent|agents|agentic|model|models|transformer|diffusion|mcp|rag|inference|"
    r"fine-?tun\w*|open.?weights?|copilot|cursor|codex|embedding\w*|neural|"
    r"reasoning|benchmark|gpu|cuda|whisper|tts|voice)\b", re.I)
OPENCLI = str(Path.home() / ".local" / "bin" / "opencli")
SUBREDDITS = ["LocalLLaMA", "ClaudeAI", "MachineLearning"]
RELEASES = ["anthropics/claude-code", "NousResearch/hermes-agent"]
GARDE_JOURS = 7          # un element non envoye expire apres 7 jours
FORT_MIN = 2             # signaux forts pour un envoi immediat
DELAI_FORT_H = 20        # 1 envoi immediat par jour au plus
DELAI_FOND_H = 84        # resume de fond tous les 3,5 jours
FOND_MIN = 5


def http_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def gh_json(*args):
    out = subprocess.run(["gh", "api", "-X", "GET", *args], capture_output=True,
                         text=True, timeout=40)
    if out.returncode:
        raise RuntimeError(out.stderr.strip()[:200])
    return json.loads(out.stdout)


def hacker_news():
    depuis = int(time.time()) - 3 * 86400
    d = http_json("https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=60"
                  f"&numericFilters=created_at_i>{depuis},points>150")
    for h in d.get("hits", []):
        titre = h.get("title") or ""
        if not MOTS_IA.search(titre):
            continue
        pts = h.get("points") or 0
        yield {"id": f"hn:{h['objectID']}", "source": "Hacker News", "titre": titre,
               "score": pts, "unite": "points", "fort": pts >= 400,
               "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
               "discussion": f"https://news.ycombinator.com/item?id={h['objectID']}",
               "desc": f"{h.get('num_comments') or 0} commentaires"}


def github_nouveaux():
    debut = (date.today() - timedelta(days=10)).isoformat()
    d = gh_json("search/repositories", "-f", f"q=created:>{debut} stars:>500",
                "-f", "sort=stars", "-f", "per_page=25")
    for r in d.get("items", []):
        s = r["stargazers_count"]
        yield {"id": f"gh:{r['full_name']}", "source": "GitHub (nouveau dépôt)",
               "titre": r["full_name"], "score": s, "unite": "étoiles",
               "fort": s >= 3000, "url": r["html_url"],
               "desc": (r.get("description") or "")[:220]
                       + (f" · {r['language']}" if r.get("language") else "")}


def hf_modeles():
    d = http_json("https://huggingface.co/api/models?sort=trendingScore&limit=12")
    for rang, m in enumerate(d, 1):
        tags = [t for t in m.get("tags", []) if ":" not in t][:6]
        yield {"id": f"hf:{m['id']}", "source": "Hugging Face (modèle tendance)",
               "titre": m["id"], "score": m.get("likes", 0), "unite": "likes",
               "fort": rang <= 3 and m.get("likes", 0) >= 500,
               "url": f"https://huggingface.co/{m['id']}",
               "desc": f"rang {rang} · {m.get('pipeline_tag') or ''} · {', '.join(tags)}"}


def hf_papiers():
    d = http_json("https://huggingface.co/api/daily_papers?limit=30")
    for p in d:
        pp = p.get("paper", {})
        up = pp.get("upvotes", 0)
        if up < 40:
            continue
        yield {"id": f"paper:{pp['id']}", "source": "Papier de recherche",
               "titre": pp.get("title", ""), "score": up, "unite": "votes",
               "fort": up >= 150, "url": f"https://huggingface.co/papers/{pp['id']}",
               "desc": re.sub(r"\s+", " ", pp.get("summary", ""))[:260]}


def reddit():
    for sub in SUBREDDITS:
        out = subprocess.run([OPENCLI, "reddit", "subreddit", sub, "--sort", "top",
                              "--time", "day", "--limit", "10", "-f", "json",
                              "--window", "background"],
                             capture_output=True, text=True, timeout=90)
        for p in json.loads(out.stdout):
            up = p.get("upvotes") or 0
            if up < 200:
                continue
            yield {"id": f"reddit:{p['id']}", "source": f"Reddit {p.get('subreddit', sub)}",
                   "titre": p.get("title", ""), "score": up, "unite": "votes",
                   "fort": up >= 800, "url": p.get("url", ""),
                   "desc": f"{p.get('comments', 0)} commentaires · "
                           + re.sub(r"\s+", " ", p.get("selftext") or "")[:200]}


def releases():
    for depot in RELEASES:
        r = gh_json(f"repos/{depot}/releases/latest")
        corps = re.sub(r"\s+", " ", r.get("body") or "")[:400]
        yield {"id": f"rel:{depot}:{r['tag_name']}", "source": "Mise à jour d'un outil que tu utilises",
               "titre": f"{depot} {r['tag_name']}", "score": 0, "unite": "",
               "fort": False, "url": r["html_url"], "desc": corps}


def collecter():
    items, erreurs = [], []
    for f in (hacker_news, github_nouveaux, hf_modeles, hf_papiers, reddit, releases):
        try:
            items.extend(f())
        except Exception as e:  # une source en panne ne bloque pas les autres
            erreurs.append(f"{f.__name__}: {e}")
    return items, erreurs


def main():
    forcer, sec = "--forcer" in sys.argv, "--sec" in sys.argv
    etat = json.loads(ETAT.read_text()) if ETAT.exists() else {}
    vus = etat.get("vus", {})               # id -> horodatage de 1re vue
    attente = etat.get("attente", {})       # id -> element pas encore envoye
    dernier = etat.get("dernier_envoi", 0)
    maintenant = time.time()

    items, erreurs = collecter()
    for it in items:
        if it["id"] in vus and it["id"] not in attente:
            continue
        vus.setdefault(it["id"], maintenant)
        attente[it["id"]] = it              # met a jour le score s'il monte
    limite = maintenant - GARDE_JOURS * 86400
    attente = {k: v for k, v in attente.items() if vus.get(k, maintenant) >= limite}
    vus = {k: t for k, t in vus.items() if t >= maintenant - 60 * 86400}

    forts = [v for v in attente.values() if v["fort"]]
    heures = (maintenant - dernier) / 3600
    envoyer = forcer or (len(forts) >= FORT_MIN and heures >= DELAI_FORT_H) \
        or (heures >= DELAI_FOND_H and len(attente) >= FOND_MIN)

    if envoyer:
        choix = sorted(attente.values(), key=lambda v: (not v["fort"], -v["score"]))[:30]
        print(f"Nouveautes depuis le dernier resume ({len(attente)} elements, "
              f"{len(forts)} signaux forts). Tries du plus fort au plus faible.\n")
        for v in choix:
            fort = " [FORT]" if v["fort"] else ""
            score = f" · {v['score']} {v['unite']}" if v["unite"] else ""
            print(f"- {v['source']}{fort} · {v['titre']}{score}\n  {v['url']}\n  {v['desc']}")
        if erreurs:
            print("\nSources en panne ce tour : " + " ; ".join(erreurs))
        attente, dernier = {}, maintenant

    if not sec:
        ETAT.parent.mkdir(parents=True, exist_ok=True)
        ETAT.write_text(json.dumps({"vus": vus, "attente": attente,
                                    "dernier_envoi": dernier}, ensure_ascii=False))
    if not envoyer:
        print(json.dumps({"wakeAgent": False}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
