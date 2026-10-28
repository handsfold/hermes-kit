#!/usr/bin/env python3
"""Anatomie du cache_read : ou part reellement le budget.

Usage: cache-bilan.py [jours]   (defaut 7)

cout ~= nb_appels x contexte_relu. Cet outil separe les deux facteurs,
par projet, et detecte les caches qui expirent (cache_write repaye).
"""
import json, os, re, sys, glob, time, statistics
from collections import defaultdict

JOURS = int(sys.argv[1]) if len(sys.argv) > 1 else 7
LIMITE = time.time() - JOURS * 86400

proj = defaultdict(lambda: defaultdict(int))
sess = defaultdict(lambda: defaultdict(int))
ctx = []
outils = defaultdict(int)
dollars = defaultdict(float)
par_jour = defaultdict(float)
premier = {}
# $/million : (input, output, cache_write_5m, cache_read). Meme grille que cout-modeles.py.
# Sous abonnement, ce n'est pas une facture : c'est le poids relatif sur les limites.
GRILLES = {"opus": (5.0, 25.0, 6.25, 0.50), "fable": (10.0, 50.0, 12.50, 0.25),
           "sonnet": (3.0, 15.0, 3.75, 0.30), "haiku": (1.0, 5.0, 1.25, 0.10)}
GRILLES["opus-5"] = GRILLES["opus"]
def famille_modele(nom):
    for k in ("fable", "sonnet", "haiku", "opus"):
        if k in nom:
            return k
    return "opus"

froids = []   # reprises a cache froid : (ecart s, cw, projet, session, $ en trop)
deja_vus = set()
SEUIL_CW = 100_000   # ecriture de cache assez grosse pour compter comme reprise lourde
def ts_epoch(s):
    from datetime import datetime
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None

for f in glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True):
    try:
        if os.path.getmtime(f) < LIMITE:
            continue
        # Des liens symboliques (rangement du 2026-10-24) montrent chaque fichier 2 fois.
        reel = os.path.realpath(f)
        if reel in deja_vus:
            continue
        deja_vus.add(reel)
        dernier_ts = None
        # Un sous-agent vit dans <projet>/<session>/subagents/ : on le rend a son projet.
        parts = os.path.relpath(f, os.path.expanduser("~/.claude/projects")).split(os.sep)
        p = parts[0] + (" [sous-ag]" if "subagents" in parts else "")
        sid = (parts[1] if "subagents" in parts else os.path.basename(f))[:8]
        texte = open(f, errors="ignore").read()
        # Prime Agent passe par le relais d'outils du proxy : son outil ipython le signe.
        if '"name":"mcp__relay__ipython"' in texte:  # un vrai appel, pas une mention
            p = re.sub(r"^(agent|amazon|archives|contenu|entreprise-a|musique|outils|perso|sites)-", "",
                       parts[0].split("-Projets-")[-1]) + " [prime]"
        vus = set()
        for ligne in texte.splitlines():
            if '"usage"' not in ligne and '"tool_use"' not in ligne:
                continue
            try:
                o = json.loads(ligne)
            except Exception:
                continue
            m = o.get("message") or {}
            c = m.get("content")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        outils[b.get("name", "?")] += 1
            u = m.get("usage") or {}
            if not u:
                continue
            # Le CLI ecrit une ligne par bloc de contenu, avec le meme usage : compter une fois.
            if m.get("id"):
                if m["id"] in vus:
                    continue
                vus.add(m["id"])
            cr = u.get("cache_read_input_tokens", 0)
            cw = u.get("cache_creation_input_tokens", 0)
            g = GRILLES.get(famille_modele(m.get("model", "")), GRILLES["opus-5"])
            usd = (u.get("input_tokens", 0) * g[0] + u.get("output_tokens", 0) * g[1] + cw * g[2] + cr * g[3]) / 1e6
            t_ = ts_epoch(o.get("timestamp", ""))
            if t_ is not None:
                if dernier_ts is not None and cw >= SEUIL_CW and t_ - dernier_ts > 300:
                    froids.append((t_ - dernier_ts, cw, p, sid, cw * (g[2] - g[3]) / 1e6))
                dernier_ts = t_
            jour = o.get("timestamp", "")[:10]
            if jour >=time.strftime("%Y-%m-%d", time.localtime(LIMITE)):
                par_jour[jour] += usd
            dollars[p] += usd
            sess[(p, sid)]["usd"] += usd
            sess[(p, sid)]["mod_" + famille_modele(m.get("model", ""))] += usd
            if (p, sid) not in premier and isinstance(c, list):
                pass
            for d in (proj[p], sess[(p, sid)]):
                d["appels"] += 1
                d["cr"] += cr
                d["cw"] += cw
                d["out"] += u.get("output_tokens", 0)
            if cr:
                ctx.append(cr + cw)
    except Exception:
        continue

print(f"=== Ou part le budget, {JOURS} jours ===\n")
print(f"{'projet':42s} {'appels':>7s} {'ctx moy':>9s} {'cr (M)':>9s} {'% budget':>9s}")
tot_cr = sum(d["cr"] for d in proj.values()) or 1
for p, d in sorted(proj.items(), key=lambda x: -x[1]["cr"])[:12]:
    if d["appels"] < 20:
        continue
    print(f"{p[:42]:42s} {d['appels']:7d} {d['cr']/d['appels']/1000:8.0f}k"
          f" {d['cr']/1e6:9.0f} {100*d['cr']/tot_cr:8.1f}%")

print(f"\n=== Contexte relu par appel ({len(ctx)} appels) ===")
if ctx:
    ctx.sort()
    q = lambda x: ctx[int(len(ctx)*x)]/1000
    print(f"  mediane {q(.5):.0f}k   p75 {q(.75):.0f}k   p90 {q(.9):.0f}k   p99 {q(.99):.0f}k   max {ctx[-1]/1000:.0f}k")
    for seuil in (50, 100, 150, 200):
        n = sum(1 for x in ctx if x > seuil*1000)
        b = sum(x for x in ctx if x > seuil*1000)
        print(f"  > {seuil}k : {n:6d} appels ({100*n/len(ctx):4.1f}%)  = {100*b/sum(ctx):4.1f}% du budget")

print("\n=== Cache repaye (write/read) ===")
tot_cw = sum(d["cw"] for d in proj.values())
print(f"  ratio global : 1 ecriture pour {tot_cr/max(tot_cw,1):.1f} lectures")
mauvais = [(k, d) for k, d in sess.items() if d["appels"] >= 20 and d["cw"] and d["cr"]/d["cw"] < 8]
mauvais.sort(key=lambda x: -x[1]["cw"])
print(f"  sessions ou le cache expire souvent (< 8 lectures / ecriture) : {len(mauvais)}")
for (p, s), d in mauvais[:6]:
    print(f"    {p[:34]:34s} {s} {d['appels']:5d} app  ratio {d['cr']/d['cw']:4.1f}  cw {d['cw']/1e6:6.0f}M")

print(f"\n=== Reprises a cache froid (ecriture >= {SEUIL_CW//1000}k apres une pause) ===")
tot_usd_pre = sum(dollars.values()) or 1
for nom, mini in (("pause > 5 min", 300), ("pause > 1 h", 3600), ("pause > 6 h", 21600)):
    sel = [x for x in froids if x[0] > mini]
    print(f"  {nom:14s} {len(sel):5d} reprises  {sum(x[1] for x in sel)/1e6:7.1f}M tokens ecrits"
          f"  {sum(x[4] for x in sel):6.0f} $ en trop vs cache chaud ({100*sum(x[4] for x in sel)/tot_usd_pre:.1f}% du total)")
for e, w, p_, s_, usd_ in sorted(froids, key=lambda x: -x[4])[:5]:
    print(f"    {p_[-30:]:30s} {s_}  pause {e/3600:5.1f} h  ecrit {w/1000:4.0f}k  {usd_:5.2f} $")

print("\n=== Equivalent API en $ (poids sur les limites de l'abonnement) ===")
tot_usd = sum(dollars.values()) or 1
print(f"  total {tot_usd:.0f} $ sur {JOURS} j")
for j in sorted(par_jour):
    print(f"  {j}  {par_jour[j]:7.0f} $")
print()
for p, v in sorted(dollars.items(), key=lambda x: -x[1])[:10]:
    print(f"  {p[:44]:44s} {v:7.0f} $  {100*v/tot_usd:5.1f}%")
print("\n  Sessions les plus cheres :")
for (p, s_), d in sorted(sess.items(), key=lambda x: -x[1]["usd"])[:12]:
    mods = "+".join(k[4:] for k, v in sorted(d.items(), key=lambda x: -x[1]) if k.startswith("mod_") and v > d["usd"] * .1)
    print(f"    {p[-30:]:30s} {s_} {d['usd']:6.0f} $  {d['appels']:5d} app  ctx {d['cr']/max(d['appels'],1)/1000:4.0f}k  {mods}")

print("\n=== Appels d'outils (ce qui declenche un aller-retour) ===")
tot_o = sum(outils.values()) or 1
for n, c in sorted(outils.items(), key=lambda x: -x[1])[:12]:
    print(f"  {n:22s} {c:7d}  {100*c/tot_o:5.1f}%")
print(f"  TOTAL {tot_o} appels d'outils")
