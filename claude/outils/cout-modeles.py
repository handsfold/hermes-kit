#!/usr/bin/env python3
"""Cout reel par modele a partir des transcripts Claude Code.

Usage: cout-modeles.py [jours]   (defaut 7)

Lit ~/.claude/projects/**/*.jsonl, agrege les 4 postes de tokens
(input, output, cache_write, cache_read) et applique les grilles
tarifaires API pour comparer les modeles sur LE MIX REEL de USER.
"""
import json, os, sys, glob, time
from collections import defaultdict

JOURS = int(sys.argv[1]) if len(sys.argv) > 1 else 7
LIMITE = time.time() - JOURS * 86400

# $/million de tokens : (input, output, cache_write_5m, cache_read)
GRILLES = {
    "opus-5":   (5.0, 25.0, 6.25, 0.50),
    "fable-5.1": (10.0, 50.0, 12.50, 0.25),
    "sonnet-5": (3.0, 15.0, 3.75, 0.30),
}

agg = defaultdict(lambda: defaultdict(int))
for f in glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True):
    try:
        if os.path.getmtime(f) < LIMITE:
            continue
        for ligne in open(f, errors="ignore"):
            if '"usage"' not in ligne:
                continue
            try:
                o = json.loads(ligne)
            except Exception:
                continue
            m = o.get("message") or {}
            u = m.get("usage") or {}
            if not u:
                continue
            ts = o.get("timestamp", "")
            mod = m.get("model", "?")
            a = agg[mod]
            a["appels"] += 1
            a["input"] += u.get("input_tokens", 0)
            a["output"] += u.get("output_tokens", 0)
            a["cw"] += u.get("cache_creation_input_tokens", 0)
            a["cr"] += u.get("cache_read_input_tokens", 0)
    except Exception:
        continue

tot = defaultdict(int)
print(f"=== Mix de tokens sur {JOURS} jours ===")
for mod, a in sorted(agg.items(), key=lambda x: -x[1]["cr"]):
    if a["appels"] < 5:
        continue
    s = a["input"] + a["output"] + a["cw"] + a["cr"]
    print(f"{mod:38s} {a['appels']:6d} appels  {s/1e6:9.1f}M tok"
          f"  in {a['input']/1e6:7.1f}M  out {a['output']/1e6:6.1f}M"
          f"  cw {a['cw']/1e6:7.1f}M  cr {a['cr']/1e6:8.1f}M")
    for k in ("input", "output", "cw", "cr", "appels"):
        tot[k] += a[k]

s = tot["input"] + tot["output"] + tot["cw"] + tot["cr"]
print(f"\nTOTAL {tot['appels']} appels, {s/1e6:.0f}M tokens")
if s:
    print(f"  input {100*tot['input']/s:5.2f}%  output {100*tot['output']/s:5.2f}%"
          f"  cache_write {100*tot['cw']/s:5.2f}%  cache_read {100*tot['cr']/s:5.2f}%")

print(f"\n=== Cout API equivalent sur CE mix ({JOURS} j) ===")
base = None
for nom, (pi, po, pw, pr) in GRILLES.items():
    c = (tot["input"]*pi + tot["output"]*po + tot["cw"]*pw + tot["cr"]*pr) / 1e6
    if base is None:
        base = c
    print(f"{nom:12s} {c:9.2f} $   ({c/JOURS:7.2f} $/jour)   x{c/base:.2f}")
