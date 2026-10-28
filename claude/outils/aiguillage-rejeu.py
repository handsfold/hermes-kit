#!/usr/bin/env python3
"""Rejeu a blanc du standard vocal sur un corpus, et notation.

  aiguillage-rejeu.py rejouer <etiquette> [--ids c01,c05] [--repete N]
                      [--corpus corpus|controle] [--modele <nom>]
      Rejoue le corpus phrase par phrase, a blanc : rien ne part. Ecrit
      ~/.hermes/cache/aiguillage/resultats-<etiquette>.json.
      --corpus : corpus (30 phrases, defaut) ou controle (10 phrases neuves).
      --modele : passe QG_STANDARD_MODELE au standard (sinon le modele du reglage).
  aiguillage-rejeu.py noter <etiquette> [<etiquette2>]
      Note un jeu de resultats (bon topic, questions, temps) ou compare deux jeux.
  aiguillage-rejeu.py regle <etiquette> [<etiquette2>]
      Regle « demande floue = UNE question fermee » : respectee x/N, questions inutiles.
  aiguillage-rejeu.py boutons
      Rejoue 4 gestes de bouton sous rapport (Oui, Option A, Detail, Non), routeur coupe :
      le resultat doit etre le meme d'une version a l'autre, avec 0 appel au modele.
  aiguillage-rejeu.py etapes [jours]
      Temps de chaque etape d'un vrai tour vocal (relais, transcription, standard,
      synthese) lus dans ~/.hermes/logs/voixtour.log : mediane et pire cas.

Isolation (nee de l'ordre de USER du 2026-10-22, topic Affiner) : faux HOME
/tmp/aig-home, copie figee de qg.db dont les dates sont decalees a chaque
rejeu (l'age des topics et la fenetre de 2 h restent ceux du cliche),
PIXEL_TMP vide avant chaque phrase, QG_ENVOYER=/bin/false. Le vrai
~/.hermes/qg-dernier-ecoute et le vrai /tmp/qg-standard.json ne sont jamais
ouverts en ecriture : le faux HOME les remplace.
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time

BASE = os.path.expanduser("~/.hermes/cache/aiguillage")
FAKE = "/tmp/aig-home"
SNAP = FAKE + "/qg.snap.db"
SNAP_T = FAKE + "/qg.snap.t"
T_SNAP = 1792658288          # heure de la copie de qg.db (cliche du 2026-10-22 15:38)
SCRIPT = os.environ.get("AIG_SCRIPT") or os.path.expanduser("~/Bureau/Projets/contexte/bin/qg/qg-standard.py")
LOG = FAKE + "/.hermes/logs/qg-standard.log"
ECOUTE = FAKE + "/.hermes/qg-dernier-ecoute"
PIXEL = FAKE + "/pixel"
DB = FAKE + "/qg.db"
REEL_LOG = os.path.expanduser("~/.hermes/logs/qg-standard.log")


def corpus(ids=None, nom=None):
    """Un corpus (nom) ou, sans nom, tous : noter et regle retrouvent un cas par son id."""
    noms = [nom] if nom else ["corpus", "controle"]
    cas = []
    for n in noms:
        chemin = "{}/{}.jsonl".format(BASE, n)
        if os.path.exists(chemin):
            cas += [json.loads(l) for l in open(chemin, encoding="utf-8") if l.strip()]
    return [c for c in cas if not ids or c["id"] in ids]


def figer_base():
    """qg.db du cliche, dates ramenees a maintenant (meme ecart qu'au cliche)."""
    if not os.path.exists(SNAP):
        shutil.copyfile(DB, SNAP)
        with open(SNAP_T, "w") as f:       # heure du cliche : le cliche du jour remplace T_SNAP
            f.write(str(time.time()))
    for ext in ("", "-wal", "-shm"):
        try:
            os.remove(DB + ext)
        except OSError:
            pass
    shutil.copyfile(SNAP, DB)
    try:
        t_snap = float(open(SNAP_T).read())
    except (OSError, ValueError):
        t_snap = T_SNAP
    delta = time.time() - t_snap
    c = sqlite3.connect(DB)
    c.execute("UPDATE attente SET cree=cree+?, statut_maj=statut_maj+?", (delta, delta))
    c.execute("UPDATE topics SET derniere_activite=derniere_activite+?, etat_maj=etat_maj+?",
              (delta, delta))
    c.commit()
    c.close()


def poser_ecoute(contexte):
    """« calme » : aucun rapport ecoute. « rapport:<id> » : ce rapport vient d'etre dit."""
    try:
        os.remove(ECOUTE)
    except OSError:
        pass
    if not contexte.startswith("rapport:"):
        return
    ident = contexte.split(":", 1)[1]
    c = sqlite3.connect("file:{}?mode=ro".format(DB), uri=True)
    cible = c.execute("SELECT cible FROM attente WHERE id=?", (ident,)).fetchone()[0]
    nom = c.execute("SELECT nom FROM noms WHERE thread_id=?", (cible.rsplit(":", 1)[-1],)).fetchone()
    c.close()
    with open(ECOUTE, "w", encoding="utf-8") as f:
        f.write("{}\t{}\t{}\t\n".format(ident, cible, nom[0] if nom else ""))


def vider_pixel():
    shutil.rmtree(PIXEL, ignore_errors=True)
    os.makedirs(PIXEL)


def taille(chemin):
    try:
        return os.path.getsize(chemin)
    except OSError:
        return 0


def un_tour(cas, modele=None):
    poser_ecoute(cas["contexte"])
    vider_pixel()
    avant = taille(LOG)
    env = dict(os.environ, HOME=FAKE, QG_DB=DB, PIXEL_TMP=PIXEL, QG_ENVOYER="/bin/false",
               QG_STANDARD_A_BLANC="1")
    for k in ("VOIX_RAPPORT", "VOIX_POUR", "VOIX_ECRAN", "QG_STANDARD_REPONSE", "QG_STANDARD_MODELE"):
        env.pop(k, None)
    if modele:
        env["QG_STANDARD_MODELE"] = modele
    t0 = time.time()
    try:
        p = subprocess.run(["python3", "-I", SCRIPT, "tour", cas["phrase"]], env=env, cwd=FAKE,
                           capture_output=True, text=True, timeout=150)
        sortie, err = p.stdout, p.stderr.strip()[-300:]
    except subprocess.TimeoutExpired:
        sortie, err = "", "timeout 150 s"
    mur = time.time() - t0
    nouveau = ""
    if os.path.exists(LOG):
        with open(LOG, "rb") as f:
            f.seek(avant)
            nouveau = f.read().decode("utf-8", "replace")
    r = {"id": cas["id"], "mur_s": round(mur, 2), "erreur": err, "compte": "@compte@" in sortie,
         "choix": "", "dire": "", "action": "", "cible": "", "modele": "", "standard_s": None,
         "thread": "", "demande": "", "envoye_reel": False}
    corps = []
    for ligne in sortie.splitlines():
        if ligne.startswith("@choix@"):
            r["choix"] = ligne[7:]
        elif ligne != "@compte@":
            corps.append(ligne)
    r["dire"] = " ".join(corps).strip()
    for ligne in nouveau.splitlines():
        m = re.search(r"(\S+) (\d+\.\d)s action=(\S+) cible=(.*?) dire=", ligne)
        if m:
            r["modele"], r["standard_s"], r["action"], r["cible"] = m.group(1), float(m.group(2)), m.group(3), m.group(4)
        m = re.search(r"A BLANC thread=(\S+) demande=(.*)", ligne)
        if m:
            r["thread"], r["demande"] = m.group(1), m.group(2)
        if "envoye thread=" in ligne:
            r["envoye_reel"] = True
    return r


def rejouer(args):
    ids = set(args.ids.split(",")) if args.ids else None
    cas = corpus(ids, args.corpus)
    avant_reel = taille(REEL_LOG)
    figer_base()
    sortie = []
    for i, c in enumerate(cas, 1):
        for k in range(args.repete):
            r = un_tour(c, args.modele)
            r["essai"] = k + 1
            sortie.append(r)
            print("{:3}/{} {} essai {} {:>5}s {:9} {:12} {}".format(
                i, len(cas), c["id"], k + 1, r["standard_s"], r["action"], r["cible"],
                r["dire"][:70]), flush=True)
    chemin = "{}/resultats-{}.json".format(BASE, args.etiquette)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=1)
    parti = taille(REEL_LOG) > avant_reel and any(
        "envoye thread=" in l for l in open(REEL_LOG, "rb").read()[avant_reel:].decode("utf-8", "replace").splitlines())
    print("ecrit", chemin, "| envoi reel dans le vrai journal :", "OUI" if parti else "non")


# ------------------------------------------------------------------ notation
OUVERTE = re.compile(r"\b(qu['’]est-ce|quoi|quel|quelle|quels|quelles|comment|pourquoi|"
                     r"où|quand|combien|lequel|laquelle|répéter|repeter|redire|reformul|préciser|"
                     r"precise)\b", re.I)
FERMEE = re.compile(r"^\W*(est-ce|tu |veux-tu|c['’]est|il |elle |on |je |ça |cela |faut-il|dois-je|"
                    r"voulais-tu|parles?-tu|parlais-tu|t['’]est|ton |ta |tes |le |la |les |l['’]|"
                    r"j['’]|d['’]accord|ok )", re.I)


def questions(dire):
    phrases = [p.strip() for p in re.split(r"(?<=[.!?])\s+", dire) if p.strip()]
    return [p for p in phrases if p.endswith("?")]


def phrases_de(dire):
    return [p for p in re.split(r"(?<=[.!?])\s+", dire) if p.strip()]


def fermee(q):
    """Oui/non ou A/B : jamais un mot interrogatif ouvert."""
    if OUVERTE.search(q):
        return False
    return " ou " in q.lower() or FERMEE.match(q) is not None


def seule(dire):
    """Exactement 1 question, fermee, derniere phrase, 2 phrases au plus."""
    qs = questions(dire)
    ph = phrases_de(dire)
    return len(qs) == 1 and fermee(qs[0]) and ph[-1] == qs[0] and len(ph) <= 2


def note(cas, r):
    acts, tops = cas["attendu_action"], cas["attendu_topic"]
    action_ok = r["action"] in acts
    if r["action"] in ("proposer", "envoyer"):
        topic_ok = (not tops) is False and r["cible"] in tops
    else:
        topic_ok = True if r["cible"] == "" else False
    if not tops and r["action"] in ("proposer", "envoyer"):
        topic_ok = False
    # proposer / envoyer : la phrase annonce la demande, sa « ? » n'est pas posee a USER
    qs = [] if r["action"] in ("proposer", "envoyer") else questions(r["dire"])
    return {"bon": action_ok and topic_ok, "action_ok": action_ok, "topic_ok": topic_ok,
            "questions": qs, "n_q": len(qs), "fermee": len(qs) == 1 and fermee(qs[0]),
            "seule": seule(r["dire"]) and r["action"] == "repondre",
            "phrases": len(phrases_de(r["dire"])),
            "q_attendue": cas["question_attendue"]}


def charger(etiquette):
    par = {}
    for r in json.load(open("{}/resultats-{}.json".format(BASE, etiquette), encoding="utf-8")):
        par.setdefault(r["id"], []).append(r)
    return par


def noter(args):
    cas = {c["id"]: c for c in corpus()}
    jeux = [charger(e) for e in args.etiquettes]
    for e, par in zip(args.etiquettes, jeux):
        bons = tot = 0
        temps = []
        for i, rs in par.items():
            for r in rs:
                tot += 1
                bons += note(cas[i], r)["bon"]
                if r["standard_s"] is not None:
                    temps.append(r["standard_s"])
        print("{} : bon topic {}/{} ; standard median {:.1f}s, pire {:.1f}s".format(
            e, bons, tot, statistics.median(temps), max(temps)))
    for i in sorted(set().union(*[set(par) for par in jeux])):
        ligne = [i, cas[i]["phrase"][:38].ljust(38)]
        for par in jeux:
            rs = par.get(i, [])
            ligne.append(" ".join("{}{}{}".format("OK " if note(cas[i], r)["bon"] else "KO ", r["action"][:4],
                                                  ":" + r["cible"] if r["cible"] else "") for r in rs))
        print(" | ".join(ligne))


def regle(args):
    cas = {c["id"]: c for c in corpus()}
    for e in args.etiquettes:
        par = charger(e)
        att = [i for i in sorted(cas) if cas[i]["question_attendue"] and i in par]
        ok = [i for i in att if all(note(cas[i], r)["seule"] for r in par.get(i, []))]
        inutiles = [i for i in sorted(cas) if not cas[i]["question_attendue"] and i in par
                    and any(note(cas[i], r)["n_q"] for r in par.get(i, []))]
        print("{} : regle respectee {}/{} cas ou une question etait attendue ({}) ; "
              "question non attendue dans {} cas ({})".format(
                  e, len(ok), len(att), ",".join(ok) or "aucun", len(inutiles), ",".join(inutiles)))
        for i in att:
            for r in par.get(i, []):
                n = note(cas[i], r)
                print("   {} {} nq={} seule={} | {}".format(i, r["action"][:4], n["n_q"], n["seule"], r["dire"][:110]))


GESTES = (("858", "Oui"), ("2117", "Option A"), ("938", "Détail"), ("858", "Non"))
STUB = ("import re\n\n\ndef pour_la_voix(t):\n"
        "    return re.sub(r\"[*`#_>|]\", \" \", t)\n")


def boutons(args):
    """Chemin VOIX_RAPPORT : sans modele depuis le 12/10. Routeur injoignable = preuve."""
    stub = FAKE + "/stub-attente.py"
    with open(stub, "w", encoding="utf-8") as f:
        f.write(STUB)
    appels = 0
    for ident, geste in GESTES:
        figer_base()
        poser_ecoute("rapport:" + ident)
        vider_pixel()
        avant = taille(LOG)
        env = dict(os.environ, HOME=FAKE, QG_DB=DB, PIXEL_TMP=PIXEL, QG_ENVOYER="/bin/false",
                   QG_STANDARD_A_BLANC="1", VOIX_RAPPORT=ident, QG_ATTENTE_PY=stub,
                   QG_ROUTEUR="http://127.0.0.1:9/coupe")
        env.pop("QG_STANDARD_MODELE", None)
        t0 = time.time()
        p = subprocess.run(["python3", "-I", SCRIPT, "tour", geste], env=env, cwd=FAKE,
                           capture_output=True, text=True, timeout=60)
        nouveau = ""
        if os.path.exists(LOG):
            with open(LOG, "rb") as f:
                f.seek(avant)
                nouveau = f.read().decode("utf-8", "replace")
        n = len(re.findall(r" action=\S+ cible=", nouveau))
        appels += n
        print("{:>8} rapport {:>4} rc={} {:.1f}s appels_modele={} | {}".format(
            geste, ident, p.returncode, time.time() - t0, n,
            (p.stdout.strip() or p.stderr.strip()[-100:])[:110].replace("\n", " / ")))
    print("total appels au modele :", appels)


def etapes(args):
    """Un tour vocal = lignes « son recu » ... « reponse jouee », +Nms depuis le debut du tour."""
    from datetime import datetime, timedelta
    lim = datetime.now() - timedelta(days=args.jours)
    tours, cur = [], None
    for l in open(os.path.expanduser("~/.hermes/logs/voixtour.log"), encoding="utf-8", errors="replace"):
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) voixtour \+(-?\d+)ms : (\S+)", l)
        if not m:
            continue
        t, ms, mot = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), int(m.group(2)), m.group(3)
        if mot == "son" and "recu" in l[:80 + len(m.group(0))]:
            cur = {"t": t}
            tours.append(cur)
        if cur is None:
            continue
        cle = {"ramene": "ramene", "entendu": "entendu", "accuse": "accuse",
               "repondu": "repondu", "reponse": "jouee"}.get(mot)
        if mot == "son" and " ramene" in l:
            cle = "ramene"
        if cle and cle not in cur:
            cur[cle] = ms
    nets = [c for c in tours if c["t"] >= lim and all(k in c for k in ("ramene", "entendu", "repondu", "jouee"))]
    print("{} tours vocaux complets sur {} jours".format(len(nets), args.jours))
    defs = [("relais (son ramene)", lambda c: c["ramene"]),
            ("transcription", lambda c: c["entendu"] - c["ramene"]),
            ("standard (modele)", lambda c: c["repondu"] - c["entendu"]),
            ("synthese + lecture", lambda c: c["jouee"] - c["repondu"]),
            ("total, parole a reponse", lambda c: c["jouee"])]
    for nom, f in defs:
        v = sorted(f(c) / 1000.0 for c in nets)
        if v:
            print("  {:26} mediane {:5.1f}s  pire {:5.1f}s  (n={})".format(nom, statistics.median(v), v[-1], len(v)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("rejouer")
    a.add_argument("etiquette")
    a.add_argument("--ids")
    a.add_argument("--repete", type=int, default=1)
    a.add_argument("--corpus", choices=("corpus", "controle"), default="corpus")
    a.add_argument("--modele", default=None)
    a.set_defaults(f=rejouer)
    b = sp.add_parser("noter")
    b.add_argument("etiquettes", nargs="+")
    b.set_defaults(f=noter)
    r = sp.add_parser("regle")
    r.add_argument("etiquettes", nargs="+")
    r.set_defaults(f=regle)
    g = sp.add_parser("boutons")
    g.set_defaults(f=boutons)
    e = sp.add_parser("etapes")
    e.add_argument("jours", type=int, nargs="?", default=14)
    e.set_defaults(f=etapes)
    args = ap.parse_args()
    args.f(args)
