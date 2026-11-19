#!/usr/bin/env python3
"""Series d'appels Bash isoles et consecutifs (candidats au groupage).

Usage : bash-series.py [jours=7] [dossier-projet-contient=claude-proxy]
Lit ~/.claude/projects/*<filtre>*/*.jsonl. Un tour "Bash seul" = un message
assistant dont le seul outil est un Bash. Une serie = 3 tours Bash seuls ou plus
d'affilee. Sortie : totaux, plus longues series, premiers mots les plus repetes.
"""
import collections, glob, json, os, sys, time

jours = int(sys.argv[1]) if len(sys.argv) > 1 else 7
filtre = sys.argv[2] if len(sys.argv) > 2 else "claude-proxy"
base = os.path.expanduser("~/.claude/projects")
fichiers = [f for d in glob.glob(f"{base}/*{filtre}*")
            for f in glob.glob(f"{d}/*.jsonl")
            if time.time() - os.path.getmtime(f) < jours * 86400]
tot = collections.Counter()
pref = collections.Counter()
series = []
par_session = []
for f in fichiers:
    run, run_cmds, n_session = 0, [], 0
    def clore():
        global run, run_cmds
        if run >= 3:
            series.append((run, os.path.basename(f)[:8], run_cmds[:]))
        run, run_cmds = 0, []
    for ligne in open(f, errors="replace"):
        try:
            o = json.loads(ligne)
        except ValueError:
            continue
        if o.get("type") != "assistant":
            continue
        c = o.get("message", {}).get("content", [])
        if not isinstance(c, list):
            continue
        outils = [b for b in c if b.get("type") == "tool_use"]
        bash = [b for b in outils if b.get("name") == "Bash"]
        if outils:
            tot["tours_avec_outil"] += 1
        tot["bash"] += len(bash)
        n_session += len(bash)
        if len(bash) == 1 and len(outils) == 1:
            tot["bash_seul"] += 1
            run += 1
            cmd = (bash[0].get("input", {}).get("command", "") or "").strip().split("\n")[0]
            run_cmds.append(cmd[:70])
            pref[" ".join(cmd.split()[:2])[:40]] += 1
        else:
            clore()
    clore()
    par_session.append((n_session, os.path.basename(f)[:8]))
print(f"{len(fichiers)} sessions ({jours} j, filtre {filtre}) :", dict(tot))
print(f"series >=3 : {len(series)}, appels dedans : {sum(s[0] for s in series)}, max {max([s[0] for s in series] or [0])}")
print("top debuts de commande :", pref.most_common(12))
print("plus longues series :")
for n, sid, cmds in sorted(series, reverse=True)[:5]:
    print(f"  {n} x {sid} : {cmds[:3]}")
