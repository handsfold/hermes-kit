#!/usr/bin/env python3
"""Consommation de Prime Agent : ou partent ses tokens.

Usage: conso-prime.py [jours] [--liste N]   (defaut 7 jours, 10 tours listes)

Prime passe par le relais d'outils du proxy : chaque requete de Prime lance un
`claude` dont le transcript vit dans ~/.claude/projects/. Un transcript Prime se
reconnait a un VRAI appel de l'outil `mcp__relay__ipython` (pas a une simple
mention du nom, qui classait a tort les sessions qui parlent de Prime).

Ce qu'on mesure, par tour Prime (= un transcript) :
- prompt   : taille du premier message, souvent l'historique Prime aplati en
             <conversation>, renvoye en entier a chaque tour ;
- froid    : tokens ecrits en cache au 1er appel (ce qu'on repaie a chaque tour) ;
- relu     : cache relu sur tous les appels du tour (nb appels x contexte) ;
- $ eq.    : cout API equivalent (meme grille que cache-bilan.py), poids relatif
             sur les limites de l'abonnement, pas une facture.
"""
import glob, json, os, sys, time
from collections import defaultdict

args = [a for a in sys.argv[1:] if not a.startswith("--")]
JOURS = int(args[0]) if args else 7
LISTE = int(sys.argv[sys.argv.index("--liste") + 1]) if "--liste" in sys.argv else 10
LIMITE = time.time() - JOURS * 86400
GRILLES = {"opus": (5.0, 25.0, 6.25, 0.50), "fable": (10.0, 50.0, 12.50, 0.25),
           "sonnet": (3.0, 15.0, 3.75, 0.30), "haiku": (1.0, 5.0, 1.25, 0.10)}
MARQUE = '"name":"mcp__relay__ipython"'


def famille(nom):
    for k in ("fable", "sonnet", "haiku", "opus"):
        if k in (nom or ""):
            return k
    return "opus"


def k(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


tours = []
for f in glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True):
    if "subagents" in f or os.path.getmtime(f) < LIMITE:
        continue
    texte = open(f, errors="ignore").read()
    if MARQUE not in texte:
        continue
    # Depuis la reprise de session (2026-10-04), un transcript porte plusieurs tours
    # Prime : chaque message utilisateur en texte (pas un tool_result) en ouvre un.
    t = defaultdict(float)
    t["fichier"] = os.path.basename(f)[:8]
    vus, premier = set(), True
    for ligne in texte.splitlines():
        try:
            o = json.loads(ligne)
        except ValueError:
            continue
        m = o.get("message") or {}
        c = m.get("content")
        # Effort reellement applique par le CLI, note sur chaque message du transcript.
        # Sans `--effort` (reglage Auto du pont), c'est le defaut du modele qui s'y lit.
        if o.get("perTurnEffort") or o.get("effort"):
            t["effort"] = o.get("perTurnEffort") or o.get("effort")
        if o.get("type") == "user" and isinstance(c, str) and "prompt" in t:
            if t["appels"]:
                tours.append(t)
            t = defaultdict(float)
            t["fichier"] = os.path.basename(f)[:8]
            t["repris"] = 1
            premier = True
        if o.get("type") == "user" and isinstance(c, str) and "prompt" not in t:
            t["prompt"] = len(c)
            t["aplati"] = c.startswith("<conversation>")
            t["debut"] = o.get("timestamp", "")
            # Derniere demande de USER dans l'historique aplati : c'est elle qui a lance le tour.
            i = c.rfind("User: ")
            t["demande"] = c[i + 6:i + 76].replace("\n", " ") if i >= 0 else c[:70]
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    t["outils"] += 1
        u = m.get("usage") or {}
        if not u or (m.get("id") and m["id"] in vus):
            continue
        if m.get("id"):
            vus.add(m["id"])
        cr = u.get("cache_read_input_tokens", 0)
        cw = u.get("cache_creation_input_tokens", 0)
        g = GRILLES[famille(m.get("model"))]
        t["modele"] = famille(m.get("model"))
        t["appels"] += 1
        t["relu"] += cr
        t["ecrit"] += cw
        t["sortie"] += u.get("output_tokens", 0)
        t["usd"] += (u.get("input_tokens", 0) * g[0] + u.get("output_tokens", 0) * g[1]
                     + cw * g[2] + cr * g[3]) / 1e6
        if premier:
            t["froid"] = cw
            t["socle"] = cr  # prompt systeme + outils de Claude Code, deja en cache
            premier = False
    if t["appels"]:
        tours.append(t)

if not tours:
    print(f"Aucun tour Prime sur {JOURS} j.")
    sys.exit()

tot = lambda cle, ts=tours: sum(x[cle] for x in ts)
usd = tot("usd")
print(f"# Prime Agent · {JOURS} j · {len(tours)} tours · {int(tot('appels'))} appels · {usd:.0f} $ eq.\n")
print(f"Relu en cache {k(tot('relu'))} · ecrit {k(tot('ecrit'))} · sortie {k(tot('sortie'))}")
ecrit_usd = sum(x["ecrit"] * GRILLES[x["modele"]][2] for x in tours) / 1e6
relu_usd = sum(x["relu"] * GRILLES[x["modele"]][3] for x in tours) / 1e6
sortie_usd = sum(x["sortie"] * GRILLES[x["modele"]][1] for x in tours) / 1e6
print(f"Part du cout : ecriture cache {ecrit_usd / usd:.0%} · relecture {relu_usd / usd:.0%} · sortie {sortie_usd / usd:.0%}")
rp = [x for x in tours if x["repris"]]
if rp:
    neufs = [x for x in tours if not x["repris"]]
    print(f"Tours repris (--resume, seul le message neuf) : {len(rp)} sur {len(tours)} · "
          f"{tot('usd', rp) / len(rp):.2f} $ moy contre {tot('usd', neufs) / max(len(neufs), 1):.2f} $ "
          f"pour un tour neuf · ecrit au 1er appel {k(tot('froid', rp) / len(rp))} contre "
          f"{k(tot('froid', neufs) / max(len(neufs), 1))}")
par_effort = defaultdict(list)
for x in tours:
    par_effort[f'{x["modele"]} {x["effort"] or "?"}'].append(x)
print("Effort reel (lu dans les transcripts) : " + " · ".join(
    f"{e} {len(ts)} tours, {tot('usd', ts) / len(ts):.2f} $ moy"
    for e, ts in sorted(par_effort.items(), key=lambda kv: -len(kv[1]))))
ap = [x for x in tours if x["aplati"]]
print(f"Tours a historique aplati (<conversation>) : {len(ap)} sur {len(tours)}, "
      f"prompt moyen {k(tot('prompt', ap) / max(len(ap), 1) / 4)} tokens env.")
print(f"Ecrit au 1er appel (repaye a chaque tour) : {k(tot('froid'))} "
      f"= {tot('froid') / max(tot('ecrit'), 1):.0%} de l'ecriture totale")
print(f"Appels par tour : moyenne {tot('appels') / len(tours):.1f} · "
      f"contexte moyen relu {k(tot('relu') / tot('appels'))}\n")

print("## Par jour")
print(f"{'jour':<12}{'tours':>6}{'appels':>8}{'$ eq.':>8}{'ctx moy':>9}{'froid moy':>11}")
jours = defaultdict(list)
for x in tours:
    jours[x["debut"][:10]].append(x)
for j in sorted(jours):
    ts = jours[j]
    print(f"{j:<12}{len(ts):>6}{int(tot('appels', ts)):>8}{tot('usd', ts):>8.0f}"
          f"{k(tot('relu', ts) / tot('appels', ts)):>9}{k(tot('froid', ts) / len(ts)):>11}")

print(f"\n## Par modele")
mods = defaultdict(list)
for x in tours:
    mods[x["modele"]].append(x)
for mname, ts in sorted(mods.items(), key=lambda kv: -tot("usd", kv[1])):
    print(f"{mname:<8}{len(ts):>5} tours {tot('usd', ts):>7.0f} $")

print(f"\n## Les {LISTE} tours les plus chers")
for x in sorted(tours, key=lambda x: -x["usd"])[:LISTE]:
    print(f"{x['debut'][5:16]} {x['fichier']} {x['usd']:>5.1f}$ {int(x['appels']):>3} app "
          f"prompt {k(x['prompt'] / 4):>5} froid {k(x['froid']):>5} {x['modele']:<6} « {x['demande'][:50]} »")
