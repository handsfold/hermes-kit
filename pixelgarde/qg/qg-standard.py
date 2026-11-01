#!/usr/bin/env python3
"""Le standard vocal du QG : comprendre, reformuler, proposer, envoyer au oui.

POURQUOI CE SCRIPT EXISTE. Jusqu'au 2026-10-01, chaque phrase dite au Creeper
passait par la session Hermes du topic 2923 : Opus, effort par defaut, tous ses
outils. Mediane mesuree : 51 s par tour. Or ce tour-la ne fait presque que de la
comprehension. Le travail long, lui, appartient aux agents des topics.

Ce script tient donc le role du standardiste, et seulement celui-la :

  1. Le contexte est charge D'AVANCE, sans outil : les topics de qg.db, le
     dernier etat connu de chacun, les rapports en attente, le cap.
  2. UN seul appel au routeur 8010, en texte seul (`-notools`). Le modele rend
     un JSON : ce qu'il dit, et ce qu'il fait (repondre, proposer, envoyer,
     annuler).
  3. C'est CE SCRIPT qui envoie, par qg-envoyer.sh, et jamais le modele.
     Depuis le 2026-10-01 (soir), une proposition part seule a la fin d'un
     compte a rebours affiche sur la bulle ; toucher la bulle l'annule. Le
     telephone decide de la fin du compte et appelle `confirmer` ou `annuler`.
     USER : « je dois le voir, et une action pour annuler, pas un mot ». Sans
     proposition en attente, un « envoyer » redevient une proposition.
  4. Le modele et l'effort tiennent sur une ligne : la cle `standard` de
     ~/.hermes/qg-config.json, que le menu du Creeper change.

Usage :
  qg-standard.py tour "<phrase de USER>"   affiche la phrase a dire (stdout)
  qg-standard.py debut                   oublie la conversation precedente
  qg-standard.py confirmer               fin du compte a rebours : envoie
  qg-standard.py annuler                 la bulle a ete touchee : abandonne
  qg-standard.py contexte                affiche le contexte charge (debogage)
"""
import json
import os
import re
import sqlite3
import shutil
import subprocess
import sys
import time
import urllib.request

HOME = os.path.expanduser("~")
QG_DB = os.environ.get("QG_DB", os.path.join(HOME, ".hermes/qg.db"))
CONF = os.path.join(HOME, ".hermes/qg-config.json")
PIXEL_TMP = os.environ.get("PIXEL_TMP", "/tmp")
ETAT = os.path.join(PIXEL_TMP, "qg-standard.json")
LOG = os.path.join(HOME, ".hermes/logs/qg-standard.log")
ENVOYER = os.environ.get("QG_ENVOYER", os.path.join(HOME, "Bureau/Projets/contexte/bin/qg/qg-envoyer.sh"))
# Pose par un tour qui propose un envoi : voixtour.sh y lit qu'il doit armer le
# compte a rebours du telephone, puis l'efface. Un fichier par tour, et non la
# proposition en attente : une proposition orpheline (telephone mort avant la
# fin du compte) ne doit pas rearmer un compte au tour suivant.
PROPOSE = False  # le dernier tour a propose un envoi : compte a rebours
# Boutons a montrer sous la bulle apres la lecture (« oui », « oui,detail »).
CHOIX = ""
FOCUS = os.path.join(HOME, "Bureau/Projets/contexte/focus.md")
ROUTEUR = os.environ.get("QG_ROUTEUR", "http://127.0.0.1:8010/anthropic/v1/messages")

DEFAUT = "claude-sonnet-5-5-low"
# Au-dela, la conversation precedente est une autre conversation : on ne lui
# ressort pas une proposition vieille d'une heure parce qu'il a dit « oui ».
OUBLI_S = 20 * 60
HISTORIQUE = 6


def journal(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write("{} {}\n".format(time.strftime("%F %T"), msg))
    except OSError:
        pass


def reglage():
    """Le modele du standard, tel que le menu du Creeper l'a pose."""
    m = os.environ.get("QG_STANDARD_MODELE", "")
    if not m:
        try:
            m = str(json.load(open(CONF)).get("standard", "")).strip()
        except Exception:
            m = ""
    m = m or DEFAUT
    return m if m.endswith("-notools") else m + "-notools"


# ------------------------------------------------------------- l'etat vocal

def lire_etat():
    try:
        e = json.load(open(ETAT))
        if time.time() - e.get("maj", 0) < OUBLI_S:
            return e
    except Exception:
        pass
    return {"historique": [], "proposition": None, "maj": time.time()}


def ecrire_etat(e):
    e["maj"] = time.time()
    e["historique"] = e["historique"][-HISTORIQUE:]
    tmp = ETAT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(e, f, ensure_ascii=False)
    os.replace(tmp, ETAT)


# ---------------------------------------------------------- le contexte

def age(ts):
    if not ts:
        return "jamais"
    s = int(time.time() - float(ts))
    if s < 3600:
        return "il y a {} min".format(max(1, s // 60))
    if s < 86400:
        return "il y a {} h".format(s // 3600)
    return "il y a {} j".format(s // 86400)


def topics():
    """Un topic par thread connu : nom, dernier etat, fraicheur, en cours ou non."""
    c = sqlite3.connect("file:{}?mode=ro".format(QG_DB), uri=True, timeout=2)
    noms = dict(c.execute("SELECT thread_id, nom FROM noms"))
    actifs = {r[0] for r in c.execute(
        "SELECT t.thread_id FROM tours_actifs a JOIN topics t "
        "ON t.session_id = a.session_id")}
    lignes = c.execute(
        "SELECT thread_id, etat, derniere_activite, dernier_message, nom_infere "
        "FROM topics WHERE chat_id='__QG_CHAT__' "
        "ORDER BY derniere_activite DESC").fetchall()
    c.close()
    vus, sortie = set(), []
    for thread, etat, act, msg, infere in lignes:
        thread = str(thread)
        if thread in vus or thread == "2923":
            continue
        vus.add(thread)
        nom = noms.get(thread) or infere or ""
        if not nom:
            continue
        etat = re.sub(r"\s+", " ", etat or "").strip()
        if not etat or etat.lower().startswith("indetermin"):
            etat = "dernier message de USER : " + (msg or "?")[:160]
        sortie.append({"thread": thread, "nom": nom, "actif": thread in actifs,
                       "activite": age(act), "etat": etat[:400]})
    # Les topics nommes que qg.db n'a jamais vus restent joignables.
    for thread, nom in noms.items():
        if str(thread) not in vus and str(thread) != "2923":
            sortie.append({"thread": str(thread), "nom": nom, "actif": False,
                           "activite": "jamais", "etat": "aucun etat connu"})
    return sortie


def attente():
    try:
        c = sqlite3.connect("file:{}?mode=ro".format(QG_DB), uri=True, timeout=2)
        r = c.execute("SELECT source, titre FROM attente WHERE statut='nouveau' "
                      "ORDER BY cree DESC LIMIT 5").fetchall()
        c.close()
        return ["{} : {}".format(s or "?", t) for s, t in r]
    except Exception:
        return []


def reponses_recentes(fenetre_s=2 * 3600, n=4, taille=700):
    """Ce que les topics ont repondu recemment, qu'ils aient ete lus ou non.

    Bug du 2026-10-01 : Phone repond a une demande partie du standard, le
    rapport est marque lu, et la ligne de Phone dans la table topics parlait
    encore d'un vieux sujet. Au « vas-y » suivant de USER, le standard ignorait
    tout de la reponse et renvoyait la demande initiale. La file `attente`
    garde le texte de la reponse : on la relit ici, statut ignore.
    """
    try:
        c = sqlite3.connect("file:{}?mode=ro".format(QG_DB), uri=True, timeout=2)
        noms = {str(k): v for k, v in c.execute("SELECT thread_id, nom FROM noms")}
        lignes = c.execute(
            "SELECT cree, cible, source, statut, resume FROM attente "
            "WHERE cree > ? AND statut != 'rejete' ORDER BY cree DESC LIMIT ?",
            (time.time() - fenetre_s, n * 3)).fetchall()
        c.close()
    except Exception:
        return []
    sortie = []
    for cree, cible, source, statut, resume in lignes:
        thread = (cible or "").rsplit(":", 1)[-1]
        # Le QG lui-meme (2923) n'est pas un topic qui repond a une demande.
        if thread == "2923":
            continue
        nom = noms.get(thread) or source or "?"
        texte = re.sub(r"[*`#]", "", resume or "")
        texte = re.sub(r"\s+", " ", texte).strip()
        if not texte:
            continue
        if len(texte) > taille:
            texte = texte[:taille].rsplit(" ", 1)[0] + " [...]"
        sortie.append("{} [{}] {}{} : {}".format(
            nom, thread, age(cree), "" if statut == "nouveau" else ", deja lu",
            texte))
        if len(sortie) >= n:
            break
    return sortie


ECOUTE = os.path.join(HOME, ".hermes/qg-dernier-ecoute")
VOIX_CACHE = os.path.join(HOME, ".hermes/qg-voix")
QG_ATTENTE = os.environ.get("QG_ATTENTE_PY", os.path.join(HOME, ".hermes/scripts/qg-attente.py"))


def _rapport_api(rapport):
    """Vrai si le rapport vient d'un run de l'api_server (origine run_xxx)."""
    try:
        c = sqlite3.connect("file:{}?mode=ro".format(QG_DB), uri=True, timeout=2)
        r = c.execute("SELECT origine, cible FROM attente WHERE id=?",
                      (rapport["id"],)).fetchone()
        c.close()
    except Exception:
        return False
    return bool(r) and (str(r[0] or "").startswith("run_") or str(r[1] or "").startswith("api_server"))


def suite_agent_fond(rapport, texte):
    """Rapport d'un agent detache, sans topic : la reponse lance sa suite.

    Le 2026-10-24, « Oui » sous le rapport 4286 (reco du cockpit) a recu
    « pas de topic d'origine » et rien n'est parti. qg-attente relais lance
    maintenant un agent detache avec la consigne, le rapport et la reponse.
    Rend la phrase a dire, ou None si le rapport n'est pas d'un agent detache.
    """
    # Rapport d'un tour passe par l'api_server (cockpit : /api/demande, POST
    # /v1/runs) : session run_xxx jetable, aucun topic. Rapports 37 a 4686 :
    # meme suite qu'un agent detache (qg-attente relais).
    # Tout rapport sans topic (agent detache, api_server, routine comme
    # controle-skills) lance sa suite. Le 2026-10-28, « Fix les 5 skills »
    # sous le rapport 5456 (controle-skills) a recu « pas de topic d'origine ».
    if re.match(r"^\W*non\b", texte, re.I):
        return "Noté : je ne touche à rien."
    try:
        r = subprocess.run([sys.executable, QG_ATTENTE, "relais", str(rapport["id"]),
                            texte], capture_output=True, text=True, timeout=90)
    except Exception as e:
        journal("suite agent-fond du rapport {} : echec {}".format(rapport["id"], e))
        return "Je n'ai pas pu relancer l'agent de ce rapport."
    journal("suite agent-fond du rapport {} : {} {}".format(
        rapport["id"], r.returncode, (r.stdout or r.stderr).strip()[:200]))
    if r.returncode == 0:
        return "C'est parti : un agent applique ta réponse, son rapport reviendra ici."
    if "deja relaye" in (r.stderr or ""):
        return "Ta réponse à ce rapport est déjà partie."
    return "Je n'ai pas pu relancer l'agent de ce rapport."


def dernier_rapport():
    """Le dernier rapport que USER a ecoute : resume dit, texte entier, topic.

    Le 2026-10-02, chaque rapport finit sur « Je te conseille de X. Tu
    valides ? ». Pour que son « oui », son « detail » ou sa question portent sur
    CE rapport, le standard doit l'avoir sous les yeux, en entier, meme s'il a
    ete lu par le bouton Lire et non dans la conversation.
    """
    try:
        ligne = open(ECOUTE, encoding="utf-8").read().rstrip("\n")
        quand = os.path.getmtime(ECOUTE)
        ident, cible, nom, _ = (ligne.split("\t") + ["", "", "", ""])[:4]
        c = sqlite3.connect("file:{}?mode=ro".format(QG_DB), uri=True, timeout=2)
        r = c.execute("SELECT titre, resume, source FROM attente WHERE id=?",
                      (ident,)).fetchone()
        c.close()
    except Exception:
        return None
    if not r:
        return None
    try:
        dit = open(os.path.join(VOIX_CACHE, ident + ".txt"), encoding="utf-8").read().strip()
    except OSError:
        dit = ""
    titre, corps = (r[0] or "").strip(), (r[1] or "").strip()
    # Le titre est souvent le debut du corps, coupe : le dire deux fois agace.
    if corps.startswith(titre.rstrip(".… ")[:40]):
        titre = ""
    entier = (titre + "\n\n" + corps).strip()
    return {"id": ident, "thread": cible.rsplit(":", 1)[-1], "nom": nom,
            "quand": quand, "dit": dit, "entier": entier, "demande": r[2] or ""}


DETAIL = re.compile(r"^\W*((le |les |plus de |en )?d[ée]tails?|la suite|dis[- ]m'en plus|"
                    r"développe|developpe|raconte|lis[- ]le en entier|en entier)\W*$", re.I)


def detail():
    """« Detail » : le rapport entier, prepare pour l'oreille, borne a 2 minutes."""
    d = dernier_rapport()
    if not d or not d["entier"]:
        return "Je n'ai pas de rapport récent à détailler."
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("qg_attente", QG_ATTENTE)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        t = m.pour_la_voix(d["entier"])
    except Exception as e:
        journal("detail : nettoyage impossible {}".format(e))
        t = re.sub(r"[*`#_>|]", " ", d["entier"])
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 1800:
        t = t[:1800].rsplit(". ", 1)[0] + ". La suite est sur Telegram."
    return "Détail du rapport de {}. {}".format(d["nom"] or "ce topic", t)


def cap():
    try:
        t = open(FOCUS, encoding="utf-8").read()
        m = re.search(r"## Cap\s*\n+>\s*(.+)", t)
        return re.sub(r"\*", "", m.group(1)).strip() if m else ""
    except OSError:
        return ""


def contexte():
    blocs = ["## Topics (nom, thread, activite, dernier etat connu)"]
    for t in topics():
        blocs.append("- {nom} [{thread}] {activite}{en} : {etat}".format(
            en=", AGENT EN TRAIN DE TRAVAILLER" if t["actif"] else "", **t))
    a = attente()
    if a:
        blocs.append("\n## Rapports pas encore lus par USER")
        blocs += ["- " + x for x in a]
    r = reponses_recentes()
    if r:
        blocs.append("\n## Dernieres reponses des topics (moins de 2 h, lues ou non)"
                     "\nC'est ici que se trouve la reponse a une demande envoyee."
                     " Quand USER dit « oui » ou « vas-y » sans proposition en"
                     " attente, il repond le plus souvent a la plus recente.")
        blocs += ["- " + x for x in r]
    d = dernier_rapport()
    if d:
        blocs.append(
            "\n## Dernier rapport écouté par USER ({}, topic {} [{}])\n"
            "Ce qu'il a entendu :\n{}\n\nTexte entier du rapport (pour répondre"
            " à ses questions) :\n{}".format(
                age(d["quand"]), d["nom"], d["thread"],
                d["dit"] or "(le texte entier ci-dessous)", d["entier"][:3500]))
    c = cap()
    if c:
        blocs.append("\n## Cap actuel de USER\n" + c)
    return "\n".join(blocs)


# ---------------------------------------------------------- la consigne

CONSIGNE = """Tu es le standard vocal de USER. Il te parle au téléphone, en français.
Sa phrase vient d'une transcription automatique : des mots peuvent être mal
entendus, retiens l'intention. Tu ne fais aucun travail toi-même. Des agents,
un par topic, font le travail. Toi, tu comprends, tu reformules, tu proposes,
et tu envoies quand USER dit oui.

Tu rends UNIQUEMENT un objet JSON, rien avant, rien après :
{"action": "...", "dire": "...", "cible": "...", "demande": "...", "boutons": [...]}

boutons : 2 ou 3 réponses qu'il touche au lieu de les dire. 1 à 3 mots
chacune, 18 caractères au plus, dans ses mots à lui. Taillées sur ce que tu
viens de dire, et sur le PROFIL plus bas (sa façon réelle de répondre) :
  1. ce qu'il dira le plus probablement, selon ses réflexes du profil ;
  2. l'autre réponse plausible (le non, l'autre topic, la suite logique) ;
  3. la question qu'un excellent entrepreneur ou ingénieur poserait ici et
     que lui oublie (preuve, coût réel, retour arrière, plus petit pas,
     effet sur son cap). Seulement si elle est utile ici, sinon 2 boutons.
Une question fermée garde « Oui » et « Non » en 1 et 2.
Liste vide pour "proposer" : le compte à rebours suffit.

action :
- "repondre" : USER pose une question. Réponds avec le contexte ci-dessous.
  S'il n'y a pas la réponse, dis-le, et propose plutôt de demander au topic
  concerné (action "proposer", demande = sa question).
- "proposer" : USER veut qu'un travail soit fait. Tu choisis le topic, tu
  réécris la demande et tu la lui annonces. Elle part seule à la fin d'un
  compte à rebours affiché sur son téléphone, sauf s'il touche la bulle.
- "envoyer" : une proposition est en attente et USER l'accepte (oui, vas-y,
  envoie, ok, c'est bon...). S'il ajoute un petit ajustement clair, intègre-le
  dans "demande" et envoie. S'il change le fond, refais "proposer".
- "annuler" : USER refuse ou abandonne la proposition en attente.

Phrase floue (incompréhensible, coupée, sans sujet, transcription brouillée) :
action "repondre", cible vide, et "dire" = UNE seule question fermée, rien
d'autre : oui/non (« Tu parles du PC graphique ? ») ou A/B (« La vidéo 2 ou le
PC graphique ? »). Bâtis-la sur le sujet le plus récent (dernier rapport
écouté, dernière réponse). Interdit : « tu peux répéter ? », quel, comment,
qu'est-ce que, résumer des rapports, deviner un topic d'envoi, envoyer.

Après un rapport de topic (« Dernier rapport écouté », l'historique ou
« Dernières réponses des topics ») : un rapport qui attend USER finit par « Je
te conseille de X. Tu valides ? ». Les autres finissent sur leur résultat, sans
question. Quand USER dit oui, vas-y, lance, fais-le, valide, sans
proposition en attente, il valide CETTE recommandation. Action "proposer",
cible = ce topic, demande = « Je valide : X », avec X repris précisément du
rapport. S'il dit non, ou valide en changeant un point, la demande le dit.
Ne renvoie jamais la demande d'origine : le topic y a déjà répondu.
S'il pose une question sur ce rapport, action "repondre" : réponds avec le
texte entier du rapport, en 2 phrases. S'il n'y est pas, propose de la poser
au topic.

cible : le NOM exact d'un topic de la liste. Vide pour répondre ou annuler.
Choix du topic : USER veut qu'on agisse, pas qu'on l'interroge. Si le nom ou
l'état d'un topic touche clairement le sujet, propose-lui. Un envoi vers le
mauvais topic coûte plus cher qu'une question : si aucun topic ne traite le
sujet, n'en devine pas un. Action "repondre", une seule question fermée qui
nomme les 2 topics les plus proches (« EntrepriseA ou Amazon ? »), jamais « ou un
autre ». Même question si deux topics sont aussi plausibles l'un que l'autre.

demande : le message que l'agent du topic lira, à la première personne, comme
si USER l'avait tapé lui-même dans le topic. C'est un prompt : écris celui qui
obtiendra le meilleur résultat possible sur l'objectif de USER.
- D'abord l'objectif, dans ses mots à lui.
- Puis le contexte utile tiré de la conversation ou de l'état des topics
  ci-dessus, que l'agent pourrait ignorer. Rien de ce qu'il sait déjà.
- Puis ce que USER attend en retour (une action, un point, une décision), si
  cela découle de ce qu'il a dit.
- Jamais un mot sur le standard, la voix, le QG, un test, ni sur la façon dont
  le message arrive. Aucune formule creuse comme « c'est fini quand ».
- Garde ses noms propres. Corrige un mot mal transcrit seulement si
  l'intention est sûre. N'invente aucun fait, chiffre ou nom.
- Court pour une question simple, détaillé pour un vrai travail.

dire : ce que la voix lui dit. Français parlé, avec tous les accents (une
synthèse vocale le lit), 2 phrases au plus, aucune puce, aucun chemin, aucun
caractère de mise en forme, aucun tiret long.
- pour proposer : « J'envoie à <topic> : <la demande en une phrase>. » Aucune
  question : il annule d'un geste s'il ne veut pas.
- pour envoyer : « C'est parti vers <topic>. » et rien de plus.
- pour annuler : « D'accord, j'annule. »
Une question n'est permise que dans deux cas : phrase floue (règle plus haut),
et choix entre deux topics. Ailleurs, aucune question : ni « tu veux que
j'envoie ? » (le compte à rebours sert de confirmation), ni relance après une
réponse. Quand USER pose une question, donne la réponse, puis tais-toi. Seule
exception : la question « Tu valides ? » qui termine déjà un rapport.
Une seule question à la fois. Jamais de flatterie, jamais de préambule."""


PROFIL = os.path.expanduser("~/.hermes/qg-profil.md")


def profil():
    """Sa façon de répondre, tirée de 60 jours de messages (qg-profil.py)."""
    try:
        with open(PROFIL, encoding="utf-8") as f:
            t = re.sub(r"<!--.*?-->", "", f.read(), flags=re.S).strip()
    except OSError:
        return ""
    return "\n\n# PROFIL : COMMENT USER RÉPOND (pour les boutons)\n" + t[:3000] if t else ""


def message_systeme(etat):
    s = CONSIGNE + profil() + "\n\n# CONTEXTE CHARGÉ À L'INSTANT\n" + contexte()
    p = etat.get("proposition")
    if p:
        s += ("\n\n## PROPOSITION EN ATTENTE DE SON OUI\nTopic : {nom}\n"
              "Demande : {demande}").format(**p)
    else:
        s += "\n\n## Aucune proposition en attente."
    d = etat.get("dernier_envoi")
    if d:
        s += ("\n\n## Dernier envoi réellement parti\nÀ {} il y a {} : {}\n"
              "Seul cet envoi est parti. Ne dis jamais « c'est parti » pour"
              " autre chose.").format(d["nom"], age(d["heure"]), d["demande"][:400])
    else:
        s += "\n\n## Rien n'est parti depuis le début de la conversation."
    return s


OUI = re.compile(r"^\W*(oui|ouais|ok|okay|vas-y|vas y|go|envoie|envoie-le|"
                 r"c'est bon|d'accord|lance|lance-le)\W*$", re.I)


def meme_demande(a, b):
    """Deux demandes quasi identiques : le modele a recopie l'envoi deja fait."""
    a = re.sub(r"\W+", " ", (a or "").lower()).strip()
    b = re.sub(r"\W+", " ", (b or "").lower()).strip()
    if not a or not b:
        return False
    if a == b:
        return True
    ma, mb = set(a.split()), set(b.split())
    return len(ma & mb) / max(len(ma | mb), 1) > 0.8


def noter_envoi(etat, cible, demande):
    etat["dernier_envoi"] = {"thread": cible["thread"], "nom": cible["nom"],
                             "demande": demande, "heure": time.time()}


# ---------------------------------------------------------- l'appel

def appeler(modele, systeme, historique, phrase):
    # Les essais du chantier (tests/creeper-file.sh) remplacent le modele par
    # une reponse fixe, et sa lenteur par une attente : le routeur reste hors jeu.
    if os.environ.get("QG_STANDARD_REPONSE"):
        time.sleep(float(os.environ.get("QG_STANDARD_ATTENTE_S", "0") or 0))
        return os.environ["QG_STANDARD_REPONSE"]
    msgs = []
    for h in historique:
        msgs.append({"role": "user", "content": h["poste"]})
        msgs.append({"role": "assistant", "content": h["moi"]})
    msgs.append({"role": "user", "content": phrase})
    corps = json.dumps({"model": modele, "max_tokens": 900,
                        "system": systeme, "messages": msgs}).encode()
    req = urllib.request.Request(ROUTEUR, data=corps, headers={
        "content-type": "application/json", "x-api-key": "local",
        "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    return "".join(b.get("text", "") for b in d.get("content", [])
                   if b.get("type") == "text").strip()


def extraire(texte):
    """Le JSON du modele, meme entoure de texte ou de balises de code."""
    m = re.search(r"\{.*\}", texte, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    # JSON tronque (max_tokens atteint) : on recupere au moins le message,
    # et le resume s'il est entier. Sinon le panneau affichait le JSON brut
    # (vu le 2026-11-01 00:00). On cherche dans tout le texte : un JSON coupe
    # en plein "nom" n'a plus d'accolade fermante.
    md = re.search(r'"dire"\s*:\s*"((?:[^"\\]|\\.)*)', texte)
    if md:
        d = {"action": "repondre", "dire": json.loads('"' + md.group(1) + '"')}
        mp = re.search(r'"resume"\s*:\s*"((?:[^"\\]|\\.)*)', texte)
        if mp:
            d["personne"] = {"resume": json.loads('"'+mp.group(1)+'"')}
        return d
    # Le modele a parle au lieu de rendre du JSON : on dit ce qu'il a dit.
    return {"action": "repondre", "dire": texte[:400]}


def resoudre(cible, liste):
    """Le nom dit par le modele vers un topic connu, ou None."""
    c = (cible or "").strip().lower()
    if not c:
        return None
    for t in liste:
        if t["nom"].lower() == c or t["thread"] == c:
            return t
    for t in liste:
        if c in t["nom"].lower():
            return t
    return None


def occupe_depuis(thread):
    """Minutes depuis lesquelles le topic travaille deja, ou None s'il est libre.

    Le 2026-10-13, « Chiffre la marge » touche a 19:51 sous le rapport 2557 est
    parti vers Amazon 2, alors en plein travail depuis 19:30. La demande a
    attendu la fin du tour, 11 min, et sa reponse est tombee a 20:03, juste
    apres un « vas-y » envoye a Amazon. USER a cru que son oui etait parti dans
    le mauvais topic. Un tour de plus de 2 h est tenu pour perime.
    """
    if not str(thread or "").strip():
        return None
    try:
        c = sqlite3.connect("file:{}?mode=ro".format(QG_DB), uri=True, timeout=2)
        r = c.execute(
            "SELECT MIN(a.debut) FROM tours_actifs a JOIN topics t "
            "ON t.session_id = a.session_id WHERE t.thread_id = ?",
            (str(thread),)).fetchone()
        c.close()
    except sqlite3.Error:
        return None
    if not r or not r[0] or time.time() - r[0] > 7200:
        return None
    return max(1, int((time.time() - r[0]) // 60))


def prevenir_si_occupe(dire, t):
    """Ajoute a l'annonce d'un envoi que le topic vise est deja occupe."""
    if not t or not re.match(r"(J'envoie à|C'est parti vers)", dire or ""):
        return dire
    m = occupe_depuis(t.get("thread"))
    if m is None:
        return dire
    journal("topic {} occupe depuis {} min, USER prevenu".format(t.get("nom"), m))
    return dire.rstrip() + (" {} travaille déjà depuis {} min : ta demande passera"
                            " après, sa réponse arrivera en retard.").format(t.get("nom"), m)


def envoyer(t, demande):
    """Lance le dispatch detache : il survit a la fin du tour vocal.

    qg-envoyer.sh bloque jusqu'a la reponse de l'agent (une heure au plus).
    Le tour vocal, lui, doit rendre la parole tout de suite.

    QG_STANDARD_A_BLANC=1 : on journalise sans envoyer. Pour les essais, qui
    sinon feraient travailler un agent pour de vrai.
    """
    # Un topic vide ne part nulle part : le 2026-10-10 a 18:34, un rapport
    # d'agent-fond sans cible a produit « envoye thread= », perdu en silence.
    if not str(t.get("thread") or "").strip():
        journal("REFUS envoi sans topic : {}".format(demande[:120]))
        return False
    if os.environ.get("QG_STANDARD_A_BLANC"):
        journal("A BLANC thread={} demande={}".format(t["thread"], demande[:120]))
        return
    # systemd-run et pas setsid : setsid quitte la session, pas le cgroup.
    # Lance depuis pixel-garde, l'envoi restait dans son cgroup ; le
    # redemarrage du service a 11:27 le 2026-10-03 l'a tue pendant qu'il
    # attendait l'agent. La reponse de ProjetA n'a jamais ete postee dans
    # le topic, seul le rapport est arrive au QG. Une unite a part survit.
    lanceur = ["setsid", "nohup"]
    if shutil.which("systemd-run"):
        lanceur = ["systemd-run", "--user", "--collect", "--quiet",
                   "--setenv=PATH=" + os.environ.get("PATH", "/usr/bin:/bin"),
                   "--setenv=HOME=" + HOME]
    subprocess.Popen(
        lanceur + [ENVOYER, t["thread"], demande],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    journal("envoye thread={} demande={}".format(t["thread"], demande[:120]))


def replier(etat, phrase):
    """Fond dans la phrase de USER ce qui s'est passe depuis le tour precedent.

    Bug du 2026-10-02 : un rapport de Prime 2 est lu a USER, il demande « ce
    skill la, il voit l'ecran ? », et le standard repond « de quel topic tu
    parles ? ». Le rapport etait bien inscrit (`entendu`), mais le proxy Claude
    reprend la session CLI au plus long prefixe connu et prend tout ce qui suit
    pour des messages d'outils deja vus : il ne renvoie que le dernier message
    (journal : « saut=6 msgs d'outils du CLI »). Les paires glissees entre deux
    tours n'arrivaient donc jamais au modele. On les replie ici dans le message
    de USER, qui, lui, part toujours.
    """
    notes = []
    while etat["historique"] and (etat["historique"][-1].get("hors_tour")
                                  or etat["historique"][-1].get("poste", "").startswith("(")):
        notes.insert(0, etat["historique"].pop())
    if not notes:
        return phrase
    lignes = []
    for h in notes:
        try:
            dit = json.loads(h["moi"]).get("dire", "") or h["moi"]
        except Exception:
            dit = h.get("moi", "")
        lignes.append("{}\n{}".format(h["poste"], dit).strip())
    return ("Depuis ton dernier tour :\n" + "\n\n".join(lignes)
            + "\n\nVJ dit maintenant : " + phrase)


FIXES = {"oui": "oui", "non": "non", "détail": "detail", "detail": "detail"}
QG_VOIX = os.path.join(HOME, ".hermes/qg-voix")


def boutons(liste, fichier=None):
    """Les reponses devinees, au format du telephone : « id:Libelle|... ».

    Oui, Non et Detail gardent leur identifiant fixe. Les autres prennent b1 a
    b3, et leur libelle est garde dans qg-voix/<id>.libelles : le telephone
    renvoie l'identifiant du bouton avec celui de sa bulle (voixb1:t1759),
    voixbouton.sh relit le texte sous cet id. L'id d'un tour est VOIX_POUR,
    pose par voixtour.sh. Bug du 2026-10-06 : un seul fichier /tmp pour tous,
    le tour suivant ecrasait les libelles d'une bulle encore a l'ecran.
    """
    if fichier is None:
        pour = os.environ.get("VOIX_POUR", "").strip()
        if not re.fullmatch(r"[a-z0-9]{1,12}", pour):
            fichier = os.devnull
        else:
            os.makedirs(QG_VOIX, exist_ok=True)
            fichier = os.path.join(QG_VOIX, pour + ".libelles")
    vus, sortie, libres = set(), [], []
    for x in (liste if isinstance(liste, list) else [])[:3]:
        lib = re.sub(r"[|:\n\r\"`$\\]", " ", str(x)).replace("'", "\u2019")
        lib = re.sub(r"\s+", " ", lib).strip()[:24]
        if not lib or lib.lower() in vus:
            continue
        vus.add(lib.lower())
        ident = FIXES.get(lib.lower().rstrip(" .!?"))
        if not ident:
            ident = "b{}".format(len(libres) + 1)
            libres.append("{}\t{}".format(ident, lib))
        sortie.append("{}:{}".format(ident, lib))
    try:
        if fichier == os.devnull:
            pass
        elif libres:
            with open(fichier, "w", encoding="utf-8") as f:
                f.write("\n".join(libres) + "\n")
        elif os.path.exists(fichier):
            os.remove(fichier)
    except OSError:
        pass
    return "|".join(sortie)


APRES_RAPPORT = """Tu prépares les boutons qui s'afficheront sous la bulle de USER
quand il aura écouté ce rapport d'un de ses agents. Il touche au lieu de parler.

CE QUE FAIT UN BOUTON : le texte touché part tel quel comme réponse de USER à
CET agent, dans SON topic. L'agent le lit avec tout le fil de la conversation.
Un bouton est donc une consigne que l'agent peut exécuter tout de suite, ou
une question à laquelle il sait répondre. « Détail » lit le rapport entier.

Tu reçois : le chantier, la demande de USER qui a lancé ce travail, le fil
récent du topic, le rapport entier, ce que USER vient d'entendre, et son cap.
Sers-t'en. Un bon bouton nomme l'objet précis du rapport (les 5 mails, le
commit, le 17/10, l'imprimeur à 9 800) au lieu d'une formule passe-partout.

Rends UNIQUEMENT {"boutons": ["texte 1", "texte 2", "texte 3"]}, des chaînes
simples : 2 ou 3 réponses, 1 à 3 mots chacune,
18 caractères au plus, dans ses mots à lui (voir le PROFIL).
  1. ce qu'il répondra le plus probablement à CE rapport, vu sa demande ;
  2. l'autre réponse plausible (« Non », la suite logique, un autre choix) ;
  3. la question qui apporte le plus de valeur ICI : celle qu'un excellent
     entrepreneur poserait et que lui oublie. Elle vise le point faible de CE
     rapport : un chiffre sans preuve, un risque, un coût, un retour arrière,
     le plus petit pas, le lien avec son cap. Si le rapport répond déjà à une
     question (« 410 tests passent »), ne la repose pas.
Si le rapport finit par une question fermée, « Oui » et « Non » en 1 et 2.
Si le rapport ne finit pas par une question (ou dit « Rien à décider »),
jamais « Oui » ni « Non » : il n'y a rien à valider. Propose alors la suite
qui fait avancer le chantier, et la question utile.
La liste « question d'expert » du PROFIL donne des familles, pas des formules
à recopier : écris la question pour CE rapport, avec son objet (« Les 337
mails comptent ? » plutôt que « On mesure quoi ? »). Relis le rapport entier
avant : s'il dit déjà « rien ne part si ça bloque », ne demande pas le risque.
Jamais la même formule d'un rapport à l'autre par réflexe : « Testé
comment ? » ne vaut que si le rapport affirme un test sans dire lequel."""


def contexte_rapport(ident):
    """Ce que l'agent des boutons doit savoir, au-dela des 60 mots dits.

    Jusqu'au 2026-10-03, il ne recevait que le texte condense et le profil :
    ni le chantier, ni la demande de USER, ni le fil, ni le cap. D'ou des
    boutons passe-partout (« Testé comment ? » sur 4 rapports sur 6).
    """
    blocs = []
    try:
        c = sqlite3.connect("file:{}?mode=ro".format(QG_DB), uri=True, timeout=2)
        r = c.execute("SELECT source, origine, cible, resume FROM attente"
                      " WHERE id=?", (ident,)).fetchone()
        nom = ""
        if r and r[2] and r[2].count(":") >= 2:
            n = c.execute("SELECT nom FROM noms WHERE thread_id=?",
                          (r[2].rsplit(":", 1)[1],)).fetchone()
            nom = n[0] if n else ""
        c.close()
    except Exception:
        r, nom = None, ""
    if r:
        source, origine, _, entier = r
        blocs.append("## Chantier : {}".format(nom or "inconnu"))
        if source:
            blocs.append("## Demande de USER qui a lancé ce travail\n" + source[:600])
        fil = fil_topic(origine)
        if fil:
            blocs.append("## Fil récent du topic (du plus ancien au plus récent)\n" + fil)
        if entier:
            blocs.append("## Rapport entier\n" + entier[:3500])
    c = cap()
    if c:
        blocs.append("## Cap de USER\n" + c)
    return "\n\n".join(blocs)


def fil_topic(session, n=8):
    """Les derniers echanges USER / agent de la session du topic, sans les outils."""
    if not session:
        return ""
    try:
        c = sqlite3.connect("file:{}?mode=ro".format(
            os.path.join(HOME, ".hermes/state.db")), uri=True, timeout=2)
        lignes = c.execute(
            "SELECT role, content FROM messages WHERE session_id=? AND role IN"
            " ('user','assistant') AND content IS NOT NULL AND content!=''"
            " ORDER BY id DESC LIMIT ?", (session, n)).fetchall()
        c.close()
    except Exception:
        return ""
    sortie = []
    for role, texte in reversed(lignes):
        texte = re.sub(r"\s+", " ", texte).strip()
        sortie.append("{} : {}".format("USER" if role == "user" else "Agent", texte[:400]))
    return "\n".join(sortie)


def choix_rapport(ident):
    """Les boutons d'un rapport, calcules a la prefabrication de sa voix.

    Le texte dit arrive sur l'entree standard. Sortie : <id>.choix (la ligne
    pour le telephone) et <id>.libelles (le texte des b1 a b3), a cote du
    mp3. rapport.sh les passe au telephone au moment de l'ecoute : rien n'est
    calcule pendant que USER attend. Le texte dit peut manquer (stdin vide) : le
    calcul part alors avec le seul rapport entier.
    """
    texte = sys.stdin.read().strip()[:4000]
    if not re.fullmatch(r"[\w-]+", ident):
        return 1
    if not texte:
        # Lance avant le resume vocal (2026-10-28) : le rapport entier est deja
        # dans le contexte, le resume n'ajoute que ce que USER entendra.
        texte = ("(le resume dit a voix haute se prepare en meme temps : il"
                 " reprend l'essentiel du rapport entier ci-dessus)")
    cache = os.path.expanduser("~/.hermes/qg-voix")
    t0 = time.time()
    try:
        # [appelant:...] : le proxy nomme l'appel dans proxy-usage.jsonl.
        brut = appeler("claude-opus-5-5-medium-notools",
                       APRES_RAPPORT + profil() + "\n[appelant:qg-boutons-rapport]", [],
                       contexte_rapport(ident)
                       + "\n\n## Ce que USER vient d'entendre\n" + texte)
        liste = json.loads(re.search(r"\{.*\}", brut, re.S).group(0)).get("boutons")
        # Le modele rend parfois [{"text": "Oui"}] au lieu de ["Oui"].
        if isinstance(liste, list):
            liste = [next((v for v in x.values() if isinstance(v, str)), "")
                     if isinstance(x, dict) else str(x) for x in liste]
            liste = [x for x in liste if x.strip()]
    except Exception as e:
        print("boutons du rapport impossibles : {}".format(e), file=sys.stderr)
        return 1
    if isinstance(liste, list) and len(liste) < 3 and not any(
            str(x).lower().startswith(("détail", "detail")) for x in liste):
        liste.append("Détail")
    ligne = boutons(liste, os.path.join(cache, ident + ".libelles"))
    if not ligne:
        return 1
    with open(os.path.join(cache, ident + ".choix"), "w", encoding="utf-8") as f:
        f.write(ligne + "\n")
    journal("boutons du rapport {} : {} ({:.1f} s)".format(ident, ligne, time.time() - t0))
    print(ligne)
    return 0


def bouton_de_rapport(etat):
    """Le rapport dont USER vient de toucher un bouton, sinon None.

    Le bouton porte l'id de son rapport (voixb1:1375), le garde le passe a
    voixtour.sh, qui le passe ici par VOIX_RAPPORT. Le 2026-10-03 a 12:04,
    « Oui vas-y » sous le rapport d'Idea est parti vers Coach : le standard
    ignorait quel rapport portait le bouton. Ce rapport devient le dernier
    ecoute, et une proposition nee d'un autre rapport tombe, meme du meme
    topic : sinon le oui franc l'enverrait.
    """
    ident = os.environ.get("VOIX_RAPPORT", "").strip()
    if not ident.isdigit():
        return None
    subprocess.run([sys.executable, QG_ATTENTE, "ecoute", ident],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    d = dernier_rapport()
    if not d or d["id"] != ident:
        journal("bouton du rapport {} : rapport introuvable".format(ident))
        return None
    p = etat.get("proposition")
    if p and (p.get("rapport") != ident if p.get("rapport")
              else p.get("thread") != d["thread"]):
        journal("bouton du rapport {} : proposition vers {} abandonnee".format(
            ident, p.get("nom")))
        etat["proposition"] = None
    return d



def consigne_ecran():
    """Consigne du mode choisi dans le panneau Ecrire (2.48).

    ecrire.sh pose dans VOIX_CONSIGNE le texte du mode (bin/qg/modes/<id>.md,
    sans sa ligne « muet: ») suivi des derniers tours de la conversation.
    Sans fichier, on garde la consigne du mode « question ».
    """
    chemin = os.environ.get("VOIX_CONSIGNE", "")
    if chemin and os.path.exists(chemin):
        try:
            texte = open(chemin, encoding="utf-8", errors="replace").read().strip()
            if texte:
                return texte[:9000]
        except OSError:
            pass
    return ("Sa question porte sur CET ecran. Reponds avec ce qui y est ecrit, en"
            " 3 phrases courtes au plus, avec une recommandation nette. Ne parle"
            " que de l'ecran : aucun rapport, aucun projet en cours, sauf si"
            " l'ecran en parle. action=repondre, sauf s'il demande lui-meme"
            " d'envoyer quelque chose a un topic. Si le texte ne suffit pas"
            " (image, jeu, champ masque), dis-le en une phrase et propose le"
            " bouton « Envoyer au QG ».")

def tour(phrase):
    global PROPOSE, CHOIX
    PROPOSE = False
    CHOIX = ""
    t0 = time.time()
    etat = lire_etat()
    modele = reglage()
    rapport = bouton_de_rapport(etat)
    # Bouton « Oui 03 » sous un rapport qui demande « oui 03 ou non 03 » :
    # le toucher EST l'accord de USER, il part tel quel vers le topic du rapport.
    # Le 2026-10-03 a 12:18, le modele a repondu « je ne connais aucun 03 »
    # alors que le rapport 931 de ProjetA le demandait en toutes lettres.
    m = re.match(r"^\W*(oui|non)\W*(\d{1,2})\W*$", phrase, re.I)
    if rapport and m and rapport.get("thread"):
        code = "{} {:02d}".format(m.group(1).lower(), int(m.group(2)))
        if re.search(r"\b" + code.replace(" ", r"\s*") + r"\b", rapport["entier"], re.I):
            cible = {"thread": rapport["thread"], "nom": rapport["nom"] or "ce topic"}
            envoyer(cible, "{} (rapport {})".format(code, rapport["id"]))
            noter_envoi(etat, cible, code)
            etat["proposition"] = None
            dire = "C'est parti vers {} : {}.".format(cible["nom"], code)
            etat["historique"].append({"poste": phrase, "moi": json.dumps(
                {"action": "envoyer", "dire": dire, "cible": cible["nom"], "demande": code},
                ensure_ascii=False)})
            ecrire_etat(etat)
            journal("bouton {} du rapport {} : envoi direct vers {}".format(
                code, rapport["id"], cible["nom"]))
            return dire
    # Tout autre bouton sous un rapport part tel quel, sans passer par le
    # modele : « Oui, option A (rapport 2322) ». Le 2026-10-11 a 23:48, le
    # modele a reecrit ce geste avec l'option A d'un rapport /mwbot voisin,
    # partie vers ProjetA. Le topic a son rapport sous les yeux : le geste
    # brut et le numero lui suffisent. Accord de USER le 2026-10-12.
    # « Détail » reste une lecture, il ne part pas.
    if rapport and not DETAIL.match(phrase):
        if not rapport.get("thread"):
            journal("bouton du rapport {} : rapport sans topic".format(rapport["id"]))
            dire = suite_agent_fond(rapport, phrase.strip()) or (
                "Ce rapport n'a pas de topic d'origine : je ne peux rien lui renvoyer.")
            action = "repondre"
            demande = ""
            cible = {"nom": ""}
        else:
            cible = resoudre(rapport["thread"], topics()) or {
                "thread": rapport["thread"], "nom": rapport["nom"] or "ce topic"}
            p = etat.get("proposition")
            if p and OUI.match(phrase) and p.get("rapport") == rapport["id"]:
                # Oui franc sous le meme rapport : il confirme ce qui attend.
                demande = p["demande"]
                envoyer(cible, demande)
                noter_envoi(etat, cible, demande)
                etat["proposition"] = None
                action = "envoyer"
                dire = "C'est parti vers {}.".format(cible["nom"])
            else:
                demande = "{} (rapport {})".format(phrase.strip(), rapport["id"])
                etat["proposition"] = {"thread": cible["thread"], "nom": cible["nom"],
                                       "demande": demande, "rapport": rapport["id"]}
                PROPOSE = True
                action = "proposer"
                dire = "J'envoie à {} : {}.".format(cible["nom"], demande)
            journal("bouton du rapport {} : geste tel quel, {} vers {} : {}".format(
                rapport["id"], action, cible["nom"], demande))
            dire = prevenir_si_occupe(dire, cible)
        etat["historique"].append({"poste": phrase, "moi": json.dumps(
            {"action": action, "dire": dire, "cible": cible["nom"], "demande": demande},
            ensure_ascii=False)})
        ecrire_etat(etat)
        return dire
    systeme = message_systeme(etat)
    # Question tapee dans Creeper avec l'ecran joint (2.45) : ecrire.sh lit
    # l'ecran par ADB et pose son texte dans VOIX_ECRAN. Il va dans le
    # message systeme, pas dans l'historique : un ecran ne se rejoue pas.
    ecran_ctx = ""
    chemin_ecran = os.environ.get("VOIX_ECRAN", "")
    if chemin_ecran and os.path.exists(chemin_ecran):
        try:
            ecran_ctx = open(chemin_ecran, encoding="utf-8", errors="replace").read()[:5000]
        except OSError:
            ecran_ctx = ""
    if ecran_ctx:
        systeme += (
            "\n\n## ECRAN DU TELEPHONE DE USER (priorite sur tout le reste)\n"
            "USER t'ecrit depuis son telephone. Voici ce qui est affiche a cet"
            " instant, lu dans l'arbre des vues (texte seul, sans images) :\n"
            "<ecran>\n" + ecran_ctx + "\n</ecran>\n" + consigne_ecran())
    if rapport:
        systeme += (
            "\n\n## BOUTON SOUS UN RAPPORT\nVJ vient de toucher « {} » sous le"
            " rapport de {}. Sa réponse porte sur CE rapport : cible={},"
            " jamais un autre topic, jamais une demande plus ancienne."
            " Ses options (A, B, oui, non) s'entendent au sens de CE rapport,"
            " jamais d'un rapport plus ancien qui proposait aussi une option A."
            "\n\nTexte du rapport :\n{}".format(
                phrase, rapport["nom"], rapport["nom"],
                (rapport.get("entier") or "")[:2500]))
    # `dit` part au modele et reste dans l'historique ; `phrase` sert aux
    # tests sur les mots de USER (le oui franc).
    dit = replier(etat, phrase)
    if DETAIL.match(phrase):
        dire = detail()
        etat["historique"].append({"poste": dit, "moi": json.dumps(
            {"action": "repondre", "dire": dire[:600], "cible": "", "demande": ""},
            ensure_ascii=False)})
        ecrire_etat(etat)
        # Oui / Non seulement si le rapport finit sur une question : depuis
        # le 2026-10-03, seuls les rapports qui attendent USER en posent une.
        if dire.startswith("Détail du rapport") and dire.rstrip().endswith("?"):
            CHOIX = boutons(["Oui", "Non"])
        journal("detail {:.1f}s {} car".format(time.time() - t0, len(dire)))
        return dire
    # Un oui sec, sans proposition en attente : USER valide le dernier rapport.
    # Le 2026-10-03 a 10:41, le bouton Oui apres un rapport « rien a decider »
    # a fait reciter un resume, et rien n'est parti.
    oui_sec = OUI.match(phrase) and not etat.get("proposition")
    if oui_sec:
        systeme += (
            "\n\n## OUI SEC\nVJ dit oui et rien n'attend d'envoi : il valide le"
            " dernier rapport entendu. S'il recommande une action, action=proposer,"
            " cible=ce topic, demande=son accord sur cette recommandation, dite en"
            " clair. Sinon action=repondre et dire=« Rien à valider sur ce"
            " rapport. », mot pour mot, sans résumé.")
    # Un 500 passager du routeur (jeton OAuth expire le 2026-10-23 a 18:09)
    # ne doit pas arriver a USER : un 2e essai apres 4 s, puis l'echec.
    brut = None
    for essai in (1, 2):
        try:
            brut = appeler(modele, systeme, [] if ecran_ctx else etat["historique"], dit)
            break
        except Exception as e:
            journal("echec appel {} (essai {}) : {}".format(modele, essai, e))
            if essai == 1:
                time.sleep(4)
    if brut is None:
        return "Le standard ne répond pas. Redis ta phrase dans un instant."
    d = extraire(brut)
    # Mode « Repondre » (2.49) : le modele dit aussi qui est la personne.
    sortie_personne = os.environ.get("VOIX_PERSONNE_OUT", "")
    if sortie_personne and isinstance(d.get("personne"), dict):
        try:
            with open(sortie_personne, "w", encoding="utf-8") as f:
                json.dump(d["personne"], f, ensure_ascii=False)
        except OSError:
            pass
    liste = topics()
    t = resoudre(d.get("cible"), liste)
    # Le 2026-10-01, apres le rapport de Phone, « vas-y, fais-le » a repropose
    # mot pour mot la demande deja envoyee. On redemande une fois au modele.
    der = etat.get("dernier_envoi")
    if (str(d.get("action", "")).lower() in ("proposer", "envoyer") and der and t
            and (t["thread"] == der["thread"] or rapport)
            and meme_demande(d.get("demande"), der["demande"])):
        journal("doublon de l'envoi precedent, on redemande")
        try:
            brut = appeler(modele, systeme + (
                "\n\n## CORRECTION\nTa demande recopie l'envoi déjà parti, et le"
                " topic y a répondu. Écris la SUITE : l'accord de USER sur ce que le"
                " topic a recommandé dans son dernier rapport, en le rappelant."),
                etat["historique"], dit)
            d = extraire(brut)
            t = resoudre(d.get("cible"), liste)
        except Exception as e:
            journal("echec appel correctif : {}".format(e))
    action = str(d.get("action", "repondre")).lower()
    dire = str(d.get("dire", "")).strip()
    demande = str(d.get("demande", "")).strip()
    # Bouton d'un rapport : la cible est celle du rapport, quoi que dise le modele.
    if rapport and action in ("proposer", "envoyer") and not rapport.get("thread"):
        # Rapport sans topic d'origine : rien a viser, on le dit au lieu
        # d'envoyer vers un topic vide ou vers le topic d'un autre rapport.
        journal("bouton du rapport {} : rapport sans topic".format(rapport["id"]))
        action, t = "repondre", None
        dire = suite_agent_fond(rapport, (demande or phrase).strip()) or (
            "Ce rapport n'a pas de topic d'origine : je ne peux rien lui renvoyer.")
    elif rapport and action in ("proposer", "envoyer"):
        vise = resoudre(rapport["thread"], liste) or {
            "thread": rapport["thread"], "nom": rapport["nom"]}
        if not t or t["thread"] != vise["thread"]:
            journal("bouton du rapport {} : cible {} remplacee par {}".format(
                rapport["id"], (t or {}).get("nom", "?"), vise["nom"]))
            # Le 2026-10-11 a 23:48, « Oui, option A » sous le rapport 2322
            # (ProjetA, quota) : le modele a vise Idea et ecrit l'option A
            # d'un rapport /mwbot. Seul le nom etait corrige, la demande /mwbot
            # est partie vers ProjetA. Une demande ecrite pour un autre
            # topic ne vaut rien : on envoie le geste de USER tel quel, avec le
            # numero du rapport, que le topic sait relire.
            demande = "{} (rapport {})".format(phrase.strip(), rapport["id"])
            dire = "J'envoie à {} : {}.".format(vise["nom"], demande)
            journal("bouton du rapport {} : demande du modele ecartee, envoi du geste".format(
                rapport["id"]))
        t = vise
    # Un oui franc, avec une proposition en attente, envoie. Toujours.
    if etat.get("proposition") and OUI.match(phrase) and action not in ("envoyer", "annuler"):
        journal("oui franc avec proposition en attente : envoi force")
        action, dire, demande, t = "envoyer", "", "", None

    if action == "proposer":
        if t and demande:
            etat["proposition"] = {"thread": t["thread"], "nom": t["nom"],
                                   "demande": demande,
                                   "rapport": (rapport or {}).get("id")}
            PROPOSE = True
            # Le modele a pu garder l'ancienne formule : la question n'a plus
            # lieu d'etre, c'est le geste qui annule.
            dire = re.sub(r"\s*Je lance\s*\?\s*$", "", dire)
        else:
            action = "repondre"
            dire = dire or "Je n'ai pas compris vers quel topic l'envoyer."
    elif action == "envoyer":
        p = etat.get("proposition")
        if not p:
            # Garde-fou : rien ne part sans une proposition entendue par USER.
            if t and demande:
                etat["proposition"] = {"thread": t["thread"], "nom": t["nom"],
                                       "demande": demande,
                                       "rapport": (rapport or {}).get("id")}
                action = "proposer"
                PROPOSE = True
                dire = "J'envoie à {} : {}.".format(t["nom"], demande)
            else:
                action = "repondre"
                dire = "Il n'y a rien en attente d'envoi."
        else:
            cible = t or {"thread": p["thread"], "nom": p["nom"]}
            envoyer(cible, demande or p["demande"])
            noter_envoi(etat, cible, demande or p["demande"])
            etat["proposition"] = None
            dire = dire or "C'est parti vers {}.".format(cible["nom"])
    elif action == "annuler":
        etat["proposition"] = None
        dire = dire or "D'accord, j'annule."

    # Faux seulement si une demande attend encore, ou si rien n'est jamais parti.
    if action != "envoyer" and (etat.get("proposition") or not etat.get("dernier_envoi")) \
            and re.search(r"(c'est|est|déjà|deja|bien) (parti|envoyé)|j'ai envoyé", dire, re.I) \
            and not dire.startswith("J'envoie à"):
        journal("dire corrige, il annoncait un envoi qui n'a pas eu lieu : " + dire[:100])
        p = etat.get("proposition")
        dire = ("Rien n'est parti. La demande pour {} attend : dis oui pour"
                " l'envoyer.".format(p["nom"]) if p else "Rien n'est parti.")
    dire = dire or "Je n'ai pas compris, tu peux reformuler ?"
    # Filet : apres un oui sec, jamais de resume a voix haute.
    # Une question (« lequel des deux ? ») reste : il y a bien quelque chose a
    # valider, la couper mentait a USER (11:17, deux rapports en attente).
    if oui_sec and action == "repondre" and len(dire) > 60 and not dire.rstrip().endswith("?"):
        journal("oui sec sans action : resume coupe : " + dire[:100])
        dire = "Rien à valider sur ce rapport."
    if action != "proposer":
        CHOIX = boutons(d.get("boutons"))
    if action in ("proposer", "envoyer"):
        dire = prevenir_si_occupe(dire, t or etat.get("proposition") or etat.get("dernier_envoi"))
    # Un tour d'Ecrire (ecran joint) ne se rejoue pas : sa reponse porte sur UN
    # ecran. Gardee dans l'historique, « ecran d'accueil » se recopiait de tour
    # en tour meme quand l'ecran etait redevenu une conversation (2026-10-23).
    if not ecran_ctx:
        etat["historique"].append({"poste": dit, "moi": json.dumps(
            {"action": action, "dire": dire, "cible": (t or {}).get("nom", ""),
             "demande": demande}, ensure_ascii=False)})
        ecrire_etat(etat)
    journal("{} {:.1f}s action={} cible={} dire={}".format(
        modele, time.time() - t0, action, (t or {}).get("nom", ""), dire[:100]))
    return dire


def entendu(sujet, texte):
    """Un rapport de topic vient d'etre dit a USER au milieu de la conversation.

    On l'inscrit dans l'historique comme si le standard l'avait dit lui-meme :
    au tour suivant, « oui, vas-y » se comprend comme une reponse a CE rapport,
    et le standard sait vers quel topic la renvoyer.
    """
    etat = lire_etat()
    etat["historique"].append({
        "hors_tour": True,
        "poste": "(pas de phrase : le rapport du topic {} arrive et t'est lu a voix"
              " haute)".format(sujet),
        "moi": json.dumps({"action": "repondre", "dire": "Rapport de {} : {}".format(
            sujet, re.sub(r"\s+", " ", texte).strip()[:1500]),
            "cible": sujet, "demande": ""}, ensure_ascii=False)})
    ecrire_etat(etat)
    journal("entendu : rapport de {} inscrit dans la conversation".format(sujet))


# ------------------------------------------- la fin du compte a rebours

def confirmer():
    """Le compte a rebours du telephone est arrive au bout : on envoie.

    Appele par actions/envoiconfirme.sh. Rend la ligne a laisser dans le QG,
    ou rien s'il n'y avait plus rien en attente (deja envoye, deja annule).
    """
    etat = lire_etat()
    p = etat.get("proposition")
    if not p:
        journal("confirmer : rien en attente")
        return ""
    envoyer({"thread": p["thread"], "nom": p["nom"]}, p["demande"])
    noter_envoi(etat, p, p["demande"])
    etat["proposition"] = None
    ecrire_etat(etat)
    return "Parti vers {}.".format(p["nom"])


def annuler():
    """USER a touche la bulle pendant le compte a rebours : rien ne part."""
    etat = lire_etat()
    p = etat.get("proposition")
    if not p:
        return ""
    etat["proposition"] = None
    etat["historique"].append({"hors_tour": True,
                               "poste": "(touche la bulle : envoi annule)",
                               "moi": json.dumps({"action": "annuler"})})
    ecrire_etat(etat)
    journal("annule par la bulle : {}".format(p["nom"]))
    return "Envoi à {} annulé.".format(p["nom"])


# ------------------------------------------------- le point « Ou j'en suis »

BILAN = """USER vient d'appuyer sur « Où j'en suis » sur son téléphone. Il écoute, il ne lit pas.
Réponds en 3 phrases parlées au plus, de 20 mots maximum chacune, en français, avec tous les accents.
Dans l'ordre : ce qui a bougé aujourd'hui, ce qui attend une décision de USER, puis la seule chose que tu lui recommandes maintenant.
Si un sujet traîne depuis longtemps, dis-le. Aucune question, aucune puce, aucun numéro de topic, aucun chemin de fichier, aucun tiret long.
Tu ne t'appuies que sur l'état ci-dessous. Rien d'inventé."""


def taches():
    """La to-do du jour, telle que `focus` la rend. Bornee a 6 s."""
    try:
        r = subprocess.run(["focus"], capture_output=True, text=True, timeout=6)
        return "\n".join(r.stdout.splitlines()[:40])
    except Exception:
        return ""


def bilan():
    t0 = time.time()
    etat = contexte()
    td = taches()
    if td:
        etat += "\n\n## Taches et cap (focus)\n" + td
    modele = reglage()
    try:
        dire = appeler(modele, BILAN, [], "Voici l'état :\n\n" + etat + "\n\nOù j'en suis ?")
    except Exception as e:
        journal("bilan : echec routeur {}".format(e))
        return ""
    dire = dire.replace("\u2014", ",").replace("\u2013", "-")
    journal("bilan {} {:.1f}s {}".format(modele, time.time() - t0, dire[:160]))
    return dire


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "tour" and len(sys.argv) > 2:
        dire = tour(sys.argv[2])
        # Le compte a rebours voyage avec la reponse. Un fichier partage dans
        # /tmp se perdait : 3 propositions sur 11 sans compte le 2026-10-01.
        print(("@compte@\n" if PROPOSE else "")
              + ("@choix@{}\n".format(CHOIX) if CHOIX else "") + dire)
    elif cmd == "bilan":
        print(bilan())
    elif cmd == "confirmer":
        print(confirmer())
    elif cmd == "annuler":
        print(annuler())
    elif cmd == "rapport" and len(sys.argv) > 2:
        sys.exit(choix_rapport(sys.argv[2]))
    elif cmd == "entendu" and len(sys.argv) > 3:
        entendu(sys.argv[2], sys.argv[3])
    elif cmd == "debut":
        try:
            os.remove(ETAT)
        except OSError:
            pass
    elif cmd == "contexte":
        print(message_systeme(lire_etat()))
        print("\nmodele : " + reglage())
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
