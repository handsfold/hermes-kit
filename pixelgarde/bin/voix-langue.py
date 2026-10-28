#!/usr/bin/env python3
"""Juge si un tour de micro en mains libres vient de USER parlant francais.

Usage : voix-langue.py <texte_fr> <auto.json> [libelles]
  texte_fr   la transcription forcee en francais (celle qu'on enverrait)
  auto.json  la reponse verbose_json de Groq SANS langue imposee : elle dit
             quelle langue whisper a reconnue
  libelles   fichier <id>.libelles du rapport ecoute (boutons du moment)

Ecrit « ok » ou « rejet : <raison> » sur la sortie, code 0 dans les 2 cas.

Pourquoi deux etages (mesure du 2026-10-12, Groq whisper-large-v3-turbo) :
forcer language=fr ne protege de rien, whisper ecrit alors du francais
approximatif sous une chanson anglaise. Et la detection seule ne suffit pas :
« Oui » seul sort en portugais (« Oi »), en japonais (« うい »), « Ouais » en
chinois, « Stop » en anglais. Donc :
  1. langue reconnue = francais : accepte ;
  2. sinon, accepte seulement une commande courte connue (oui, non, detail,
     stop, un bouton du rapport...), sauf si whisper libre a entendu un mot
     anglais (« No », « Yes ») ;
  3. tout le reste est rejete : chanson, radio, anglais, thai.
Si la detection a echoue (quota, reseau), on accepte : mieux vaut un tour de
trop qu'un USER que le micro n'entend plus.
"""
import json
import re
import sys
import unicodedata

# Mots d'une commande courte. Une phrase n'est « commande » que si TOUS ses
# mots sont ici (ou dans les boutons du rapport), et qu'elle en a 4 au plus.
COMMANDES = set("""
oui ouais ouai non nan detail details stop fin pause relis relire repete repeter
redis ok okay daccord accord vas y vasy go lance le la attends attend termine
raccroche silence merci cest bon au revoir plus tard parfait super top envoie
""".split())

# Ce que whisper libre rend quand il entend de l'anglais dans un mot court.
ANGLAIS = {"yes", "yeah", "yep", "no", "nope", "hey", "baby",
           "love", "oh", "the", "you", "i", "and", "we", "me", "my"}

# Les hallucinations classiques de whisper sur de la musique ou du silence
# en francais : sous-titres de YouTube, appels a s'abonner.
HALLUCINATIONS = ("sous-titr", "amara", "merci d'avoir regard", "abonnez",
                  "merci de votre attention", "radio-canada", "st' 501")


def mots(texte):
    t = unicodedata.normalize("NFD", texte.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("’", "'").replace("'", "").replace("-", " ")
    return re.findall(r"[a-z0-9]+", t)


def juger(texte_fr, auto, libelles=""):
    bas = texte_fr.lower()
    for h in HALLUCINATIONS:
        if h in bas:
            return "rejet : hallucination whisper (%s)" % h
    if not auto:
        return "ok"
    langue = (auto.get("language") or "").strip().lower()
    if not langue:
        return "ok"
    if langue in ("french", "fr"):
        return "ok"
    vocab = COMMANDES | set(mots(libelles))
    m = mots(texte_fr)
    if m and len(m) <= 4 and all(x in vocab for x in m):
        libre = mots(auto.get("text") or "")
        if libre and all(x in ANGLAIS for x in libre):
            return "rejet : mot anglais (%s)" % " ".join(libre)
        return "ok"
    return "rejet : langue %s (%s)" % (langue, (auto.get("text") or "").strip()[:60])


def main():
    texte_fr = sys.argv[1] if len(sys.argv) > 1 else ""
    auto = None
    if len(sys.argv) > 2:
        try:
            with open(sys.argv[2], encoding="utf-8") as f:
                auto = json.load(f)
            if not isinstance(auto, dict) or "error" in auto:
                auto = None
        except Exception:
            auto = None
    libelles = ""
    if len(sys.argv) > 3:
        try:
            with open(sys.argv[3], encoding="utf-8") as f:
                libelles = " ".join(l.split("\t", 1)[-1] for l in f)
        except Exception:
            pass
    print(juger(texte_fr, auto, libelles))


if __name__ == "__main__":
    main()
