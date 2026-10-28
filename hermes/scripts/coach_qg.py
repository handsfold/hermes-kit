"""Ce que USER a REELLEMENT fait, vu depuis le QG.

Pourquoi ce module existe (2026-09-10). Le coach ne regardait que git. Or le
travail de USER ne passe plus par des commits : il passe par des conversations
Telegram et des sous-agents, dont la trace vit dans `~/.hermes/qg.db`. Resultat
mesure ce jour : 383 rapports en base, 0 lu par le coach ; `taches.md` fige
depuis 10 jours ; le briefing parlait de projet-a pendant que les journees
allaient sur les torrents et la bibliotheque. Le coach lisait un monde qui
n'existait plus, et USER a decroche.

Deux tables suffisent, aucune n'est relue en entier :
  topics   une ligne par sujet, avec son nom et son nombre de tours.
  attente  un rapport de sous-agent, titre + resume, horodate.
"""
import os
import re
import sqlite3
import time

DB = os.path.expanduser("~/.hermes/qg.db")

# Sujets techniques qui ne sont pas du travail de projet.
IGNORES = ("coach", "qg", "test", "hermes qg")


def _co():
    if not os.path.exists(DB):
        return None
    try:
        c = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=3.0)
        c.row_factory = sqlite3.Row
        return c
    except Exception:
        return None


def sujets(heures=24):
    """Sujets touches recemment, du plus recent au plus ancien."""
    c = _co()
    if not c:
        return []
    seuil = time.time() - heures * 3600
    out = []
    try:
        for r in c.execute(
            """select t.thread_id, coalesce(t.nom_infere, '') as auto,
                      coalesce(n.nom, '') as vrai,
                      t.tours, t.derniere_activite, t.etat
               from topics t left join noms n on n.thread_id = t.thread_id
               where t.derniere_activite > ?
               order by t.derniere_activite desc""", (seuil,)):
            # Le vrai nom du topic prime. Le nom deduit par le modele n'est
            # qu'un secours : fige un jour, il a fait parler le coach de
            # « integration webhooks Stripe » pour le topic ProjetA (2026-10-08).
            vrai = r["vrai"].strip()
            if vrai.endswith(f'topic {r["thread_id"]}'):
                vrai = ""
            nom = vrai or r["auto"].strip()
            if not nom or nom.lower() in IGNORES:
                continue
            # Deux sujets ne different parfois que par la casse : on fusionne.
            cle = nom.lower()
            for e in out:
                if e["cle"] == cle:
                    e["tours"] += r["tours"] or 0
                    break
            else:
                out.append({"cle": cle, "nom": nom, "tours": r["tours"] or 0,
                            "quand": r["derniere_activite"], "etat": r["etat"] or ""})
    except Exception:
        return []
    finally:
        c.close()
    return out


def rapports(heures=24):
    """Rapports de sous-agents deposes dans la file, lus ou non."""
    c = _co()
    if not c:
        return []
    seuil = time.time() - heures * 3600
    out = []
    try:
        for r in c.execute(
            "select titre, statut, cree from attente where cree > ? "
            "order by cree desc", (seuil,)):
            t = re.sub(r"\s+", " ", (r["titre"] or "")).strip()
            if t:
                out.append({"titre": t, "statut": r["statut"], "quand": r["cree"]})
    except Exception:
        return []
    finally:
        c.close()
    return out


def _mots(s):
    return {m for m in re.split(r"[^a-z0-9]+", s.lower()) if len(m) > 3}


def rattacher(sujets_, noms_projets):
    """Separe les sujets qui servent un projet actif de ceux qui s'en ecartent.

    Le rattachement est volontairement grossier : un mot commun suffit. Mieux
    vaut ranger un sujet du bon cote de temps en temps que de tout classer en
    derive et rendre la section illisible.
    """
    dans, hors = [], []
    index = {p: _mots(p) for p in noms_projets}
    for s in sujets_:
        ms = _mots(s["nom"])
        # Un nom court (« DJ ») n'a aucun mot de 4 lettres : on compare aussi
        # le nom entier, sinon le topic DJ passait en derive (2026-10-08).
        touche = next((p for p, mp in index.items()
                       if ms & mp or s["nom"].strip().lower() == p.strip().lower()), None)
        (dans if touche else hors).append(dict(s, projet=touche))
    return dans, hors


def non_lus():
    """Rapports jamais ecoutes : c'est du travail fini que USER ignore."""
    c = _co()
    if not c:
        return 0
    try:
        return c.execute(
            "select count(*) from attente where statut = 'nouveau'").fetchone()[0]
    except Exception:
        return 0
    finally:
        c.close()
