#!/usr/bin/env python3
"""Coach focus : ce que USER a fait, vu de git ET du QG, face a focus.md.

Aucune invention : tout sort de git, de qg.db et de focus.md.
Sortie = texte court, style USER, pret a envoyer sur Telegram.
"""
import os
import re
import subprocess
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import focus as taches_mod  # noqa: E402  (CLI to-do, meme dossier)
import journal  # noqa: E402  (memoire des questions/reponses)
import coach_questions  # noqa: E402  (choix de la question du jour)
import coach_qg  # noqa: E402  (le travail reel, lu dans qg.db)

PROJETS = os.path.expanduser("~/Bureau/Projets")
FOCUS = os.path.join(PROJETS, "contexte", "focus.md")
JOUR = 86400


def git(repo, *args):
    try:
        r = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def scan_depots():
    """Retourne {nom: {age_j, dirty, dernier_msg}} pour chaque depot git."""
    out = {}
    now = time.time()
    if not os.path.isdir(PROJETS):
        return out
    # Rangement du 2026-10-24 : <univers>/<famille>/<nom>. On garde aussi la racine.
    candidats = []
    for nom in sorted(os.listdir(PROJETS)):
        candidats.append((nom, os.path.join(PROJETS, nom), None))
    for univers in ("business", "perso"):
        base_u = os.path.join(PROJETS, univers)
        if not os.path.isdir(base_u):
            continue
        for famille in sorted(os.listdir(base_u)):
            base_f = os.path.join(base_u, famille)
            if not os.path.isdir(base_f):
                continue
            for nom in sorted(os.listdir(base_f)):
                candidats.append((nom, os.path.join(base_f, nom), famille))
    familles = {}
    for nom, chemin, famille in candidats:
        if os.path.islink(chemin) or not os.path.isdir(os.path.join(chemin, ".git")):
            continue
        ligne = git(chemin, "log", "-1", "--format=%ct|%s")
        if not ligne or "|" not in ligne:
            continue
        ts, msg = ligne.split("|", 1)
        try:
            ts = int(ts)
        except ValueError:
            continue
        statut = git(chemin, "status", "--porcelain")
        out[nom] = {
            "age_j": (now - ts) / JOUR,
            "dirty": len([l for l in statut.splitlines() if l.strip()]),
            "msg": msg.strip()[:60],
        }
        if famille:
            familles.setdefault(famille, []).append(out[nom])
    # Un actif peut nommer une famille entiere (ex. EntrepriseA) : depot le plus recent.
    for famille, liste in familles.items():
        if famille in out:
            continue
        recent = min(liste, key=lambda d: d["age_j"])
        out[famille] = dict(recent, dirty=sum(d["dirty"] for d in liste))
    return out


def lire_focus():
    """Parse focus.md -> (cap, [(nom, prochaine, fini_quand)], set(pause), set(outils))."""
    if not os.path.exists(FOCUS):
        return None, [], set(), set()
    txt = open(FOCUS, encoding="utf-8").read()

    cap = ""
    m = re.search(r"^## Cap\s*\n(.*?)(?=^## )", txt, re.S | re.M)
    if m:
        lignes = [
            l.strip().lstrip("> ").strip()
            for l in m.group(1).splitlines()
            if l.strip() and not l.strip().startswith("> À corriger")
        ]
        # les apartes entierement entre parentheses ne font pas partie du cap
        lignes = [l for l in lignes if not (l.startswith("(") and l.endswith(")"))]
        cap = " ".join(lignes).strip()

    actifs = []
    m = re.search(r"^## Actifs.*?\n(.*?)(?=^## )", txt, re.S | re.M)
    if m:
        for l in m.group(1).splitlines():
            mm = re.match(r"\s*-\s*\*\*(.+?)\*\*\s*·\s*(.*)", l)
            if not mm:
                continue
            nom = mm.group(1).strip()
            reste = mm.group(2)
            proch = re.search(r"Prochaine:\s*(.*?)(?:·|$)", reste)
            fini = re.search(r"Fini quand:\s*(.*?)(?:·|$)", reste)
            actifs.append((
                nom,
                proch.group(1).strip() if proch else "",
                fini.group(1).strip() if fini else "",
            ))

    pause = set()
    m = re.search(r"^## En pause assum.e\s*\n(.*?)(?=^## |\Z)", txt, re.S | re.M)
    if m:
        for l in m.group(1).splitlines():
            l = l.strip()
            if not l or l.startswith("#"):
                continue
            # nom en gras dans une ligne de prose : **ProjetC**, projet perso...
            for nom in re.findall(r"\*\*(.+?)\*\*", l):
                pause.add(nom.strip())
            if "**" in l:
                continue
            # une phrase (point final ou tiret long) n'est pas une liste de noms
            if re.search(r"[.!?]$", l) or "\u2014" in l:
                continue
            for p in l.split(","):
                p = p.strip()
                if p:
                    pause.add(p)

    outils = set()
    m = re.search(r"^## Outils.*?\n(.*?)(?=^## |\Z)", txt, re.S | re.M)
    if m:
        for l in m.group(1).splitlines():
            l = l.strip()
            if not l or l.startswith("#") or re.search(r"[.!?]$", l) or "\u2014" in l:
                continue
            outils.update(p.strip() for p in l.split(",") if p.strip())

    return cap, actifs, pause, outils


def age_txt(j):
    if j < 1:
        return "aujourd'hui"
    if j < 2:
        return "hier"
    if j < 14:
        return f"il y a {int(j)} j"
    if j < 60:
        return f"il y a {int(j / 7)} sem"
    return f"il y a {int(j / 30)} mois"


def lire_taches():
    """Retourne (ouvertes numerotees, faites hier, faites aujourd'hui)."""
    toutes, _ = taches_mod.charger()
    hier = (date.today() - timedelta(days=1)).isoformat()
    auj = date.today().isoformat()
    ouv = [t for t in toutes if not t["faite"]]
    for i, t in enumerate(ouv):
        t["n"] = i + 1
        t["jours"] = taches_mod.age(t)
    return (
        ouv,
        [t for t in toutes if t["fait_le"] == hier],
        [t for t in toutes if t["fait_le"] == auj],
    )


def main():
    cap, actifs, pause, outils = lire_focus()
    if not actifs:
        print(f"focus.md illisible ou vide : {FOCUS}")
        return 0

    taches_mod.cmd_purge(silencieux=True)  # archive les faites de + de 7 j
    ouvertes, faites_hier, _ = lire_taches()
    depots = scan_depots()
    noms_actifs = {n for n, _, _ in actifs}

    # Le QG est la trace la plus fidele des journees : les conversations et les
    # rapports de sous-agents portent le travail que git ne voit jamais passer.
    qg_sujets = coach_qg.sujets(48)
    qg_rapports = coach_qg.rapports(48)
    qg_dans, qg_hors = coach_qg.rattacher(qg_sujets, noms_actifs)
    qg_non_lus = coach_qg.non_lus()
    L = []

    # 1. Verdict en tete
    bouge = [n for n in noms_actifs if n in depots and depots[n]["age_j"] < 2]
    derive = sorted(
        (
            n for n, d in depots.items()
            if n not in noms_actifs and n not in outils and d["age_j"] < 2
        ),
        key=lambda n: depots[n]["age_j"],
    )
    if faites_hier:
        L.append(f"**Hier : {len(faites_hier)} tache(s) cochee(s).**")
        for t in faites_hier[:3]:
            L.append(f"· [x] {t['texte']}")
    elif qg_sujets:
        gros = sorted(qg_sujets, key=lambda s: -s["tours"])[:3]
        L.append(f"**48 h : {len(qg_sujets)} sujets, {len(qg_rapports)} rapports.** "
                 "Aucune tache cochee.")
        for s_ in gros:
            L.append(f"· {s_['nom']} ({s_['tours']} tours)")
    elif bouge:
        L.append(f"**Hier tu as avance sur : {', '.join(bouge)}.** Aucune tache cochee.")
    else:
        L.append("**Aucun projet actif n'a bouge depuis 48 h.**")
    if qg_non_lus:
        L.append(f"· {qg_non_lus} rapport(s) jamais ouvert(s) dans le QG.")

    reps = journal.reponses_depuis(2)
    if reps:
        r = reps[0]
        quand = "aujourd'hui" if r["jour"] == date.today().isoformat() else "hier"
        L.append(f"\nTu m'as dit {quand} : « {r['texte'][:140]} »")

    if cap:
        L.append(f"\nCap : {cap}")

    # 2. Etat des 3 actifs
    L.append("\n**Tes 3 actifs**")
    # Le travail d'un actif se voit dans git OU dans ses topics du QG : EntrepriseA
    # avance sur le Pi, sans depot sur hote-1, et passait « au point mort » (2026-10-27).
    qg_age = {}
    for sj in qg_dans:
        a = (time.time() - sj["quand"]) / JOUR
        p = sj["projet"]
        qg_age[p] = min(a, qg_age.get(p, a))
    for nom, proch, _fini in actifs:
        d = depots.get(nom) or {k.lower(): v for k, v in depots.items()}.get(nom.lower())
        a_qg = qg_age.get(nom)
        if not d and a_qg is None:
            L.append(f"· {nom} : ni depot git ni topic actif")
            continue
        age_git = d["age_j"] if d else None
        age = min(x for x in (age_git, a_qg) if x is not None)
        source = "QG" if age_git is None or (a_qg is not None and a_qg < age_git) else "git"
        marque = ""
        if age > 7:
            marque = "  ← au point mort"
        elif d and d["dirty"] > 10:
            marque = f"  ← {d['dirty']} fichiers non commites"
        L.append(f"· **{nom}** : {age_txt(age)} ({source}){marque}")
        siennes = [t for t in ouvertes if t["projet"].lower() == nom.lower()]
        if not siennes:
            L.append("  **aucune tache** : `focus add " + nom + " \"...\"`")
        for t in siennes[:3]:
            rep = f"  ← reportee {t['jours']} j" if t["jours"] >= 3 else ""
            L.append(f"  {t['n']}. [ ] {t['texte']}{rep}")
        if len(siennes) > 3:
            L.append(f"  (+{len(siennes) - 3} autres)")

    # 3. Derive
    if derive or qg_hors:
        L.append("\n**Derive**")
        for n in derive[:3]:
            etat = "en pause assumee" if n in pause else "hors liste"
            L.append(f"· {n} a bouge ({etat})")
        # Un sujet QG hors des 3 actifs est du temps passe ailleurs, en clair.
        for s_ in sorted(qg_hors, key=lambda s: -s["tours"])[:3]:
            L.append(f"· {s_['nom']} : {s_['tours']} tours, hors actifs")

    # 4. Une seule action
    L.append("\n**Aujourd'hui**")
    noms_bas = {n.lower() for n, _, _ in actifs}
    ouv_actifs = [t for t in ouvertes if t["projet"].lower() in noms_bas]
    vieilles = sorted(ouv_actifs, key=lambda t: -t["jours"])

    if vieilles and vieilles[0]["jours"] >= 5:
        t = vieilles[0]
        L.append(
            f"La {t['n']} traine depuis {t['jours']} j : « {t['texte'][:60]} ». "
            f"Fais-la, ou `focus rm {t['n']}`."
        )
    elif ouv_actifs:
        t = ouv_actifs[0]
        L.append(f"{t['n']}. {t['texte']}  ({t['projet']})")
    elif not ouvertes:
        L.append("Aucune tache ouverte. Ecris-en une : `focus add <projet> \"...\"`.")
    # 5. La question du jour - c'est elle qui ouvre la boucle
    ctx = {
        "cap": cap,
        "actifs": actifs,
        "depots": depots,
        "ouvertes": ouvertes,
        "derive": derive,
        "bouge": bouge,
        "faites_hier": faites_hier,
        "qg_sujets": qg_sujets,
        "qg_hors": qg_hors,
        "qg_rapports": qg_rapports,
        "qg_non_lus": qg_non_lus,
    }
    _cle, question = coach_questions.choisir(ctx, journal.questions_recentes(6))
    L.append(f"\n**Question**\n{question}")
    L.append("\n_Reponds directement a ce message. "
             "Je l'ecris dans le journal et je m'en sers demain._")
    if ouvertes:
        L.append(f"_Cocher : `focus ok <n>` · tout voir : `focus` · {len(ouvertes)} ouvertes._")

    journal.ajouter("Q", question)
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
