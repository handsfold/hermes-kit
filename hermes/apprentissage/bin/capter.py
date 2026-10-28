#!/usr/bin/env python3
"""Capte les signaux de feedback de USER sur la FORME et la PERTINENCE des reponses.

Deterministe, aucun LLM, aucun cout. Le tri fin est fait plus tard par la boucle
a deux agents : ici on ratisse large mais borne.

Le signal utile n'est pas l'erreur technique (deja couverte par retro-extract.py),
c'est la phrase ou USER dit ce qu'il attend d'une reponse : trop long, hors sujet,
mal presente, ou au contraire exactement ce qu'il voulait.

Sortie : ajoute les nouveaux signaux dans ~/.hermes/apprentissage/signaux.jsonl
et imprime un resume sur stdout.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta

BASE = os.path.expanduser("~/.hermes/apprentissage")
SESS = os.path.expanduser("~/.hermes/sessions")
DB = os.path.expanduser("~/.hermes/state.db")
SIGNAUX = os.path.join(BASE, "signaux.jsonl")

# Chaque motif nomme CE QUE USER REPROCHE OU APPROUVE, pas son humeur.
# Un motif = un axe sur lequel une regle pourra se former.
NEGATIF = {
    "longueur": r"\b(trop long|trop de texte|trop verbeux|abr[eè]ge|plus court|"
                r"r[eé]sume|tu parles trop|pav[eé]|c'est long)\b",
    "bruit": r"\b(flood|pour rien|j'ai pas besoin|je n'ai pas besoin|inutile|"
             r"sert [aà] rien|arr[eê]te de|pourquoi [cç]a m'envoie|pourquoi tu m'envoies|"
             r"encombre|pollue)\b",
    "hors_sujet": r"\b(c'est pas ce que|je n'ai pas demand[eé]|j'ai pas demand[eé]|"
                  r"[aà] c[oô]t[eé] de la plaque|hors sujet|tu r[eé]ponds pas [aà]|"
                  r"relis ma question|ma question c'[eé]tait)\b",
    "erreur_de_fond": r"\b(tu te trompes|c'est faux|non[,.] +(en fait|pas)|au contraire|"
                      r"tu confonds|c'est inexact|v[eé]rifie avant)\b",
    "oubli_de_repondre": r"\b(tu oublies de me r[eé]pondre|tu n'as pas r[eé]pondu|"
                         r"et ma question|tu as oubli[eé]|alors\s*\?$)",
    "presentation": r"\b(fais(-| )en un menu|en boutons|pas de tableau|mets [cç]a en|"
                    r"j'aime pas devoir taper|plus pratique|illisible|mal pr[eé]sent[eé])\b",
    "langue": r"(pourquoi c'est (en |)anglais|[cç]a doit [eê]tre en fran[cç]ais|"
              r"pas en anglais|besoin de l'avoir en fran[cç]ais|r[eé]ponds en fran[cç]ais|"
              r"parle fran[cç]ais)",
    "repetition": r"\b(je t'ai d[eé]j[aà] dit|comme je (t'ai |)ai dit|je r[eé]p[eè]te|"
                  r"encore une fois|combien de fois)\b",
    "sur_action": r"\b(je t'ai pas demand[eé] de|touche [aà] rien|ne fais rien|"
                  r"pour le moment ne|juste un tour d'horizon|arr[eê]te)\b",
}
POSITIF = {
    "valide": r"\b(parfait|nickel|exactement [cç]a|impec|excellent|"
              r"tr[eè]s bien vu|c'est exactement|bravo|tr[eè]s bonne r[eé]ponse)\b",
}
# Un « c'est ca ? » au milieu d'une question n'est pas une validation. Un compliment
# se place en tete de message et ne s'accompagne pas d'une nouvelle demande.
POSITIF_FENETRE = 45
# La relance de statut n'est ni un reproche ni un compliment : c'est une question
# neutre. Elle etait donc invisible pour les deux dictionnaires ci-dessus, alors que
# l'audit du 2026-08-26 en compte 40 sur 60 jours, jusqu'a 8 dans la meme journee.
# Le signal n'est pas ce que USER dit, c'est le fait qu'il ait DU le demander.
RELANCE = {
    "relance_de_statut": r"^\s*(\[[^\]]{0,20}\]\s*)?("
                         r"(ca|ou) en (est|es|ets) (ou|t on)|on en (est|es) ou|"
                         r"ou (on |)en (est|es|sommes)( on|)|ou j'en suis|"
                         r"ca (en |)est ou|c'est ou|ca avance|ca donne quoi|"
                         r"(c'est|tu as|t'as) (fini|termine|bon)|toujours en cours|"
                         r"du coup|et donc|et alors|alors|et sinon"
                         r")\s*[?!.]*\s*$",
}
# Une relance tient en quelques mots : le filtre de longueur ci-dessous l'ecarterait.
RELANCE_MAX = 60

# Un message qui ne fait qu'accepter une proposition n'est pas un feedback de forme.
TROP_COURT = 12


def sessions_recentes(jours):
    cutoff = datetime.now() - timedelta(days=jours)
    out = []
    if not os.path.isdir(SESS):
        return out
    for name in sorted(os.listdir(SESS)):
        if not name.endswith(".jsonl"):
            continue
        p = os.path.join(SESS, name)
        try:
            if datetime.fromtimestamp(os.path.getmtime(p)) < cutoff:
                continue
        except OSError:
            continue
        out.append(p)
    return out


def sans_accents(t):
    """USER ecrit indifferemment « ca en est ou » et « ca en est ou ? » avec accents."""
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


def texte(d):
    c = d.get("content")
    if isinstance(c, list):
        parts = []
        for b in c:
            if isinstance(b, dict):
                parts.append(str(b.get("text") or ""))
            else:
                parts.append(str(b))
        return " ".join(parts)
    return str(c or "")


def lire_jsonl(path):
    msgs = []
    try:
        for line in open(path, errors="replace"):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("role") in ("user", "assistant"):
                msgs.append(d)
    except OSError:
        return []
    return msgs


def sessions_db(jours):
    """Depuis le 2026-09-14, Hermes n'ecrit plus ~/.hermes/sessions/*.jsonl :
    tout part dans state.db. Sans cette lecture, signaux.jsonl restait fige
    au 14/09 (reparation du 2026-10-13, meme correctif que retro-extract.py)."""
    import sqlite3
    if not os.path.exists(DB):
        return []
    since = (datetime.now() - timedelta(days=jours)).timestamp()
    con = sqlite3.connect("file:{}?mode=ro".format(DB), uri=True, timeout=5)
    rows = con.execute(
        "SELECT session_id, role, content, timestamp FROM messages"
        " WHERE timestamp >= ? AND role IN ('user','assistant')"
        " ORDER BY session_id, timestamp, id", (since,))
    par = {}
    for sid, role, content, ts in rows:
        par.setdefault(sid, []).append({
            "role": role, "content": content,
            "timestamp": datetime.fromtimestamp(ts).isoformat()})
    con.close()
    return [("db:" + k, v) for k, v in par.items()]


def scanner(label, msgs):
    """Retourne les couples (reponse precedente, reproche) d'une session."""
    out = []
    derniere_reponse = ""
    for d in msgs:
        if d.get("role") == "assistant":
            t = texte(d).strip()
            if t:
                derniere_reponse = t
            continue
        txt = texte(d).strip()
        low = txt.lower()
        # Les injections du gateway ne sont pas la voix de USER.
        if re.match(r"\s*\[(note|system note|syst)", low):
            continue
        relance = (len(txt) <= RELANCE_MAX
                   and any(re.search(p, sans_accents(low)) for p in RELANCE.values()))
        if not relance and len(txt) < TROP_COURT:
            continue
        tete = re.sub(r"^\s*\[[^\]]{0,20}\]\s*", "", low)[:POSITIF_FENETRE]
        motifs = [k for k, p in NEGATIF.items() if re.search(p, low)]
        classe = "negatif"
        if not motifs:
            motifs = [k for k, p in POSITIF.items() if re.search(p, tete)]
            classe = "positif"
        if not motifs and relance:
            motifs = ["relance_de_statut"]
            classe = "relance"
        if not motifs:
            continue
        # Sans reponse en face, on ne sait pas sur QUOI porte le reproche.
        if not derniere_reponse:
            continue
        sig = {
            "ts": d.get("timestamp", ""),
            "session": label,
            "classe": classe,
            "motifs": motifs,
            "user": txt[:700],
            "reponse_avant": derniere_reponse[-900:],
            "taille_reponse": len(derniere_reponse),
        }
        sig["id"] = hashlib.sha1(
            (sig["session"] + sig["ts"] + txt[:120]).encode()
        ).hexdigest()[:16]
        out.append(sig)
    return out


def deja_vus():
    vus = set()
    if os.path.exists(SIGNAUX):
        for line in open(SIGNAUX, errors="replace"):
            try:
                vus.add(json.loads(line)["id"])
            except Exception:
                continue
    return vus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jours", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    os.makedirs(BASE, exist_ok=True)
    vus = deja_vus()
    neufs = []
    sources = [(os.path.basename(p), lire_jsonl(p)) for p in sessions_recentes(a.jours)]
    sources += sessions_db(a.jours)
    for label, msgs in sources:
        for s in scanner(label, msgs):
            if s["id"] not in vus:
                vus.add(s["id"])
                neufs.append(s)

    neufs.sort(key=lambda s: s["ts"])
    if neufs and not a.dry_run:
        with open(SIGNAUX, "a") as f:
            for s in neufs:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

    par_motif = {}
    for s in neufs:
        for m in s["motifs"]:
            par_motif[m] = par_motif.get(m, 0) + 1
    print(json.dumps({
        "nouveaux": len(neufs),
        "par_motif": dict(sorted(par_motif.items(), key=lambda kv: -kv[1])),
        "fenetre_jours": a.jours,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
