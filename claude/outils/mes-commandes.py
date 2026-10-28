#!/usr/bin/env python3
"""Taille et repetition des commandes Bash ecrites par l'agent.

  mes-commandes.py [nb_sessions]   (defaut : 25)
"""
import json, glob, os, sys, collections

N = int(sys.argv[1]) if len(sys.argv) > 1 else 25
fs = sorted(glob.glob(os.path.expanduser('~/.claude/projects') + '/*/*.jsonl'),
            key=os.path.getmtime)[-N:]
cmds = []
for f in fs:
    for l in open(f, errors='ignore'):
        if '"Bash"' not in l:
            continue
        try:
            c = json.loads(l).get('message', {}).get('content')
        except Exception:
            continue
        if not isinstance(c, list):
            continue
        for b in c:
            if b.get('type') == 'tool_use' and b.get('name') == 'Bash':
                cmds.append(b.get('input', {}).get('command', ''))
if not cmds:
    sys.exit('aucune commande trouvee')
tot = sum(map(len, cmds))
gros = [c for c in cmds if len(c) > 1200]
here = [c for c in cmds if '<<' in c]
med = sorted(map(len, cmds))
print(f"{len(cmds)} commandes, {tot//4/1000:.0f}k tokens de corps")
print(f"  > 300 tokens : {len(gros):4d} cmd = {sum(map(len,gros))//4/1000:6.0f}k "
      f"({sum(map(len,gros))*100//tot} % du total)")
print(f"  heredocs     : {len(here):4d} cmd = {sum(map(len,here))//4/1000:6.0f}k "
      f"({sum(map(len,here))*100//tot} %)")
print(f"  mediane {med[len(med)//2]//4} tokens, max {med[-1]//4} tokens\n")
print("Premiers mots les plus frequents :")
for m, n in collections.Counter(c.strip().split()[0] for c in cmds if c.strip()).most_common(12):
    print(f"  {n:5d}x  {m[:40]}")

# --- Repetition des heredocs : quels scripts jetables refont la meme analyse ---
# Un heredoc qui revient est un candidat a devenir un outil permanent ici.
import re

def empreinte(cmd):
    """Mots distinctifs du corps d'un heredoc, pour comparer deux scripts."""
    corps = cmd.split('<<', 1)[1] if '<<' in cmd else cmd
    mots = re.findall(r'[A-Za-z_][A-Za-z_0-9]{3,}', corps)
    banal = {'import', 'print', 'from', 'else', 'elif', 'None', 'True', 'False',
             'self', 'return', 'with', 'open', 'errors', 'ignore', 'type', 'name'}
    return {m for m in mots if m not in banal}

def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0

restants = [(c, empreinte(c)) for c in here if len(c) > 200]
groupes = []
while restants:
    tete, emp = restants.pop(0)
    grp = [tete]
    autres = []
    for c, e in restants:
        (grp if jaccard(emp, e) > 0.35 else autres).append(c if jaccard(emp, e) > 0.35 else (c, e))
    restants = [x for x in autres if isinstance(x, tuple)]
    groupes.append(grp)
groupes.sort(key=lambda g: -sum(map(len, g)))
repetes = [g for g in groupes if len(g) > 1]
cout_rep = sum(sum(map(len, g)) for g in repetes)
print(f"\nHeredocs de plus de 200 car. : {sum(len(g) for g in groupes)}")
print(f"  dont repetes  : {sum(len(g) for g in repetes)} en {len(repetes)} familles "
      f"= {cout_rep//4/1000:.0f}k tokens")
print(f"  uniques       : {len([g for g in groupes if len(g)==1])}\n")
print("Familles les plus couteuses (candidates a un outil) :")
for g in repetes[:8]:
    ligne = re.sub(r'\s+', ' ', g[0])[:88]
    print(f"  {len(g):2d}x  {sum(map(len,g))//4/1000:5.1f}k tok  {ligne}")

# --- Les regles sont-elles suivies ? groupage et delegation, en chiffres ---
# Mesure du 2026-09-14 : compter les commandes contenant && et un mot de lecture
# surestime enormement le gaspillage. Ces commandes sont DEJA un seul aller-retour.
# Le vrai gaspillage est une lecture simple qui suit une autre lecture simple,
# chacune dans son propre appel.
import shlex
SEP = re.compile(r'&&|\|\||;|\|')

def est_lecture_simple(c):
    c = c.strip()
    if any(x in c for x in '|><`$(') or '\n' in c:
        return False
    try:
        m = shlex.split(c)
    except ValueError:
        return False
    if not m:
        return False
    v = os.path.basename(m[0])
    return v in ('cat', 'ls', 'wc', 'stat', 'file', 'head', 'tail', 'tree') or (
        v == 'sed' and '-n' in m)

def est_recherche(c):
    for seg in SEP.split(c):
        try:
            m = shlex.split(seg.strip())
        except ValueError:
            continue
        if not m:
            continue
        v = os.path.basename(m[0])
        o = [x for x in m[1:] if x.startswith('-')]
        if v in ('find', 'rg', 'ag'):
            return True
        if v == 'grep' and any('r' in x.lower() for x in o):
            return True
    return False

def suites(fichiers):
    """Les commandes de chaque session, dans l'ordre du transcript."""
    for f in fichiers:
        seq = []
        for l in open(f, errors='ignore'):
            if '"Bash"' not in l:
                continue
            try:
                c = json.loads(l).get('message', {}).get('content')
            except Exception:
                continue
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get('type') == 'tool_use' and b.get('name') == 'Bash':
                        seq.append(b.get('input', {}).get('command', ''))
        yield seq

consec = series = enserie = rech = 0
for seq in suites(fs):
    lec = [est_lecture_simple(c) for c in seq]
    consec += sum(1 for i in range(1, len(seq)) if lec[i] and lec[i - 1])
    marq = [est_recherche(c) for c in seq]
    rech += sum(marq)
    i = 0
    while i < len(marq):
        if marq[i]:
            j = i
            while j < len(marq) and marq[j]:
                j += 1
            if j - i >= 2:
                series += 1
                enserie += j - i
            i = j
        else:
            i += 1

agents = 0
for f in fs:
    for l in open(f, errors='ignore'):
        if '"Agent"' in l:
            try:
                c = json.loads(l).get('message', {}).get('content')
            except Exception:
                continue
            if isinstance(c, list):
                agents += sum(1 for b in c if isinstance(b, dict)
                              and b.get('type') == 'tool_use' and b.get('name') == 'Agent')

st = [c for c in cmds if 'supertool' in c]
print(f"\nLes regles sont-elles suivies ?")
print(f"  appels Bash                   : {len(cmds)}")
print(f"  dont supertool                : {len(st)} ({len(st)*100//max(len(cmds),1)} %)")
print(f"  lecture simple apres lecture  : {consec} (aller-retour evitable par supertool)")
print(f"  recherches recursives         : {rech}, dont {enserie} en {series} series")
print(f"  appels Agent                  : {agents} (1 sous-agent pour "
      f"{len(cmds)//max(agents,1)} Bash)")
