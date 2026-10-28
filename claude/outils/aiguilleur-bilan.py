#!/usr/bin/env python3
"""Bilan de l'aiguilleur de skills : Hermes (plugin ~/.hermes/plugins/aiguilleur)
et Claude Code (hook ~/.claude/hooks/aiguilleur-cc.py).

  aiguilleur-bilan.py [jours]        defaut 7

Lit ~/.hermes/logs/aiguilleur.jsonl et ~/.claude/logs/aiguilleur-cc.jsonl (une
ligne par tour : voie, choix, ms) et les appels du proxy nommes hk-aiguilleur
ou hk-aiguilleur-cc dans ~/.hermes/proxy-usage.jsonl
(tokens, cache, cout equivalent API). Donne : tours vus, part injectee, voies,
latence ajoutee, replis et pannes, skills les plus choisies, cout.
"""
import collections
import datetime as dt
import json
import sys
from pathlib import Path

J = int(sys.argv[1]) if len(sys.argv) > 1 else 7
DEPUIS = (dt.datetime.now() - dt.timedelta(days=J)).strftime("%Y-%m-%dT%H:%M:%S")
DEPUIS_UTC = (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=J)).strftime("%Y-%m-%dT%H:%M:%S")


def lignes(f):
    try:
        for l in Path(f).expanduser().open(encoding="utf-8"):
            try:
                yield json.loads(l)
            except ValueError:
                pass
    except OSError:
        return


def quantile(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else 0


JOURNAUX = [("Hermes", "~/.hermes/logs/aiguilleur.jsonl", "hk-aiguilleur"),
            ("Claude Code", "~/.claude/logs/aiguilleur-cc.jsonl", "hk-aiguilleur-cc")]


def bilan(nom, journal, appelant):
    tours = [r for r in lignes(journal) if r.get("ts", "") >= DEPUIS]
    print(f"Aiguilleur {nom}, {J} derniers jours : {len(tours)} tours vus")
    if tours:
        voies = collections.Counter(r.get("voie") for r in tours)
        print("  voies : " + " · ".join(f"{k} {v}" for k, v in voies.most_common()))
        inj = [r for r in tours if r.get("chars")]
        print(f"  injectes : {len(inj)} ({100 * len(inj) // len(tours)} %), {sum(r['chars'] for r in inj) // 1000}k caracteres au total")
        vides = sum(1 for r in tours if r.get("voie") in ("llm", "cache", "repli") and not r.get("choix"))
        deja = sum(1 for r in tours if r.get("deja"))
        print(f"  aucune skill : {vides} · deja en contexte : {deja}")
        ms = [r["ms"] for r in tours if r.get("voie") == "llm"]
        if ms:
            print(f"  latence ajoutee (voie llm) : mediane {quantile(ms, .5) / 1000:.1f} s · p90 {quantile(ms, .9) / 1000:.1f} s · max {max(ms) / 1000:.1f} s")
        err = collections.Counter((r.get("erreur") or "")[:60] for r in tours if r.get("voie") in ("repli", "panne", "muet"))
        for e, n in err.most_common(3):
            print(f"  erreur x{n} : {e}")
        sk = collections.Counter(n for r in tours for n in r.get("choix") or [])
        print("  skills choisies : " + " · ".join(f"{k} {v}" for k, v in sk.most_common(10)))
    appels = [r for r in lignes("~/.hermes/proxy-usage.jsonl")
              if r.get("appelant") == appelant and r.get("ts", "") >= DEPUIS_UTC]
    if appels:
        s = lambda k: sum(r.get(k) or 0 for r in appels)
        print(f"  proxy : {len(appels)} appels · cache ecrit {s('cache_ecrit') // 1000}k · cache lu {s('cache_lu') // 1000}k"
              f" · sortie {s('sortie') // 1000}k · equivalent API {s('cout_usd'):.2f} $ ({s('cout_usd') / len(appels):.3f} $ par appel)")


for j in JOURNAUX:
    bilan(*j)
