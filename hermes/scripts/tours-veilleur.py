#!/usr/bin/env python3
"""Veilleur des tours du proxy Claude : previent USER quand un agent meurt en silence.

Le healthcheck de claude-proxy ne surveille que le PROCESS. Un tour qui se fait
tuer (client parti, timeout, erreur) ou qui reste fige ne declenchait rien :
USER voyait simplement une reponse qui n'arrive jamais. Le proxy expose /encours
pour ca, mais personne ne le lisait.

Deux alertes, une seule fois par tour :
  - fin anormale : issue = coupure, timeout ou erreur. Tue si la passerelle
    s'arretait de facon planifiee ; sinon UNE alerte groupee par fenetre de
    2 min (qg_coupures.py, partage avec qg-pouls.py)
  - tour fige    : silence du CLI au-dela de SEUIL_SILENCE_S, sans issue

Etat : ~/.hermes/tours-veilleur.json
Option --test : poste l'etat courant sans rien filtrer.
"""
import json, os, re, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime
from qg_adresse import adresse
import qg_coupures

HOME = os.path.expanduser("~")
ETAT = f"{HOME}/.hermes/tours-veilleur.json"
ENV = f"{HOME}/.hermes/.env"
ENCOURS = os.environ.get("TOURS_ENCOURS", "http://127.0.0.1:8000/encours")
CHAT, THREAD = adresse()
LOG_GATEWAY = f"{HOME}/.hermes/logs/gateway.log"
LOG_AGENT = f"{HOME}/.hermes/logs/agent.log"
MARGE_ARRET_S = 15             # ecart tolere entre l'arret demande et la coupure (vu : 6 s)
SEUIL_SILENCE_S = 900          # 15 min sans un octet du CLI
TTL_ETAT_S = 6 * 3600          # oubli des tours vus, pour ne pas gonfler


def env(cle):
    try:
        for l in open(ENV):
            if l.startswith(cle + "="):
                return l.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def poster(texte):
    tok = env("TELEGRAM_BOT_TOKEN")
    if not tok:
        print(f"pas de TELEGRAM_BOT_TOKEN, message non envoye :\n{texte}", file=sys.stderr)
        return
    data = urllib.parse.urlencode({"chat_id": CHAT, "message_thread_id": THREAD,
                                   "text": texte}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage",
                           data, timeout=20).read()


def charger():
    try:
        return json.load(open(ETAT))
    except (OSError, ValueError):
        return {}


def enregistrer(etat):
    limite = time.time() - TTL_ETAT_S
    etat = {k: v for k, v in etat.items() if v > limite}
    tmp = ETAT + ".tmp"
    json.dump(etat, open(tmp, "w"))
    os.replace(tmp, ETAT)


def arrets_voulus():
    """Instants ou le gateway a coupe un tour lui-meme : /stop, nouvelle commande, reset.

    Une coupure qui tombe sur l'un d'eux n'est pas une mort : USER a appuye sur Stop
    ou a relance. Ne pas l'alerter (USER, 2026-09-30 : « une erreur qui n'est meme
    pas reelle »).
    Depuis le 2026-10-13 : aussi quand Hermes annule son propre appel (agent.log,
    « Interrupt requested », « reason=interrupted ») parce que USER a ecrit pendant
    le tour, ou qu'une relecture de fond a ete remplacee. Toutes les coupures
    datees du 06 au 13/10 etaient de ce type.
    """
    motifs = [
        (LOG_GATEWAY, re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ .*Invalidated run generation "
                                 r".*\((stop_command|new_command|session_reset)\)")),
        # Redemarrage prevu du gateway (systemd SIGTERM) : le 2026-10-27 a 21:13,
        # 2 tours Sonnet sans un octet ont ete alertes « morts » (fausse alerte).
        (LOG_GATEWAY, re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ .*"
                                 r"(Received SIGTERM as a planned gateway stop|Shutdown \(final-cleanup\))")),
        (LOG_AGENT, re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ .*"
                               r"(Interrupt requested|Turn ended: reason=interrupted)")),
    ]
    instants = []
    for chemin, motif in motifs:
        try:
            with open(chemin, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 2_000_000))
                for l in f.read().decode("utf-8", "replace").splitlines():
                    m = motif.match(l)
                    if m:
                        instants.append(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp())
        except OSError:
            pass
    return instants


def encours():
    return json.load(urllib.request.urlopen(ENCOURS, timeout=10))


def main():
    test = "--test" in sys.argv
    try:
        d = encours()
    except (urllib.error.URLError, OSError, ValueError) as e:
        # Le proxy injoignable est deja le rayon du healthcheck : on se tait.
        print(f"/encours injoignable : {e}", file=sys.stderr)
        return

    tours = d.get("tours", [])
    if test:
        poster(f"Veilleur des tours : {len(tours)} tour(s) suivi(s), "
               f"{d.get('running', 0)} en cours, {d.get('queued', 0)} en file.")
        return

    etat = charger()
    maintenant = time.time()
    messages = []
    arrets = arrets_voulus()

    # Les morts : un arret planifie de la passerelle les explique (on se tait),
    # sinon UNE alerte par fenetre de 2 min (qg_coupures, partage avec qg-pouls).
    morts = [t for t in tours
             if t.get("issue") in qg_coupures.MORTS and f"{t.get('id')}:{t.get('issue')}" not in etat]
    muets, groupes = qg_coupures.trier(
        morts, voulue=lambda fin: any(abs(fin - a) <= MARGE_ARRET_S for a in arrets))
    a_noter = list(muets)
    for cles, texte in groupes:
        messages.append(texte)
        a_noter += cles
    for k in a_noter:
        etat[k] = maintenant

    for t in tours:
        tid = str(t.get("id"))
        silence = int(t.get("silenceS") or 0)
        age = int(t.get("ageS") or 0)

        if t.get("issue") is None and silence >= SEUIL_SILENCE_S:
            cle = f"{tid}:fige"
            if cle in etat:
                continue
            etat[cle] = maintenant
            messages.append(f"Agent figé : {silence // 60} min sans un octet, "
                            f"lancé il y a {age // 60} min.\n"
                            f"Demande : {qg_coupures.demande(t)}.")

    for m in messages:
        poster(m)
    qg_coupures.noter(a_noter)
    enregistrer(etat)
    print(f"{len(tours)} tour(s), {len(messages)} alerte(s)")


if __name__ == "__main__":
    main()
