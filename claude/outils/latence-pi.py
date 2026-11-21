#!/usr/bin/env python3
"""Mesure Pi : latence demande -> livraison par tour, decomposee en LLM / outils.

Source : ~/.pi/agent/sessions/*/*.jsonl (timestamps par evenement).
Sortie : resume par tranche de nombre de requetes LLM, detail des tours les plus
lents, et commandes bash cumulant le plus de temps d'attente.

Usage :
  python3 ~/.claude/outils/latence-pi.py            # 3 derniers jours
  python3 ~/.claude/outils/latence-pi.py --jours 7
  python3 ~/.claude/outils/latence-pi.py --json     # pour un cockpit
"""
import argparse
import collections
import glob
import json
import os
import statistics
import sys
from datetime import datetime, timedelta

FICHIERS = os.path.expanduser("~/.pi/agent/sessions/*/*.jsonl")


def ts(e):
    return datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))


def texte_user(m):
    c = m.get("content")
    if isinstance(c, str):
        return "" if c.startswith("<") else c
    if isinstance(c, list):
        for x in c:
            if isinstance(x, dict) and x.get("type") == "text" and not x.get("text", "").startswith("<"):
                return x.get("text", "")
    return ""


def parse_session(path):
    """Rend (tours, commandes_lentes).

    tours : dicts t0, duree, n_llm, t_llm, t_out, modele, pire_duree, pire_outil
    commandes_lentes : (duree, outil, apercu)
    """
    try:
        with open(path) as f:
            evts = [json.loads(l) for l in f]
    except (OSError, ValueError):
        return [], []

    tours = []
    lentes = []
    modele = None
    # etat du tour courant
    t_tour = None
    n_llm = 0
    t_llm = 0.0
    t_out = 0.0
    t_prev = None
    derniere_reponse = None
    pire = (0.0, "")
    # appels d'outils en attente : id -> (t0, nom, apercu)
    attente = {}

    def cloture(t):
        nonlocal t_tour, n_llm, t_llm, t_out, derniere_reponse, pire
        if t_tour is not None and derniere_reponse is not None:
            tours.append({
                "t0": t_tour,
                "duree": (derniere_reponse - t_tour).total_seconds(),
                "n_llm": n_llm,
                "t_llm": t_llm,
                "t_out": t_out,
                "modele": modele,
                "pire_duree": pire[0],
                "pire_outil": pire[1],
            })
        t_tour = None
        n_llm = 0
        t_llm = 0.0
        t_out = 0.0
        derniere_reponse = None
        pire = (0.0, "")

    for e in evts:
        if e.get("type") == "model_change":
            modele = e.get("modelId")
            continue
        if e.get("type") != "message":
            continue
        m = e["message"]
        role = m.get("role")
        t = ts(e)

        if role == "user":
            if texte_user(m):
                cloture(t)
                t_tour = t
            t_prev = t
        elif role == "assistant":
            if t_tour is None:
                t_tour = t
            if t_prev:
                t_llm += (t - t_prev).total_seconds()
            n_llm += 1
            contenu = m.get("content")
            if isinstance(contenu, list):
                for x in contenu:
                    if isinstance(x, dict) and x.get("type") == "toolCall":
                        apercu = str(x.get("arguments", {}))[:120].replace("\n", " ")
                        attente[x.get("id")] = (t, x.get("name", "?"), apercu)
                if any(isinstance(x, dict) and x.get("type") == "text" for x in contenu):
                    derniere_reponse = t
            elif isinstance(contenu, str) and contenu:
                derniere_reponse = t
            t_prev = t
        elif role == "toolResult":
            d = (t - t_prev).total_seconds() if t_prev else 0.0
            t_out += d
            nom = m.get("toolName", "?")
            if d > pire[0]:
                pire = (d, nom)
            appel = attente.pop(m.get("toolCallId"), None)
            if appel and d >= 5:
                lentes.append((d, appel[1], appel[2]))
            t_prev = t
    cloture(None)
    return tours, lentes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jours", type=int, default=3)
    p.add_argument("--json", action="store_true", dest="json_sortie")
    args = p.parse_args()

    borne = datetime.now() - timedelta(days=args.jours)
    tous = []
    lentes = []
    for path in sorted(glob.glob(FICHIERS), key=os.path.getmtime):
        if datetime.fromtimestamp(os.path.getmtime(path)) < borne:
            continue
        tours, lentes_session = parse_session(path)
        tous.extend(tours)
        lentes.extend(lentes_session)

    if args.json_sortie:
        print(json.dumps({
            "tours": [{**t, "t0": t["t0"].isoformat()} for t in tous],
            "lentes": lentes,
        }, ensure_ascii=False))
        return 0

    if not tous:
        print("Aucun tour trouve sur la periode.")
        return 0

    durs = sorted(t["duree"] for t in tous)
    n = len(durs)
    print(f"Tours mesures : {n}  (sessions des {args.jours} derniers jours)")
    print(f"Latence demande -> livraison : mediane {statistics.median(durs):.0f}s  "
          f"p75 {durs[int(n*0.75)]:.0f}s  p90 {durs[int(n*0.9)]:.0f}s  max {durs[-1]:.0f}s")
    repartition = [
        ("<15s", sum(1 for x in durs if x < 15)),
        ("15-60s", sum(1 for x in durs if 15 <= x < 60)),
        ("1-5min", sum(1 for x in durs if 60 <= x < 300)),
        (">5min", sum(1 for x in durs if x >= 300)),
    ]
    print("Repartition : " + ", ".join(f"{k}={v} ({v/n*100:.0f}%)" for k, v in repartition))

    print("\nLatence par nombre de requetes LLM dans le tour :")
    tranches = [(0, 1), (2, 5), (6, 15), (16, 40), (41, 9999)]
    for a, b in tranches:
        sel = [t["duree"] for t in tous if a <= t["n_llm"] <= b]
        if sel:
            print(f"  {a:>2}-{b:<4} requetes : n={len(sel):3d}  mediane {statistics.median(sel):6.0f}s")

    print("\nRepartition du temps cumule :")
    total = sum(t["duree"] for t in tous)
    t_llm = sum(t["t_llm"] for t in tous)
    t_out = sum(t["t_out"] for t in tous)
    if total:
        print(f"  total {total/60:.0f} min : LLM {t_llm/total*100:.0f}%  outils {t_out/total*100:.0f}%  reste {100-t_llm/total*100-t_out/total*100:.0f}%")

    print("\nTours les plus lents :")
    for t in sorted(tous, key=lambda x: -x["duree"])[:10]:
        print(f"  {t['duree']:6.0f}s  {t['n_llm']:3d} requetes  LLM {t['t_llm']:5.0f}s  "
              f"outils {t['t_out']:5.0f}s  {str(t['modele'])[:26]:26s}  pire {t['pire_duree']:.0f}s {t['pire_outil']}  ({t['t0'].strftime('%d %H:%M')})")

    if lentes:
        print("\nAppels d'outils >= 5s, les plus lourds :")
        cumules = collections.Counter()
        for d, nom, _ in lentes:
            cumules[nom] += d
        for nom, total_o in cumules.most_common(6):
            nb = sum(1 for _, nom_l, _ in lentes if nom_l == nom)
            print(f"  {nom:8s} total {total_o:6.0f}s  n={nb}  moy {total_o/nb:5.1f}s")
        for d, nom, apercu in sorted(lentes, reverse=True)[:5]:
            print(f"    {d:6.1f}s {nom:8s} {apercu[:90]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
