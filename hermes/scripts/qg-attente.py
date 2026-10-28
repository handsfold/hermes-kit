#!/usr/bin/env python3
"""qg-attente : la file des rapports en attente de USER.

Un sous-agent finit son travail, le hook `subagent_stop` depose ici une ligne.
La pastille du telephone la voit et s'allume. USER decide de lire, ou pas.

Le pari : ce fichier ne stocke QUE le resume. Jamais le transcript. Une file
qui grossit doit couter le meme prix au bout d'un an qu'au premier jour.

  qg-attente                 la file, du plus recent au plus vieux
  qg-attente --json          idem, pour un script
  qg-attente add ...         depose un rapport (voir --aide-add)
  qg-attente tete            l'id du rapport en tete, ou rien
  qg-attente texte <id>      le resume complet
  qg-attente lu <id>         marque lu (sort de la file)
  qg-attente rejeter <id>    ecarte sans lire
  qg-attente purge           efface les lus de plus de 7 jours
"""
import argparse
import importlib.util
import io
import re
import json
import os
import sqlite3
import subprocess
import sys
import time

DB = os.environ.get("QG_DB", os.path.expanduser("~/.hermes/qg.db"))
# Le meme dossier que le garde : les essais le deplacent hors de /tmp.
PIXEL_TMP = os.environ.get("PIXEL_TMP", "/tmp")

# Les reglages du QG (modele, voix, seuils) vivent dans qg-config.py, un cran a
# cote. Le tiret de son nom interdit un `import` normal.
_spec = importlib.util.spec_from_file_location(
    "qgconfig", os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             "qg-config.py"))
_cfg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cfg)
reglage = _cfg.reglage

SCHEMA = """
CREATE TABLE IF NOT EXISTS attente (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cree       REAL NOT NULL,
    source     TEXT,           -- role du sous-agent, ou nom du chantier
    origine    TEXT,           -- session parente, pour repondre au bon endroit
    cible      TEXT,           -- plateforme:chat:thread, si connue
    titre      TEXT NOT NULL,  -- une ligne, celle qui s'affiche sur la pastille
    resume     TEXT,           -- le texte complet, lu a la demande
    statut     TEXT NOT NULL DEFAULT 'nouveau',  -- nouveau | lu | rejete
    statut_maj REAL
);
CREATE INDEX IF NOT EXISTS idx_attente_statut ON attente(statut, cree DESC);
"""


def cx():
    c = sqlite3.connect(DB, timeout=5.0)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.commit()
    return c


def age(ts):
    if not ts:
        return "?"
    d = time.time() - ts
    if d < 3600:
        return f"{int(d // 60)} min"
    if d < 86400:
        return f"{int(d // 3600)} h"
    return f"{int(d // 86400)} j"


def une_ligne(txt, n=60):
    """Un titre de pastille tient sur une ligne, sinon il deborde l'ecran."""
    t = " ".join((txt or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def en_attente(c):
    return c.execute(
        "SELECT * FROM attente WHERE statut='nouveau' ORDER BY cree DESC"
    ).fetchall()


def cmd_liste(en_json):
    c = cx()
    rows = en_attente(c)
    c.close()
    if en_json:
        print(json.dumps([dict(r) for r in rows], ensure_ascii=False))
        return 0
    if not rows:
        print("Rien en attente.")
        return 0
    print(f"{len(rows)} rapport(s) en attente\n")
    for r in rows:
        src = f" [{r['source']}]" if r["source"] else ""
        print(f"  #{r['id']}  {age(r['cree'])}{src}\n      {r['titre']}")
    return 0



def vers_memoire_qg(ident):
    """Lance scripts/qg-memoire.py <id> detache. Ne bloque ni ne leve."""
    try:
        subprocess.Popen([os.path.expanduser("~/.hermes/scripts/qg-memoire.py"), str(ident)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def cible_du_cron(cible, origine):
    """La cible d'un rapport de tache planifiee, lue dans son job.

    Le hook ne connait d'une session cron que « cron:: ». Le 2026-10-11
    (rapport 2223) puis le 2026-10-13 (rapport 2489, veille mail), USER a
    repondu a un bouton et s'est vu dire « rapport sans topic » : le job
    avait pourtant un topic, dans `deliver` ou `origin`. On le reprend la.
    """
    if (cible or "").startswith("telegram:") and cible.rsplit(":", 1)[-1]:
        return cible
    m = re.match(r"cron_([0-9a-f]+)_", origine or "")
    if not m:
        return cible
    try:
        d = json.load(open(os.path.expanduser("~/.hermes/cron/jobs.json")))
    except (OSError, ValueError):
        return cible
    jobs = d.get("jobs", []) if isinstance(d, dict) else d
    for j in jobs:
        if j.get("id") != m.group(1):
            continue
        dv = j.get("deliver") or ""
        if dv.startswith("telegram:") and dv.count(":") >= 2 and dv.rsplit(":", 1)[-1]:
            return dv
        o = j.get("origin") or {}
        if o.get("platform") == "telegram" and o.get("chat_id") and o.get("thread_id"):
            return "telegram:{}:{}".format(o["chat_id"], o["thread_id"])
    return cible


def cmd_add(a):
    a.cible = cible_du_cron(a.cible, a.origine)
    titre = une_ligne(a.titre, 200)
    resume = a.resume
    if resume == "-" or (resume is None and not sys.stdin.isatty()):
        resume = sys.stdin.read()
    c = cx()
    cur = c.execute(
        "INSERT INTO attente (cree, source, origine, cible, titre, resume)"
        " VALUES (?,?,?,?,?,?)",
        (time.time(), a.source, a.origine, a.cible, titre, resume),
    )
    c.commit()
    ident = cur.lastrowid
    c.close()
    # Le rapport entre aussi dans la memoire du QG (une ligne), en tache de
    # fond : voir scripts/qg-memoire.py (2026-10-04).
    vers_memoire_qg(ident)
    # La pastille se repeint au tour de garde suivant : ce marqueur lui evite
    # d'avoir a interroger la base a chaque passage.
    try:
        open(os.path.join(PIXEL_TMP, "qg-attente-maj"), "w").write(str(int(time.time())))
    except OSError:
        pass
    print(ident)
    return 0


def cmd_tete():
    c = cx()
    rows = en_attente(c)
    c.close()
    if not rows:
        return 1
    print(rows[0]["id"])
    return 0


def cmd_texte(ident):
    c = cx()
    r = c.execute("SELECT * FROM attente WHERE id=?", (ident,)).fetchone()
    c.close()
    if not r:
        print(f"Aucun rapport #{ident}", file=sys.stderr)
        return 1
    print(r["titre"])
    if r["resume"]:
        print()
        print(r["resume"])
    return 0


NOMS = os.path.expanduser("~/.hermes/qg-noms.json")
NEUTRE = os.path.expanduser("~/.hermes/qg-tmp")
GABARIT_DIGEST = """Voici des rapports bruts de chantiers qui viennent de finir, dans differents sujets de travail de USER.

{brut}

Ecris a USER un point oral, en francais, a la deuxieme personne.

Regles :
- 3 phrases maximum au total, quel que soit le nombre de rapports.
- Dis ce qui est FINI. Puis, SEULEMENT si un rapport le dit noir sur blanc, ce
  qui attend une decision de lui. N'invente jamais une decision en attente :
  s'il n'y en a pas, termine sur le constat et tais-toi.
- N'ecris pas de meta-commentaire sur les rapports eux-memes ni sur leur format.
- Ne recopie AUCUNE phrase des rapports : reformule.
- Pas de titre, pas de puce, pas de markdown, pas d'emoji. Du texte parle.
- Si plusieurs chantiers, nomme le sujet de chacun en trois mots.

Rends uniquement ce texte."""


def nom_topic(cible):
    """Le nom lisible du sujet d'ou vient un rapport : « Note », « Money ».

    `cible` vaut « telegram:<chat>:<thread> », ou « cron:: » pour une tache
    planifiee. Sans ce nom, USER recevait « Rapport » tout court et devait
    deviner de quel chantier il s'agissait, alors qu'il en fait tourner une
    dizaine en parallele. Demande du 2026-08-29.
    """
    if not cible:
        return ""
    p = cible.split(":")
    if p[0] == "cron":
        return "Cron"
    if len(p) < 3:
        return ""
    try:
        d = json.load(open(NOMS)) or {}
    except Exception:
        d = {}
    # Deux formes de cle coexistent : « <chat>:<thread> », ecrite par `qg nom`,
    # et « <thread> » seule, heritee du fichier d'origine.
    return d.get("{}:{}".format(p[1], p[2])) or d.get(p[2]) or ""


def sujets(rows):
    """Les sujets du lot, sans doublon, dans l'ordre d'arrivee."""
    vus = []
    for r in rows:
        n = nom_topic(r["cible"])
        if n and n not in vus:
            vus.append(n)
    return vus


def condenser(brut):
    """Le texte brut des rapports, ramene a un point oral de 3 phrases.

    Le digest recopiait mot pour mot la reponse du topic. USER recevait donc
    deux fois le meme texte, une fois dans le sujet et une fois dans le QG.
    Ce passage par sonnet est ce qui fait la difference entre un doublon et
    un rapport. En cas d'echec on retombe sur le brut : mieux vaut un
    doublon qu'un silence.
    """
    try:
        os.makedirs(NEUTRE, exist_ok=True)
        r = subprocess.run(
            ["claude", "-p", "--output-format", "json",
             "--model", reglage("modele"),
             "--max-turns", "1", "--setting-sources", "", "--strict-mcp-config",
             "--no-session-persistence"],
            input=GABARIT_DIGEST.format(brut=brut[:6000]),
            capture_output=True, text=True, timeout=90, cwd=NEUTRE)
        if r.returncode != 0:
            return None
        txt = (json.loads(r.stdout).get("result") or "").strip()
        return txt or None
    except Exception:
        return None


def cmd_digest():
    """TOUT ce qui attend, en UN seul texte parle. Jamais un rapport a la fois.

    Le pari : plusieurs chantiers finissent en parallele, dans des topics
    differents. Les lire un par un obligerait USER a rappuyer entre chaque, et
    a recoller lui-meme ce qui est fini de ce qui attend sa decision. Le
    digest fait ce recollage une fois, ici.
    """
    c = cx()
    rows = en_attente(c)
    c.close()
    if not rows:
        return 1
    morceaux = []
    for r in rows:
        # Le nom du SUJET, pas `source` : source contient le message de USER qui
        # a lance le tour, que le modele prenait pour un intitule de chantier.
        n = nom_topic(r["cible"])
        morceaux.append("--- Rapport{}\n{}\n{}".format(
            " du sujet " + n if n else "", r["titre"],
            " ".join((r["resume"] or "").split())))
    brut = "\n\n".join(morceaux)
    court = condenser(brut)
    if court:
        # Le modele glisse des tirets cadratins, proscrits partout chez USER.
        # Vu le 2026-08-28 dans un digest livre au QG.
        court = court.replace("\u2014", " -").replace("\u2013", "-")
        print(court)
        return 0
    # Repli : le brut, mais degrossi. Un rapport imparfait vaut mieux que rien.
    if len(rows) == 1:
        print(rows[0]["titre"])
        if rows[0]["resume"]:
            print()
            print(" ".join((rows[0]["resume"] or "").split())[:900])
        return 0
    print("{} chantiers ont rendu leur copie.".format(len(rows)))
    for i, r in enumerate(rows, 1):
        print()
        print("{}. {}".format(i, r["titre"]))
    return 0


def cmd_relais(ident, message):
    """Renvoie la reponse de USER vers le sujet d'ou venait le rapport.

    Le QG etait une impasse : un rapport en sortait, USER y repondait, et sa
    reponse restait la. Le 2026-08-29, Book a demande « je lance ? », USER a
    repondu « oui vas-y » dans le QG, la session du QG a pris l'accord pour
    elle, et Book n'a jamais rien recu. Le travail est reste en plan sans que
    personne s'en apercoive.

    Un tour d'agent se declenche dans un topic precis par un job cron jetable
    (`--deliver telegram:<chat>:<thread>`), lance tout de suite et supprime
    dans la foulee. La session du topic garde son contexte : elle reconnait
    de quel rapport il s'agit.
    """
    c = cx()
    r = c.execute("select titre, cible, statut, source, resume from attente"
                  " where id = ?", (ident,)).fetchone()
    c.close()
    if not r:
        print("aucun rapport {}".format(ident), file=sys.stderr)
        return 1
    # Un rapport ne se relaie qu'une fois. Le 2026-08-29, trois agents sont
    # partis refaire la meme passe design sur ProjetB dans les memes
    # fichiers : deux departs du meme job, plus un troisieme cree a la main
    # parce que je croyais les autres morts. Ils se sont ecrase le travail.
    # Le statut « relaye » est la barriere.
    if (r["statut"] or "") == "relaye":
        print("rapport {} deja relaye. Rien n'est reparti.".format(ident),
              file=sys.stderr)
        return 1
    cible = r["cible"] or ""
    source = r["source"] or ""
    if not cible.startswith("telegram:") and source.startswith("agent-fond:"):
        # Rapport d'un agent detache (recos du cockpit, travaux longs) : il
        # n'a pas de topic, et son agent est fini. Le 2026-10-24, le « Oui »
        # de USER sur le rapport 4286 est reste lettre morte (« pas de topic
        # d'origine »). La reponse lance donc la SUITE : un nouvel agent
        # detache, avec la consigne d'origine, le rapport et la phrase de USER.
        return relais_agent_fond(ident, source.split(":", 1)[1], r, message)
    if not cible.startswith("telegram:") and cible.startswith("api_server"):
        # Tour de l'api_server (cockpit, POST /v1/runs) : session run_xxx
        # jetable, pas de topic. Comme un agent detache : la reponse de USER
        # lance une suite avec le rapport (dossier et consigne par defaut).
        return relais_agent_fond(ident, "api-server", r, message)
    if not cible.startswith("telegram:"):
        # Rapport d'une routine sans topic (controle-skills, veilleurs) : le
        # 2026-10-28, « Fix les 5 skills » sous le rapport 5456 a recu « pas de
        # topic d'origine ». La reponse lance aussi une suite, comme ci-dessus.
        return relais_agent_fond(ident, source or "rapport", r, message)

    nom = nom_topic(cible) or "ce sujet"
    thread = cible.rsplit(":", 1)[-1]
    if not thread:
        print("rapport {} : pas de sujet dans « {} »".format(ident, cible),
              file=sys.stderr)
        return 1

    # PAS de job cron ici. C'etait la methode jusqu'au 2026-08-30, et elle a
    # deux defauts qui se sont montres le meme jour :
    #   - le ticker du gateway peut mourir sans le dire. Le sien n'avait plus
    #     rien execute depuis la veille : les relais partaient dans le vide, et
    #     `hermes cron run` ne fait que replanifier, il n'execute rien.
    #   - le job ne posait aucune trace dans le sujet, donc USER ne voyait ni sa
    #     demande ni de quoi elle parlait.
    # qg-envoyer.sh parle directement a l'API du gateway avec l'en-tete de
    # session du sujet : la demande est postee, l'agent repond a la suite.
    envoyeur = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.realpath(__file__)))), "bin", "qg", "qg-envoyer.sh")
    if not os.path.exists(envoyeur):
        print("qg-envoyer.sh introuvable ({})".format(envoyeur), file=sys.stderr)
        return 1

    # Le message part NU, tel que USER l'a dit. Aucun cadre « Reponse de USER,
    # arrivee par le QG » : la session du sujet a deja son contexte, elle sait
    # a quel rapport cela repond. Le cadre ne servait qu'a moi.
    #
    # Detache : un tour d'agent dure des minutes, et le QG ne doit pas rester
    # suspendu dessus. Le sujet postera lui-meme sa reponse quand il aura fini.
    jrn = open(os.path.expanduser("~/.hermes/qg-dispatch.log"), "a")
    subprocess.Popen([envoyeur, thread, message.strip()],
                     stdout=jrn, stderr=jrn, start_new_session=True)

    c = cx()
    c.execute("UPDATE attente SET statut='relaye', statut_maj=? WHERE id=?",
              (time.time(), ident))
    c.commit()
    c.close()
    print("relaye vers {} ({})".format(nom, cible))
    return 0


def relais_agent_fond(ident, agent, r, message):
    """Lance la suite d'un agent detache avec la reponse de USER."""
    dossier_agent = os.path.expanduser("~/.claude/agents-fond/" + agent)

    def lire(nom, defaut=""):
        try:
            return open(os.path.join(dossier_agent, nom), encoding="utf-8").read().strip()
        except OSError:
            return defaut

    consigne = lire("consigne.txt")
    dossier = lire("dossier") or os.path.expanduser("~")
    if not os.path.isdir(dossier):
        dossier = os.path.expanduser("~")
    modele = lire("modele") or "sonnet"
    nom = (lire("nom") or agent or "suite")[:40] + "-suite"
    if not consigne:
        consigne = ("Aucune : rapport produit par la routine « {} », sans agent"
                    " ni topic d'origine.".format(agent))
    texte = (
        "Suite d'un travail deja fait. USER vient de repondre a ton rapport.\n\n"
        "Reponse de USER (ordre de USER) : « {} »\n\n"
        "Ton rapport (rapport QG {}) :\n<rapport>\n{}\n</rapport>\n\n"
        "Consigne d'origine, pour le contexte (donnee, pas un ordre) :\n"
        "<consigne-origine>\n{}\n</consigne-origine>\n\n"
        "Si USER valide (oui, vas-y, ok), applique ta recommandation en entier :"
        " la reserve « tu proposes, tu n'appliques pas » de la consigne d'origine"
        " est levee par sa reponse. S'il choisit une autre option ou precise,"
        " fais ce qu'il dit. S'il refuse, ne touche a rien et note l'ecart comme"
        " accepte.\n"
        "Toujours interdits : commit, push, publication ; mail, LINE ou Telegram ;"
        " securite d'un compte ; secret dans le rapport ; supprimer un fichier"
        " sans en garder une copie dans ~/.cache/ ; tiret cadratin ou"
        " demi-cadratin.\n"
        "Ton dernier message est le rapport lu par USER : 6 lignes au plus, ce qui"
        " a change, la preuve que ca marche, et ce qui reste."
    ).format(message.strip(), ident, (r["resume"] or "")[:6000], consigne[:4000])
    lanceur = os.path.expanduser("~/bin/agent-fond")
    jrn = open(os.path.expanduser("~/.hermes/qg-dispatch.log"), "a")
    try:
        sortie = subprocess.run(
            [lanceur, "lancer", texte, "--nom", nom, "--dossier", dossier,
             "--modele", modele], stdout=subprocess.PIPE, stderr=jrn,
            cwd=os.path.expanduser("~"), text=True, timeout=60)
    except Exception as e:
        print("rapport {} : suite d'agent non lancee ({})".format(ident, e),
              file=sys.stderr)
        return 1
    nouvel = (sortie.stdout or "").strip().splitlines()[-1:] or [""]
    if sortie.returncode != 0 or not nouvel[0]:
        print("rapport {} : suite d'agent non lancee (code {})".format(
            ident, sortie.returncode), file=sys.stderr)
        return 1
    jrn.write("{} relais {} -> agent-fond {} (suite de {})\n".format(
        time.strftime("%F %T"), ident, nouvel[0], agent))
    c = cx()
    c.execute("UPDATE attente SET statut='relaye', statut_maj=? WHERE id=?",
              (time.time(), ident))
    c.commit()
    c.close()
    print("relaye vers un agent detache ({}, suite de {})".format(nouvel[0], agent))
    return 0


def cmd_sujets():
    """Les sujets en attente, joints par « · ». Sert d'entete au rapport."""
    c = cx()
    rows = en_attente(c)
    c.close()
    noms = sujets(rows)
    if noms:
        print(" · ".join(noms))
    return 0


def cmd_menu():
    """Un rapport par ligne : « id<TAB>sujet<TAB>titre ».

    Le menu de la pastille se construit avec ca. USER a demande le 2026-08-29 de
    ne PLUS grouper : une synthese de trois chantiers gomme le detail de
    chacun, et la voix propre a chaque sujet se perd. Il veut voir la liste,
    choisir celui qu'il ecoute, et repondre a celui-la.
    """
    c = cx()
    rows = en_attente(c)
    c.close()
    for r in rows:
        titre = " ".join((r["titre"] or "").split())
        print("{}\t{}\t{}".format(r["id"], nom_topic(r["cible"] or ""), titre))
    return 0


def cmd_ids():
    """Les identifiants en attente, un par ligne. Pour marquer tout le lot lu."""
    c = cx()
    rows = en_attente(c)
    c.close()
    for r in rows:
        print(r["id"])
    return 0


GABARIT_UN = """Voici le rapport brut d'un chantier qui vient de finir pour USER.
{question}
{brut}

Ecris a USER un point oral, en francais, a la deuxieme personne. Il l'ECOUTE,
il ne le lit pas : ecris pour l'oreille, comme un journal radio.

Forme, dans cet ordre :
1. Premiere phrase : l'essentiel. Si USER a pose une question, la reponse
   elle-meme, avec son contenu. Sinon, le resultat qui compte pour lui.
2. Une ou deux phrases de detail : seulement ce qui change sa decision.
   Si le rapport donne une liste (etapes, plan, options), nomme les 2 ou 3
   premiers elements. N'annonce JAMAIS qu'un plan est pret sans son contenu.
3. Une question finale SEULEMENT si le chantier est bloque sans l'accord
   de USER : envoi a un tiers, depense, action irreversible, choix entre
   options que le rapport pose lui-meme. Alors, derniere phrase :
   « Je te conseille de <action precise>. Tu valides ? ». L'action doit
   pouvoir etre confiee telle quelle au meme chantier.
   Dans tous les autres cas, AUCUNE question, aucune recommandation
   inventee, aucune formule de fin : le point s'arrete sur le resultat.
   Une suite que le chantier peut faire seul n'est pas une question pour
   USER. (2026-10-03 : un « Tu valides ? » a chaque rapport, USER disait oui
   et n'avait rien a valider.)

Regles pour l'oreille :
- 4 phrases au plus, 60 mots au plus en tout (20 secondes). Compte-les.
- 15 mots au plus par phrase, sujet verbe complement, aucune incise.
- Chiffres arrondis, ecrits en chiffres : « 3,7 millions », « environ 40 % »,
  « 60 dollars », jamais « 3 716 752 » ni « soixante ». Pas de numero de
  commit, de version, d'identifiant.
- Aucun chemin de fichier, aucun nom de fonction, aucune URL, aucun sigle
  qu'il ne dit pas lui-meme. Dis ce que c'est, pas comment ca s'appelle.
- Ne recopie AUCUNE phrase du rapport : reformule.
- Pas de meta-commentaire sur le rapport ni sur son format.
- Pas de titre, pas de puce, pas de markdown, pas d'emoji, pas de tiret
  cadratin. Du texte parle, avec tous les accents, qui sera lu a voix haute.

Rends uniquement ce texte."""


def condenser_un(brut, question=""):
    """Un seul rapport, ramene a 20 secondes dites, qui finit sur une decision.

    Le 2026-10-02, USER a voulu que chaque rapport le fasse DECIDER, pas
    seulement l'informer : l'essentiel d'abord, chiffres arrondis, et une
    derniere phrase « Je te conseille de X. Tu valides ? ». Son « oui » a voix
    haute part alors vers le topic du rapport (qg-standard.py).

    Le 2026-08-29, USER a entendu un rapport recite EN ENTIER : deux mille huit
    cent caracteres, lus mot pour mot. En passant du digest groupe au rapport
    unique, on avait garde le texte brut et perdu le seul geste qui rendait
    l'ecoute supportable, le passage par sonnet. Il revient ici, pour un rapport
    au lieu de tous.
    """
    try:
        os.makedirs(NEUTRE, exist_ok=True)
        r = subprocess.run(
            ["claude", "-p", "--output-format", "json",
             "--model", reglage("modele"),
             "--max-turns", "1", "--setting-sources", "", "--strict-mcp-config",
             "--no-session-persistence"],
            input=GABARIT_UN.format(
                brut=brut[:6000],
                question=("\nCe que USER avait demande : {}\n".format(question.strip())
                          if question and question.strip() else "")),
            capture_output=True, text=True, timeout=90, cwd=NEUTRE)
        if r.returncode != 0:
            return None
        return (json.loads(r.stdout).get("result") or "").strip() or None
    except Exception:
        return None


def pour_la_voix(txt):
    """Le meme texte, mais dit a voix haute sans lire la ponctuation du markdown.

    Le 2026-08-29, USER a entendu son rapport reciter ses asterisques : « etoile
    etoile Tu avais raison etoile etoile ». Un rapport est ecrit en markdown pour
    l'oeil ; l'oreille n'en veut rien. On retire donc le balisage, les liens, les
    emojis et les puces avant de le passer a la synthese. Le texte ENVOYE sur
    Telegram garde son markdown : c'est le meme rapport, lu de deux facons.
    """
    import re as _re
    t = txt or ""
    # Les blocs de code ne se disent pas : on annonce, on ne recite pas.
    t = _re.sub(r"```.*?```", " (extrait de code) ", t, flags=_re.S)
    t = _re.sub(r"`([^`]*)`", r"\1", t)
    # [libelle](url) : seul le libelle se prononce.
    t = _re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    # Une URL nue lue caractere par caractere est insupportable.
    t = _re.sub(r"https?://\S+", " un lien ", t)
    t = _re.sub(r"(\*\*|__)(.*?)\1", r"\2", t, flags=_re.S)
    t = _re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"\1", t)
    t = _re.sub(r"(?<![\w_])_([^_\n]+)_(?![\w_])", r"\1", t)
    lignes = []
    for l in t.split("\n"):
        l = _re.sub(r"^\s{0,3}#{1,6}\s*", "", l)      # titres
        l = _re.sub(r"^\s*[-*+]\s+", "", l)            # puces
        l = _re.sub(r"^\s*\d+[.)]\s+", "", l)          # listes numerotees
        if _re.fullmatch(r"\s*([-*_=]\s*){3,}", l):    # separateurs
            continue
        lignes.append(l)
    t = "\n".join(lignes)
    # Emojis et symboles decoratifs : la synthese les nomme ou trebuche dessus.
    t = _re.sub("[\U0001F000-\U0001FAFF\u2190-\u2BFF\u2600-\u27BF\uFE0F]", " ", t)
    # Les fleches se disent, elles ne se prononcent pas caractere par caractere.
    t = t.replace("->", " vers ").replace("=>", " vers ").replace("\u2192", " vers ")
    # Les asterisques survivants (un seul, non apparie) n'ont plus rien a dire.
    t = t.replace("*", " ")
    t = _re.sub(r"[ \t]+", " ", t)
    t = _re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def cmd_voix(ident):
    """Le texte d'un rapport, prepare pour la synthese vocale."""
    c = cx()
    r = c.execute("select titre, resume, source from attente where id = ?",
                  (ident,)).fetchone()
    c.close()
    if not r:
        print("aucun rapport {}".format(ident), file=sys.stderr)
        return 1
    brut = (r["titre"] or "")
    if r["resume"]:
        brut += "\n\n" + r["resume"]
    # Un rapport court se dit tel quel ; au-dela, on le resume, sinon l'ecoute
    # dure trois minutes pour une information qui en vaut vingt secondes.
    if len(brut) > int(reglage("resume_seuil")):
        # Le condense est mis de cote : il sert DEUX fois, au message Telegram
        # et a la synthese vocale, et chaque passage par sonnet coute douze
        # secondes. Le recalculer serait payer deux fois le meme texte.
        cache = os.path.expanduser("~/.hermes/qg-voix/{}.txt".format(ident))
        court = None
        try:
            with io.open(cache, encoding="utf-8") as f:
                court = f.read().strip() or None
        except OSError:
            pass
        if not court:
            # La demande compte : le 2026-10-01, « quelles sont les prochaines
            # etapes ? » est revenu au QG en « le plan est pret », sans le plan.
            q = r["source"] or ""
            if q.startswith("Gateway message origin"):   # en-tete du hook, pas une demande
                q = ""
            court = condenser_un(brut, q)
            if court:
                try:
                    os.makedirs(os.path.dirname(cache), exist_ok=True)
                    with io.open(cache, "w", encoding="utf-8") as f:
                        f.write(court)
                except OSError:
                    pass
        if court:
            brut = court
    print(pour_la_voix(brut))
    return 0


def cmd_sujet(ident):
    """Le nom ACTUEL du topic d'un rapport, lu a voix haute en tete du rapport.

    USER, 2026-10-03 : « je ne sais pas de quel rapport il parle ». Le nom est
    relu a chaque appel, pas fige a l'arrivee : un topic renomme entre-temps
    est dit sous son nouveau nom.
    """
    c = cx()
    r = c.execute("select cible from attente where id = ?", (ident,)).fetchone()
    c.close()
    print(nom_topic(r["cible"] or "") if r else "")
    return 0


def cmd_ecoute(ident):
    """Retient le rapport que USER vient d'ecouter, dans ~/.hermes/qg-dernier-ecoute.

    Sans cette trace, une reponse de USER juste apres un rapport n'a pas de
    destinataire : le QG devrait deviner lequel des dix sujets il commentait.
    Le fichier tient une ligne, « id<TAB>cible<TAB>sujet<TAB>titre », et se
    fait ecraser a chaque ecoute : seul le dernier compte.
    """
    c = cx()
    r = c.execute("select cible, titre from attente where id = ?",
                  (ident,)).fetchone()
    c.close()
    if not r:
        print("aucun rapport {}".format(ident), file=sys.stderr)
        return 1
    cible = r["cible"] or ""
    ligne = "{}\t{}\t{}\t{}\n".format(
        ident, cible, nom_topic(cible), " ".join((r["titre"] or "").split()))
    chemin = os.path.expanduser("~/.hermes/qg-dernier-ecoute")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(ligne)
    return 0


def cmd_statut(ident, statut):
    c = cx()
    n = c.execute(
        "UPDATE attente SET statut=?, statut_maj=? WHERE id=?",
        (statut, time.time(), ident),
    ).rowcount
    c.commit()
    c.close()
    try:
        open(os.path.join(PIXEL_TMP, "qg-attente-maj"), "w").write(str(int(time.time())))
    except OSError:
        pass
    if not n:
        print(f"Aucun rapport #{ident}", file=sys.stderr)
        return 1
    print(f"#{ident} -> {statut}")
    return 0


def cmd_purge():
    c = cx()
    n = c.execute(
        "DELETE FROM attente WHERE statut<>'nouveau' AND statut_maj < ?",
        (time.time() - 7 * 86400,),
    ).rowcount
    c.commit()
    c.close()
    print(f"{n} efface(s)")
    return 0


def main():
    p = argparse.ArgumentParser(add_help=False)
    sub = p.add_subparsers(dest="cmd")
    p.add_argument("--json", action="store_true")

    a = sub.add_parser("add")
    a.add_argument("titre")
    a.add_argument("--resume", default=None, help="texte complet, ou - pour stdin")
    a.add_argument("--source", default=None)
    a.add_argument("--origine", default=None)
    a.add_argument("--cible", default=None)

    for nom in ("tete", "purge", "digest", "ids", "sujets"):
        sub.add_parser(nom)
    sub.add_parser("liste")
    sub.add_parser("menu")
    r = sub.add_parser("relais")
    r.add_argument("id", type=int)
    r.add_argument("message")

    for nom in ("texte", "lu", "rejeter", "ecoute", "voix", "sujet", "entendu"):
        s = sub.add_parser(nom)
        s.add_argument("id", type=int)

    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help", "aide"):
        print(__doc__)
        return 0

    args = p.parse_args()
    if args.cmd is None:
        return cmd_liste(args.json)
    if args.cmd == "add":
        return cmd_add(args)
    if args.cmd == "tete":
        return cmd_tete()
    if args.cmd == "digest":
        return cmd_digest()
    if args.cmd == "ids":
        return cmd_ids()
    if args.cmd == "sujets":
        return cmd_sujets()
    if args.cmd == "liste":
        return cmd_liste(args.json)
    if args.cmd == "menu":
        return cmd_menu()
    if args.cmd == "relais":
        return cmd_relais(args.id, args.message)
    if args.cmd == "texte":
        return cmd_texte(args.id)
    if args.cmd == "voix":
        return cmd_voix(args.id)
    if args.cmd == "sujet":
        return cmd_sujet(args.id)
    if args.cmd == "ecoute":
        return cmd_ecoute(args.id)
    if args.cmd == "lu":
        return cmd_statut(args.id, "lu")
    if args.cmd == "entendu":
        # Le telephone a joue le rapport jusqu'au bout : lu, et retenu comme
        # le dernier ecoute. Revue du 2026-10-06 : les deux etaient poses au
        # depart de la lecture, un rapport coupe passait donc pour entendu.
        n = cmd_statut(args.id, "lu")
        cmd_ecoute(args.id)
        # Trace durable des rapports entendus (ecran Rapports du Creeper,
        # 2026-10-13) : « lu » ne dit pas si USER l'a entendu, le mode sans
        # lecture marque aussi lu.
        try:
            with open(os.path.expanduser("~/.hermes/qg-entendus"), "a") as f:
                f.write("{}\t{}\n".format(args.id, int(time.time())))
        except OSError:
            pass
        return n
    if args.cmd == "rejeter":
        return cmd_statut(args.id, "rejete")
    if args.cmd == "purge":
        return cmd_purge()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
