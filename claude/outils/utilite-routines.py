#!/usr/bin/env python3
"""Utilite des routines : cout, resultats produits, resultats repris par USER, sur 7 jours.

Critere valide par USER : une routine est utile si USER ouvre, lit ou reprend ce qu'elle produit.

Mesure (lecture seule, aucun appel de modele) :
  - cout        : bloc `cout_routines` du cockpit (donnees/instantane.json), en $ equivalent API.
  - resultat    : un passage de cron dont la reponse finale n'est pas vide et pas [SILENT]
                  (state.db d'Hermes, sessions `cron_<job>_<date>_<heure>`).
  - repris      : un resultat suivi, dans les 12 h, d'un message de USER dans le topic Telegram
                  ou la routine livre (state.db, sessions telegram, cle de session terminee par le topic).
                  C'est un signal de reaction, pas une preuve de lecture : un topic tres actif
                  surestime. Les colonnes `attendu_hasard` (resultats qui auraient une reaction par simple bavardage du topic) et `topic_actif` donnent les messages de USER par jour dans ce topic.
  - timers      : pas de reponse finale ni de topic. Usage reste `None` avec la raison dans `pourquoi`.

    utilite-routines.py [jours] [--json]
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / "Bureau/Projets/perso/outils/cockpit/donnees/blocs"))
H = Path.home() / ".hermes"
JOBS = H / "cron" / "jobs.json"
ETAT = H / "state.db"
INSTANTANE = Path.home() / "Bureau/Projets/perso/outils/cockpit/donnees/instantane.json"
FENETRE_S = 12 * 3600

# Timers dont la sortie n'est lue par personne de mesurable : la raison est ecrite en clair.
TIMERS = {
    "timer:user:qg-profil.timer": "sortie lue par le standard vocal (fichier qg-profil.md), aucun compteur de lecture",
    "timer:user:kana-veille.timer": "messages postes par bot dans EntrepriseA et le QG : Telegram ne rend aucun accuse de lecture, "
                                    "les reponses du chat EntrepriseA ne sont pas dans state.db",
    "timer:user:amorce-quota.timer": "ne produit rien de lisible : ouvre la fenetre de quota de 5 h",
}


def _jobs():
    d = json.loads(JOBS.read_text(encoding="utf-8"))
    return {j["id"]: j for j in (d["jobs"] if isinstance(d, dict) else d)}


def _couts():
    try:
        d = json.loads(INSTANTANE.read_text(encoding="utf-8"))["cout_routines"]["routines"]
    except (OSError, ValueError, KeyError):
        return {}
    return {r["id"]: r for r in d}


def _topic(job):
    cible = str(job.get("deliver") or "")
    return cible.rsplit(":", 1)[-1] if cible.startswith("telegram:") else None


def _cout_silence(res, jours):
    """{job: $} des passages dont la reponse est vide ou [SILENT] (appels du proxy tombes dans leur fenetre)."""
    try:
        import _hermes
        lignes = _hermes.lignes(jours)
    except Exception:
        return {}
    fen = [(a, b, j) for j, r in res.items() for a, b in r.get("silence", [])]
    out = {}
    for l in lignes:
        if l.get("source") != "cron":
            continue
        try:
            t = _hermes._outils.hermes().quand(l["ts"]).timestamp()
        except Exception:
            continue
        for a, b, j in fen:
            if a <= t <= b:
                out[j] = out.get(j, 0.0) + _hermes.usd(l)
                break
    return out


def mesurer(jours=7):
    depuis = time.time() - jours * 86400
    jobs, couts = _jobs(), _couts()
    con = sqlite3.connect(f"file:{ETAT}?mode=ro", uri=True, timeout=5)
    try:
        # messages de USER par topic (epoch triee), 7 jours + marge
        poste = {}
        for cle, t in con.execute(
                "select s.session_key, m.timestamp from messages m join sessions s on s.id=m.session_id "
                "where m.role='user' and s.source='telegram' and m.timestamp >= ? and m.content like '[Vin]%' "
                "order by m.timestamp", (depuis,)):
            if cle:
                poste.setdefault(cle.rsplit(":", 1)[-1], []).append(t)
        res = {}
        for sid, deb, fin in con.execute(
                "select id, started_at, ended_at from sessions where id like 'cron\\_%' escape '\\' and started_at >= ?",
                (depuis,)):
            job_id = sid.split("_")[1]
            r = res.setdefault(job_id, {"passages": 0, "resultats": 0, "repris": 0, "ts": []})
            r["passages"] += 1
            dern = con.execute("select content from messages where session_id=? and role='assistant' "
                               "order by timestamp desc limit 1", (sid,)).fetchone()
            texte = (dern[0] or "").strip() if dern else ""
            if texte and "[SILENT]" not in texte:
                r["resultats"] += 1
                r["ts"].append(float(fin or deb))
            else:
                r.setdefault("silence", []).append((float(deb), float(fin or deb + 1800)))
    finally:
        con.close()

    silence_usd = _cout_silence(res, jours)
    out = []
    for cid, c in couts.items():
        usd = c.get("usd_semaine")
        if not usd:
            continue
        ligne = {"id": cid, "nom": c["nom"], "usd": usd, "passages": c.get("passages_7j", 0),
                 "statut": c.get("statut"), "genre": c.get("genre") or "cron",
                 "resultats": None, "repris": None, "topic": None, "topic_actif": None, "attendu_hasard": None, "pourquoi": None}
        if cid.startswith("cron:"):
            job_id = cid[5:]
            job = jobs.get(job_id, {})
            r = res.get(job_id, {"passages": 0, "resultats": 0, "repris": 0, "ts": []})
            topic = _topic(job)
            ligne["topic"] = topic
            ligne["resultats"] = r["resultats"]
            ligne["usd_silence"] = round(silence_usd.get(job_id, 0.0), 2)
            ligne["passages_silence"] = len(r.get("silence", []))
            if topic and topic in poste:
                ligne["topic_actif"] = round(len(poste[topic]) / jours, 1)
            if not topic:
                ligne["pourquoi"] = "pas de topic Telegram de livraison"
            else:
                repris = sum(1 for t in r["ts"] if any(t <= m <= t + FENETRE_S for m in poste.get(topic, [])))
                ligne["repris"] = repris
                # au hasard : part des heures de la semaine suivies d'un message de USER dans les 12 h, appliquee aux resultats
                grille = [depuis + i * 3600 for i in range(int(jours * 24))]
                part = sum(1 for g in grille if any(g <= m <= g + FENETRE_S for m in poste.get(topic, []))) / len(grille)
                ligne["attendu_hasard"] = round(part * r["resultats"], 1)
        else:
            ligne["pourquoi"] = TIMERS.get(cid, "sortie sans lecteur observable")
        out.append(ligne)
    out.sort(key=lambda x: -x["usd"])
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    jours = int(args[0]) if args else 7
    lignes = mesurer(jours)
    if "--json" in sys.argv:
        print(json.dumps(lignes, ensure_ascii=False, indent=1))
        return
    print(f"{'routine':46} {'$':>6} {'pass':>4} {'res':>4} {'repris':>6} {'hasard':>6} {'topic/j':>7}")
    for x in lignes:
        usage = "non mesure" if x["repris"] is None else x["repris"]
        print(f"{x['nom'][:46]:46} {x['usd']:6.2f} {x['passages']:4} {str(x['resultats']):>4} {str(usage):>6} {str(x['attendu_hasard']):>6} "
              f"{str(x['topic_actif']):>7} sil={x.get('passages_silence')}/{x.get('usd_silence')}$ {x['pourquoi'] or ''}")


if __name__ == "__main__":
    main()
