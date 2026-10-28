#!/usr/bin/env python3
"""Justesse des delais annonces par l'agent : reel / annonce.
Usage : estimations.py [jours=60] [--liste N]
Sources : transcripts Claude Code + ~/.hermes/state.db, dedoublonnes.
"""
import glob, json, os, re, sqlite3, statistics as st, sys, time
from datetime import datetime

jours = int(next((a for a in sys.argv[1:] if a.isdigit()), 60))
liste = int(sys.argv[sys.argv.index("--liste") + 1]) if "--liste" in sys.argv else 0
depuis = time.time() - jours * 86400

NUM = r"(\d+(?:[.,]\d+)?)"
CUE = r"(?:environ|~|≈|compte|comptez|prévois|prevois|dans|d'ici|prend|prendra|encore|faut|durée de|duree de|dure)"
UNIT = r"(secondes?|sec|minutes?|min|heures?|h|jours?|semaines?)\b"
RE_NUM = re.compile(CUE + r"\s*(?:de |d'|environ |~)?\s*" + NUM + r"(?:\s*(?:à|a|-|ou|to)\s*" + NUM + r")?\s*" + UNIT, re.I)
RE_WORD = re.compile(r"\b(?:environ |dans |compte |comptez |prévois |d'ici |prend |prendra )(une demi-heure|un quart d'heure|une heure|une minute|une semaine|demain|quelques secondes)", re.I)
RE_FAIT = re.compile(r"\b(terminé|terminée|c'est en place|livré|déployé|c'est fini|bouclé|c'est fait|est fait|tout est en ligne)\b", re.I)
RE_ENCOURS = re.compile(r"(en cours|reste|pas encore|lancé|je lance|compte \d|environ \d|attends|prochaine|maintenant|je (?:pose|vérifie|verifie|teste|l'|j'|vais)|puis |échoué)", re.I)
RE_TIERS = re.compile(r"\b(dns|propagation|client|réponse de|reponse de|livraison|livré par|fournisseur|central|transporteur|registrar|banque|virement|meta|tiktok|line support|attend[sr]?e? (?:la|leur|sa))", re.I)
BRUIT = re.compile(r"(humain|avec claude|reset|restant|depuis|contre|il y a|écoulé|sur une semaine|en une semaine|à \d+ ?h|\d+h\d|bpm|décision|expir|déconnexion|mariage|programme|bilan automatique|relecture|rappel|par chapitre|chaque|\bpar \w+\b ~|secondes? par)", re.I)
PAS_FUTUR = re.compile(r"(il y a|depuis|pendant|en moins de|ça a pris|ca a pris|a pris|était|etait)\s*$", re.I)

def secondes(val, unit):
    u = unit.lower()
    f = 1 if u.startswith("s") else 60 if u.startswith("min") else 3600 if u.startswith("h") else 86400 if u.startswith("j") else 604800
    return val * f

def annonces(texte):
    """Rend [(secondes, phrase)] pour chaque delai futur annonce."""
    res = []
    for ph in re.split(r"(?<=[.!?:\n])\s+", texte):
        if len(ph) > 400 or BRUIT.search(ph): continue
        m = RE_NUM.search(ph)
        if m and not PAS_FUTUR.search(ph[:m.start()]):
            a = float(m.group(1).replace(",", ".")); b = float((m.group(2) or m.group(1)).replace(",", "."))
            res.append(((a + b) / 2 * 0 + secondes((a + b) / 2, m.group(3)), ph.strip()))
            continue
        m = RE_WORD.search(ph)
        if m and not PAS_FUTUR.search(ph[:m.start()]):
            w = m.group(1).lower()
            s = {"une demi-heure": 1800, "un quart d'heure": 900, "une heure": 3600, "une minute": 60,
                 "une semaine": 604800, "demain": 86400, "quelques secondes": 5}[w]
            res.append((s, ph.strip()))
    return res

def lire_claude():
    """Rend {session: [(ts, role, texte)]} ; role user = vrai message de USER."""
    S = {}
    for f in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        if os.path.getmtime(f) < depuis: continue
        ev = []
        for l in open(f, errors="ignore"):
            if '"type":"assistant"' not in l and '"type":"user"' not in l: continue
            try: d = json.loads(l)
            except Exception: continue
            if d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary"): continue
            m = d.get("message") or {}
            c = m.get("content")
            try: ts = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).timestamp()
            except Exception: continue
            if ts < depuis: continue
            if d["type"] == "assistant" and isinstance(c, list):
                t = "\n".join(b.get("text", "") for b in c if b.get("type") == "text").strip()
                if t: ev.append((ts, "assistant", t))
            elif d["type"] == "user":
                t = c if isinstance(c, str) else "".join(b.get("text", "") for b in c if b.get("type") == "text") if isinstance(c, list) else ""
                if t.strip() and not t.startswith("<"): ev.append((ts, "user", t))
        if ev: S["cc:" + os.path.basename(f)[:8]] = sorted(ev)
    return S

def lire_hermes():
    S = {}
    db = sqlite3.connect("file:" + os.path.expanduser("~/.hermes/state.db") + "?mode=ro", uri=True)
    for sid, ts, role, c in db.execute("select session_id,timestamp,role,content from messages where timestamp>? and role in ('user','assistant') and content is not null and active=1 order by session_id,timestamp", (depuis,)):
        if c and c.strip(): S.setdefault("h:" + sid[:12], []).append((ts, role, c))
    return S

def paires(S):
    out = []
    for sid, ev in S.items():
        for i, (ts, role, t) in enumerate(ev):
            if role != "assistant": continue
            for sec, ph in annonces(t):
                tiers = bool(RE_TIERS.search(ph))
                fin, inter, fin_txt = None, False, ""
                lim = ts + max(6 * 3600, sec * 3)
                for ts2, r2, t2 in ev[i + 1:]:
                    if ts2 > lim: break
                    if r2 == "user": inter = True; break
                    if RE_FAIT.search(t2[:300]) and not RE_ENCOURS.search(t2[:300]): fin = ts2; fin_txt = t2[:140]; break
                out.append(dict(sid=sid, ts=ts, sec=sec, ph=ph, tiers=tiers, reel=(fin - ts) if fin else None, inter=inter, fin=fin_txt))
    return out

def tranche(s):
    return "<5 min" if s < 300 else "5-30 min" if s <= 1800 else "30 min-2 h" if s <= 7200 else "2 h-1 j" if s < 86400 else "jours/semaines"

if __name__ == "__main__":
    tout = paires(lire_claude()) + paires(lire_hermes())
    vus, P = set(), []
    for p in sorted(tout, key=lambda p: p["ts"]):
        k = (re.sub(r"\W+", "", p["ph"].lower())[:100], int(p["ts"] // 120))
        if k in vus: continue
        vus.add(k); P.append(p)
    print(f"annonces uniques : {len(P)} (brut {len(tout)})")
    tiers = [p for p in P if p["tiers"]]
    mes = [p for p in P if not p["tiers"] and p["reel"] and p["reel"] > 0]
    print(f"tiers : {len(tiers)} · sans fin trouvee : {sum(1 for p in P if not p['tiers'] and not p['reel'])} · mesurables : {len(mes)}")
    def stats(L):
        r = sorted(p["reel"] / p["sec"] for p in L)
        q = lambda x: r[min(len(r) - 1, int(x * len(r)))]
        return f"n={len(r)} med={st.median(r):.2f} moy={st.mean(r):.2f} P25={q(.25):.2f} P75={q(.75):.2f}"
    if mes:
        print("TOTAL", stats(mes))
        for t in ["<5 min", "5-30 min", "30 min-2 h", "2 h-1 j", "jours/semaines"]:
            L = [p for p in mes if tranche(p["sec"]) == t]
            print(t, stats(L) if L else "non mesure")
        print("--- plus gros ecarts (reel/annonce)")
        for p in sorted(mes, key=lambda p: -p["reel"] / p["sec"])[:max(5, liste)]:
            print(f"x{p['reel']/p['sec']:.1f} annonce={p['sec']/60:.0f}min reel={p['reel']/60:.0f}min {p['sid']} | {p['ph'][:200]} => {p['fin']}")
        print("--- plus gros ecarts a la baisse")
        for p in sorted(mes, key=lambda p: p["reel"] / p["sec"])[:max(3, liste)]:
            print(f"x{p['reel']/p['sec']:.2f} annonce={p['sec']/60:.0f}min reel={p['reel']/60:.1f}min {p['sid']} | {p['ph'][:200]}")
