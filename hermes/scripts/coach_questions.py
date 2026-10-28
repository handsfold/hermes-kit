#!/usr/bin/env python3
"""Choix de LA question du passage. Regles deterministes, rien d'invente.

Chaque regle regarde un fait mesure (qg.db, git, taches.md, journal.md) et rend
une question fermee, repondable en une phrase. On prend la premiere qui mord,
en evitant de reposer une question posee dans les 6 derniers passages.
"""
import re

VAGUE = re.compile(
    r"^(definir|d.finir|reflechir|r.fl.chir|voir|penser|regarder|clarifier|decider|d.cider)\b",
    re.I,
)


def _vague(texte):
    return bool(VAGUE.match(texte.strip()))


def candidates(ctx):
    """ctx : cap, actifs, depots, ouvertes, derive, bouge, faites_hier, sans_reponse.

    Rend [(cle, question)] par ordre de priorite.
    """
    out = []
    ouvertes = ctx.get("ouvertes") or []
    actifs = ctx.get("actifs") or []
    depots = ctx.get("depots") or {}
    noms = {n.lower() for n, _, _ in actifs}
    miennes = [t for t in ouvertes if t["projet"].lower() in noms]
    vieilles = sorted(miennes, key=lambda t: -t.get("jours", 0))

    # 0. L'ecart le plus parlant : le travail reel n'est pas dans les 3 actifs.
    # Mesure le 2026-09-10 : 49 tours sur « Sync calendrier », 0 sur les
    # actifs declares. Tant que focus.md decrit un monde que les journees ne
    # confirment pas, tout le reste du briefing parle dans le vide.
    hors = sorted(ctx.get("qg_hors") or [], key=lambda s: -s.get("tours", 0))
    if hors and hors[0].get("tours", 0) >= 10:
        h = hors[0]
        out.append((
            "ecart_qg",
            f"Tu as passe {h['tours']} tours sur « {h['nom'][:60]} », "
            f"qui n'est dans aucun de tes 3 actifs. "
            f"Tu le fais monter en actif, ou tu le laches ?",
        ))

    # 0 bis. Du travail fini que personne n'a releve.
    if (ctx.get("qg_non_lus") or 0) >= 5:
        out.append((
            "rapports_non_lus",
            f"{ctx['qg_non_lus']} rapports d'agents attendent dans le QG sans "
            f"que tu les ouvres. Ils te servent a quelque chose, ou j'arrete "
            f"de les produire ?",
        ))

    # 1. Une tache pourrit depuis une semaine : le blocage n'est pas le temps.
    if vieilles and vieilles[0].get("jours", 0) >= 5:
        t = vieilles[0]
        out.append((
            "blocage",
            f"« {t['texte'][:70]} » traine depuis {t['jours']} j. "
            f"Qu'est-ce qui te retient vraiment : tu ne sais pas comment faire, "
            f"ou tu n'as pas envie ?",
        ))

    # 2. Une tache formulee en verbe mou n'est pas une action.
    molles = [t for t in miennes if _vague(t["texte"])]
    if molles:
        t = molles[0]
        out.append((
            "vague",
            f"« {t['texte'][:70]} » n'est pas une action, c'est une intention. "
            f"C'est quoi le premier geste concret de 20 minutes ?",
        ))

    # 3. Rien n'a bouge sur les actifs depuis 2 jours.
    if not ctx.get("bouge") and not ctx.get("faites_hier"):
        out.append((
            "arret",
            "Aucun actif n'a bouge depuis 48 h. C'est un manque de temps, "
            "d'envie, ou tu ne sais pas par ou reprendre ?",
        ))

    # 4. Tu bosses ailleurs que sur tes actifs.
    derive = ctx.get("derive") or []
    if derive:
        n = derive[0]
        out.append((
            "derive",
            f"Tu as pousse du code sur {n}, qui n'est pas dans tes 3 actifs. "
            f"C'est une fuite, ou {n} merite un slot ?",
        ))

    # 5. Un actif sans aucune tache : personne ne sait quoi y faire.
    orphelins = [n for n, _, _ in actifs
                 if not any(t["projet"].lower() == n.lower() for t in ouvertes)]
    if orphelins:
        out.append((
            "orphelin",
            f"{orphelins[0]} est un actif sans aucune tache ouverte. "
            f"Quelle est la prochaine chose a y faire : ou faut-il le sortir des actifs ?",
        ))

    # 6. Un 'fini quand' flou rend le projet infini.
    flous = [n for n, _, fini in actifs if not fini or "definir" in fini.lower()
             or "à définir" in fini.lower() or "a definir" in fini.lower()]
    if flous:
        out.append((
            "fini-quand",
            f"{flous[0]} n'a pas de « fini quand ». A quoi tu verras que c'est termine ?",
        ))

    # 7. Chantier dormant depuis longtemps qu'on garde par culpabilite.
    morts = sorted(
        (n for n, _, _ in actifs if depots.get(n, {}).get("age_j", 0) > 14),
        key=lambda n: -depots[n]["age_j"],
    )
    if morts:
        n = morts[0]
        out.append((
            "mort",
            f"{n} n'a pas bouge depuis {int(depots[n]['age_j'])} j. "
            f"Tu le relances cette semaine, ou tu le mets en pause assumee ?",
        ))

    # 8. Tout roule : on remonte d'un cran.
    cap = ctx.get("cap") or ""
    out.append((
        "cap",
        f"Cap : {cap[:80]}. " if cap else "",
    ))
    out[-1] = (
        "cap",
        (out[-1][1] + "Quelle est la seule chose qui, faite aujourd'hui, "
                      "rendrait tout le reste inutile ?").strip(),
    )
    return out


def choisir(ctx, deja_posees=()):
    """Premiere question qui mord et qui n'a pas ete posee recemment."""
    cands = candidates(ctx)
    recentes = set(deja_posees)
    for cle, q in cands:
        if q not in recentes:
            return cle, q
    return cands[0] if cands else ("cap", "Sur quoi tu bosses aujourd'hui ?")
