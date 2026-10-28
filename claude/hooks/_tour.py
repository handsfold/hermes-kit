"""Lecture du tour en cours dans le transcript d'une session Claude Code.

Module partage par les hooks Stop de regles-texte-en-hooks (2026-10-07) :
tiret-interdit.py, verif-avant-annonce.py, prochaine-etape.py.
Ne leve jamais : sur toute erreur, renvoie un tour vide.
"""
import json


def lire_tour(transcript, resultats=None):
    """(dernier_texte, outils, demande) depuis le dernier vrai message de USER.

    outils : liste chronologique de (nom, entree) des tool_use du tour.
    demande : texte du message qui a ouvert le tour (str, '' si inconnu).
    resultats : dict facultatif, rempli avec {indice de l'outil: (en_erreur, texte)}
    (ajout du 2026-10-13, pour juger si une verification a reussi).
    """
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            lignes = f.readlines()
    except (OSError, TypeError):
        return "", [], ""
    texte, outils, demande = "", [], ""
    ids, sorties = [], {}
    for l in reversed(lignes):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        msg = e.get("message") or {}
        contenu = msg.get("content")
        if e.get("type") == "user":
            if isinstance(contenu, str):
                demande = contenu
                break
            blocs = [c for c in contenu or [] if isinstance(c, dict)]
            for c in blocs:
                if c.get("type") == "tool_result":
                    t = c.get("content")
                    if isinstance(t, list):
                        t = " ".join(x.get("text", "") for x in t if isinstance(x, dict))
                    sorties[c.get("tool_use_id")] = (bool(c.get("is_error")), str(t or ""))
            if any(c.get("type") == "text" for c in blocs):
                demande = " ".join(c.get("text", "") for c in blocs if c.get("type") == "text")
                break
            continue
        if e.get("type") != "assistant" or not isinstance(contenu, list):
            continue
        for c in reversed(contenu):
            if c.get("type") == "text" and not texte:
                texte = c.get("text", "")
            elif c.get("type") == "tool_use":
                outils.append((c.get("name", ""), c.get("input") or {}))
                ids.append(c.get("id"))
    outils.reverse()
    ids.reverse()
    if resultats is not None:
        for i, tid in enumerate(ids):
            if tid in sorties:
                resultats[i] = sorties[tid]
    return texte, outils, demande
