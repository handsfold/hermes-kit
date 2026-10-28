#!/usr/bin/env python3
"""focus - to-do list du coach. Lit et ecrit ~/Bureau/Projets/contexte/taches.md

Usage:
  focus                       liste les taches ouvertes, numerotees
  focus ok 2                  coche la tache 2
  focus add projet-a "texte"  ajoute une tache
  focus rm 3                  supprime la tache 3
  focus edit 3 "nouveau"      remplace le texte de la tache 3
  focus purge                 archive les taches faites depuis + de 7 j
  focus note "texte"          repond a la question du coach (journal.md)
  focus appris "texte"        note une lecon apprise (methodes/appris.md)
  focus appris                liste les lecons, les candidates au socle en tete
  focus appris --revue        ce qui a survecu a 2 projets : a promouvoir dans le socle
  focus journal               affiche les 10 derniers echanges
  focus --json                sortie machine (pour le coach)

Format d'une ligne :  - [ ] texte  <!-- 2026-08-14 -->
"""
import json
import os
import re
import sys
from datetime import date, datetime

FICHIER = os.path.expanduser("~/Bureau/Projets/contexte/taches.md")
APPRIS = os.path.expanduser("~/Bureau/Projets/contexte/methodes/appris.md")
ENTETE = """# Taches - gere par le CLI `focus`

Ce fichier est ecrit par la machine. Tu peux l'editer a la main, le format est simple.
Le cap et les projets actifs restent dans `focus.md` - ce fichier ne contient que le faire.

Format : `- [ ] texte  <!-- date-de-creation -->`

"""
LIGNE = re.compile(r"^-\s*\[( |x|X)\]\s*(.*?)\s*(?:<!--\s*(.*?)\s*-->)?\s*$")
TITRE = re.compile(r"^##\s+(.+?)\s*$")


def aujourdhui():
    return date.today().isoformat()


def charger():
    """Retourne [(projet, faite, texte, cree, fait_le, index_ligne)] + les lignes brutes."""
    if not os.path.exists(FICHIER):
        return [], []
    lignes = open(FICHIER, encoding="utf-8").read().splitlines()
    taches, projet = [], "divers"
    for i, l in enumerate(lignes):
        t = TITRE.match(l)
        if t:
            projet = t.group(1).strip()
            continue
        m = LIGNE.match(l)
        if not m:
            continue
        meta = m.group(3) or ""
        cree = re.search(r"(\d{4}-\d{2}-\d{2})", meta)
        fait = re.search(r"fait:(\d{4}-\d{2}-\d{2})", meta)
        taches.append({
            "projet": projet,
            "faite": m.group(1).lower() == "x",
            "texte": m.group(2).strip(),
            "cree": cree.group(1) if cree else aujourdhui(),
            "fait_le": fait.group(1) if fait else None,
            "ligne": i,
        })
    return taches, lignes


def rendre(t):
    case = "x" if t["faite"] else " "
    meta = t["cree"] + (f" fait:{t['fait_le']}" if t["fait_le"] else "")
    return f"- [{case}] {t['texte']}  <!-- {meta} -->"


def ecrire(lignes):
    os.makedirs(os.path.dirname(FICHIER), exist_ok=True)
    open(FICHIER, "w", encoding="utf-8").write("\n".join(lignes).rstrip() + "\n")


def ouvertes(taches):
    return [t for t in taches if not t["faite"]]


def age(t):
    try:
        d = datetime.strptime(t["cree"], "%Y-%m-%d").date()
        return (date.today() - d).days
    except ValueError:
        return 0


def cmd_list(as_json=False):
    taches, _ = charger()
    ouv = ouvertes(taches)
    if as_json:
        print(json.dumps([
            {"n": i + 1, "projet": t["projet"], "texte": t["texte"], "jours": age(t)}
            for i, t in enumerate(ouv)
        ], ensure_ascii=False))
        return 0
    if not ouv:
        print("Aucune tache ouverte. `focus add <projet> \"texte\"` pour en creer une.")
        return 0
    projet = None
    for i, t in enumerate(ouv):
        if t["projet"] != projet:
            projet = t["projet"]
            print(f"\n{projet}")
        j = age(t)
        report = f"  ← reportee {j} j" if j >= 3 else ""
        print(f"  {i + 1}. [ ] {t['texte']}{report}")
    faites = [t for t in taches if t["faite"] and t["fait_le"] == aujourdhui()]
    if faites:
        print(f"\nFait aujourd'hui : {len(faites)}")
        for t in faites:
            print(f"  [x] {t['texte']}")
    return 0


def cmd_ok(n):
    taches, lignes = charger()
    ouv = ouvertes(taches)
    if not 1 <= n <= len(ouv):
        print(f"Numero hors liste. {len(ouv)} taches ouvertes.")
        return 1
    t = ouv[n - 1]
    t["faite"] = True
    t["fait_le"] = aujourdhui()
    lignes[t["ligne"]] = rendre(t)
    ecrire(lignes)
    reste = len(ouv) - 1
    print(f"Fait : {t['texte']}\nReste {reste} tache(s) ouverte(s).")
    return 0


def cmd_add(projet, texte):
    taches, lignes = charger()
    if not lignes:
        lignes = ENTETE.splitlines()
    nouvelle = {"faite": False, "texte": texte, "cree": aujourdhui(), "fait_le": None}
    # inserer sous le titre du projet s'il existe, sinon creer la section
    idx = None
    for i, l in enumerate(lignes):
        t = TITRE.match(l)
        if t and t.group(1).strip().lower() == projet.lower():
            idx = i + 1
            while idx < len(lignes) and LIGNE.match(lignes[idx]):
                idx += 1
            break
    if idx is None:
        if lignes and lignes[-1].strip():
            lignes.append("")
        lignes.append(f"## {projet}")
        idx = len(lignes)
    lignes.insert(idx, rendre(nouvelle))
    ecrire(lignes)
    print(f"Ajoute a {projet} : {texte}")
    return 0


def cmd_rm(n):
    taches, lignes = charger()
    ouv = ouvertes(taches)
    if not 1 <= n <= len(ouv):
        print(f"Numero hors liste. {len(ouv)} taches ouvertes.")
        return 1
    t = ouv[n - 1]
    del lignes[t["ligne"]]
    ecrire(lignes)
    print(f"Supprime : {t['texte']}")
    return 0


def cmd_edit(n, texte):
    taches, lignes = charger()
    ouv = ouvertes(taches)
    if not 1 <= n <= len(ouv):
        print(f"Numero hors liste. {len(ouv)} taches ouvertes.")
        return 1
    t = ouv[n - 1]
    ancien = t["texte"]
    t["texte"] = texte
    lignes[t["ligne"]] = rendre(t)
    ecrire(lignes)
    print(f"Modifie : {ancien}\n      ->  {texte}")
    return 0


def cmd_purge(silencieux=False):
    taches, lignes = charger()
    a_virer = []
    for t in taches:
        if not t["faite"] or not t["fait_le"]:
            continue
        try:
            d = datetime.strptime(t["fait_le"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if (date.today() - d).days > 7:
            a_virer.append(t["ligne"])
    if a_virer:
        for i in sorted(a_virer, reverse=True):
            del lignes[i]
        ecrire(lignes)
    if not silencieux:
        print(f"Archive : {len(a_virer)} tache(s) faite(s) de plus de 7 j.")
    return 0


def cmd_note(texte):
    import journal
    journal.ajouter("R", texte)
    q = journal.derniere_question()
    print("Note enregistree." + (f"\nEn reponse a : {q['texte'][:80]}" if q else ""))
    return 0


ENTETE_APPRIS = """# Appris - retour d'experience, ecrit par `focus appris`

Chaque ligne est une lecon tiree d'un vrai incident, datee et rattachee a son projet.
Une lecon n'entre pas dans `socle-projet.md` parce qu'elle a plu un soir :
elle y entre quand elle a survecu a **deux projets differents**.
`focus appris --revue` liste celles qui ont franchi ce seuil.

Format : `- AAAA-MM-JJ · [projet] texte`

"""
LIGNE_APPRIS = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\s*·\s*\[(.+?)\]\s*(.*?)\s*$")


def projet_courant():
    """Devine le projet depuis le dossier courant."""
    cwd = os.path.abspath(os.getcwd())
    racine = os.path.expanduser("~/Bureau/Projets")
    if cwd.startswith(racine + os.sep):
        return cwd[len(racine) + 1:].split(os.sep)[0]
    return os.path.basename(cwd) or "divers"


def charger_appris():
    if not os.path.exists(APPRIS):
        return []
    out = []
    for ligne in open(APPRIS, encoding="utf-8"):
        m = LIGNE_APPRIS.match(ligne.rstrip("\n"))
        if m:
            out.append({"date": m.group(1), "projet": m.group(2), "texte": m.group(3)})
    return out


def _mots(texte):
    """Sac de mots significatifs, pour rapprocher deux lecons voisines."""
    vides = {"le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "a",
             "au", "aux", "en", "dans", "sur", "pour", "par", "que", "qui", "ne",
             "pas", "plus", "ce", "cet", "cette", "se", "son", "sa", "ses", "est",
             "il", "elle", "on", "avec", "sans", "toujours", "jamais", "faut"}
    mots = re.findall(r"[a-z0-9_.-]{3,}", texte.lower())
    return {m for m in mots if m not in vides}


def cmd_appris(texte=None, revue=False):
    entrees = charger_appris()

    if texte:
        projet = projet_courant()
        ligne = f"- {aujourdhui()} · [{projet}] {texte}\n"
        os.makedirs(os.path.dirname(APPRIS), exist_ok=True)
        if not os.path.exists(APPRIS):
            open(APPRIS, "w", encoding="utf-8").write(ENTETE_APPRIS)
        with open(APPRIS, "a", encoding="utf-8") as f:
            f.write(ligne)
        print(f"Appris, sur [{projet}].")
        # Cette lecon rejoint-elle une lecon d'un autre projet ?
        cle = _mots(texte)
        voisins = [e for e in entrees
                   if e["projet"] != projet and len(cle & _mots(e["texte"])) >= 2]
        if voisins:
            v = voisins[-1]
            print(f"Deja vu sur [{v['projet']}] le {v['date']} : {v['texte'][:70]}")
            print("Survecu a deux projets : candidate au socle.")
        return 0

    groupes = grouper_appris(entrees)
    murs = [g for g in groupes if len(g["projets"]) >= 2]

    if revue:
        if not murs:
            print("Rien de mur. Aucune lecon n'a encore survecu a deux projets.")
            return 0
        print("A promouvoir dans methodes/socle-projet.md :\n")
        for g in murs:
            print(f"  [{' + '.join(sorted(g['projets']))}] {g['entrees'][0]['texte']}")
            for e in g["entrees"][1:]:
                print(f"      {e['date']} · {e['projet']} · {e['texte']}")
        return 0

    if not entrees:
        print("Rien d'appris pour l'instant. `focus appris \"...\"` pour commencer.")
        return 0
    if murs:
        print(f"Mur pour le socle ({len(murs)}) :")
        for g in murs:
            print(f"  * [{' + '.join(sorted(g['projets']))}] {g['entrees'][0]['texte']}")
        print()
    par_projet = {}
    for e in entrees:
        par_projet.setdefault(e["projet"], []).append(e)
    for projet in sorted(par_projet):
        print(projet)
        for e in par_projet[projet]:
            print(f"  {e['date']} · {e['texte']}")
    return 0


def grouper_appris(entrees):
    """Regroupe les lecons qui parlent de la meme chose, meme redigees autrement."""
    groupes = []
    for e in entrees:
        cle = _mots(e["texte"])
        for g in groupes:
            if len(cle & g["mots"]) >= 2:
                g["entrees"].append(e)
                g["projets"].add(e["projet"])
                g["mots"] |= cle
                break
        else:
            groupes.append({"entrees": [e], "projets": {e["projet"]}, "mots": cle})
    return groupes


def cmd_journal(n=10):
    import journal
    entrees = journal.charger()[-n:]
    if not entrees:
        print("Journal vide.")
        return 0
    jour = None
    for e in entrees:
        if e["jour"] != jour:
            jour = e["jour"]
            print(f"\n{jour}")
        print(f"  {e['type']} {e['heure']} · {e['texte']}")
    return 0


def main(argv):
    if not argv or argv[0] in ("list", "ls"):
        return cmd_list()
    c = argv[0]
    if c in ("--json", "json"):
        return cmd_list(as_json=True)
    try:
        if c in ("ok", "done", "fait"):
            return cmd_ok(int(argv[1]))
        if c == "add":
            return cmd_add(argv[1], " ".join(argv[2:]))
        if c in ("rm", "del"):
            return cmd_rm(int(argv[1]))
        if c == "edit":
            return cmd_edit(int(argv[1]), " ".join(argv[2:]))
        if c == "purge":
            return cmd_purge()
        if c in ("note", "n"):
            return cmd_note(" ".join(argv[1:]))
        if c in ("appris", "learn"):
            reste = argv[1:]
            if reste and reste[0] in ("--revue", "revue"):
                return cmd_appris(revue=True)
            return cmd_appris(" ".join(reste).strip() or None)
        if c in ("journal", "j"):
            return cmd_journal()
    except (IndexError, ValueError):
        print(__doc__)
        return 1
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
