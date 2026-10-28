#!/usr/bin/env python3
"""journal : memoire du coach. Lit et ecrit ~/Bureau/Projets/contexte/journal.md

Le coach y pose ses questions, USER y depose ses reponses.
Le lendemain, le coach relit la derniere reponse et s'en sert.

Format d'une journee :

## 2026-08-21
- Q 07:52 · Qu'est-ce qui bloque vraiment sur X ?
- R 09:14 · j'ai pas envie de toucher au paiement Stripe
"""
import os
import re
from datetime import date, datetime, timedelta

FICHIER = os.path.expanduser("~/Bureau/Projets/contexte/journal.md")
ENTETE = """# Journal du coach

Ecrit par la machine et par USER. Le coach pose une question par passage,
USER repond avec `focus note "..."` ou simplement en repondant sur Telegram.

Le coach relit la derniere reponse au passage suivant. C'est la boucle.

Format : `- Q hh:mm · question` / `- R hh:mm · reponse`

"""
JOUR = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
LIGNE = re.compile(r"^-\s*([QR])\s+(\d{2}:\d{2})\s*·\s*(.*?)\s*$")


def _lignes():
    if not os.path.exists(FICHIER):
        return []
    return open(FICHIER, encoding="utf-8").read().splitlines()


def _ecrire(lignes):
    os.makedirs(os.path.dirname(FICHIER), exist_ok=True)
    open(FICHIER, "w", encoding="utf-8").write("\n".join(lignes).rstrip() + "\n")


def charger():
    """Retourne [{'jour','type','heure','texte'}] du plus ancien au plus recent."""
    out, jour = [], None
    for l in _lignes():
        m = JOUR.match(l)
        if m:
            jour = m.group(1)
            continue
        m = LIGNE.match(l)
        if m and jour:
            out.append({
                "jour": jour, "type": m.group(1),
                "heure": m.group(2), "texte": m.group(3),
            })
    return out


def ajouter(type_, texte):
    """Ajoute une Q ou une R dans la section du jour, la creant au besoin."""
    texte = " ".join(texte.split())
    if not texte:
        return
    lignes = _lignes() or ENTETE.splitlines()
    auj = date.today().isoformat()
    heure = datetime.now().strftime("%H:%M")
    idx = None
    for i, l in enumerate(lignes):
        m = JOUR.match(l)
        if m and m.group(1) == auj:
            idx = i + 1
            while idx < len(lignes) and (LIGNE.match(lignes[idx]) or not lignes[idx].strip()):
                if LIGNE.match(lignes[idx]):
                    idx += 1
                else:
                    break
            break
    if idx is None:
        # jours les plus recents en haut, juste apres l'entete
        anc = next((i for i, l in enumerate(lignes) if JOUR.match(l)), len(lignes))
        bloc = [f"## {auj}", f"- {type_} {heure} · {texte}", ""]
        lignes[anc:anc] = bloc
    else:
        lignes.insert(idx, f"- {type_} {heure} · {texte}")
    _ecrire(lignes)


def derniere_question():
    qs = [e for e in charger() if e["type"] == "Q"]
    return qs[-1] if qs else None


def reponses_depuis(jours=2):
    """Reponses des N derniers jours, plus recentes en premier."""
    limite = (date.today() - timedelta(days=jours)).isoformat()
    rs = [e for e in charger() if e["type"] == "R" and e["jour"] >= limite]
    return sorted(rs, key=lambda e: (e["jour"], e["heure"]), reverse=True)


def sans_reponse():
    """True si la derniere question du jour n'a recu aucune reponse apres elle."""
    j = charger()
    qs = [i for i, e in enumerate(j) if e["type"] == "Q"]
    if not qs:
        return False
    dernier_q = qs[-1]
    return not any(e["type"] == "R" for e in j[dernier_q + 1:])


def deja_pose_aujourdhui():
    auj = date.today().isoformat()
    return any(e["type"] == "Q" and e["jour"] == auj for e in charger())


def questions_recentes(n=6):
    return [e["texte"] for e in charger() if e["type"] == "Q"][-n:]
