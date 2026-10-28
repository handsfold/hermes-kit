#!/usr/bin/env python3
"""Repartition de ce que l'agent PRODUIT, par categorie.

  mes-tokens.py [nb_sessions]   (defaut : 25 dernieres sessions)
"""
import json, glob, os, sys, collections

N = int(sys.argv[1]) if len(sys.argv) > 1 else 25
fs = sorted(glob.glob(os.path.expanduser('~/.claude/projects') + '/*/*.jsonl'),
            key=os.path.getmtime)[-N:]
NOM = {'Bash': 'corps des commandes Bash', 'Write': 'contenu ecrit (Write)',
       'Edit': 'contenu ecrit (Edit)', 'Agent': 'consignes aux sous-agents'}
cat = collections.Counter()
for f in fs:
    for l in open(f, errors='ignore'):
        if '"assistant"' not in l:
            continue
        try:
            c = json.loads(l).get('message', {}).get('content')
        except Exception:
            continue
        if not isinstance(c, list):
            continue
        for b in c:
            t = b.get('type')
            if t == 'text':
                cat['prose (reponses)'] += len(b.get('text', '')) // 4
            elif t == 'thinking':
                cat['raisonnement'] += len(b.get('thinking', '')) // 4
            elif t == 'tool_use':
                k = NOM.get(b.get('name'), 'autres outils')
                cat[k] += len(json.dumps(b.get('input', {}))) // 4
tot = sum(cat.values()) or 1
print(f"{len(fs)} sessions, {tot/1000:.0f}k tokens produits par l'agent\n")
for k, v in cat.most_common():
    print(f"  {v*100/tot:5.1f} %  {v/1000:7.1f}k  {k}")
