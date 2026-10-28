#!/usr/bin/env python3
"""Met une skill importee au format USER. Le corps d'origine est GARDE.

Usage :
    mettre-au-format.py <dossier> --accroche "..." --fait "..." --pas-pour "Pas pour ..." \\
        --quand "USER dit ..." --motif REGEX [--motif REGEX] [--categorie CAT]
    mettre-au-format.py <dossier>      # rejoue l'en-tete memorise (en-tetes/<nom>.json)
    mettre-au-format.py --tout         # toutes les skills du lock ~/.agents/.skill-lock.json

Options :
    --a-blanc   rien n'est ecrit : dit ce qui changerait
    --local     en-tete, tirets et sommaire seulement (ni liens, ni declencheurs.json)

Ce que le script refait (decision de USER, 2026-10-25) :
    en-tete   name = dossier ; description = accroche + ce que fait + « Pas pour » ; when_to_use.
              Les autres champs d'origine (allowed-tools, metadata...) restent tels quels.
    corps     INTACT, sauf 2 retouches mecaniques : tirets longs remplaces, sommaire insere
              au-dela de 100 lignes. Ses regles a lui vont dans une skill compagne.
    liens     ~/.claude/skills/<nom> et ~/.hermes/skills/[<categorie>/]<nom> (jamais une copie).
    mesure    entree dans ~/.claude/outils/declencheurs.json, jamais forcee.
    controle  verifier-skill.py, jusqu'a 0 erreur. Reste en erreur ce qui exige un choix de USER.

L'en-tete francais est memorise dans en-tetes/<nom>.json : un `skills update` ecrase
le fichier, `--tout` le reapplique. Sans en-tete memorise, la description d'origine reste.

Contenu telecharge = non fiable : lu comme du texte, jamais execute, liens symboliques
ignores, nom de dossier valide. Lancer avec `python3 -I`. Stdlib seule.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

HOME = Path.home()
AGENTS = HOME / ".agents/skills"
LOCK = HOME / ".agents/.skill-lock.json"
CLAUDE = HOME / ".claude/skills"
HERMES = HOME / ".hermes/skills"
DECLENCHEURS = HOME / ".claude/outils/declencheurs.json"
VERIFIER = CLAUDE / "fabrique-skill/scripts/verifier-skill.py"
EN_TETES = Path(__file__).resolve().parent.parent / "en-tetes"

EXCLUES = {"find-skills"}          # tierce, « NE PAS la modifier » (decision de USER, 2026-10-25)
ACCROCHE_MAX = 57                  # Hermes montre 57 car. de description
DESC_MAX = 1024
DESC_ALERTE = 500
SOMMAIRE_DES = 100
TIERS = {"node_modules", ".git", ".venv", "venv", "__pycache__", "site-packages"}
SUFFIXES = {".md", ".py", ".sh", ".json", ".txt", ".yaml", ".yml", ".html"}   # ce que verifier-skill.py controle
DOCS = {".md", ".txt"}   # les seuls fichiers retouches : le code tiers n'est jamais reecrit (USER, 2026-10-25)
TAILLE_MAX = 2_000_000
TIRET = "[" + chr(0x2013) + chr(0x2014) + "]"
CHAMPS_REFAITS = {"name", "description", "when_to_use"}
SOMMAIRE = re.compile(r"(?im)^(sommaire|##\s*sommaire|table des mati)")


# ---------------------------------------------------------------- texte

def sans_tirets(t):
    """Chiffre-tiret-chiffre -> '-', tiret entoure d'espaces -> ' - ', le reste -> '-'."""
    t, a = re.subn(r"(?<=\d)" + TIRET + r"(?=\d)", "-", t)
    t, b = re.subn(r"[ \t]+" + TIRET + r"[ \t]+", " - ", t)
    t, c = re.subn(TIRET, "-", t)
    return t, a + b + c


def guillemets(s):
    return '"' + s.replace('"', '\\"') + '"'


def titres(lignes, niveau):
    """Titres '#' de ce niveau, hors blocs de code."""
    marque, en_code, res = "#" * niveau + " ", False, []
    for l in lignes:
        if l.lstrip().startswith(("```", "~~~")):
            en_code = not en_code
        elif not en_code and l.startswith(marque):
            res.append(l[len(marque):].strip().rstrip("#").strip())
    return [t for t in res if t]


def avec_sommaire(corps):
    """Insere « Sommaire : » apres le 1er H1 si le corps depasse 100 lignes. -> (corps, ajoute)."""
    lignes = corps.split("\n")
    if len(lignes) <= SOMMAIRE_DES or SOMMAIRE.search(corps):
        return corps, False
    liste = titres(lignes, 2) or titres(lignes, 3)
    if not liste:
        return corps, False
    en_code, pos = False, 0
    for i, l in enumerate(lignes):
        if l.lstrip().startswith(("```", "~~~")):
            en_code = not en_code
        elif not en_code and l.startswith("# "):
            pos = i + 1
            break
    bloc = ["", "Sommaire :"] + [f"- {t}" for t in liste]
    if pos >= len(lignes) or lignes[pos].strip():
        bloc.append("")        # une seule ligne vide entre la liste et la suite
    return "\n".join(lignes[:pos] + bloc + lignes[pos:]), True


def ecrire(chemin, texte):
    """Ecriture atomique dans le meme dossier."""
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".mef-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texte)
        os.chmod(tmp, chemin.stat().st_mode & 0o777 if chemin.exists() else 0o644)
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------- SKILL.md

def decouper(texte):
    """-> (blocs [(cle, lignes)], prefixe, corps, etat). etat : 'ok' | 'sans' | 'ouvert'."""
    lignes = texte.split("\n")
    if lignes[0].strip() != "---":
        return [], "", texte, "sans"
    try:
        fin = next(i for i in range(1, len(lignes)) if lignes[i].strip() == "---")
    except StopIteration:
        return [], "", texte, "ouvert"
    blocs, cle, brut = [], None, []
    for l in lignes[1:fin]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):", l)
        if m:
            if cle is not None:
                blocs.append((cle, brut))
            cle, brut = m.group(1), [l]
        elif cle is not None:
            brut.append(l)
    if cle is not None:
        blocs.append((cle, brut))
    return blocs, "\n".join(lignes[:fin + 1]), "\n".join(lignes[fin + 1:]), "ok"


def empreinte(lignes):
    return hashlib.sha256(re.sub(r"\s+", " ", " ".join(lignes)).strip().encode()).hexdigest()[:16]


def verifier_entete(e):
    """Liste des problemes d'un en-tete (vide = valide)."""
    pb = []
    for cle in ("accroche", "fait", "pas_pour", "quand"):
        v = e.get(cle, "")
        if not v.strip():
            pb.append(f"{cle} manquant")
        elif "\n" in v or "\\" in v:
            pb.append(f"{cle} : ni retour a la ligne ni barre oblique inverse")
    if pb:
        return pb
    if len(e["accroche"]) > ACCROCHE_MAX:
        pb.append(f"accroche {len(e['accroche'])} car. (max {ACCROCHE_MAX})")
    if not re.search(r"[.!?…]$", e["accroche"]):
        pb.append("accroche : doit finir par . ! ou ?")
    if not e["pas_pour"].startswith("Pas pour"):
        pb.append("pas-pour doit commencer par « Pas pour »")
    desc = description(e)
    if len(desc) > DESC_MAX:
        pb.append(f"description {len(desc)} car. (max {DESC_MAX})")
    for m in e.get("motifs", []):
        try:
            re.compile(m)
        except re.error as exc:
            pb.append(f"motif invalide {m!r} : {exc}")
    return pb


def description(e):
    return sans_tirets(" ".join([e["accroche"].strip(), e["fait"].strip(), e["pas_pour"].strip()]))[0]


def frontmatter(nom, e, blocs):
    quand = sans_tirets(e["quand"].strip())[0]
    sortie = ["---", f"name: {nom}", f"description: {guillemets(description(e))}",
              f"when_to_use: {guillemets(quand)}"]
    for cle, lignes in blocs:
        if cle not in CHAMPS_REFAITS:
            sortie += lignes
    return "\n".join(sortie + ["---"])


# ---------------------------------------------------------------- fichiers du dossier

def parcourir(reel, suffixes):
    """Fichiers texte d'une skill importee. Ni lien symbolique, ni dossier tiers, ni SKILL.md."""
    for racine, dirs, fichiers in os.walk(reel, followlinks=False):
        dirs[:] = [d for d in dirs if d not in TIERS and not os.path.islink(os.path.join(racine, d))]
        for f in fichiers:
            p = Path(racine, f)
            if p == reel / "SKILL.md" or p.is_symlink() or p.suffix not in suffixes:
                continue
            try:
                if p.stat().st_size > TAILLE_MAX:
                    continue
                yield p, p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue


def tirets_dossier(reel, a_blanc):
    """Retouche les tirets des documents (.md, .txt) seulement. -> fichiers touches."""
    touches = []
    for p, t in parcourir(reel, DOCS):
        nouveau, n = sans_tirets(t)
        if n:
            touches.append((p.relative_to(reel), n))
            if not a_blanc:
                ecrire(p, nouveau)
    return touches


def tirets_code(reel):
    """Tirets longs restant dans le code tiers (.py, .sh...). Lecture seule : signale, ne corrige pas."""
    return [(p.relative_to(reel), sans_tirets(t)[1]) for p, t in parcourir(reel, SUFFIXES - DOCS) if sans_tirets(t)[1]]


# ---------------------------------------------------------------- liens et mesure

def cible_lien(reel, depuis):
    """Lien relatif pour une skill de ~/.agents/skills, absolu pour une skill de ~/.claude/skills."""
    return os.path.relpath(reel, depuis) if AGENTS in reel.parents else str(reel)


def lien_claude(nom, reel, a_blanc):
    cible = CLAUDE / nom
    if os.path.lexists(cible):
        return "ok" if cible.resolve() == reel else f"ATTENTION : {cible} existe et pointe ailleurs"
    if AGENTS not in reel.parents:
        return "sans objet"
    if not a_blanc:
        os.symlink(cible_lien(reel, CLAUDE), cible)
    return "a creer" if a_blanc else "cree"


def lien_hermes(nom, reel, categorie, a_blanc):
    candidats = [HERMES / nom] + [d / nom for d in sorted(HERMES.iterdir()) if d.is_dir() and not d.is_symlink()]
    existants = [p for p in candidats if os.path.lexists(p)]
    if existants:
        copies = [p for p in existants if not p.is_symlink()]
        if copies:
            return f"ATTENTION : copie (pas un lien) a ne pas laisser diverger : {copies[0]}"
        return "ok"
    if categorie and not re.fullmatch(r"[a-z0-9-]{1,40}", categorie):
        return f"categorie refusee : {categorie}"
    parent = HERMES / categorie if categorie else HERMES
    if not a_blanc:
        parent.mkdir(exist_ok=True)
        os.symlink(cible_lien(reel, parent), parent / nom)
    return "a creer" if a_blanc else "cree"


def declarer(nom, motifs, a_blanc):
    """Ajoute l'entree a declencheurs.json si absente. Relit juste avant d'ecrire (autres agents)."""
    if not motifs:
        return "pas de motif memorise : entree non ajoutee"
    d = json.loads(DECLENCHEURS.read_text(encoding="utf-8"))
    if nom in d:
        return "deja presente"
    if a_blanc:
        return "a ajouter"
    d[nom] = {"chemin": f"~/.claude/skills/{nom}/SKILL.md", "forcer": False, "motifs": motifs}
    ecrire(DECLENCHEURS, json.dumps(d, indent=2, ensure_ascii=False))
    return "ajoutee"


def controler(reel):
    r = subprocess.run([sys.executable, "-I", str(VERIFIER), str(reel)], cwd="/",
                       capture_output=True, text=True, timeout=120)
    E = [l[4:] for l in r.stdout.splitlines() if l.startswith("  E ")]
    A = [l[4:] for l in r.stdout.splitlines() if l.startswith("  A ")]
    return E, A


# ---------------------------------------------------------------- une skill

def memorise(nom):
    p = EN_TETES / f"{nom}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def traiter(dossier, neuf, a_blanc, local):
    """Rend (nom, lignes de rapport, nb d'erreurs restantes)."""
    reel = Path(dossier).expanduser().resolve()
    nom = reel.name
    rap = []
    if not re.fullmatch(r"[a-z0-9-]{1,64}", nom):
        return nom, [f"nom de dossier refuse : {nom!r} ([a-z0-9-], 64 car.)"], 1
    fichier = reel / "SKILL.md"
    if not fichier.is_file() or fichier.is_symlink():
        return nom, ["SKILL.md absent ou lien symbolique : ignore"], 1

    entete = dict(memorise(nom) or {})
    if neuf:
        entete.update(neuf)
    elif entete:
        rap.append("en-tete : rejoue celui memorise")
    pb = verifier_entete(entete) if entete else []
    if pb:
        return nom, [f"en-tete refuse : {p}" for p in pb], 1

    original = fichier.read_text(encoding="utf-8").replace("\r\n", "\n").lstrip(chr(0xFEFF))
    blocs, prefixe, corps, etat = decouper(original)
    if etat == "ouvert":
        return nom, ["frontmatter jamais referme : a reparer a la main"], 1

    # 1. en-tete
    if entete:
        actuel = next((l for c, l in blocs if c == "description"), [])
        notre = [f"description: {guillemets(description(entete))}"]
        if actuel != notre:
            sha = empreinte(actuel)
            if entete.get("origine_sha") and entete["origine_sha"] != sha:
                rap.append("ATTENTION : la description d'origine a change depuis l'import, relire l'en-tete francais")
            entete["origine_sha"] = sha
        prefixe = frontmatter(nom, entete, blocs) if etat == "ok" else frontmatter(nom, entete, [])
        if etat == "sans":
            corps = original
    # 2. tirets puis sommaire (l'ordre compte : les titres du sommaire sont deja propres)
    prefixe, n1 = sans_tirets(prefixe)
    corps, n2 = sans_tirets(corps)
    corps, somm = avec_sommaire(corps)
    nouveau = (prefixe + "\n" + corps) if prefixe else corps
    if nouveau != original:
        if not a_blanc:
            ecrire(fichier, nouveau)
        rap.append(("a reecrire" if a_blanc else "reecrit") + " : SKILL.md")
    else:
        rap.append("SKILL.md deja au format")
    if n1 + n2:
        rap.append(f"tirets longs : {n1 + n2} dans SKILL.md")
    if somm:
        rap.append("sommaire insere")
    for rel, n in tirets_dossier(reel, a_blanc):
        rap.append(f"tirets longs : {n} dans {rel}")
    code = tirets_code(reel)
    if code:
        rap.append(f"code tiers NON retouche : tirets longs dans {len(code)} fichier(s), ex. {code[0][0]}")
    if not entete:
        rap.append("pas d'en-tete francais memorise : description d'origine gardee")

    # 3. memoriser l'en-tete
    if entete and not a_blanc and (neuf or not memorise(nom)):
        entete["date"] = date.today().isoformat()
        EN_TETES.mkdir(exist_ok=True)
        (EN_TETES / f"{nom}.json").write_text(json.dumps(entete, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        rap.append(f"en-tete memorise : en-tetes/{nom}.json")
    elif entete and not a_blanc and neuf is None and entete.get("origine_sha") != (memorise(nom) or {}).get("origine_sha"):
        (EN_TETES / f"{nom}.json").write_text(json.dumps(entete, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 4. liens et mesure
    if not local:
        rap.append(f"lien Claude : {lien_claude(nom, reel, a_blanc)}")
        rap.append(f"lien Hermes : {lien_hermes(nom, reel, entete.get('categorie', ''), a_blanc)}")
        rap.append(f"declencheurs.json : {declarer(nom, entete.get('motifs', []), a_blanc)}")

    # 5. controle, 3 passes au plus (une passe suffit sauf tiret apparu entre-temps)
    for _ in range(3):
        E, A = controler(reel)
        if not [e for e in E if e.startswith("tiret long")] or a_blanc:
            break
        t = fichier.read_text(encoding="utf-8")
        corrige, n = sans_tirets(t)
        if not (n or tirets_dossier(reel, False)):
            break          # tiret hors de portee (lien symbolique, par ex.) : a signaler, pas a forcer
        if n:
            ecrire(fichier, corrige)
    etiquette = "verifier-skill (avant retouches)" if a_blanc else "verifier-skill"
    rap.append(f"{etiquette} : {len(E)} erreur(s), {len(A)} avertissement(s)")
    rap += [f"  E {e}" for e in E] + [f"  A {a}" for a in A]
    return nom, rap, len(E)


# ---------------------------------------------------------------- entree

def noms_du_lock():
    d = json.loads(LOCK.read_text(encoding="utf-8"))
    return sorted(d.get("skills", {}))


def main(argv):
    ap = argparse.ArgumentParser(description="Met une skill importee au format USER (corps garde).")
    ap.add_argument("dossier", nargs="?")
    ap.add_argument("--tout", action="store_true")
    ap.add_argument("--a-blanc", action="store_true")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--accroche")
    ap.add_argument("--fait")
    ap.add_argument("--pas-pour", dest="pas_pour")
    ap.add_argument("--quand")
    ap.add_argument("--motif", action="append", dest="motifs")
    ap.add_argument("--categorie")
    a = ap.parse_args(argv)

    if a.tout == bool(a.dossier):
        ap.error("donner un dossier, ou --tout (pas les deux)")
    champs = {"accroche": a.accroche, "fait": a.fait, "pas_pour": a.pas_pour, "quand": a.quand}
    neuf = None
    if any(champs.values()) or a.motifs:
        if a.tout:
            ap.error("--tout rejoue les en-tetes memorises : pas d'en-tete en argument")
        manque = [k for k, v in champs.items() if not v] + ([] if a.motifs else ["motif"])
        if manque:
            ap.error("en-tete incomplet, manque : " + ", ".join(manque))
        neuf = dict(champs, motifs=a.motifs)
        if a.categorie:
            neuf["categorie"] = a.categorie

    if a.tout:
        cibles = []
        for nom in noms_du_lock():
            if nom in EXCLUES:
                print(f"== {nom} : ignoree (tierce, ne pas modifier)")
            elif (AGENTS / nom).is_dir():
                cibles.append(AGENTS / nom)
            elif (CLAUDE / nom).is_dir() and not (CLAUDE / nom).is_symlink():
                cibles.append(CLAUDE / nom)   # `skills add -a claude-code` copie ici
            else:
                print(f"== {nom} : dossier absent de ~/.agents/skills et de ~/.claude/skills")
    else:
        cibles = [a.dossier]

    pannes = 0
    for c in cibles:
        nom, rap, erreurs = traiter(c, neuf, a.a_blanc, a.local)
        print(f"== {nom} : {'ERREUR' if erreurs else 'ok'}")
        for l in rap:
            print(l if l.startswith("  ") else f"  {l}")
        pannes += erreurs
    return 1 if pannes else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
