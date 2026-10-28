#!/usr/bin/env python3
"""Veilleur : signale une panne AVANT que USER ait a demander 'ca en est ou'.

Le constat qui l'a fait naitre : sur 426 messages, 40 sont des relances de
statut. Elles ne viennent pas d'impatience mais d'aveuglement : quand un tour
meurt (rate limit, 502, SIGKILL, connexion coupee), rien ne le dit. Le silence
d'un agent au travail et le silence d'un agent mort sont identiques.

Ce script les distingue, et parle de lui-meme dans le topic concerne.

Il se tait quand tout va bien. Une alerte qui se repete est une alerte qu'on
n'ouvre plus.
"""
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request

DB = os.path.expanduser("~/.hermes/qg.db")
ERRLOG = os.path.expanduser("~/.hermes/logs/errors.log")
ETAT = os.path.expanduser("~/.hermes/veilleur-etat.json")
ENV = os.path.expanduser("~/.hermes/.env")
SESSIONS = os.path.expanduser("~/.hermes/sessions")
HEALTH = "http://localhost:8000/health"

# Un tour SANS aucun outil ne dure jamais longtemps : au-dela, il est mort.
SEUIL_MUET = 14 * 60
# Un tour AVEC outils peut legitimement durer une heure (construire, deployer).
# Ce n'est donc pas sa duree qui le juge, c'est son pouls : le temps ecoule
# depuis le dernier outil termine. Un tour vivant bat toutes les secondes.
SEUIL_POULS = 10 * 60
# Ne jamais redire la meme chose avant 45 min, meme si la cause persiste.
SILENCE = 45 * 60

# Chaque motif porte son verdict : est-ce que ca repart tout seul, ou pas.
# C'est la seule information qui compte quand on lit l'alerte sur un telephone.
FATALES = [
    (r"session limit(?:[^|]*resets ([^|·]+))?", "limite de session atteinte", "reprend a la remise a zero", False),
    (r"rate.?limit", "limite de debit", "repart seul dans quelques minutes", False),
    (r"HTTP 402|requires more credits", "credits insuffisants", "NE repartira pas seul", True),
    (r"peer closed connection|incomplete chunked read", "connexion coupee en plein flux", "NE repart pas seul, le tour est perdu", True),
    (r"HTTP 50[23]|Bad Gateway|Service Unavailable", "passerelle amont en echec", "repart seul si c'est passager", False),
    (r"No Anthropic credentials", "authentification perdue", "NE repartira pas seul", True),
    (r"Timeout|timed out", "delai depasse", "NE repart pas seul, le tour est perdu", True),
]


def env(cle):
    try:
        for l in open(ENV):
            if l.startswith(cle + "="):
                return l.split("=", 1)[1].strip().strip("'\"")
    except Exception:
        pass
    return ""


def etat_lu():
    try:
        return json.load(open(ETAT))
    except Exception:
        return {"offset": None, "dits": {}}


def etat_ecrit(e):
    tmp = ETAT + ".tmp"
    json.dump(e, open(tmp, "w"))
    os.replace(tmp, ETAT)


def cible_de(sid, defaut):
    """Alerter dans le topic ou le tour est mort, pas dans un canal fourre-tout."""
    try:
        c = sqlite3.connect(DB, timeout=3)
        r = c.execute(
            "SELECT platform, chat_id, thread_id, nom_infere FROM topics WHERE session_id=?",
            (sid,)).fetchone()
        c.close()
    except Exception:
        return defaut, ""
    if not r or not r[1]:
        return defaut, ""
    return (str(r[1]), str(r[2] or "")), (r[3] or "")


def poster(cible, texte):
    tok = env("TELEGRAM_BOT_TOKEN")
    if not tok:
        return False
    chat, thread = cible
    d = {"chat_id": chat, "text": texte, "parse_mode": "Markdown"}
    if thread:
        d["message_thread_id"] = thread
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data=urllib.parse.urlencode(d).encode())
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception:
        return False


def _pid_proxy():
    """PID du claude-proxy, ou None. Sert a ne juger que ses propres enfants."""
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show", "-p", "MainPID", "--value",
             "claude-proxy"], capture_output=True, text=True, timeout=3)
        pid = int(out.stdout.strip())
        return pid if pid > 0 else None
    except Exception:
        return None


def _descend_de(pid, ancetre, profondeur=6):
    """Vrai si `pid` a `ancetre` quelque part dans sa chaine de parents."""
    try:
        cur = int(pid)
    except Exception:
        return False
    for _ in range(profondeur):
        if cur == ancetre:
            return True
        if cur <= 1:
            return False
        try:
            cur = int(open("/proc/%d/stat" % cur).read().rsplit(")", 1)[1].split()[1])
        except Exception:
            return False
    return False


def _fichiers_du_tour(uuid):
    """Transcript principal et transcripts des sous-agents d'un CLI.

    Un sous-agent au premier plan n'ecrit QUE dans <uuid>/subagents/ : le
    transcript principal reste fige pendant tout son travail. Le 2026-10-09,
    EntrepriseA 2 a tourne 3 h ainsi, le pouls du seul fichier principal mentait.
    """
    base = os.path.expanduser("~/.claude/projects/*/")
    return (glob.glob(base + "%s.jsonl" % uuid)
            + glob.glob(base + "%s/subagents/agent-*.jsonl" % uuid))


def travaux_en_cours():
    """Chaque CLI `claude` lance par le proxy, avec son depart et son pouls.

    Les outils ne sont pas executes par Hermes mais par ces processus : le hook
    post_tool_call d'Hermes ne se declenche donc JAMAIS en production, quoi
    qu'on y mette. Le seul battement observable est le transcript JSONL, qui
    grossit a chaque outil termine.

    On rend la liste, pas le maximum. Prendre le maximum revenait a se taire
    partout des qu'un seul sujet travaillait : le 2026-08-31, un tour mort
    depuis 2 h 55 est reste invisible tant qu'un scraping tournait ailleurs.
    """
    proxy = _pid_proxy()
    travaux = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = open("/proc/%s/cmdline" % pid, "rb").read().split(b"\0")
        except Exception:
            continue
        if not any(c.endswith(b"claude") for c in cmd[:1]):
            continue
        # Ne compter QUE les CLI lances par le proxy. USER garde des sessions
        # Claude Code interactives ouvertes dans ses terminaux, parfois depuis
        # des jours : le 2026-08-27, trois onglets du projet DJ dataient du
        # 18 aout et faisaient croire au veilleur a un pouls mort de 218 h.
        if proxy and not _descend_de(pid, proxy):
            continue
        uuid = None
        for drapeau in (b"--resume", b"--session-id"):
            try:
                uuid = cmd[cmd.index(drapeau) + 1].decode()
                break
            except Exception:
                continue
        if not uuid:
            continue
        try:
            depart = os.stat("/proc/%s" % pid).st_ctime
        except Exception:
            continue
        pouls = None
        for f in _fichiers_du_tour(uuid):
            try:
                m = os.path.getmtime(f)
            except Exception:
                continue
            if pouls is None or m > pouls:
                pouls = m
        travaux.append({"uuid": uuid, "depart": depart,
                        "pouls": pouls if pouls is not None else depart})
    return travaux


# Un CLI demarre quelques secondes apres le tour Hermes qui l'a declenche.
# Au-dela de cette fenetre, l'appariement n'est plus credible.
FENETRE_APPARIEMENT = (-60, 420)


def apparier(tours, travaux, liens):
    """Associe chaque tour Hermes au CLI qui travaille pour lui.

    Rien ne relie directement les deux : le proxy chaine ses sessions sur le
    contenu des messages, il ignore le session_id d'Hermes. Mais un CLI demarre
    dans les secondes qui suivent le tour, et garde le meme UUID d'un tour a
    l'autre tant que la chaine --resume tient. On apparie donc une fois par
    proximite de depart, puis on se souvient.

    Un tour sans CLI apparie n'est pas juge sur un pouls : il n'a pas de travail
    en cours, seule sa duree compte. Un appariement douteux (deux candidats dans
    la meme fenetre) est abandonne : se taire a tort coute une question de USER,
    alerter a tort coute la confiance dans l'alerte.
    """
    libres = {t["uuid"]: t for t in travaux}
    resultat = {}

    # 1. Les liens deja appris valent tant que leur CLI vit encore.
    for sid, uuid in list(liens.items()):
        if uuid in libres:
            resultat[sid] = libres.pop(uuid)

    # 2. Les tours restants s'apparient par proximite de depart, sans ambiguite.
    for sid, debut in tours:
        if sid in resultat or debut is None:
            continue
        cands = [t for t in libres.values()
                 if FENETRE_APPARIEMENT[0] <= t["depart"] - debut <= FENETRE_APPARIEMENT[1]]
        if len(cands) > 1:
            # Plusieurs tours partis ensemble : un CLI ne a 15 s du tour, les
            # autres a plus de 30 s, ce n'est pas deviner. Le 2026-10-09, 3 tours
            # en 3 min laissaient EntrepriseA 2 sans juge ni point d'etape.
            cands.sort(key=lambda c: abs(c["depart"] - debut))
            if (abs(cands[0]["depart"] - debut) <= 15
                    and abs(cands[1]["depart"] - debut) >= 30):
                cands = cands[:1]
        if len(cands) != 1:
            # 0 : aucun travail pour ce tour. Plusieurs : on ne devine pas.
            if len(cands) > 1:
                resultat[sid] = None  # ambigu : ne pas juger ce tour
            continue
        t = cands[0]
        libres.pop(t["uuid"], None)
        resultat[sid] = t
        liens[sid] = t["uuid"]

    # 3. Oublier les liens dont le CLI a disparu ET dont le tour est fini.
    vivants = {t["uuid"] for t in travaux}
    ouverts = {sid for sid, _ in tours}
    for sid in [s for s, u in liens.items()
                if u not in vivants and s not in ouverts]:
        liens.pop(sid, None)

    return resultat


def _demarrage_gateway():
    """Heure de demarrage du gateway, ou None.

    Sert a reconnaitre les tours fantomes : quand le gateway redemarre en plein
    tour, la fin du tour n'est jamais enregistree et la ligne reste en base
    pour toujours. Le veilleur alertait alors sur du vide, parfois des heures
    plus tard (2026-08-31, alerte de 2 h 55 sur un tour deja disparu).
    Tout tour commence AVANT le demarrage courant est donc mort par
    construction : on l'efface sans rien dire.
    """
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show", "-p", "MainPID", "--value",
             "hermes-gateway"], capture_output=True, text=True, timeout=3)
        pid = int(out.stdout.strip())
        if pid <= 0:
            return None
        return os.stat("/proc/%d" % pid).st_ctime
    except Exception:
        return None


def a_repondu(sid, debut):
    """Le transcript a-t-il bouge depuis le depart du tour ?

    Un tour peut finir sans que sa fin soit enregistree dans tours_actifs
    (gateway occupe, ecriture perdue). L'entree reste alors inscrite pour
    toujours et le veilleur crie a la panne sur un tour qui a repondu.
    Le transcript, lui, ne ment pas : s'il a ete ecrit apres le depart du
    tour, le tour a produit quelque chose. Constate le 2026-09-06 sur
    20260906_205614_2305f4, signale mort alors qu'il avait repondu.
    """
    try:
        f = os.path.join(SESSIONS, sid + ".jsonl")
        return os.path.getmtime(f) > (debut or 0) + 5
    except Exception:
        return False


def tours_bloques(now, e_liens=None, vivants=None):
    """Un tour parti et jamais rendu.

    Juger sur la duree seule produirait une fausse alerte a chaque tache longue.
    On juge donc sur le battement du transcript quand un travail tourne, sur la
    duree seulement quand plus aucun processus ne travaille.
    """
    out = []
    travaux = travaux_en_cours()
    try:
        c = sqlite3.connect(DB, timeout=3)
        # Un tour dont la fin n'a jamais ete enregistree (redemarrage du
        # gateway en plein vol) reste inscrit pour toujours et fait sonner
        # l'alerte a chaque passage. Au-dela de 3 h, c'est un fantome : on
        # l'efface au lieu de le signaler une deuxieme fois.
        # Sauf s'il a encore un CLI vivant : le 2026-10-09, EntrepriseA 2 a
        # travaille 3 h pour de vrai, la purge l'aurait rendu invisible.
        _vivants = {t["uuid"] for t in travaux}
        _liens = e_liens if e_liens is not None else {}
        for (_sid,) in c.execute("SELECT session_id FROM tours_actifs WHERE debut < ?",
                                 (now - 3 * 3600,)).fetchall():
            if _liens.get(_sid) not in _vivants:
                c.execute("DELETE FROM tours_actifs WHERE session_id = ?", (_sid,))
        # Meme raison, sans attendre 3 h : un tour anterieur au demarrage du
        # gateway courant n'a plus personne pour le finir. C'est un fantome,
        # pas une panne. On l'efface en silence.
        _demarre = _demarrage_gateway()
        if _demarre:
            c.execute("DELETE FROM tours_actifs WHERE debut < ?", (_demarre,))
        c.commit()
        tours = c.execute(
            "SELECT session_id, debut FROM tours_actifs").fetchall()
        liens = e_liens if e_liens is not None else {}
        assoc = apparier(tours, travaux, liens)
        for (sid, debut) in tours:
            age = now - (debut or now)
            t = assoc.get(sid, "absent")
            if t is None:
                continue  # appariement ambigu : on ne juge pas
            if t == "absent":
                # Aucun CLI ne travaille pour ce tour. Avant de le declarer
                # mort, on demande au transcript s'il a rendu quelque chose.
                if a_repondu(sid, debut):
                    c.execute(
                        "DELETE FROM tours_actifs WHERE session_id = ?", (sid,))
                    c.commit()
                    continue
                if age >= SEUIL_MUET:
                    out.append((sid, age, None, debut))
                continue
            mort = now - t["pouls"]
            if mort >= SEUIL_POULS:
                out.append((sid, age, mort, debut))
            elif vivants is not None:
                vivants.append((sid, debut, t))
        c.close()
    except Exception:
        pass
    return out


def erreurs_neuves(e):
    """Ne relit jamais deux fois la meme ligne : l'offset est persiste.

    Une rotation de log remet l'offset a zero plutot que de sauter le fichier :
    rater une panne coute plus cher que la redire une fois.
    """
    trouve = []
    try:
        taille = os.path.getsize(ERRLOG)
    except Exception:
        return trouve, e
    off = e.get("offset")
    if off is None or off > taille:
        # Premier passage : se caler sur la FIN. Alerter sur des pannes deja
        # passees et deja resolues detruirait la confiance dans l'alerte.
        off = taille if off is None else 0
    try:
        with open(ERRLOG, errors="replace") as f:
            f.seek(off)
            lignes = f.readlines()
            e["offset"] = f.tell()
    except Exception:
        return trouve, e
    for l in lignes:
        if " ERROR " not in l and " CRITICAL " not in l:
            continue
        for motif, cause, verdict, grave in FATALES:
            m = re.search(motif, l, re.I)
            if not m:
                continue
            s = re.search(r"\[([^\]]+)\]", l)
            detail = ""
            if m.groups() and m.group(1):
                detail = m.group(1).strip()
            trouve.append({
                "sid": s.group(1) if s else "",
                "cause": cause, "verdict": verdict,
                "grave": grave, "detail": detail,
                "quand": l[:19],
            })
            break
    return trouve, e


def proxy_degrade():
    try:
        with urllib.request.urlopen(HEALTH, timeout=6) as r:
            h = json.loads(r.read())
    except Exception:
        return "le proxy ne repond plus sur /health"
    if h.get("status") == "degraded":
        return f"proxy degrade, {h.get('consecutiveFailures')} echecs d'affilee"
    return ""


# Point d'etape d'un tour long qui travaille : USER doit savoir s'il travaille,
# s'il l'attend, ou s'il tourne sur une commande qui ne rend rien.
# Ne d'un constat du 2026-10-09 : EntrepriseA 2 a travaille 3 h sans un mot, USER a
# cru a un blocage. Le silence d'un agent qui avance et celui d'un agent coince
# se ressemblent : ce point les distingue.
POINT_PREMIER = 30 * 60      # premier point apres 30 min
POINT_ENSUITE = 60 * 60      # puis un par heure, sauf changement d'etat
COMMANDE_LONGUE = 10 * 60    # un outil sans resultat depuis 10 min : a signaler
CAPTCHAS = os.path.expanduser("~/.cache/opencli-humain/captchas.jsonl")


def _propre(t, n=90):
    """Texte sur une ligne, sans les caracteres qui cassent le Markdown Telegram."""
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    t = re.sub(r"[_*`\[\]]", " ", t)
    return t[:n] + ("..." if len(t) > n else "")


def _quand(iso):
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _resume_outil(nom, entree):
    if not isinstance(entree, dict):
        return nom
    if nom == "Bash":
        return "commande : " + _propre(entree.get("description") or entree.get("command"), 70)
    if nom in ("Agent", "Task"):
        return "sous-agent : " + _propre(entree.get("description"), 70)
    for v in entree.values():
        if isinstance(v, str) and v.strip():
            return f"{nom} : {_propre(v, 60)}"
    return nom


def dernier_geste(uuid, depuis):
    """Ce que fait le CLI : dernier outil lance, s'il a rendu, et par qui.

    Lit la fin de chaque transcript (principal et sous-agents) touche depuis le
    depart du tour. Rend None si rien n'est lisible.
    """
    lances, rendus = {}, set()
    for f in _fichiers_du_tour(uuid):
        try:
            if os.path.getmtime(f) < depuis:
                continue
            qui = ""
            meta = f[:-len(".jsonl")] + ".meta.json"
            if os.path.exists(meta):
                qui = _propre(json.load(open(meta)).get("description"), 50)
            with open(f, "rb") as h:
                h.seek(0, 2)
                h.seek(max(0, h.tell() - 400_000))
                lignes = h.read().decode("utf-8", "replace").splitlines()[1:]
        except Exception:
            continue
        for l in lignes:
            try:
                o = json.loads(l)
            except Exception:
                continue
            contenu = (o.get("message") or {}).get("content")
            if not isinstance(contenu, list):
                continue
            for b in contenu:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    t = _quand(o.get("timestamp", ""))
                    if t:
                        lances[b.get("id")] = (t, _resume_outil(b.get("name", "?"), b.get("input")), qui)
                elif b.get("type") == "tool_result":
                    rendus.add(b.get("tool_use_id"))
    # Un sous-agent lance au premier plan reste sans resultat pendant tout son
    # travail : ce n'est pas une commande coincee, c'est lui qui travaille.
    en_vol = [v for k, v in lances.items() if k not in rendus
              and not v[1].startswith("sous-agent")]
    if not lances:
        return None
    dernier = max(lances.values())
    return {"dernier": dernier, "en_vol": max(en_vol) if en_vol else None,
            "outils": len(lances)}


def _il_y_a(s):
    return "il y a moins d'1 min" if s < 60 else f"il y a {duree(s)}"


def captcha_en_attente(now):
    """Un CAPTCHA envoye a USER dans les 15 dernieres minutes et pas encore resolu."""
    try:
        with open(CAPTCHAS, "rb") as h:
            h.seek(0, 2)
            h.seek(max(0, h.tell() - 20_000))
            lignes = h.read().decode("utf-8", "replace").splitlines()[1:]
    except Exception:
        return None
    ouverts = {}
    for l in lignes:
        try:
            o = json.loads(l)
        except Exception:
            continue
        s = o.get("session")
        if "message" in o:
            ouverts[s] = o
        elif o.get("resolu") is not None:
            ouverts.pop(s, None)
    for o in ouverts.values():
        t = _quand(o.get("t", ""))
        if t and now - t < 15 * 60:
            return o.get("domaine") or "un site"
    return None


def points_d_etape(now, vivants, points, defaut):
    """Points deja dits : {cle: [instant, etat]}. Un point se redit apres 1 h,
    ou tout de suite si l'etat change (il travaillait, il t'attend)."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from qg_adresse import adresse
        qg = tuple(str(x) for x in adresse())
    except Exception:
        qg = defaut
    captcha = None
    for sid, debut, t in vivants:
        if not debut or str(sid).startswith("cron_"):
            continue
        age = now - debut
        if age < POINT_PREMIER:
            continue
        g = dernier_geste(t["uuid"], debut)
        if g is None:
            continue
        if captcha is None:
            captcha = captcha_en_attente(now) or ""
        en_vol = g["en_vol"]
        if captcha:
            etat = "attend"
            verdict = (f"Il t'attend : un CAPTCHA sur {_propre(captcha, 40)}. "
                       f"Le lien est dans le QG, il reprend seul une fois résolu.")
        elif en_vol and now - en_vol[0] >= COMMANDE_LONGUE:
            etat = "long"
            par = f" (sous-agent {en_vol[2]})" if en_vol[2] else ""
            verdict = (f"Une commande tourne depuis {duree(now - en_vol[0])} sans rendre{par} :\n"
                       f"{en_vol[1]}\n"
                       f"Si c'est une page à débloquer, c'est à toi. Sinon elle finira par expirer.")
        else:
            etat = "travaille"
            d = g["dernier"]
            par = f" (sous-agent {d[2]})" if d[2] else ""
            verdict = (f"Il travaille : dernière action {_il_y_a(now - d[0])}{par}.\n"
                       f"{d[1]}\nRien à faire de ton côté.")
        cle = f"point:{sid}:{int(debut)}"
        avant = points.get(cle)
        if avant and avant[1] == etat and now - avant[0] < POINT_ENSUITE:
            continue
        _, nom = cible_de(sid, defaut)
        titre = f"*{_propre(nom, 40)}*" if nom else "*Un agent*"
        texte = (f"{titre} tourne depuis {duree(age)}, {g['outils']} outils lancés.\n\n"
                 f"{verdict}")
        if poster(qg, texte):
            points[cle] = [now, etat]


def duree(s):
    m = int(s // 60)
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d}"


def main():
    e = etat_lu()
    now = time.time()
    dits = e.get("dits", {})
    defaut = (env("TELEGRAM_HOME_CHANNEL"), "")
    envoyes = 0

    def dire(empreinte, cible, texte):
        nonlocal envoyes
        if now - dits.get(empreinte, 0) < SILENCE:
            return
        if poster(cible, texte):
            dits[empreinte] = now
            envoyes += 1

    liens = e.get("liens") or {}
    # Un tour mort se dit UNE fois. Le redire toutes les 45 min n'apporte
    # aucune information neuve et noie le fil (retour USER du 2026-09-07).
    _JAMAIS = 10 ** 12
    vivants = []
    for sid, age, mort, debut in tours_bloques(now, liens, vivants):
        cible, nom = cible_de(sid, defaut)
        ou = f" _{nom}_" if nom else ""
        if mort is None:
            preuve = (f"Un tour est parti il y a {duree(age)} sans lancer un seul "
                      f"outil, et n'est jamais revenu.")
        else:
            preuve = (f"Un tour tourne depuis {duree(age)}, mais rien ne bat depuis "
                      f"{duree(mort)} : plus aucun outil ne se termine.")
        # Par tour, plus par session : un topic vit des semaines. Avec la cle
        # par session, une seule alerte le rendait muet pour toujours (EntrepriseA 2
        # l'etait depuis le 18/09, d'ou 3 h de silence le 2026-10-09).
        _emp = f"bloque:{sid}:{int(debut or 0)}"
        _neuf = _emp not in dits
        dire(_emp, cible,
             f"⏳ *Ca ne repond plus*{ou}\n\n{preuve}\n"
             f"Ce n'est pas du travail en cours, c'est un tour mort.\n\n"
             f"Dis-moi de reprendre, je repars du dernier etat connu.")
        if _neuf and _emp in dits:
            dits[_emp] = _JAMAIS  # dit une fois, plus jamais repete

    points = e.get("points") or {}
    points_d_etape(now, vivants, points, defaut)
    e["points"] = {k: v for k, v in points.items() if now - v[0] < 6 * 3600}

    neuves, e = erreurs_neuves(e)
    for n in neuves:
        cible, nom = cible_de(n["sid"], defaut)
        ou = f" _{nom}_" if nom else ""
        d = f" (retour a {n['detail']})" if n["detail"] else ""
        marque = "🔴" if n["grave"] else "🟠"
        dire(f"err:{n['cause']}:{n['sid']}", cible,
             f"{marque} *Tour interrompu*{ou}\n\n"
             f"Cause : {n['cause']}{d}.\n"
             f"Suite : {n['verdict']}.\n\n"
             f"Je ne relance pas de moi-meme.")

    p = proxy_degrade()
    if p:
        dire("proxy", defaut,
             f"🔴 *La passerelle est en panne*\n\n{p.capitalize()}.\n\n"
             f"Tant que ca dure, aucun agent ne peut repondre. "
             f"Le healthcheck tente un redemarrage toutes les 3 min.")

    # Purge : une empreinte plus vieille que la fenetre ne sert plus a rien.
    # Une alerte de tour mort porte le depart du tour : oubliee apres 2 jours.
    def _garder(k, v):
        if k.count(":") >= 2 and k.startswith("bloque:"):
            try:
                return now - int(k.rsplit(":", 1)[1]) < 2 * 86400
            except ValueError:
                pass
        return now - v < SILENCE * 4
    e["dits"] = {k: v for k, v in dits.items() if _garder(k, v)}
    e["liens"] = liens
    etat_ecrit(e)
    return envoyes


if __name__ == "__main__":
    try:
        n = main()
        if "--verbeux" in sys.argv:
            print(f"veilleur: {n} alerte(s) envoyee(s)")
    except Exception as ex:
        print(f"veilleur en echec: {ex}", file=sys.stderr)
        sys.exit(1)
