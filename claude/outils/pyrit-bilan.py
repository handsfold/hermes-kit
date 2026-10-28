#!/usr/bin/env python3
"""Bilan du mode PyRIT : est-ce que le systeme marche, ou partent les tokens.

Lit DEUX journaux, tous deux sans contenu :
  - pyrit-events.jsonl : les points de check (debut, attaque, fin). Metadonnees
    seules, poses par pyrit_events.py cote routeur-llm.
  - conso.jsonl : le registre de tokens du routeur. Les appels d'attaque y
    portent backend='pyrit', avec le vrai fournisseur et le modele.

Jamais un prompt, une question ni une reponse : ces fichiers n'en contiennent
pas. Cet outil ne fait que compter.

Usage : pyrit-bilan.py [jours]   (defaut : 7)
"""

import collections
import json
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

RACINE = Path.home() / "Bureau" / "Projets" / "perso" / "agent" / "routeur-llm"
EVENEMENTS = RACINE / "pyrit-events.jsonl"
CONSO = RACINE / "conso.jsonl"


def k(n):
    """Formate un nombre de tokens : 12345 -> '12.3k'."""
    n = n or 0
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(int(n))


def lire(chemin):
    if not chemin.exists():
        return []
    lignes = []
    for ligne in chemin.read_text(encoding="utf-8", errors="replace").splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            lignes.append(json.loads(ligne))
        except json.JSONDecodeError:
            continue
    return lignes


def ts_conso(valeur):
    """conso.jsonl : ts = 'YYYY-MM-DD HH:MM:SS' (heure locale) -> epoch."""
    try:
        return datetime.strptime(str(valeur), "%Y-%m-%d %H:%M:%S").timestamp()
    except (TypeError, ValueError):
        return 0.0


def pct(part, total):
    return f"{100 * part / total:.0f}%" if total else "-"


def main():
    jours = 7
    if len(sys.argv) > 1:
        try:
            jours = int(sys.argv[1])
        except ValueError:
            pass
    limite = (datetime.now() - timedelta(days=jours)).timestamp()

    evts = [e for e in lire(EVENEMENTS) if float(e.get("ts") or 0) >= limite]
    conso = [c for c in lire(CONSO) if ts_conso(c.get("ts")) >= limite]

    print(f"\n# Bilan PyRIT : {jours} derniers jours\n")

    if not evts and not EVENEMENTS.exists():
        print(f"  (pas encore de {EVENEMENTS.name} : aucune attaque depuis la pose "
              "des points de check)\n")

    debut = [e for e in evts if e.get("evt") == "debut"]
    attaque = [e for e in evts if e.get("evt") == "attaque"]
    fin = [e for e in evts if e.get("evt") == "fin"]

    duels = {e.get("duel") for e in evts if e.get("duel")}
    perces = sum(1 for a in attaque if a.get("perce") is True)

    # --- Verdict en une ligne -------------------------------------------------
    tok_pyrit = sum((c.get("entree") or 0) + (c.get("sortie") or 0)
                    + (c.get("cache_lu") or 0) + (c.get("cache_ecrit") or 0)
                    for c in conso if c.get("backend") == "pyrit")
    cout_pyrit = sum(c.get("cout") or 0 for c in conso if c.get("backend") == "pyrit")
    print(f"  {len(duels)} duels · {len(attaque)} techniques lancees · "
          f"{perces} percees ({pct(perces, len(attaque))}) · "
          f"{k(tok_pyrit)} tokens · {cout_pyrit:.2f} USD\n")

    # --- Percees par technique ------------------------------------------------
    if attaque:
        par_mode = collections.defaultdict(list)
        for a in attaque:
            par_mode[a.get("mode") or "?"].append(a)
        print("## Percees par technique\n")
        for mode, lot in sorted(par_mode.items(), key=lambda x: -len(x[1])):
            ok = sum(1 for a in lot if a.get("perce") is True)
            durees = [a["duree_s"] for a in lot if isinstance(a.get("duree_s"), (int, float))]
            med = f"{statistics.median(durees):.0f}s" if durees else "-"
            print(f"  {mode:<12} {len(lot):>4} lances · {ok:>4} perces "
                  f"({pct(ok, len(lot)):>4}) · mediane {med}")
        print()

    # --- Issue finale ---------------------------------------------------------
    if fin:
        print("## Issue des duels\n")
        par_verdict = collections.Counter(f.get("verdict") or "?" for f in fin)
        for v, n in par_verdict.most_common():
            print(f"  {v:<26} {n:>4}")
        print()

    # --- Pourquoi le duel finit ainsi (raison, sans contenu) ------------------
    # Repartit les fins par raison : attaque = une vraie attaque a tourne ;
    # interne/anodin = court-circuit voulu ; sans_refus = cible a repondu du 1er
    # coup, rien a percer. Dit si le systeme attaque vraiment ou court-circuite.
    raisons = collections.Counter(f.get("raison") for f in fin if f.get("raison"))
    if raisons:
        print("## Pourquoi le duel finit (raison)\n")
        total_r = sum(raisons.values())
        for r, n in raisons.most_common():
            print(f"  {r:<16} {n:>4}  ({pct(n, total_r)})")
        sans_raison = sum(1 for f in fin if not f.get("raison"))
        if sans_raison:
            print(f"  {'(sans raison)':<16} {sans_raison:>4}  "
                  "(fins d'avant la pose du champ)")
        print()

    # --- Erreurs --------------------------------------------------------------
    err = collections.Counter(a.get("erreur_type") for a in attaque if a.get("erreur_type"))
    if err:
        print("## Erreurs (par type, aucun texte)\n")
        for t, n in err.most_common():
            print(f"  {t:<16} {n:>4}")
        print()

    # --- Ou partent les tokens ------------------------------------------------
    if conso:
        print("## Ou partent les tokens (backend=pyrit)\n")
        par_four = collections.defaultdict(lambda: [0, 0.0])
        par_mod = collections.defaultdict(lambda: [0, 0.0])
        autre_tok = autre_cout = 0
        for c in conso:
            t = ((c.get("entree") or 0) + (c.get("sortie") or 0)
                 + (c.get("cache_lu") or 0) + (c.get("cache_ecrit") or 0))
            if c.get("backend") != "pyrit":
                autre_tok += t
                autre_cout += c.get("cout") or 0
                continue
            f = par_four[c.get("fournisseur") or "?"]
            f[0] += t
            f[1] += c.get("cout") or 0
            m = par_mod[c.get("modele") or "?"]
            m[0] += t
            m[1] += c.get("cout") or 0
        print("  Par fournisseur :")
        for nom, (t, co) in sorted(par_four.items(), key=lambda x: -x[1][0])[:8]:
            print(f"    {nom:<18} {k(t):>8} tokens · {co:.2f} USD")
        print("\n  Par modele :")
        for nom, (t, co) in sorted(par_mod.items(), key=lambda x: -x[1][0])[:8]:
            print(f"    {nom:<34} {k(t):>8} tokens · {co:.2f} USD")
        # par role et par technique (etiquettes posees depuis le 2026-10-20)
        for titre, cle in (("Par role", "role"), ("Par technique", "technique")):
            g = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0.0])
            for c in conso:
                if c.get("backend") != "pyrit":
                    continue
                x = g[c.get(cle) or "(sans etiquette, avant 20/10)"]
                ent, lu, ec = c.get("entree") or 0, c.get("cache_lu") or 0, c.get("cache_ecrit") or 0
                x[0] += 1
                x[1] += max(0, ent - lu - ec)
                x[2] += lu
                x[3] += ec
                x[4] += c.get("sortie") or 0
                x[5] += c.get("cout") or 0
            print(f"\n  {titre} (brut / cache lu / cache ecrit / sortie) :")
            for nom, (n, br, lu, ec, so, co) in sorted(g.items(), key=lambda x: -x[1][5])[:10]:
                ent = br + lu + ec
                cache = f"{round(100 * lu / ent)} %" if ent else "?"
                print(f"    {nom:<30} {n:>6} appels · {k(br)} / {k(lu)} / {k(ec)} / {k(so)}"
                      f" · cache {cache} · {co:.2f} USD")
        duels = collections.defaultdict(lambda: [0, 0.0])
        for c in conso:
            if c.get("backend") == "pyrit" and c.get("duel"):
                duels[c["duel"]][0] += 1
                duels[c["duel"]][1] += c.get("cout") or 0
        if duels:
            tot = sum(v[1] for v in duels.values())
            print(f"\n  Par duel (depuis le 2026-10-20) : {len(duels)} duels, "
                  f"{tot / len(duels):.2f} USD en moyenne, 5 plus chers :")
            for d, (n, co) in sorted(duels.items(), key=lambda x: -x[1][1])[:5]:
                print(f"    {d}  {n:>5} appels · {co:.2f} USD")
        if autre_tok:
            print(f"\n  (hors pyrit, meme routeur : {k(autre_tok)} tokens · "
                  f"{autre_cout:.2f} USD)")
        print()


if __name__ == "__main__":
    main()
