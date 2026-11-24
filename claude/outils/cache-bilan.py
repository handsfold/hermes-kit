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

# Anatomie (2026-11-13) : poids de chaque poste, allers-retours par demande, prefixes reecrits.
poids = defaultdict(float)      # $ par poste : lecture, ecriture, sortie, entree
demandes = 0                    # messages tapes par USER (hors resultats d'outils, hors sous-agents)
ecrits = []                     # cache ecrit par appel
reecrits = []                   # (cw, projet, session) : gros prefixe reecrit sans pause
debuts = []                     # cache ecrit au premier appel de chaque session (hors sous-agents)
gros = defaultdict(lambda: [0, 0])  # cause -> [appels, tokens] pour les appels >= 30k ecrits
outils_par_msg = defaultdict(int)
froids = []   # reprises a cache froid : (ecart s, cw, projet, session, $ en trop)
deja_vus = set()
SEUIL_CW = 100_000   # ecriture de cache assez grosse pour compter comme reprise lourde
# Compactages (2026-11-14) : [ts, preTokens, contexte au 1er appel suivant, cw de cet appel, appels depuis le precedent, projet, session]
compacts = []
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
        ctx_prec = 0
        attend = None       # compactage dont on attend le premier appel
        depuis = 0          # appels au modele depuis le dernier compactage
        for ligne in texte.splitlines():
            if '"compactMetadata"' in ligne and '"type":"system"' in ligne:
                try:
                    o = json.loads(ligne)
                    cm = o.get("compactMetadata")
                    if o.get("type") == "system" and isinstance(cm, dict) and cm.get("preTokens"):
                        attend = [ts_epoch(o.get("timestamp", "")), cm["preTokens"], None, 0, depuis, p, sid]
                        compacts.append(attend)
                        depuis = 0
                        continue
                except Exception:
                    pass
            if ('"type":"user"' in ligne and '"tool_result"' not in ligne and "subagents" not in parts
                    and '"isMeta":true' not in ligne and '"isCompactSummary":true' not in ligne
                    and '"isSidechain":true' not in ligne):
                demandes += 1
                continue
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
                        outils_par_msg[m.get("id") or id(o)] += 1
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
            depuis += 1
            if attend is not None:
                attend[2] = cr + cw + u.get("input_tokens", 0)
                attend[3] = cw
                attend = None
            g = GRILLES.get(famille_modele(m.get("model", "")), GRILLES["opus-5"])
            usd = (u.get("input_tokens", 0) * g[0] + u.get("output_tokens", 0) * g[1] + cw * g[2] + cr * g[3]) / 1e6
            poids["lecture"] += cr * g[3] / 1e6
            poids["ecriture"] += cw * g[2] / 1e6
            poids["sortie"] += u.get("output_tokens", 0) * g[1] / 1e6
            poids["entree"] += u.get("input_tokens", 0) * g[0] / 1e6
            ecrits.append(cw)
            t_ = ts_epoch(o.get("timestamp", ""))
            # Prefixe reecrit a chaud : le contexte existait, il est repaye en ecriture sans pause.
            if (ctx_prec > 30_000 and cw > 20_000 and cr < ctx_prec / 2
                    and t_ is not None and dernier_ts is not None and t_ - dernier_ts <= 300):
                reecrits.append((cw, p, sid))
            if dernier_ts is None and "subagents" not in parts:
                debuts.append(cw + cr)
            if cw >= 30_000:
                sous = "subagents" in parts
                if dernier_ts is None:
                    cause = "debut de sous-agent" if sous else "debut de session"
                elif t_ is not None and t_ - dernier_ts > 3600:
                    cause = "reprise apres pause > 1 h"
                elif t_ is not None and t_ - dernier_ts > 300:
                    cause = "reprise apres pause 5 min - 1 h"
                elif cr < ctx_prec / 2:
                    cause = "prefixe reecrit a chaud"
                else:
                    cause = "gros ajout (sortie d'outil, fichier lu)"
                gros[cause][0] += 1
                gros[cause][1] += cw
            ctx_prec = cr + cw + u.get("input_tokens", 0)
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

print("\n=== Anatomie : ce qui pese vraiment ===")
tp = sum(poids.values()) or 1
print("  poids par poste : " + "   ".join(f"{k} {100*v/tp:.0f}%" for k, v in sorted(poids.items(), key=lambda x: -x[1])))
n_app = len(ecrits) or 1
print(f"  {demandes} demandes de USER, {n_app} appels au modele : {n_app/max(demandes,1):.0f} allers-retours par demande")
if ecrits:
    e = sorted(ecrits)
    te = sum(e) or 1
    print(f"  cache ecrit par appel : mediane {e[len(e)//2]/1000:.1f}k   p90 {e[int(len(e)*.9)]/1000:.1f}k   moyenne {te/len(e)/1000:.1f}k")
    for bas, haut in ((0, 2), (2, 10), (10, 30), (30, 10**6)):
        sel = [x for x in e if bas*1000 <= x < haut*1000]
        print(f"    {bas:>3d}-{haut if haut < 10**6 else 'max':>3}k : {100*len(sel)/len(e):5.1f}% des appels = {100*sum(sel)/te:5.1f}% de l'ecriture")
print("  appels >= 30k ecrits, par cause :")
for c_, (n_, t2_) in sorted(gros.items(), key=lambda x: -x[1][1]):
    print(f"    {c_:<42} {n_:>4} appels  {t2_/1e6:>5.1f}M = {100*t2_/max(sum(ecrits),1):>4.1f}% de l'ecriture")
if debuts:
    d_ = sorted(debuts)
    print(f"  premier appel de session (socle + reprise eventuelle) : {len(d_)} sessions,"
          f" mediane {d_[len(d_)//2]/1e3:.0f}k   p90 {d_[int(len(d_)*.9)]/1e3:.0f}k   max {d_[-1]/1e3:.0f}k"
          f"   dont {sum(1 for x in d_ if x > 60_000)} au-dessus de 60k (reprises)")
print(f"  prefixes reecrits a chaud (compactage, changement de modele, invalidation) : {len(reecrits)} appels,"
      f" {sum(x[0] for x in reecrits)/1e6:.1f}M = {100*sum(x[0] for x in reecrits)/max(sum(ecrits),1):.0f}% de l'ecriture")
par_s = defaultdict(lambda: [0, 0])
for cw_, p_, s_ in reecrits:
    par_s[(p_, s_)][0] += 1; par_s[(p_, s_)][1] += cw_
for (p_, s_), (n_, w_) in sorted(par_s.items(), key=lambda x: -x[1][1])[:5]:
    print(f"    {p_[-30:]:30s} {s_}  {n_:3d} fois  {w_/1000:5.0f}k")
# Compactages : un seuil trop proche du socle reinjecte declenche des rafales.
if compacts:
    med = lambda l: sorted(l)[len(l)//2] if l else 0
    print(f"  compactages : {len(compacts)}, par seuil de declenchement (preTokens) :")
    for nom, bas, haut in (("< 90k (fenetre 100k)", 0, 90_000), ("90-140k (fenetre 150k)", 90_000, 140_000), (">= 140k", 140_000, 10**9)):
        sel = [x for x in compacts if bas <= x[1] < haut]
        if not sel:
            continue
        ap = [x[2] for x in sel if x[2]]
        marge = [x[1] - x[2] for x in sel if x[2]]
        # ecart entre deux compactages consecutifs de la meme session
        ec = []
        der = {}
        for x in sorted(sel, key=lambda x: x[0] or 0):
            k = (x[5], x[6])
            if k in der and x[0] and der[k]:
                ec.append((x[0] - der[k]) / 60)
            der[k] = x[0]
        print(f"    {nom:<24} {len(sel):3d} fois  avant {med([x[1] for x in sel])/1e3:4.0f}k  repart a {med(ap)/1e3:4.0f}k"
              f"  marge {med(marge)/1e3:4.0f}k  appels entre deux {med([x[4] for x in sel]):3d}"
              f"  ecart median {med(ec):4.0f} min  rafales (< 10 min) {sum(1 for e in ec if e < 10):2d}"
              f"  reecrit {sum(x[3] for x in sel)/1e6:.1f}M")
    par_c = defaultdict(list)
    for x in compacts:
        par_c[(x[5], x[6])].append(x)
    for (p_, s_), l in sorted(par_c.items(), key=lambda x: -len(x[1]))[:5]:
        print(f"    {p_[-30:]:30s} {s_}  {len(l):3d} fois  avant {med([x[1] for x in l])/1e3:4.0f}k"
              f"  repart a {med([x[2] for x in l if x[2]])/1e3:4.0f}k  reecrit {sum(x[3] for x in l)/1e3:5.0f}k")
nm = len(outils_par_msg) or 1
seuls = sum(1 for v in outils_par_msg.values() if v == 1)
print(f"  appels avec outils : {100*seuls/nm:.0f}% lancent un seul outil, {100*(nm-seuls)/nm:.0f}% en groupent plusieurs")

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
