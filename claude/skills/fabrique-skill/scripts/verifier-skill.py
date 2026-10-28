#!/usr/bin/env python3
"""Controle une skill (Claude Code, Hermes, Prime) avant livraison ou en revue.

Usage :
    verifier-skill.py <dossier-ou-SKILL.md> [...]
    verifier-skill.py --perso         # les skills de USER, 3 dossiers, classees par leur source (parc_skills.py)
    verifier-skill.py --tout          # toutes, skills d'usine comprises

Sortie : erreurs (E) et avertissements (A), code 1 s'il y a au moins une erreur.
Stdlib seule : le frontmatter est lu par un petit analyseur (pas de PyYAML sur hote-1).
"""
import json
import re
import sys
from pathlib import Path

HOME = Path.home()
SKILLS = HOME / ".claude/skills"
HERMES = HOME / ".hermes/skills"
DECLENCHEURS = HOME / ".claude/outils/declencheurs.json"

ACCROCHE_HERMES = 57          # skill_utils.py : coupe a 57 au-dela de 60
LIMITE_HERMES = 60
DESC_MAX = 1024
DESC_ALERTE = 500
LISTING_MAX = 1536
CORPS_MAX = 500
SOMMAIRE_DES = 100

CHAMPS_CONNUS = {
    # Claude Code
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools",
    "disallowed-tools", "model", "effort", "context", "agent", "background",
    "hooks", "paths", "shell", "metadata", "license", "compatibility",
    # Hermes
    "version", "author", "platforms", "tags", "related_skills",
}
REPLIS = []  # valeurs lues par repli (YAML strict invalide)
TIRETS = re.compile("[\u2013\u2014]")
PREMIERE_PERSONNE = re.compile(r"^\s*(je |j'|i |i'm |nous )", re.I)


TIERS = {"node_modules", ".git", ".venv", "venv", "__pycache__", "site-packages"}


def lire_frontmatter(texte):
    """Rend (dict, corps, erreur). Analyse les cles de 1er niveau seulement."""
    if texte.startswith("﻿"):
        return None, texte, "BOM avant le frontmatter : Claude Code ne le lit pas"
    lignes = texte.split("\n")
    if not lignes or lignes[0].strip() != "---":
        return None, texte, "la 1re ligne doit etre '---'"
    try:
        fin = next(i for i in range(1, len(lignes)) if lignes[i].strip() == "---")
    except StopIteration:
        return None, texte, "frontmatter jamais referme par '---'"
    bloc, corps = lignes[1:fin], "\n".join(lignes[fin + 1:])
    champs, cle, brut = {}, None, []

    def ranger():
        if cle is not None:
            champs[cle] = valeur(brut)

    for ligne in bloc:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(\s.*|)$", ligne)
        if m and not ligne.startswith((" ", "\t")):
            ranger()
            cle, brut = m.group(1), [m.group(2).strip()]
        elif cle is not None:
            brut.append(ligne)
    ranger()
    return champs, corps, None


def valeur(brut):
    tete, suite = brut[0], [l for l in brut[1:]]
    if tete in (">", ">-", "|", "|-", ">+", "|+"):
        morceaux = [l.strip() for l in suite if l.strip()]
        return (" " if tete.startswith(">") else "\n").join(morceaux)
    if tete and tete[0] in "\"'":
        q = tete[0]
        txt = " ".join([tete] + [l.strip() for l in suite]).strip()
        if len(txt) < 2 or not txt.endswith(q):
            raise ValueError(f"guillemet {q} non referme")
        txt = txt[1:-1]
        return txt.replace('\\"', '"') if q == '"' else txt.replace("''", "'")
    if tete == "":
        return "\n".join(suite)          # liste ou dictionnaire imbrique
    txt = " ".join([tete] + [l.strip() for l in suite]).strip()
    if re.search(r":\s", txt) and not txt.startswith(("[", "{")):
        REPLIS.append(txt[:30])
    return txt


def verifier(chemin):
    chemin = Path(chemin).expanduser().resolve()
    fichier = chemin / "SKILL.md" if chemin.is_dir() else chemin
    dossier = fichier.parent
    E, A = [], []
    if not fichier.exists():
        return [f"{fichier} introuvable"], []
    texte = fichier.read_text(encoding="utf-8")
    REPLIS.clear()
    try:
        fm, corps, err = lire_frontmatter(texte)
    except ValueError as exc:
        return [f"YAML : {exc}"], []
    if err:
        return [err], []

    for r in REPLIS:
        A.append(f"YAML strict invalide (': ' sans guillemets, « {r}... ») : "
                 "lu par repli, mettre la valeur entre guillemets")

    # name
    nom = fm.get("name", "")
    if not nom:
        E.append("champ 'name' absent")
    else:
        if not re.fullmatch(r"[a-z0-9-]{1,64}", nom):
            E.append(f"name '{nom}' : [a-z0-9-], 64 car. au plus")
        if nom != dossier.name:
            A.append(f"name '{nom}' differe du dossier '{dossier.name}'")
        if re.search(r"anthropic|claude", nom):
            E.append("name ne doit contenir ni 'anthropic' ni 'claude'")

    # description
    desc = fm.get("description", "")
    wtu = fm.get("when_to_use", "")
    if not desc:
        E.append("champ 'description' absent")
    else:
        if len(desc) > DESC_MAX:
            E.append(f"description {len(desc)} car. (max {DESC_MAX})")
        elif len(desc) > DESC_ALERTE:
            A.append(f"description {len(desc)} car. (audit-skills alerte au-dela de {DESC_ALERTE})")
        if len(desc) + len(wtu) > LISTING_MAX:
            A.append(f"description + when_to_use = {len(desc) + len(wtu)} car. : listing Claude coupe a {LISTING_MAX}")
        if len(desc) > LIMITE_HERMES:
            tete = desc[:ACCROCHE_HERMES + 1]
            if not re.search(r"[.!?\u2026](\s|$)", tete):
                A.append(f"aucune phrase complete dans les {ACCROCHE_HERMES} car. vus par Hermes : "
                         f"« {desc[:ACCROCHE_HERMES]}... »")
        if PREMIERE_PERSONNE.search(desc):
            A.append("description a la 1re personne : ecrire a la 3e")
        if re.match(r"\s*(use when|helps|this skill)", desc, re.I):
            A.append("accroche en anglais generique : mettre les mots de USER en tete")

    # champs
    for champ in fm:
        if champ not in CHAMPS_CONNUS:
            A.append(f"champ inconnu '{champ}' : ignore sans erreur (faute de frappe ?)")
    for b in ("disable-model-invocation", "user-invocable", "background"):
        if b in fm and fm[b].lower() not in {"true", "false", "yes", "no", "on", "off", "1", "0"}:
            E.append(f"{b} : booleen attendu, lu '{fm[b]}'")
    if fm.get("context") and fm["context"] != "fork":
        E.append(f"context '{fm['context']}' : seule valeur valide 'fork'")

    # corps
    n = corps.count("\n") + 1
    if not corps.strip():
        E.append("corps vide (Hermes refuse la skill)")
    if n > CORPS_MAX:
        E.append(f"corps {n} lignes (max {CORPS_MAX}) : deplacer vers references/")
    if n > SOMMAIRE_DES and not re.search(r"(?im)^(sommaire|##\s*sommaire|table des mati)", corps):
        A.append(f"corps {n} lignes sans sommaire")

    # fichiers cites
    for ref in sorted(set(re.findall(r"(?<![\w/~.])((?:references|scripts|assets|agents|evals)/[\w./-]+\.\w+)", corps))):
        if "<" in ref:
            continue
        if not (dossier / ref).exists():
            E.append(f"fichier cite absent : {ref}")
    for ref in sorted((dossier / "references").glob("*.md")) if (dossier / "references").is_dir() else []:
        t = ref.read_text(encoding="utf-8")
        if re.search(r"(?<![\w/])references/[\w-]+\.md", t):
            A.append(f"{ref.name} renvoie a une autre reference : garder 1 seul niveau")
        if t.count("\n") > SOMMAIRE_DES and "ommaire" not in t[:600]:
            A.append(f"{ref.name} > {SOMMAIRE_DES} lignes sans sommaire en tete")

    # tirets longs, partout dans le dossier
    for f in sorted(dossier.rglob("*")):
        # third-party code (installed packages) is not USER's text: skip it
        if TIERS & set(f.relative_to(dossier).parts):
            continue
        if f.is_file() and f.suffix in {".md", ".py", ".sh", ".json", ".txt", ".yaml", ".yml", ".html"}:
            try:
                for i, l in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
                    if TIRETS.search(l):
                        E.append(f"tiret long : {f.relative_to(dossier)}:{i}")
                        break
            except UnicodeDecodeError:
                pass

    # declencheurs et Hermes (skills perso seulement)
    perso = nom and "synced" not in dossier.parts and est_de_vj(nom)
    cote_claude = SKILLS in dossier.parents or SKILLS in dossier.resolve().parents
    if perso:
        try:
            dec = json.loads(DECLENCHEURS.read_text(encoding="utf-8"))
            if nom not in dec:
                A.append("absente de declencheurs.json : ratés non mesures")
        except (OSError, ValueError) as exc:
            A.append(f"declencheurs.json illisible : {exc}")
        copies = [p for p in HERMES.glob(f"*/{nom}") if p.exists()] + \
                 [p for p in HERMES.glob(nom) if p.exists()]
        # ~/.agents/skills est lu par Hermes (external_dirs) : y etre suffit
        externe = (HOME / ".agents/skills" / nom).exists()
        if not cote_claude:
            copies = []  # skill nee dans Hermes ou Prime : rien a lier
        elif not copies and not externe:
            A.append("absente d'Hermes : lien a poser dans ~/.hermes/skills/<categorie>/")
        for p in copies:
            if not p.is_symlink():
                A.append(f"copie (pas un lien) cote Hermes : {p} : 2 versions divergeront")

    return E, A


sys.path.insert(0, str(HOME / ".claude/outils"))
from parc_skills import est_de_vj, parc  # noqa: E402


def main(args):
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args and args[0] in ("--tout", "--perso"):
        args = [str(s["chemin"]) for s in parc() if args[0] == "--tout" or s["poste"]]
    total = 0
    for a in args:
        try:
            E, A = verifier(a)
        except Exception as exc:  # une skill cassee ne bloque pas le parc
            E, A = [f"lecture impossible : {exc!r}"], []
        q = Path(a).expanduser().resolve()
        nom = q.name if q.is_dir() else q.parent.name
        etat = "ERREUR" if E else ("a revoir" if A else "ok")
        print(f"== {nom} : {etat} ({len(E)} E, {len(A)} A)")
        for e in E:
            print(f"  E {e}")
        for x in A:
            print(f"  A {x}")
        total += len(E)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
