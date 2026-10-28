#!/usr/bin/env python3
"""Memoire des personnes pour le mode « Repondre » de Creeper (2.49).

Une personne = un dossier, quel que soit le reseau : Tinder, puis WhatsApp,
puis Instagram, c'est le meme dossier. Fichiers : ~/.hermes/pixel-ecrire/personnes/<id>.json

Sous-commandes :
  contexte <ecran.txt>                 bloc de texte a ajouter a la consigne
  maj <ecran.txt> <reponse.txt> <personne.json> [consigne de USER]
                                       apres la reponse : messages vus,
                                       verdict du brouillon precedent,
                                       identite donnee par le modele
  liste                                resume lisible de tout ce qui est connu

Ce qui rend le systeme « intelligent » sans modele de plus :
  - les messages vus a l'ecran s'accumulent (l'ecran n'en montre que 15) ;
  - chaque brouillon est compare a ce que USER a REELLEMENT envoye ensuite
    (retenu tel quel, retouche, ou ignore) ;
  - le style de USER (longueur, emojis, majuscules) est calcule sur ses vrais
    messages, toutes personnes confondues.
"""
import hashlib
import json
import os
import re
import sys
import time
import unicodedata

DOSSIER = os.environ.get("PERSONNES_DIR") or os.path.expanduser("~/.hermes/pixel-ecrire/personnes")

APPLIS = {
    "com.instagram.android": "Instagram",
    "com.tinder": "Tinder",
    "com.whatsapp": "WhatsApp",
    "com.whatsapp.w4b": "WhatsApp Business",
    "jp.naver.line.android": "LINE",
    "org.telegram.messenger": "Telegram",
    "org.thoughtcrime.securesms": "Signal",
    "com.facebook.orca": "Messenger",
    "com.facebook.katana": "Facebook",
    "com.google.android.apps.messaging": "SMS",
    "com.samsung.android.messaging": "SMS",
    "com.bumble.app": "Bumble",
    "com.hinge.app": "Hinge",
    "com.snapchat.android": "Snapchat",
    "com.zhiliaoapp.musically": "TikTok",
    "com.twitter.android": "X",
    "com.google.android.gm": "Gmail",
}

# Lignes de l'interface qui ne sont pas des messages.
BRUIT = {
    "retour", "accueil", "récents", "recents", "sélecteur ime", "caméra", "camera",
    "votre message…", "votre message...", "message vocal,", "voir le profil",
    "appuyez deux fois pour ❤", "envoyer", "message", "gif", "autocollant",
    "photos", "micro", "plus", "j'aime", "like", "type a message", "message…", "appel vocal", "appel vidéo", "appel video", "galerie", "stickers", "ajout du blend", "ajouter un blend", "sticker", "emoji", "clavier",
}
HEURE = re.compile(r"^\d{1,2}[:h]\d{2}(\s?[ap]m)?$|^(hier|aujourd.hui|today|yesterday|lu|read|vu|seen|envoy[ée]|sent|delivered)$", re.I)
DATE = re.compile(r"^(\d{1,2}\s\w+\.?(\s\d{4})?|\w{3,9}\.?\s\d{1,2}|lun|mar|mer|jeu|ven|sam|dim|mon|tue|wed|thu|fri|sat|sun)\b.*\d{1,2}[:h]\d{2}.*$|^\d{1,2}/\d{1,2}(/\d{2,4})?$", re.I)
# Libelles de boutons de l'appli, jamais un nom de contact ni un message
# (releve Tinder du 2026-10-23 : « Quitter la discussion » prise pour le nom).
LIBELLE_UI = re.compile(
    r"^(bouton\b|quitter|retour\b|back\b|navigate|photo de profil|profile (photo|picture)|badge|outils|menu\b|"
    r"plus d.options|more options|options\b|rechercher|search\b|appel|call\b|vid[eé]o|infos?\b|voir\b|ouvrir|"
    r"fermer|close\b|signaler|report\b|bloquer|block\b|photos?\b|image\b|gif\b|m[eé]dias?\b|envoy[eé]|"
    r"s[eé]lecteur|nouveau message|joindre|attach|emoji|autocollant|sticker|enregistr|voice message|message vocal)", re.I)
PRESENCE = re.compile(r"^(en ligne|online|hors ligne|offline|[ée]crit|typing|derni[eè]re? (connexion|activit[eé])|last seen|actif|active|vu (pour la )?derni|vérifié|verified)", re.I)
SAISIE = re.compile(r"^(votre message|message vocal|[ée]crire un message|[ée]crivez|type a message|ajouter un message|aa$)", re.I)
LIGNE = re.compile(r"^\[(C|G|D|\?)\]\s*\{(\d+)-(\d+)\}\s*(.*)$")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿❤️]")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def mots(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z]{4,}", s)}


def lire_fichier(p, defaut=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def ecrire_fichier(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def toutes():
    out = []
    if not os.path.isdir(DOSSIER):
        return out
    for n in sorted(os.listdir(DOSSIER)):
        if n.endswith(".json"):
            d = lire_fichier(os.path.join(DOSSIER, n))
            if isinstance(d, dict) and d.get("id"):
                out.append(d)
    return out


def chemin(ident):
    return os.path.join(DOSSIER, re.sub(r"[^a-z0-9_-]", "", ident) + ".json")


def lire_ecran(chemin_ecran):
    """(appli, en-tete, messages[(cote, texte)]) depuis le texte de ecrire.sh."""
    try:
        lignes = open(chemin_ecran, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return "", "", []
    appli = ""
    if lignes and lignes[0].startswith("Appli au premier plan"):
        pk = [x.strip() for x in lignes[0].split(":", 1)[-1].split(",")]
        for p in pk:
            if p in APPLIS:
                appli = APPLIS[p]
                break
        if not appli and pk:
            autres = [p for p in pk if "launcher" not in p and "systemui" not in p]
            appli = (autres or pk)[0].split(".")[-1].capitalize()
    brut = []
    for l in lignes[1:]:
        m = LIGNE.match(l)
        if m and m.group(4).strip():
            brut.append((m.group(1), m.group(4).strip()))
    entete, apres_photo, prio = [], False, []
    for _, t in brut[:16]:
        bas = t.lower()
        m = re.match(r"^(?:photo de profil de|profile (?:photo|picture) of)\s+(.+)$", t, re.I)
        if m:
            prio.append(m.group(1).strip())
            apres_photo = False
            continue
        if re.match(r"^(photo de profil|profile (photo|picture))$", bas):
            apres_photo = True
            continue
        if bas in BRUIT or HEURE.match(t) or SAISIE.match(t) or LIBELLE_UI.match(t) or DATE.match(t):
            continue
        if apres_photo:
            prio.append(t)
            apres_photo = False
            continue
        entete.append(t)
    entete = prio + entete
    # Les messages commencent apres le bloc d'en-tete (boutons, nom, statut) et
    # finissent au champ de saisie. Avant 2026-10-23 le debut etait le 1er repere
    # d'heure : sur Tinder c'etait « Envoye », au milieu de la conversation.
    titres = set(prio) if prio else set(entete[:1])
    debut = 0
    while debut < min(len(brut), 16):
        t = brut[debut][1]
        if t.lower() in BRUIT or LIBELLE_UI.match(t) or SAISIE.match(t) or PRESENCE.match(t) or t in titres:
            debut += 1
        else:
            break
    fin = next((i for i, (c, t) in enumerate(brut) if i > debut and SAISIE.match(t)), len(brut))
    msgs = []
    for c, t in brut[debut:fin]:
        if c in ("G", "D") and t.lower() not in BRUIT and not HEURE.match(t) and not DATE.match(t) \
                and not LIBELLE_UI.match(t):
            msgs.append((c, t))
    return appli, " | ".join(entete), msgs


def nom_contact(entete):
    """Le nom du contact = premiere ligne de l'en-tete de l'ecran (2.54)."""
    return (entete or "").split(" | ")[0].strip()


def texte_ecran(chemin_ecran):
    """Tout le texte de l'ecran, normalise : sert a verifier un nom donne par le modele."""
    try:
        lignes = open(chemin_ecran, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return ""
    out = []
    for l in lignes[1:]:
        m = LIGNE.match(l)
        if m:
            out.append(m.group(4))
    return norm(" ".join(out))


def style_de_vj(personnes):
    """Statistiques et exemples tires des vrais messages de USER."""
    textes = []
    for p in personnes:
        textes += [m["t"] for m in p.get("messages", []) if m.get("c") == "D"]
    textes = [t for t in textes if len(t) > 1][-60:]
    if len(textes) < 3:
        return ""
    longueurs = sorted(len(t) for t in textes)
    med = longueurs[len(longueurs) // 2]
    avec_emoji = sum(1 for t in textes if EMOJI.search(t)) * 100 // len(textes)
    point_fin = sum(1 for t in textes if t.rstrip().endswith(".")) * 100 // len(textes)
    maj = sum(1 for t in textes if t[:1].isupper()) * 100 // len(textes)
    mine = [e for t in textes for e in EMOJI.findall(t) if e not in "️"]
    freq = {}
    for e in mine:
        freq[e] = freq.get(e, 0) + 1
    top = " ".join(e for e, _ in sorted(freq.items(), key=lambda x: -x[1])[:4]) or "aucun"
    ex = "\n".join("  - " + t[:140] for t in textes[-8:])
    return ("Style REEL de USER, mesure sur {} de ses messages envoyes : longueur mediane {} caracteres ; "
            "{} % contiennent un emoji (les siens : {}) ; {} % se terminent par un point ; "
            "{} % commencent par une majuscule.\nSes derniers messages, a imiter :\n{}"
            ).format(len(textes), med, avec_emoji, top, point_fin, maj, ex)


def identifier(personnes, appli, entete, msgs):
    """(dossier, preuve) : le titre IDENTIQUE d'abord, puis les messages deja vus.

    Le titre seul se trompe quand l'appli ecrit un libelle a sa place ; les
    messages, eux, sont propres a une conversation. 2 messages communs (ou 1
    message long) sur le MEME reseau suffisent (2026-10-23)."""
    p = trouver(personnes, appli, entete)
    if p:
        return p, "titre"
    vus = {}
    for c, t in msgs:
        n = norm(t)
        if len(n) >= 8:
            vus[n] = len(n)
    if not vus or not appli:
        return None, ""
    meilleur, score = None, 0
    for x in personnes:
        connus = {norm(m.get("t", "")) for m in x.get("messages", []) if m.get("app") == appli}
        communs = [n for n in vus if n in connus]
        if not communs:
            continue
        if len(communs) >= 2 or max(vus[n] for n in communs) >= 25:
            sc = len(communs) * 10 + len(x.get("messages", [])) / 1000.0
            if sc > score:
                meilleur, score = x, sc
    if meilleur:
        return meilleur, "messages"
    return None, ""


def trouver(personnes, appli, entete):
    """Le dossier de CE contact sur CE reseau (2.54) : le nom de l'en-tete doit
    etre IDENTIQUE a un nom de compte. Plus de mot cherche dans tout l'ecran :
    un nom connu cite dans un message ou un nom donne par le modele ne suffit
    plus a reconnaitre une conversation. Introuvable = nouvelle personne."""
    n = norm(nom_contact(entete))
    if len(n) < 2 or not appli:
        return None
    trouves = []
    for p in personnes:
        for c in p.get("comptes", []):
            if c.get("appli") == appli and norm(c.get("nom", "")) == n:
                trouves.append(p)
                break
    if not trouves:
        return None
    return max(trouves, key=lambda x: (len(x.get("messages", [])), x.get("maj", 0)))


# Mots qui, dans un message, designent un reseau (« ajoute-moi sur insta »).
INDICES = {
    "Instagram": ["insta", "instagram", "ig"],
    "WhatsApp": ["whatsapp", "whats", "whatsap", "watsapp", "wa"],
    "WhatsApp Business": ["whatsapp", "whats", "wa"],
    "LINE": ["line"],
    "Telegram": ["telegram", "tg"],
    "Snapchat": ["snap", "snapchat"],
    "Tinder": ["tinder"],
    "Messenger": ["messenger", "fb", "facebook"],
    "Facebook": ["messenger", "fb", "facebook"],
    "Signal": ["signal"],
    "SMS": ["sms", "texto"],
    "TikTok": ["tiktok"],
    "X": ["twitter"],
    "Bumble": ["bumble"],
    "Hinge": ["hinge"],
}
JOURS_LIEN = 21


def jetons(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return set(re.findall(r"[a-z0-9]+", s))


def cite_reseau(texte, appli):
    """Le texte nomme-t-il ce reseau (insta, whatsapp...) ?"""
    return bool(jetons(texte) & set(INDICES.get(appli, [])))


def telephone(s):
    """Les 9 derniers chiffres d'un numero (66616505168 et 0616505168 se rejoignent)."""
    c = re.sub(r"\D", "", s or "")
    return c[-9:] if len(c) >= 9 else ""


def _contient_identite(texte, nom):
    """Le pseudo ou le numero `nom` est ecrit dans `texte`."""
    t = telephone(nom)
    if t and t in re.sub(r"\D", "", texte):
        return True
    ids = {w for w in jetons(nom) if len(w) >= 3}
    return bool(ids) and len(norm(nom)) >= 5 and ids <= jetons(texte)


def liens(personnes, appli, tete, msgs):
    """Dossiers d'un AUTRE reseau qui sont peut-etre la meme personne (2.55).

    Un lien entre reseaux se prouve par le dernier echange, jamais par un mot
    commun seul : « on s'ecrit sur WhatsApp, voici mon insta @x », puis le
    contact @x apparait sur Instagram. Meme reseau + autre nom = autre personne.
    Rend [(dossier, 'forte'|'faible', raison)], les fortes d'abord.
    """
    sortie = []
    if not tete or not appli:
        return sortie
    ecran_msgs = [t for _, t in msgs]
    mots_tete = mots(tete)
    maintenant = time.time()
    for x in personnes:
        if any(c.get("appli") == appli for c in x.get("comptes", [])):
            continue  # cette personne a deja un compte ici sous un autre nom : autre personne
        apps_x = {c.get("appli") for c in x.get("comptes", [])}
        raison = ""
        forte = False
        if len(tete.split()) >= 2 and any(norm(tete) == norm(c.get("nom", "")) for c in x.get("comptes", [])):
            raison, forte = "meme nom complet sur l'autre reseau", True
        if not forte:
            for m in x.get("messages", [])[-150:]:
                t = m.get("t", "")
                if (cite_reseau(t, appli) or "@" in t) and _contient_identite(t, tete):
                    raison, forte = "le pseudo ou numero « {} » est ecrit dans un message ({}) : « {} »".format(
                        tete, m.get("app", "?"), t[:80]), True
                    break
        if not forte:
            for a in apps_x:
                for t in ecran_msgs:
                    if not cite_reseau(t, a):
                        continue
                    if any(_contient_identite(t, c.get("nom", "")) for c in x.get("comptes", []) if c.get("appli") == a):
                        raison, forte = "un message de cet ecran cite le compte {} de ce dossier : « {} »".format(a, t[:80]), True
                        break
                if forte:
                    break
        if forte:
            sortie.append((x, "forte", raison))
            continue
        # Faible : un mot commun ET un signe de passage d'un reseau a l'autre, recent.
        pm = set()
        for nom in x.get("noms", []):
            pm |= mots(nom)
        commun = mots_tete & pm
        recent = maintenant - x.get("maj", 0) < JOURS_LIEN * 86400
        passage = any(cite_reseau(m.get("t", ""), appli) for m in x.get("messages", [])[-40:]) or \
            any(cite_reseau(t, a) for t in ecran_msgs for a in apps_x)
        if commun and recent and passage:
            sortie.append((x, "faible", "mot commun ({}) et un message cite le changement de reseau".format(", ".join(sorted(commun)))))
    sortie.sort(key=lambda r: r[1] != "forte")
    return sortie


def fiche_courte(p):
    apps = ", ".join("{} ({})".format(c.get("appli", "?"), c.get("nom", "?")) for c in p.get("comptes", []))
    return "- id={} : {} ; reseaux : {} ; {}".format(
        p["id"], p.get("nom", "?"), apps or "?", (p.get("resume") or "pas de resume")[:140])


def dossier(p):
    L = ["DOSSIER de {} (id={}) :".format(p.get("nom", "?"), p["id"])]
    apps = ", ".join("{} ({})".format(c.get("appli", "?"), c.get("nom", "?")) for c in p.get("comptes", []))
    L.append("Reseaux ou ils se parlent : " + (apps or "?"))
    if p.get("etape"):
        L.append("Ou ils en sont : " + p["etape"])
    if p.get("resume"):
        L.append("Resume : " + p["resume"])
    for f in p.get("faits", [])[-12:]:
        L.append("Fait connu : " + f)
    msgs = p.get("messages", [])[-40:]
    if msgs:
        L.append("Echange complet depuis le debut (les plus anciens en haut ; USER = toi, Elle = l'autre) :")
        for m in msgs:
            L.append("  {} : {}".format("USER" if m["c"] == "D" else "Elle", m["t"][:240]))
    br = [b for b in p.get("brouillons", []) if b.get("verdict")][-6:]
    if br:
        L.append("Ce qui est arrive a tes derniers brouillons (apprends-en) :")
        for b in br:
            L.append("  - propose : « {} » -> {}".format(b["texte"][:140], b["verdict"][:200]))
    return "\n".join(L)


def contexte(chemin_ecran):
    perso = toutes()
    appli, entete, msgs = lire_ecran(chemin_ecran)
    p, _preuve = identifier(perso, appli, entete, msgs)
    sortie = []
    sortie.append("\nMEMOIRE DES PERSONNES (reseau actuel : {}).".format(appli or "inconnu"))
    tete = nom_contact(entete)
    if tete:
        sortie.append("Le nom du contact, lu en haut de l'ecran : « {} ». Dans personne.nom, donne CE nom (ou le pseudo exact affiche a l'ecran). Jamais un nom qui n'est pas ecrit sur l'ecran.".format(tete))
    if perso:
        sortie.append("Personnes deja connues, tous reseaux confondus :")
        sortie += [fiche_courte(x) for x in perso[-25:]]
    else:
        sortie.append("Aucune personne connue pour l'instant : cette conversation sera la premiere.")
    if p:
        sortie.append("\nCette conversation correspond au dossier suivant. Reprends le fil, ne repars JAMAIS de zero :")
        sortie.append(dossier(p))
    else:
        cand = liens(perso, appli, tete, msgs)
        fortes = [c for c in cand if c[1] == "forte"]
        faibles = [c for c in cand if c[1] == "faible"]
        if fortes:
            x, _, raison = fortes[0]
            sortie.append("\nCe contact est la MEME personne qu'un dossier d'un autre reseau (preuve : {}). Reprends son fil :\n{}".format(raison, dossier(x)))
        elif faibles:
            sortie.append("\nPiste de lien entre reseaux, NON prouvee :")
            for x, _, raison in faibles[:2]:
                sortie.append("  {} ({}). Mets son id dans personne.meme_que SEULEMENT si les derniers messages disent que c'est la meme personne ; sinon laisse vide.\n{}".format(
                    x.get("nom"), raison, dossier(x)))
        else:
            sortie.append("\nPersonne nouvelle : aucun dossier ne la reconnait. Ne reprends aucun fait des autres dossiers.")
    st = style_de_vj(perso)
    if st:
        sortie.append("\n" + st)
    return "\n".join(sortie)


def identifiant(nom, perso):
    base = norm(nom)[:12]
    if not base:  # nom thai, arabe, etc. : norm() ne garde que l'ascii
        base = "p" + hashlib.md5((nom or "").encode("utf-8")).hexdigest()[:6]
    ids = {p["id"] for p in perso}
    n = 1
    ident = base
    while ident in ids:
        n += 1
        ident = "{}{}".format(base, n)
    return ident


def fusionner(vers, source):
    """Deux dossiers = la meme personne : on garde un seul."""
    for c in source.get("comptes", []):
        if c not in vers.setdefault("comptes", []):
            vers["comptes"].append(c)
    for n in source.get("noms", []):
        if n not in vers.setdefault("noms", []):
            vers["noms"].append(n)
    vers["messages"] = (vers.get("messages", []) + source.get("messages", []))[-300:]
    vers["faits"] = (vers.get("faits", []) + [f for f in source.get("faits", []) if f not in vers.get("faits", [])])[-30:]
    vers["brouillons"] = (vers.get("brouillons", []) + source.get("brouillons", []))[-20:]
    try:
        os.remove(chemin(source["id"]))
    except OSError:
        pass


def verdict_precedent(p, nouveaux_D, consigne):
    """Compare le dernier brouillon a ce que USER a reellement envoye depuis."""
    br = p.get("brouillons", [])
    if not br or br[-1].get("verdict"):
        return
    b = br[-1]
    cible = norm(b["texte"])
    envoye = None
    for t in nouveaux_D:
        n = norm(t)
        if not n:
            continue
        # Meme texte, ou tres proche : retenu. On compare par mots communs.
        a, c = set(re.findall(r"\w+", b["texte"].lower())), set(re.findall(r"\w+", t.lower()))
        if n == cible or (a and c and len(a & c) / max(len(a | c), 1) >= 0.6):
            envoye = ("retenu tel quel" if n == cible else "retouche par USER, il a envoye : « {} »".format(t[:160]))
            break
    if envoye:
        b["verdict"] = envoye
    elif nouveaux_D:
        b["verdict"] = "ignore, USER a ecrit autre chose : « {} »".format(nouveaux_D[-1][:160])
    elif consigne:
        b["verdict"] = "rejete par USER (consigne : {})".format(consigne[:80])


def maj(chemin_ecran, chemin_rep, chemin_pers, consigne=""):
    os.makedirs(DOSSIER, exist_ok=True)
    perso = toutes()
    appli, entete, msgs = lire_ecran(chemin_ecran)
    info = lire_fichier(chemin_pers, {}) or {}
    if not isinstance(info, dict):
        info = {}
    brouillon = ""
    try:
        brouillon = open(chemin_rep, encoding="utf-8").read().strip()
    except OSError:
        pass
    # 2.54 : l'identite vient de l'ECRAN, jamais du modele seul. Le modele
    # recopiait un nom de la liste des personnes connues, meme sur un ecran
    # sans rapport, et toutes les conversations tombaient dans le meme dossier.
    tete = nom_contact(entete)
    ecran_norm = texte_ecran(chemin_ecran)
    nom = str(info.get("nom") or "").strip()
    if nom and (len(norm(nom)) < 2 or norm(nom) not in ecran_norm):
        sys.stderr.write("nom du modele ignore (absent de l'ecran) : {!r}\n".format(nom))
        nom = ""
    if appli not in APPLIS.values():
        sys.stderr.write("ecran hors messagerie ({}) : aucune personne creee\n".format(appli))
        return
    if not tete:
        tete = nom
    if not tete:
        return  # rien d'identifiable : on ne cree pas un dossier anonyme
    p, preuve = identifier(perso, appli, tete, msgs)
    if p and preuve == "messages":
        sys.stderr.write("reconnu par ses messages : {}\n".format(p["id"]))
    lie = str(info.get("meme_que") or "").strip()
    if not p:
        cand = liens(perso, appli, tete, msgs)
        choisi = next((c for c in cand if c[1] == "forte"), None)
        if not choisi and lie:
            choisi = next((c for c in cand if c[0]["id"] == lie), None)
            if not choisi:
                sys.stderr.write("meme_que refuse : aucune preuve de lien entre {!r} et le dossier {}\n".format(tete, lie))
        if choisi:
            p = choisi[0]
            sys.stderr.write("lien entre reseaux ({}) : {}\n".format(choisi[1], choisi[2]))
    if p:
        # Doublons du meme contact sur le meme reseau : un seul dossier.
        for x in perso:
            if x["id"] != p["id"] and any(c.get("appli") == appli and norm(c.get("nom", "")) == norm(tete)
                                          for c in x.get("comptes", [])):
                fusionner(p, x)
    else:
        p = {"id": identifiant(tete, perso), "nom": tete, "noms": [], "comptes": [],
             "messages": [], "faits": [], "brouillons": [], "cree": int(time.time())}
    for n in (tete, nom):
        if n and n not in p["noms"]:
            p["noms"].append(n)
    if not p.get("nom"):
        p["nom"] = tete
    if appli and not any(c.get("appli") == appli and norm(c.get("nom", "")) == norm(tete) for c in p["comptes"]):
        p["comptes"].append({"appli": appli, "nom": tete})
    # Messages : on ajoute ceux qu'on n'a pas encore, dans l'ordre de l'ecran.
    deja = p.setdefault("messages", [])
    cles = {(m["c"], m["t"]) for m in deja[-80:]}
    nouveaux_D = []
    # Le premier message deja connu aligne l'ecran sur l'historique.
    for c, t in msgs:
        if (c, t) in cles:
            continue
        deja.append({"c": c, "t": t[:400], "app": appli})
        cles.add((c, t))
        if c == "D":
            nouveaux_D.append(t)
    p["messages"] = deja[-300:]
    verdict_precedent(p, nouveaux_D, consigne)
    for champ in ("resume", "etape"):
        v = str(info.get(champ) or "").strip()
        if v:
            p[champ] = v[:300]
    faits = info.get("faits") or []
    if isinstance(faits, list):
        for f in faits[:6]:
            f = str(f).strip()[:200]
            if f and f not in p.setdefault("faits", []):
                p["faits"].append(f)
        p["faits"] = p["faits"][-30:]
    if brouillon:
        p.setdefault("brouillons", []).append(
            {"texte": brouillon[:400], "date": int(time.time()), "app": appli, "verdict": ""})
        p["brouillons"] = p["brouillons"][-20:]
    p["maj"] = int(time.time())
    conv = os.environ.get("VOIX_CONV", "")
    if conv and conv not in p.setdefault("convs", []):
        p["convs"].append(conv)
        p["convs"] = p["convs"][-10:]
    ecrire_fichier(chemin(p["id"]), p)
    carte_pour_le_telephone(p, appli, conv)
    print("personne {} ({}) : {} messages, {} faits".format(
        p["id"], appli, len(p["messages"]), len(p.get("faits", []))))


def carte_pour_le_telephone(p, appli, conv):
    """Qui est la personne, pour la liste des conversations du panneau (2.53).

    Ecrit une ligne JSON dans PERSONNE_CARTE (voixtour.sh la pousse sur le Pixel
    avant la reponse). Le panneau y lit le nom, le reseau et le pseudo, et
    rattache la conversation a celle deja ouverte avec la meme personne.
    """
    chemin_carte = os.environ.get("PERSONNE_CARTE", "")
    if not chemin_carte:
        return
    compte = next((c for c in p.get("comptes", []) if c.get("appli") == appli), {})
    autres = [c.get("appli", "") for c in p.get("comptes", []) if c.get("appli") and c.get("appli") != appli]
    ecrire_fichier(chemin_carte, {
        "conv": conv, "pid": p["id"], "nom": p.get("nom", ""), "reseau": appli,
        "pseudo": compte.get("nom", ""), "autres": autres,
    })


def carte_tot(chemin_ecran, conv):
    """Carte d'identite en 2 s, avant tout appel au modele (2026-10-23).

    Le panneau la lit pendant l'attente et bascule dans la conversation de cette
    personne. Sortie : une ligne JSON, ou rien si l'ecran n'est pas une messagerie."""
    perso = toutes()
    appli, entete, msgs = lire_ecran(chemin_ecran)
    if appli not in APPLIS.values():
        return ""
    tete = nom_contact(entete)
    p, preuve = identifier(perso, appli, tete, msgs)
    if p:
        compte = next((c for c in p.get("comptes", []) if c.get("appli") == appli), {})
        autres = [c.get("appli", "") for c in p.get("comptes", []) if c.get("appli") and c.get("appli") != appli]
        convs = p.get("convs") or []
        return json.dumps({"conv": conv, "pid": p["id"], "nom": p.get("nom", "") or tete, "reseau": appli,
                           "pseudo": compte.get("nom", "") or tete, "autres": autres,
                           "cible": convs[-1] if convs else "", "preuve": preuve}, ensure_ascii=False)
    if not tete:
        return ""
    # Personne neuve : on pose tout de suite son dossier (2.58). Le panneau recoit
    # un pid des la carte precoce ; sans lui, la conversation restait sans
    # identite et la personne suivante s'y collait.
    p = {"id": identifiant(tete, perso), "nom": tete, "noms": [tete], "comptes": [{"appli": appli, "nom": tete}],
         "messages": [], "faits": [], "brouillons": [], "cree": int(time.time()), "maj": int(time.time()),
         "convs": [conv] if conv else []}
    ecrire_fichier(chemin(p["id"]), p)
    return json.dumps({"conv": conv, "pid": p["id"], "nom": tete, "reseau": appli, "pseudo": tete,
                       "autres": [], "cible": "", "preuve": "nouvelle"}, ensure_ascii=False)


def liste():
    for p in toutes():
        print(fiche_courte(p))
        print("   {} messages, {} brouillons, maj {}".format(
            len(p.get("messages", [])), len(p.get("brouillons", [])),
            time.strftime("%F %H:%M", time.localtime(p.get("maj", 0)))))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["contexte"] and len(a) >= 2:
        print(contexte(a[1]))
    elif a[:1] == ["maj"] and len(a) >= 4:
        maj(a[1], a[2], a[3], " ".join(a[4:]))
    elif a[:1] == ["carte"] and len(a) >= 2:
        print(carte_tot(a[1], a[2] if len(a) > 2 else ""))
    elif a[:1] == ["liste"]:
        liste()
    else:
        print(__doc__)
        sys.exit(2)
