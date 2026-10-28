#!/usr/bin/env python3
"""Hook pre_llm_call : injecte les regles de redaction apprises, a chaque tour.

Sans ce hook, la boucle d'apprentissage n'aurait aucun effet : le prompt systeme
est mis en cache au demarrage d'une session, donc ecrire dans SOUL.md ne changerait
rien avant la session suivante. Ici l'injection est refaite a chaque tour, donc une
regle adoptee s'applique immediatement, sans redemarrage du gateway.

Contrat : stdin = JSON du gateway, stdout = {"context": "..."} ou rien.
Ne doit JAMAIS lever ni ralentir : en cas de doute il se tait.
"""
import json
import os
import sqlite3
import sys
import time

REGLES = os.path.expanduser("~/.hermes/apprentissage/regles.json")
QGDB = os.path.expanduser("~/.hermes/qg.db")
RECUS_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS recus (id INTEGER PRIMARY KEY, session_id TEXT, "
    "action TEXT, debut REAL, fin REAL, statut TEXT, detail TEXT, "
    "ref TEXT UNIQUE, alerte REAL)"
)
PLAFOND = 14


def marquer_debut(brut):
    """Horodate le depart de cet appel LLM, pour que le veilleur voie un blocage.

    Sans cette ligne, qg.db ne connait que les tours TERMINES : un appel mort en
    vol y est indistinguable d'un topic simplement inactif. C'est precisement le
    trou qui obligeait USER a demander 'ca en est ou'.

    Silencieux par construction : une panne d'ecriture ici ne doit jamais couter
    une reponse.
    """
    # Un Hermes isole (autre HERMES_HOME : banc d'essai) n'est pas un tour de USER.
    # Ne le 2026-10-25 : cascade-bench a inscrit 25 tours que qg-collecter.py
    # (meme filtre) n'effacait jamais, et le redemarrage a attendu 1 h.
    h = os.environ.get("HERMES_HOME", "").strip()
    if h and os.path.realpath(os.path.expanduser(h)) != os.path.realpath(
            os.path.expanduser("~/.hermes")):
        return
    try:
        p = json.loads(brut) if brut else {}
        sid = (p.get("session_id") or "").strip()
        if not sid:
            return
        c = sqlite3.connect(QGDB, timeout=1.5)
        c.execute(
            "INSERT INTO tours_actifs (session_id, debut, modele) VALUES (?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET debut=excluded.debut, modele=excluded.modele",
            (sid, time.time(), (p.get("model") or "")[:60]),
        )
        # Recu de debut (2026-10-03, demande de USER) : chaque tour laisse une
        # trace « debut », que qg-collecter.py ferme en « fin ». Un recu reste
        # ouvert = tour perdu, et recus.py le signale au QG. Un seul recu
        # ouvert par session : ce hook peut tirer plusieurs fois par tour.
        c.execute(RECUS_SCHEMA)
        c.execute(
            "INSERT INTO recus (session_id, action, debut, statut) "
            "SELECT ?, 'tour', ?, 'debut' WHERE NOT EXISTS "
            "(SELECT 1 FROM recus WHERE session_id = ? AND statut = 'debut')",
            (sid, time.time(), sid),
        )
        c.commit()
        c.close()
    except Exception:
        pass


def main():
    brut = ""
    try:
        brut = sys.stdin.read()
    except Exception:
        pass
    marquer_debut(brut)
    try:
        if not os.path.exists(REGLES):
            return 0
        etat = json.load(open(REGLES))
    except Exception:
        return 0

    actives = [r for r in etat.get("regles", []) if r.get("statut") == "active"]
    if not actives:
        return 0
    actives.sort(key=lambda r: (-r.get("confirmations", 0), r.get("id", "")))

    lignes = "\n".join(f"- {r['regle']}" for r in actives[:PLAFOND])
    # Regle retiree depuis moins de 7 jours : la dire supprimee, sinon une session
    # reprise la rejoue par imitation de ses anciens messages (r010, 2026-10-09).
    import datetime
    limite = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    recentes = [r for r in etat.get("regles", [])
                if r.get("statut") == "retiree" and r.get("resume_retrait")
                and (r.get("retiree_le") or "") >= limite]
    retirees = ""
    if recentes:
        retirees = (
            "\nSupprimees par USER : ne plus les appliquer, meme si tes reponses "
            "precedentes de ce topic le faisaient encore. Arrete aussi la ligne "
            "qu'elles produisaient.\n"
            + "\n".join(f"- {r['resume_retrait']}" for r in recentes) + "\n"
        )
    bloc = (
        "<regles-apprises>\n"
        "Regles de redaction tirees des retours explicites de USER sur tes reponses "
        "passees. Elles ont ete proposees par un agent, puis contestees par un second "
        "avant d'etre retenues. Elles priment sur tes habitudes par defaut, et cedent "
        "devant une consigne donnee par USER dans le message en cours.\n\n"
        f"{lignes}\n"
        f"{retirees}"
        "</regles-apprises>"
    )
    print(json.dumps({"context": bloc}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
