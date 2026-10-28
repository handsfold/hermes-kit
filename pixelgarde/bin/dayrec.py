#!/usr/bin/env python3
"""Rend la journee enregistree exploitable : OCR, regroupement, recherche.

Le probleme resolu : 7000 images par jour ne disent rien a personne. Ici on en
tire du texte, on colle a chaque ecran l'application qui l'affichait, et on fond
les captures quasi identiques en une seule ligne portant sa duree. Une journee
tient alors en quelques centaines de lignes de texte, cherchables instantanement.

  dayrec.py indexer [jour ...]   OCR + regroupement -> base SQLite
  dayrec.py alleger [jour ...]   une vignette WebP par ecran, purge a 14 jours
  dayrec.py chercher <mots>      recherche plein texte
  dayrec.py resume [jour]        la journee en texte compact, pour un LLM
  dayrec.py gestes [jour]        ce qui a ete touche, dans l'ordre
  dayrec.py macro [jour] [hhmm] [hhmm]   la sequence en commandes pixel-ctl.sh
  dayrec.py etat                 ce que contient la base

Les captures disent ce qui etait affiche ; actions.tsv dit ou le doigt a appuye et
ui/*.tsv donne le texte des elements vises. Les trois reunis rendent une journee
rejouable : c'est ce que `macro` produit.

Les images restent sur la machine qui les a rapatriees ; la base, elle, vit dans
~/Documents, replique par Syncthing : la recherche marche depuis n'importe quel poste.
"""
import bisect
import os
import shutil
import sys
import re
import sqlite3
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

IMAGES = Path.home() / "DayRec"
BASE = Path.home() / "Documents" / "DayRec" / "index.db"
LANGUES = "fra+eng"
# Deux captures dont l'empreinte differe de moins de SEUIL bits montrent le meme
# ecran : defilement d'un pixel, curseur qui clignote, horloge qui avance.
SEUIL_RESSEMBLANCE = 4


# --- empreinte perceptuelle ---------------------------------------------------

def empreinte(chemin):
    """dhash 64 bits : compare chaque pixel a son voisin de droite."""
    from PIL import Image
    import numpy as np
    try:
        with Image.open(chemin) as im:
            g = np.asarray(im.convert("L").resize((9, 8), Image.LANCZOS), dtype=int)
    except Exception:
        return None
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def distance(a, b):
    return bin(a ^ b).count("1") if a is not None and b is not None else 64


# --- OCR ----------------------------------------------------------------------

def lire_texte(chemin):
    """tesseract sur une image. Un thread par appel : on parallelise nous-memes."""
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    try:
        r = subprocess.run(
            ["tesseract", str(chemin), "-", "-l", LANGUES, "--psm", "6"],
            capture_output=True, text=True, env=env, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return ""
    # l'OCR d'une interface produit beaucoup de miettes : on les enleve
    txt = re.sub(r"[ \t]+", " ", r.stdout)
    lignes = [l.strip() for l in txt.splitlines()]
    return "\n".join(l for l in lignes if len(l) > 1)


# --- base ---------------------------------------------------------------------

def ouvrir():
    BASE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(BASE)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS ecrans (
            id       INTEGER PRIMARY KEY,
            jour     TEXT NOT NULL,
            debut    TEXT NOT NULL,
            fin      TEXT NOT NULL,
            duree_s  INTEGER NOT NULL DEFAULT 0,
            captures INTEGER NOT NULL DEFAULT 1,
            paquet   TEXT,
            activite TEXT,
            fichier  TEXT,
            phash    TEXT,          -- hexadecimal : un dhash non signe deborde l'INTEGER SQLite
            texte    TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS i_ecran ON ecrans(jour, debut);
        CREATE INDEX IF NOT EXISTS i_paquet ON ecrans(paquet);
        CREATE VIRTUAL TABLE IF NOT EXISTS recherche
            USING fts5(texte, paquet, jour, debut, tokenize='unicode61');

        -- Les gestes. `cible` est le texte de l'element sous le doigt, retrouve
        -- dans l'arbre photographie juste avant : c'est lui qui permet d'ecrire
        -- `click "Commander"` plutot qu'un `tap 504 1820` qui casse a la
        -- premiere mise a jour de l'application.
        CREATE TABLE IF NOT EXISTS actions (
            id       INTEGER PRIMARY KEY,
            jour     TEXT NOT NULL,
            heure    TEXT NOT NULL,
            type     TEXT NOT NULL,
            x        INTEGER, y  INTEGER,
            x2       INTEGER, y2 INTEGER,
            duree_ms INTEGER,
            doigts   INTEGER,
            paquet   TEXT,
            cible    TEXT,
            cible_id TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS i_action ON actions(jour, heure, type);
        CREATE INDEX IF NOT EXISTS i_action_jour ON actions(jour);
    """)
    return db


def journal(dossier):
    """journal.tsv : heure -> (paquet, activite). Absent pour les vieux jours."""
    f = dossier / "journal.tsv"
    m = {}
    if f.exists():
        for ligne in f.read_text(errors="replace").splitlines():
            c = ligne.split("\t")
            if len(c) >= 2:
                m[c[0]] = (c[1], c[2] if len(c) > 2 else "")
    return m


def secondes(hhmmss):
    try:
        return int(hhmmss[0:2]) * 3600 + int(hhmmss[2:4]) * 60 + int(hhmmss[4:6])
    except (ValueError, IndexError):
        return 0


# --- gestes -------------------------------------------------------------------

# Les noms de touches tels que pixel-ctl.sh les attend.
TOUCHES = {"KEY_POWER": "power", "KEY_WAKEUP": "power",
           "KEY_VOLUMEUP": "volup", "KEY_VOLUMEDOWN": "voldown"}
# Au-dela, l'arbre ne decrit plus l'ecran touche : une notification, une appli qui
# se lance ou un simple retour ont pu le remplacer sans qu'aucun geste le dise.
ARBRE_PERIME_S = 120


def arbres(dossier):
    """ui/HHMMSS.tsv -> [(heure, noeuds)] trie. Un arbre par ecran stabilise.

    Un noeud : (x1, y1, x2, y2, cliquable, texte, description, resource-id).
    """
    d = dossier / "ui"
    sortie = []
    if not d.is_dir():
        return sortie
    for f in sorted(d.glob("*.tsv")):
        noeuds = []
        for ligne in f.read_text(errors="replace").splitlines():
            c = ligne.split("\t")
            if len(c) < 8:
                continue
            try:
                x1, y1, x2, y2, clic = (int(v) for v in c[:5])
            except ValueError:
                continue
            noeuds.append((x1, y1, x2, y2, clic, c[5], c[6], c[7]))
        if noeuds:
            sortie.append((f.stem, noeuds))
    return sortie


def indexer_par_heure(paires):
    """Prepare une recherche par heure : (heures triees, valeurs alignees)."""
    paires = sorted(paires)
    return [h for h, _ in paires], [v for _, v in paires]


def precedent(index, heure):
    """Valeur en vigueur a `heure`, dans un index prepare ci-dessus."""
    heures, valeurs = index
    i = bisect.bisect_right(heures, heure) - 1
    return (heures[i], valeurs[i]) if i >= 0 else None


def viser(arbres_du_jour, heure, x, y):
    """Texte et identifiant de l'element sous le doigt.

    L'arbre retenu est le dernier anterieur au geste : photographie apres le geste
    precedent, il montre bien l'ecran ou le doigt s'est pose. Parmi les elements
    qui contiennent le point, le plus petit gagne - un bouton est toujours inclus
    dans le panneau qui le porte.
    """
    trouve = precedent(arbres_du_jour, heure[:6])
    if not trouve:
        return "", ""
    h, noeuds = trouve
    if secondes(heure) - secondes(h) > ARBRE_PERIME_S:
        return "", ""
    dedans = [n for n in noeuds if n[0] <= x <= n[2] and n[1] <= y <= n[3]]
    if not dedans:
        return "", ""
    # Un element nomme se vise par son nom ; les autres ne servent qu'a defaut.
    nommes = [n for n in dedans if n[5] or n[6]]
    n = min(nommes or dedans, key=lambda n: (n[2] - n[0]) * (n[3] - n[1]))
    return (n[5] or n[6]), n[7]


def importer_actions(db, jour, dossier):
    """actions.tsv -> table actions, chaque geste rattache a son application."""
    f = dossier / "actions.tsv"
    if not f.exists():
        return 0
    app = indexer_par_heure(journal(dossier).items())
    a = indexer_par_heure(arbres(dossier))
    for ligne in f.read_text(errors="replace").splitlines():
        c = ligne.split("\t")
        if len(c) < 8:
            continue
        heure, type_ = c[0], c[1]
        p = precedent(app, heure[:6])
        paquet = p[1][0] if p else "inconnu"
        if type_ == "touche":
            # Seul l'appui compte : garder aussi le relachement doublerait tout.
            if c[3] != "DOWN":
                continue
            cible, cible_id = TOUCHES.get(c[2], c[2]), ""
            valeurs = (jour, heure, type_, 0, 0, 0, 0, 0, 0, paquet, cible, cible_id)
        else:
            try:
                x, y, x2, y2, ms, doigts = (int(v) for v in c[2:8])
            except ValueError:
                continue
            cible, cible_id = viser(a, heure, x, y) if type_ != "swipe" else ("", "")
            valeurs = (jour, heure, type_, x, y, x2, y2, ms, doigts,
                       paquet, cible, cible_id)
        db.execute(
            "INSERT OR IGNORE INTO actions "
            "(jour,heure,type,x,y,x2,y2,duree_ms,doigts,paquet,cible,cible_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", valeurs)
    db.commit()
    return db.execute("SELECT COUNT(*) FROM actions WHERE jour=?", (jour,)).fetchone()[0]


# --- indexation ---------------------------------------------------------------

def indexer(jours):
    db = ouvrir()
    if not jours:
        jours = sorted(d.name for d in IMAGES.iterdir()
                       if d.is_dir() and re.fullmatch(r"20\d\d-\d\d-\d\d", d.name))

    for jour in jours:
        dossier = IMAGES / jour
        if not dossier.is_dir():
            continue

        # Avant les images : les gestes s'importent meme un jour ou l'OCR n'a
        # rien de neuf a lire, et ils ne coutent rien.
        gestes = importer_actions(db, jour, dossier)
        if gestes:
            print(f"{jour} : {gestes} gestes", flush=True)

        fichiers = sorted(p for p in dossier.iterdir()
                          if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
        # Reprise : on repart de la derniere capture indexee pour ce jour, ce qui
        # permet de rappeler la commande en cours de journee sans tout refaire.
        repere = db.execute("SELECT MAX(fin) FROM ecrans WHERE jour=?", (jour,)).fetchone()[0]
        if repere:
            fichiers = [f for f in fichiers if f.stem > repere]
        if not fichiers:
            continue
        app = journal(dossier)
        print(f"{jour} : {len(fichiers)} captures", flush=True)

        # 1. empreintes, en parallele
        with ProcessPoolExecutor() as ex:
            hashes = list(ex.map(empreinte, fichiers, chunksize=32))

        # 2. regrouper les captures voisines qui montrent le meme ecran
        groupes, courant = [], None
        for f, h in zip(fichiers, hashes):
            heure = f.stem
            paquet, activite = app.get(heure, ("inconnu", ""))
            meme = (courant is not None
                    and distance(h, courant["phash"]) <= SEUIL_RESSEMBLANCE
                    and paquet == courant["paquet"])
            if meme:
                courant["fin"] = heure
                courant["captures"] += 1
            else:
                if courant:
                    groupes.append(courant)
                courant = {"debut": heure, "fin": heure, "captures": 1,
                           "paquet": paquet, "activite": activite,
                           "fichier": str(f), "phash": h}
        if courant:
            groupes.append(courant)

        gain = 100 - round(100 * len(groupes) / len(fichiers))
        print(f"  {len(groupes)} ecrans distincts ({gain}% de moins)", flush=True)

        # 3. OCR sur un seul representant par ecran
        with ProcessPoolExecutor() as ex:
            textes = list(ex.map(lire_texte, [g["fichier"] for g in groupes], chunksize=4))

        for g, t in zip(groupes, textes):
            g["duree_s"] = max(0, secondes(g["fin"]) - secondes(g["debut"]))
            db.execute(
                "INSERT OR IGNORE INTO ecrans "
                "(jour,debut,fin,duree_s,captures,paquet,activite,fichier,phash,texte) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (jour, g["debut"], g["fin"], g["duree_s"], g["captures"],
                 g["paquet"], g["activite"], g["fichier"],
                 f"{g['phash']:016x}" if g["phash"] is not None else None, t))
            db.execute(
                "INSERT INTO recherche (texte,paquet,jour,debut) VALUES (?,?,?,?)",
                (t, g["paquet"], jour, g["debut"]))

        db.commit()
        mots = sum(len(t.split()) for t in textes)
        print(f"  {mots} mots extraits", flush=True)
    db.close()


# --- allegement ---------------------------------------------------------------

# Mesure sur les captures reelles : 8 Ko l'unite contre 48 en JPEG q70, soit 18 %.
# Le texte etant deja extrait, l'image ne sert plus qu'a verifier d'un coup d'oeil.
VIGNETTE = ["-quality", "35", "-resize", "50%"]
RETENTION_IMAGES = 14
# ImageMagick 7 s'appelle `magick`, la 6 `convert`. Lab a la 7, hote-1 la 6 :
# resoudre au lancement evite un allegement qui echoue en silence sur l'une.
MAGICK = shutil.which("magick") or shutil.which("convert")


def _vignette(paire):
    src, dst = paire
    if not MAGICK:
        return None
    try:
        subprocess.run([MAGICK, src, *VIGNETTE, dst],
                       capture_output=True, timeout=60, check=True)
        return dst if os.path.getsize(dst) > 0 else None
    except Exception:
        return None


def alleger(jours=None):
    """Ne garde qu'une vignette WebP par ecran distinct, puis purge les vieux jours.

    Les captures redondantes ne servent plus une fois l'OCR fait : leur texte, leur
    duree et leur application sont en base. Le jour en cours est traite lui aussi,
    sinon il gonflerait jusqu'a minuit - mais on s'arrete a la derniere capture
    indexee, pour ne jamais effacer ce que l'OCR n'a pas encore lu.
    """
    from datetime import date, timedelta
    db = ouvrir()
    limite = (date.today() - timedelta(days=RETENTION_IMAGES)).isoformat()

    if not jours:
        jours = [r[0] for r in db.execute(
            "SELECT DISTINCT jour FROM ecrans ORDER BY jour")]

    for jour in jours:
        dossier = IMAGES / jour
        if not dossier.is_dir():
            continue

        # purge complete des journees trop anciennes : la base, elle, garde tout
        if jour < limite:
            poids = sum(f.stat().st_size for f in dossier.rglob("*") if f.is_file())
            # rmtree et non rmdir : le dossier porte un sous-dossier `ui`, et tout
            # ce qu'il contient est deja en base.
            shutil.rmtree(dossier, ignore_errors=True)
            print(f"{jour} : images purgees ({poids // 1024 // 1024} Mo), texte conserve")
            continue

        gardes = db.execute(
            "SELECT id, fichier FROM ecrans WHERE jour=? AND fichier NOT LIKE '%.webp'",
            (jour,)).fetchall()
        if not gardes:
            continue

        avant = sum(f.stat().st_size for f in dossier.iterdir() if f.is_file())
        travail = [(f, str(Path(f).with_suffix(".webp"))) for _, f in gardes if Path(f).exists()]
        with ProcessPoolExecutor() as ex:
            faits = list(ex.map(_vignette, travail, chunksize=16))

        # la base doit pointer sur la vignette avant qu'on efface quoi que ce soit
        survivants = set()
        for (ident, _), (_, dst), ok in zip(gardes, travail, faits):
            if ok:
                db.execute("UPDATE ecrans SET fichier=? WHERE id=?", (dst, ident))
                survivants.add(dst)
        db.commit()

        # Garde-fou : rien au-dela de la derniere capture indexee. Sans cela, un
        # allegement lance en pleine journee effacerait des captures jamais lues.
        repere = db.execute("SELECT MAX(fin) FROM ecrans WHERE jour=?", (jour,)).fetchone()[0]
        efface = 0
        for f in dossier.iterdir():
            if not f.is_file() or f.suffix.lower() == ".tsv":
                continue
            if str(f) in survivants or (repere and f.stem > repere):
                continue
            f.unlink()
            efface += 1
        apres = sum(f.stat().st_size for f in dossier.iterdir() if f.is_file())
        print(f"{jour} : {len(survivants)} vignettes gardees, {efface} fichiers effaces "
              f"- {avant // 1024 // 1024} Mo -> {apres // 1024 // 1024} Mo")
    db.close()


# --- consultation -------------------------------------------------------------

def joli(h):
    return f"{h[0:2]}h{h[2:4]}" if len(h) >= 4 else h


def duree(s):
    return f"{s // 60} min" if s >= 60 else f"{s} s"


def chercher(mots):
    db = ouvrir()
    q = " ".join(mots)
    lignes = db.execute("""
        SELECT jour, debut, paquet, snippet(recherche, 0, '>>', '<<', '…', 14)
        FROM recherche WHERE recherche MATCH ? ORDER BY jour DESC, debut DESC LIMIT 40
    """, (q,)).fetchall()
    if not lignes:
        print(f"rien pour : {q}")
        return
    for jour, debut, paquet, extrait in lignes:
        extrait = " ".join(extrait.split())
        print(f"{jour} {joli(debut)}  {(paquet or '?').split('.')[-1][:18]:18} {extrait}")
    print(f"--- {len(lignes)} resultats")


def resume(jour=None):
    db = ouvrir()
    if not jour:
        r = db.execute("SELECT MAX(jour) FROM ecrans").fetchone()
        jour = r[0] if r else None
    if not jour:
        print("base vide - lancer : dayrec.py indexer")
        return
    print(f"# Journee du {jour}\n")
    # Les gestes s'intercalent entre les ecrans : c'est ce qui transforme une
    # suite d'images en recit, et un recit en macro.
    actions = db.execute(
        "SELECT heure,type,x,y,cible FROM actions WHERE jour=? ORDER BY heure",
        (jour,)).fetchall()
    i = 0
    for debut, fin, d, paquet, texte in db.execute(
            "SELECT debut,fin,duree_s,paquet,texte FROM ecrans WHERE jour=? ORDER BY debut", (jour,)):
        while i < len(actions) and actions[i][0][:6] < debut:
            h, t, x, y, cible = actions[i]
            print(f"        {precis(h)} {t} {cible or f'({x},{y})'}")
            i += 1
        app = (paquet or "?").split(".")[-1]
        tete = " · ".join(l for l in (texte or "").splitlines()[:3] if l)[:150]
        print(f"{joli(debut)}-{joli(fin)} ({duree(d):>7}) [{app}] {tete}")


def precis(h):
    return f"{h[0:2]}:{h[2:4]}:{h[4:6]}" if len(h) >= 6 else h


def dernier_jour(db, jour):
    if jour:
        return jour
    r = db.execute("SELECT MAX(jour) FROM actions").fetchone()
    return r[0] if r else None


def lire_gestes(db, jour, debut=None, fin=None):
    q = "SELECT heure,type,x,y,x2,y2,duree_ms,paquet,cible FROM actions WHERE jour=?"
    p = [jour]
    if debut:
        q += " AND heure >= ?"; p.append(debut.ljust(6, "0"))
    if fin:
        q += " AND heure <= ?"; p.append(fin.ljust(6, "9"))
    return db.execute(q + " ORDER BY heure", p).fetchall()


def gestes(jour=None, debut=None, fin=None):
    """La journee vue du doigt : ou il a appuye, et sur quoi."""
    db = ouvrir()
    jour = dernier_jour(db, jour)
    lignes = lire_gestes(db, jour, debut, fin) if jour else []
    if not lignes:
        print("aucun geste enregistre - voir /data/adb/rec-actions.sh sur le telephone")
        return
    print(f"# Gestes du {jour}\n")
    for h, t, x, y, x2, y2, ms, paquet, cible in lignes:
        app = (paquet or "?").split(".")[-1][:14]
        ou = f"({x},{y})" if t != "swipe" else f"({x},{y})->({x2},{y2})"
        print(f"{precis(h)}  {app:14} {t:6} {(cible or '')[:40]:40} {ou}")
    print(f"--- {len(lignes)} gestes")


def macro(jour=None, debut=None, fin=None):
    """La sequence en commandes pixel-ctl.sh, prete a relire et a rejouer.

    Ce n'est pas un script a lancer les yeux fermes : c'est le brouillon fidele de
    ce qui a ete fait, ou les clics portent le texte vise quand il a ete retrouve.
    Un `tap` en coordonnees signale un endroit ou l'arbre n'a rien nomme.
    """
    db = ouvrir()
    jour = dernier_jour(db, jour)
    lignes = lire_gestes(db, jour, debut, fin) if jour else []
    if not lignes:
        print("# aucun geste sur cette plage")
        return
    print("#!/usr/bin/env bash")
    print(f"# {jour} {precis(lignes[0][0])} -> {precis(lignes[-1][0])}, "
          f"{len(lignes)} gestes, rejoue par pixel-ctl.sh")
    print("set -e\nP=~/Bureau/Projets/contexte/bin/pixel/pixel-ctl.sh\n")

    app_courante = None
    heure_avant = None
    for h, t, x, y, x2, y2, ms, paquet, cible in lignes:
        # Le temps mort entre deux gestes est une donnee : c'est le chargement de
        # l'ecran, et le rejouer trop vite tape dans le vide.
        if heure_avant:
            attente = secondes(h) - secondes(heure_avant)
            if attente >= 2:
                print(f"sleep {min(attente, 10)}")
        heure_avant = h

        if paquet and paquet not in ("inconnu", app_courante) and "." in paquet:
            print(f'"$P" open {paquet}')
            app_courante = paquet

        if t == "touche":
            print(f'"$P" touche {cible}')
        elif t == "swipe":
            print(f'"$P" swipe {x} {y} {x2} {y2} {max(ms, 100)}')
        elif t == "long":
            # pixel-ctl.sh n'a pas d'appui long : un swipe immobile en tient lieu.
            print(f'"$P" swipe {x} {y} {x} {y} {max(ms, 600)}   # appui long')
        elif cible:
            sur = cible.replace('"', "'")
            print(f'"$P" click "{sur}"')
        else:
            print(f'"$P" tap {x} {y}   # aucun element nomme a cet endroit')


def etat():
    db = ouvrir()
    n, = db.execute("SELECT COUNT(*) FROM ecrans").fetchone()
    if not n:
        print(f"base vide : {BASE}")
        return
    print(f"base : {BASE} ({BASE.stat().st_size // 1024} Ko)")
    print(f"{n} ecrans indexes\n")
    par_jour = dict(db.execute("SELECT jour, COUNT(*) FROM actions GROUP BY jour"))
    for jour, k, c, s in db.execute(
            "SELECT jour, COUNT(*), SUM(captures), SUM(duree_s) FROM ecrans GROUP BY jour ORDER BY jour"):
        g = par_jour.get(jour, 0)
        print(f"  {jour} : {k:5} ecrans   {c:6} captures   {s // 60} min couvertes"
              f"   {g:5} gestes")
    print("\napplications les plus vues :")
    for paquet, k, s in db.execute(
            "SELECT paquet, COUNT(*), SUM(duree_s) FROM ecrans "
            "GROUP BY paquet ORDER BY SUM(duree_s) DESC LIMIT 8"):
        print(f"  {(paquet or '?').split('.')[-1][:24]:24} {k:5} ecrans  {duree(s or 0)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "etat"
    arg = sys.argv[2:]
    if cmd == "indexer":
        indexer(arg)
    elif cmd == "alleger":
        alleger(arg)
    elif cmd == "chercher":
        chercher(arg) if arg else print("usage: dayrec.py chercher <mots>")
    elif cmd == "resume":
        resume(arg[0] if arg else None)
    elif cmd == "gestes":
        gestes(*arg[:3])
    elif cmd == "macro":
        macro(*arg[:3])
    elif cmd == "etat":
        etat()
    else:
        print(__doc__)
