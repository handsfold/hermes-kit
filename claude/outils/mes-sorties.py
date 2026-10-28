#!/usr/bin/env python3
"""Ce que les sorties d'outils versent dans le contexte, par famille.

  mes-sorties.py [jours] [filtre]   (defaut : 7 jours, tout)

Une sortie reste dans le contexte et se relit a chaque tour suivant :
c'est elle, plus que la commande, qui fait le cout d'une session.
Compte aussi les sous-agents (dossier subagents/ de chaque session).
Le filtre (ex. opencli) detaille une famille par sous-commande.
"""
import json, glob, os, sys, time, re, collections

JOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 7
FILTRE = sys.argv[2] if len(sys.argv) > 2 else None
limite = time.time() - JOURS * 86400
racine = os.path.expanduser('~/.claude/projects')
fs = [f for f in glob.glob(racine + '/**/*.jsonl', recursive=True)
      if os.path.getmtime(f) >= limite]


def famille(nom, entree):
    """Nom court d'un appel : premier mot utile d'une commande, ou l'outil."""
    if nom != 'Bash':
        if nom == 'Read' and re.search(r'\.(png|jpe?g|webp)$', entree.get('file_path', ''), re.I):
            return 'Read image'
        return nom
    cmd = entree.get('command', '')
    for mot in ('opencli', 'supertool', 'ssh', 'curl', 'agent-fond', 'grep', 'cat', 'sed', 'python3'):
        if re.search(r'(^|[\s;&|(])' + mot + r'\b', cmd):
            return mot
    return (cmd.strip().split() or ['?'])[0][:20]


def detail_opencli(cmd):
    """opencli browser <session> <verbe> -> le verbe ; opencli <site> <cmd> -> site."""
    m = re.search(r'opencli\s+browser\s+(?:--\S+\s+)*\S+\s+(\S+)', cmd)
    if m:
        return 'browser ' + m.group(1)
    m = re.search(r'opencli\s+(\S+)(?:\s+(\S+))?', cmd)
    return ' '.join(x for x in (m.groups() if m else ('?',)) if x and not x.startswith('-'))[:30]


def jetons_image(b):
    """Tokens reels d'une image : (l x h) / 750, apres reduction a 1456x819 au plus."""
    try:
        import base64, io
        from PIL import Image
        l, h = Image.open(io.BytesIO(base64.b64decode(b['source']['data']))).size
        r = min(1.0, 1456 / l, 819 / h) if l >= h else min(1.0, 819 / l, 1456 / h)
        return int(l * r * h * r / 750)
    except Exception:
        return 1500


def taille(contenu):
    if isinstance(contenu, str):
        return len(contenu), 0
    car, img = 0, 0
    for b in contenu or []:
        if b.get('type') == 'text':
            car += len(b.get('text', ''))
        elif b.get('type') == 'image':
            img += jetons_image(b)
    return car, img


appels, par_fam, par_detail = {}, collections.defaultdict(lambda: [0, 0, 0]), collections.defaultdict(lambda: [0, 0])
for f in fs:
    for l in open(f, errors='ignore'):
        if 'tool_' not in l:
            continue
        try:
            c = json.loads(l).get('message', {}).get('content')
        except Exception:
            continue
        if not isinstance(c, list):
            continue
        for b in c:
            if b.get('type') == 'tool_use':
                appels[b['id']] = (b.get('name'), b.get('input', {}))
            elif b.get('type') == 'tool_result' and b.get('tool_use_id') in appels:
                nom, entree = appels[b['tool_use_id']]
                fam = famille(nom, entree)
                car, img = taille(b.get('content'))
                par_fam[fam][0] += 1
                par_fam[fam][1] += car
                par_fam[fam][2] += img
                if FILTRE and fam == FILTRE:
                    d = detail_opencli(entree.get('command', '')) if FILTRE == 'opencli' else (entree.get('command') or re.sub(r'\d+', 'N', os.path.basename(entree.get('file_path', ''))))[:40]
                    if fam == 'Read image':
                        d = 'reduite (.lisible)' if '.lisible.' in d else 'brute'
                    par_detail[d][0] += 1
                    par_detail[d][1] += car + img * 4

tot = sum(v[1] // 4 + v[2] for v in par_fam.values())
print(f"{len(fs)} transcriptions sur {JOURS:g} j, {tot/1e6:.2f} M tokens de sorties (versement initial)")
print(f"{'famille':<14}{'appels':>8}{'k tok':>9}{'tok/appel':>11}{'tok img':>8}  part")
for fam, (n, car, img) in sorted(par_fam.items(), key=lambda kv: -(kv[1][1] // 4 + kv[1][2]))[:14]:
    t = car // 4 + img
    print(f"{fam:<14}{n:>8}{t/1000:>9.0f}{t//max(n,1):>11}{img:>8}  {100*t//max(tot,1)} %")
if FILTRE:
    print(f"\n{FILTRE}, par sous-commande :")
    for d, (n, car) in sorted(par_detail.items(), key=lambda kv: -kv[1][1])[:15]:
        print(f"  {d:<32}{n:>6} appels {car/4000:>7.0f}k tok  {car//4//max(n,1):>6} tok/appel")


def sequences_opencli():
    """Ce qui gaspille : commandes par run, doublons, echecs, enchainements."""
    runs = []  # un run = un transcript (session ou sous-agent) avec >= 1 opencli
    for f in fs:
        att, suite = {}, []
        for l in open(f, errors='ignore'):
            if 'tool_' not in l:
                continue
            try:
                c = json.loads(l).get('message', {}).get('content')
            except Exception:
                continue
            if not isinstance(c, list):
                continue
            for b in c:
                if b.get('type') == 'tool_use' and b.get('name') == 'Bash' \
                        and re.search(r'(^|[\s;&|(])opencli\s+browser\b', b['input'].get('command', '')):
                    att[b['id']] = len(suite)
                    suite.append({'cmd': b['input']['command'], 'verbe': detail_opencli(b['input']['command']),
                                  'err': False, 'car': 0})
                elif b.get('type') == 'tool_result' and b.get('tool_use_id') in att:
                    s = suite[att[b['tool_use_id']]]
                    car, _ = taille(b.get('content'))
                    txt = json.dumps(b.get('content'))[:1500].lower()
                    s['car'] = car
                    s['txt'] = txt
                    s['err'] = bool(b.get('is_error')) or '"ok": false' in txt or 'error' in txt[:300] \
                        or 'not found' in txt[:300] or 'timeout' in txt[:300]
        if suite:
            runs.append((f, suite))
    n_cmd = [len(s) for _, s in runs]
    tot = sum(n_cmd)
    print(f"\nSequences opencli browser : {len(runs)} runs, {tot} commandes")
    if not runs:
        return
    n_cmd.sort()
    print(f"  commandes par run : mediane {n_cmd[len(n_cmd)//2]}, p90 {n_cmd[int(len(n_cmd)*.9)]}, max {n_cmd[-1]}")
    err = sum(x['err'] for _, s in runs for x in s)
    print(f"  commandes en echec (probable) : {err} ({100*err//tot} %)")
    # doublons exacts dans un run
    dbl = sum(1 for _, s in runs for i, x in enumerate(s) if any(y['cmd'] == x['cmd'] for y in s[:i]))
    print(f"  commandes identiques deja lancees dans le meme run : {dbl} ({100*dbl//tot} %)")
    # open d'une URL deja ouverte
    ropen = 0
    for _, s in runs:
        vus = set()
        for x in s:
            if x['verbe'] == 'browser open':
                u = (re.findall(r'https?://\S+', x['cmd']) or [''])[0].strip('\'"')
                if u in vus:
                    ropen += 1
                vus.add(u)
    print(f"  open d'une URL deja ouverte dans le run : {ropen}")
    # state/find juste avant eval = inspection payee puis lecture
    insp = sum(1 for _, s in runs for a, b in zip(s, s[1:])
               if a['verbe'] in ('browser state', 'browser find') and b['verbe'] == 'browser eval')
    print(f"  state/find suivi d'un eval (l'eval seul aurait suffi ?) : {insp}")
    # poids: commandes qui versent le plus
    gros = sorted((x for _, s in runs for x in s), key=lambda x: -x['car'])[:5]
    print("  5 sorties les plus lourdes :")
    for x in gros:
        print(f"    {x['car']//4:>6} tok  {x['verbe']:<14} {x['cmd'][-70:].strip()!r}")
    # motifs d'echec
    mot = collections.Counter()
    for _, s in runs:
        for x in s:
            if x['err']:
                m = re.search(r'(stale[_ ]ref|no match|not found|timeout|timed out|attach_failed|selector|disconnected|navigation|blocked|captcha|invalid|usage|unknown|cannot|failed)', x.get('txt', ''))
                mot[m.group(1) if m else 'autre'] += 1
    print("  motifs d'echec :", ', '.join(f"{k} {v}" for k, v in mot.most_common(8)))
    # enchainements les plus frequents
    bi = collections.Counter((a['verbe'][8:], b['verbe'][8:]) for _, s in runs for a, b in zip(s, s[1:]))
    print("  enchainements les plus frequents :")
    for (a, b), k in bi.most_common(8):
        print(f"    {a} -> {b}: {k}")
    # runs les plus longs
    print("  5 runs les plus longs (commandes, echecs, fichier) :")
    for f, s in sorted(runs, key=lambda r: -len(r[1]))[:5]:
        print(f"    {len(s):>4} cmd, {sum(x['err'] for x in s):>3} echecs  {os.path.basename(os.path.dirname(f))[-28:]}/{os.path.basename(f)[:14]}")


if FILTRE == 'opencli':
    sequences_opencli()
