#!/usr/bin/env python3
"""Sentinelle des systemes de revue : chacun produit-il encore quelque chose ?

Ne d'une panne du 2026-10-13 : capter.py lisait un dossier fige depuis le
14/09, son cron rendait « ok » chaque matin, et la collecte des signaux est
restee aveugle 4 semaines. Un statut « ok » ne prouve rien : on regarde ici
la SORTIE de chaque systeme (age du fichier temoin, dernier passage du cron).

Usage :
  sentinelle-revue.py           controle, alerte au QG les pannes NOUVELLES
  sentinelle-revue.py --sec     controle, affiche, n'alerte pas
  sentinelle-revue.py --essai   simule une panne pour tester toute la chaine

Un systeme jamais vu sur cette machine est ignore (installation sans lui) ;
une fois vu, sa disparition devient une panne.
Une panne n'est signalee qu'une fois : elle revient au QG seulement apres
avoir ete reparee puis recassee. Lance par surveillance.py (timer surveillance.timer), 9 h chaque jour.
"""
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime

H = os.path.expanduser
ETAT = H("~/.hermes/state/sentinelle-revue.json")
JOBS = H("~/.hermes/cron/jobs.json")

# (systeme, fichier temoin ou motif glob, age maximal en heures)
FICHIERS = [
    ("Apprentissage : signaux", "~/.hermes/apprentissage/signaux.jsonl", 8 * 24 + 6),
    ("Retro hebdo : journal", "~/.hermes/retro/JOURNAL.md", 8 * 24 + 6),
    ("Auto-amelioration : journal", "~/.hermes/logs/auto-amelioration.jsonl", 8 * 24 + 6),
    ("Boucle des skills", "~/.hermes/skill-boucle/vus.json", 8 * 24 + 6),
    ("Journal des skills", "~/.claude/journal-skills/20*.jsonl", 48),
    ("Coach : journal", "~/Bureau/Projets/contexte/journal.md", 50),
    ("fil : index", "~/.hermes/fil/fil.db", 50),
    ("fil : motifs", "~/.hermes/fil/motifs.md", 50),
    ("Profil QG", "~/.hermes/qg-profil.md", 8 * 24 + 6),
    ("Alerte disque hote-1", "~/.hermes/state/disque-alerte.json", 3),
]

# (systeme, id du cron Hermes, delai maximal depuis le dernier passage, en heures)
CRONS = [
    # Apprentissage, boucle des skills, retro, levier, socle et controle des
    # skills : fusionnes le 2026-10-23 dans ce seul cron du lundi.
    ("Auto-amelioration hebdo", "adfa4f4f7750", 8 * 24 + 6),
    ("Coach quotidien", "3ddc2c712244", 26),
]

# (systeme, unite systemd user, delai maximal depuis la fin du dernier passage, en heures)
UNITES = [
    ("fil-nuit", "fil-nuit.service", 26),
    ("Profil QG", "qg-profil.service", 8 * 24),
    ("Alerte disque hote-1", "disque-alerte.service", 3),
]


def heures(ts):
    return (time.time() - ts) / 3600


CONNUS = set()   # systemes vus au moins une fois sur cette machine
VUS = set()      # vus pendant ce passage


def absent(cle, nom, message, pannes):
    """Absent : panne si deja vu ici, sinon systeme non installe, ignore."""
    if cle in CONNUS:
        pannes.append((nom, message))


def controler_fichiers():
    pannes = []
    for nom, motif, maxi in FICHIERS:
        chemins = glob.glob(H(motif))
        cle = "fichier:" + motif
        if not chemins:
            absent(cle, nom, "aucun fichier " + motif, pannes)
            continue
        VUS.add(cle)
        p = max(chemins, key=os.path.getmtime)
        age = heures(os.path.getmtime(p))
        if age > maxi:
            pannes.append((nom, "{} fige depuis {:.0f} h (max {} h)".format(
                os.path.basename(p), age, maxi)))
        elif os.path.getsize(p) == 0:
            pannes.append((nom, os.path.basename(p) + " vide"))
    return pannes


def controler_crons():
    pannes = []
    try:
        d = json.load(open(JOBS))
    except OSError:
        return []
    except ValueError as e:
        return [("Crons Hermes", "jobs.json illisible : {}".format(e))]
    jobs = {j.get("id"): j for j in (d.get("jobs", d) if isinstance(d, dict) else d)}
    for nom, jid, maxi in CRONS:
        j = jobs.get(jid)
        if not j:
            absent("cron:" + jid, nom, "cron {} introuvable".format(jid), pannes)
            continue
        VUS.add("cron:" + jid)
        if not j.get("enabled", True):
            pannes.append((nom, "cron {} desactive".format(jid)))
            continue
        dernier = j.get("last_run_at")
        if not dernier and j.get("created_at"):
            # cron neuf : on mesure depuis sa creation, pas d'alerte avant son 1er rendez-vous
            dernier = j["created_at"]
        if not dernier:
            pannes.append((nom, "cron {} jamais lance".format(jid)))
            continue
        age = heures(datetime.fromisoformat(dernier).timestamp())
        if age > maxi:
            pannes.append((nom, "cron {} sans passage depuis {:.0f} h".format(jid, age)))
        st = str(j.get("last_status") or "")
        if st and st != "ok":
            pannes.append((nom, "cron {} en echec : {} {}".format(
                jid, st, str(j.get("last_error") or "")[:120])))
    return pannes


def controler_unites():
    pannes = []
    for nom, unite, maxi in UNITES:
        r = subprocess.run(["systemctl", "--user", "show", unite, "-p", "Result",
                            "-p", "ExecMainExitTimestampMonotonic", "-p", "LoadState"],
                           capture_output=True, text=True)
        v = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
        if v.get("LoadState") != "loaded":
            absent("unite:" + unite, nom, unite + " introuvable", pannes)
            continue
        VUS.add("unite:" + unite)
        if v.get("Result") not in ("success", None):
            pannes.append((nom, "{} en echec ({})".format(unite, v.get("Result"))))
        fin = int(v.get("ExecMainExitTimestampMonotonic") or 0)
        if not fin:
            pannes.append((nom, "{} jamais termine depuis le demarrage".format(unite)))
            continue
        age = (time.monotonic() - fin / 1e6) / 3600
        if age > maxi:
            pannes.append((nom, "{} sans passage depuis {:.0f} h".format(unite, age)))
    return pannes


def main():
    essai = "--essai" in sys.argv
    sec = "--sec" in sys.argv
    try:
        etat = json.load(open(ETAT))
    except (OSError, ValueError):
        etat = {}
    if isinstance(etat, list):          # format du premier jour
        etat = {"alertees": etat}
    CONNUS.update(etat.get("connus", []))
    deja = set(etat.get("alertees", []))
    pannes = controler_fichiers() + controler_crons() + controler_unites()
    if essai:
        pannes.append(("ESSAI", "panne simulee pour tester la chaine"))

    cles = {"{} | {}".format(n, m.split(" depuis")[0]) for n, m in pannes}
    neuves = [(n, m) for n, m in pannes if "{} | {}".format(n, m.split(" depuis")[0]) not in deja]

    print("{} panne(s), {} nouvelle(s)".format(len(pannes), len(neuves)))
    for n, m in pannes:
        print("- {} : {}".format(n, m))

    if neuves and not sec:
        texte = "\n".join("- {} : {}".format(n, m) for n, m in neuves)
        texte += ("\n\nUn systeme de revue ne produit plus rien. Son cron peut "
                  "afficher ok : c'est la sortie qui compte.")
        titre = "Revue en panne : {} systeme(s)".format(len(neuves))
        if essai:
            titre = "[ESSAI] " + titre
        subprocess.run(["qg-attente", "add", titre, "--resume", texte,
                        "--source", "sentinelle-revue"], check=False)
    if not sec and not essai:
        os.makedirs(os.path.dirname(ETAT), exist_ok=True)
        json.dump({"alertees": sorted(cles), "connus": sorted(CONNUS | VUS)},
                  open(ETAT, "w"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
