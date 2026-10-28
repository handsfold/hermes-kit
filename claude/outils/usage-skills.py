#!/usr/bin/env python3
"""Usage reel des skills : combien de fois chacune est chargee, et lesquelles dorment.

Sources : les transcripts Claude Code (~/.claude/projects, sous-agents compris),
ou passent aussi les tours d'Hermes depuis qu'il tourne sur Claude Code, et les
anciennes sessions Hermes (~/.hermes/sessions).

Un chargement compte quand l'agent :
- appelle l'outil Skill (Claude Code) ;
- appelle skill_view (Hermes) ;
- lit un fichier SKILL.md avec Read.

Option --rates : rates de declenchement. Un rate = un message de USER contient un
motif de declencheurs.json et la skill n'est pas chargee dans la meme session.
Un message tape avant la naissance de la skill (creation de son dossier) ne compte
pas : avant le 2026-10-28, 9 des 12 skills signalees l'etaient a tort pour ca.
Un message tape avant l'aiguilleur (2026-10-25) ne compte pas non plus, ni un brief
d'agent colle dans Telegram (brief_colle).

Option --hors-aiguilleur : sessions Hermes (tours Telegram sur Claude Code) ou
l'agent charge lui-meme une skill que l'aiguilleur n'a pas injectee. C'est ce
que les listes de skills du contexte rapportent encore (mesure du 2026-10-27,
avant de les retirer). --voir=SKILL donne des exemples de messages.

Option --tout : liste toutes les skills chargees (par defaut, les 40 premieres).

Usage : usage-skills.py [jours=30] [--dormantes] [--rates [--voir=SKILL]] [--hors-aiguilleur] [--tout]
--voir=SKILL : avec --rates, jusqu'a 25 exemples de rates pour cette skill (repetable).
"""
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HOME = Path.home()
SOURCES = [HOME / ".claude/projects", HOME / ".hermes/sessions"]
INSTALLEES = {
    "claude": HOME / ".claude/skills",
    "hermes": HOME / ".hermes/skills",
}
MARQUEURS = (b'"Skill"', b'skill_view', b'SKILL.md')
NOM_SKILL = re.compile(rb"[A-Za-z0-9_.-]+$")
# Mise en service de l'aiguilleur (Hermes et hook aiguilleur-cc.py, 2026-10-25 a 4 h) : avant, 21 des 27 rates.
AIGUILLEUR = datetime(2026, 10, 25, 4, 5).timestamp()
SKILL_JSON = re.compile(rb'"skill": ?"([^"]+)"')


def skills_chargees(brut):
    """Skills chargees dans un transcript, par bytes.find (1 passage par motif).
    Avant : 3 recherches du fichier entier par skill, 277 s sur 30 j (5,7 Go)."""
    noms = set()
    i = brut.find(b"/SKILL.md")
    while i != -1:
        m = NOM_SKILL.search(brut, max(0, i - 80), i)
        if m:
            noms.add(m.group().decode(errors="replace"))
        i = brut.find(b"/SKILL.md", i + 9)
    i = brut.find(b'"skill":')
    while i != -1:
        m = SKILL_JSON.match(brut, i)
        if m:
            noms.add(m.group(1).decode(errors="replace"))
        i = brut.find(b'"skill":', i + 8)
    return noms

INJECTEE = re.compile(rb"\[Skill router: the skill '([^']+)'")
DECLENCHEURS = HOME / ".claude/outils/declencheurs.json"
BLOCS = re.compile(
    r"<(memory-context|regles-apprises|system-reminder|task-notification)>.*?</\1>", re.S
)


def naissance(n, chemin):
    """Date de creation du dossier de la skill (Claude Code ou Hermes, la plus ancienne).
    Birth time ext4 par stat %W : le mtime de SKILL.md bouge a chaque retouche."""
    dossiers = [Path(os.path.expanduser(chemin)).parent] if chemin else []
    dossiers += [HOME / ".claude/skills" / n, *(HOME / ".hermes/skills").glob(f"*/{n}")]
    dates = []
    for d in dossiers:
        if d.exists():
            r = subprocess.run(["stat", "-L", "-c", "%W", str(d)], capture_output=True, text=True)
            if r.stdout.strip().isdigit() and int(r.stdout) > 0:
                dates.append(int(r.stdout))
    return min(dates) if dates else 0


def date_ligne(ligne, defaut):
    """Horodatage d'une ligne de transcript (ISO), sinon le mtime du fichier."""
    t = ligne.get("timestamp")
    if isinstance(t, str):
        try:
            return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return defaut


def session_de(f):
    """Cle de session : un sous-agent (dossier subagents) compte pour sa session parente."""
    return f.parent.parent.name if f.parent.name == "subagents" else f.stem


def message_vin(t):
    """Garde le message de USER seul : coupe avant les blocs ajoutes par Hermes."""
    return re.split(r"\n\n<|\n\[System:", t, maxsplit=1)[0]


# Tours "[Vin]" ecrits par Hermes, pas par USER : relance d'objectif, fin de tache de fond, resume.
AUTOMATIQUES = ("[Continuing toward your standing goal]", "[IMPORTANT: Background process", "You are a summarization agent")


def automatique(t):
    return t.removeprefix("[Vin]").lstrip().startswith(AUTOMATIQUES) or brief_colle(t)


def brief_colle(t):
    """Brief d'agent colle dans Telegram : long et avec un tiret long, que la dictee de USER ne produit pas.
    Ne a 1 200 caracteres le 2026-10-28 : les 2 briefs reperes font 1 519 et 2 478, ses messages longs moins de 1 000."""
    return len(t) > 1200 and ("\u2014" in t or "\u2013" in t)


def textes_humains(ligne):
    """Textes tapes par USER dans une ligne de transcript (hors sidechain, prompts SDK sauf les tours Telegram "[Vin]", et tool_result)."""
    if ligne.get("isSidechain"):
        return
    # sdk-cli = prompts assembles par Hermes (fil, chantier, resumes) : pas USER au clavier
    # Tour Telegram : Hermes lance claude en sdk-cli, le message de USER commence par "[Vin]".
    telegram = ligne.get("entrypoint", "cli") == "sdk-cli"
    if (ligne.get("entrypoint", "cli") not in ("cli", "sdk-cli")) or ligne.get("promptSource") == "system":
        return
    if ligne.get("isMeta") or ligne.get("isCompactSummary"):
        return
    msg = ligne.get("message") if isinstance(ligne.get("message"), dict) else ligne
    if (ligne.get("type") or msg.get("role")) != "user" or msg.get("role") not in (None, "user"):
        return
    contenu = msg.get("content")
    if isinstance(contenu, str):
        if not contenu.startswith("This session is being continued") and not automatique(contenu) and (not telegram or contenu.startswith("[Vin]")):
            yield message_vin(contenu) if telegram else contenu
    elif isinstance(contenu, list):
        for b in contenu:
            if isinstance(b, dict) and b.get("type") == "text":
                t = b.get("text") or ""
                if not t.startswith("This session is being continued") and not automatique(t) and (not telegram or t.startswith("[Vin]")):
                    yield message_vin(t) if telegram else t


def exemple(texte, m):
    a, b = max(0, m.start() - 25), min(len(texte), m.end() + 25)
    return " ".join(texte[a:b].split())[:60]


def affiche_rates(declenchees, chargees, exemples):
    print("Rates · sessions declenchees · chargees · rate % · skill")
    lignes = []
    for n, ss in declenchees.items():
        ok = len(ss & chargees[n])
        lignes.append((100 * (len(ss) - ok) // len(ss), len(ss), ok, n))
    lignes.sort(key=lambda t: (-t[0], -t[1], t[3]))
    for pct, nb, ok, n in lignes:
        print(f"  {nb} · {ok} · {pct} % · {n}")
    voir = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--voir=")]
    choix = [l for l in lignes if l[3] in voir] if voir else lignes[:3]
    for pct, nb, ok, n in choix:
        print(f"\nExemples ({n}) :")
        rates = [e for sess, e in exemples[n] if sess not in chargees[n]]
        for e in rates[: 25 if voir else 2]:
            print(f"  ...{e}...")


def hermes_desactivees():
    """Noms listes sous skills.disabled de config.yaml : Hermes ne les charge pas.

    Quelle que soit l'indentation des puces (le fichier en a 4 espaces)."""
    noms, dans_skills, dedans = set(), False, False
    try:
        lignes = (HOME / ".hermes/config.yaml").read_text().splitlines()
    except OSError:
        return noms
    for l in lignes:
        brut = l.strip()
        if not brut or brut.startswith("#"):
            continue
        if not l[0].isspace():  # cle de premier niveau
            dans_skills, dedans = brut == "skills:", False
        elif dans_skills and brut == "disabled:":
            dedans = True
        elif dedans and brut.startswith("- "):
            noms.add(brut[2:].split(" #")[0].strip().strip("'\""))
        else:
            dedans = False
    return noms


def skills_installees():
    noms = {}
    off = hermes_desactivees()
    for origine, racine in INSTALLEES.items():
        if not racine.exists():
            continue
        for f in racine.rglob("SKILL.md"):
            if origine == "hermes" and f.parent.name in off:
                continue
            noms.setdefault(f.parent.name, set()).add(origine)
    return noms


def nom_depuis(bloc):
    nom, entree = bloc.get("name"), bloc.get("input") or {}
    if nom == "Skill":
        s = entree.get("skill") or ""
        return s.split(":")[-1].split("/")[-1] or None
    if nom == "skill_view":
        s = entree.get("name") or entree.get("skill") or ""
        return s.split("/")[-1] or None
    if nom == "Read":
        p = entree.get("file_path") or ""
        if p.endswith("/SKILL.md"):
            return Path(p).parent.name
    return None


def blocs_outils(ligne):
    msg = ligne.get("message") if isinstance(ligne.get("message"), dict) else ligne
    contenu = msg.get("content")
    if isinstance(contenu, list):
        for b in contenu:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                yield b
    for tc in msg.get("tool_calls") or []:  # format Hermes
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except (ValueError, TypeError):
            args = {}
        yield {"name": fn.get("name"), "input": args}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    jours = int(args[0]) if args else 30
    limite = time.time() - jours * 86400
    compte, sessions = Counter(), defaultdict(set)
    rates = "--rates" in sys.argv
    motifs, declenchees, chargees, exemples = {}, defaultdict(set), defaultdict(set), defaultdict(list)
    nees = {}
    if rates:
        for n, d in json.loads(DECLENCHEURS.read_text()).items():
            if not n.startswith("_"):
                motifs[n] = [re.compile(x, re.I) for x in d["motifs"]]
                nees[n] = naissance(n, d.get("chemin"))
    hors = "--hors-aiguilleur" in sys.argv
    h_sess, h_auto, h_skills, h_ex = set(), set(), Counter(), defaultdict(list)
    fichiers = 0
    voulue = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--source=")]
    for racine in SOURCES:
        if voulue and not any(v in str(racine) for v in voulue):
            continue
        if not racine.exists():
            continue
        for f in racine.rglob("*.jsonl"):
            try:
                if f.stat().st_mtime < limite:
                    continue
                brut = f.read_bytes()
            except OSError:
                continue
            fichiers += 1
            sess = session_de(f)
            if rates:
                # Un seul passage sur le fichier (avant : 3 recherches par skill, 277 s sur 30 j).
                for n in skills_chargees(brut):
                    if n in motifs:
                        chargees[n].add(sess)
                for l in brut.splitlines():
                    if b'"user"' not in l:
                        continue
                    try:
                        ligne = json.loads(l)
                    except ValueError:
                        continue
                    if not isinstance(ligne, dict):
                        continue
                    quand = date_ligne(ligne, f.stat().st_mtime)
                    for t in textes_humains(ligne):
                        t = BLOCS.sub("", t)
                        if quand < AIGUILLEUR:
                            continue  # avant l'aiguilleur, rien n'injectait la skill : pas un rate de declenchement
                        for n, ms in motifs.items():
                            if quand < nees[n]:
                                continue  # message tape avant que la skill existe
                            for mo in ms:
                                m = mo.search(t)
                                if m:
                                    declenchees[n].add(sess)
                                    if len(exemples[n]) < 400:
                                        exemples[n].append((sess, exemple(t, m)))
                                    break
            injectees = {m.decode(errors="replace") for m in INJECTEE.findall(brut)}
            hermes = hors and (b'"content":"[Vin]' in brut or b'"text":"[Vin]' in brut or injectees)
            if hermes:
                h_sess.add(sess)
            if not any(m in brut for m in MARQUEURS):
                continue
            for l in brut.splitlines():
                if not any(m in l for m in MARQUEURS):
                    continue
                try:
                    ligne = json.loads(l)
                except ValueError:
                    continue
                if not isinstance(ligne, dict):
                    continue
                for b in blocs_outils(ligne):
                    n = nom_depuis(b)
                    if n:
                        compte[n] += 1
                        sessions[n].add(f.stem)
                        chargees[n].add(sess)
                        if hermes and n not in injectees:
                            h_auto.add(sess)
                            if sess not in h_ex[n]:
                                h_skills[n] += 1
                                h_ex[n].append(sess)

    if hors:
        print(f"{len(h_sess)} sessions Hermes sur {jours} jours")
        print(f"{len(h_auto)} ou l'agent charge seul une skill non injectee par l'aiguilleur\n")
        print("Sessions · skill")
        for n, c in h_skills.most_common(40):
            print(f"{c:5d} · {n}")
        for n in [a.split("=", 1)[1] for a in sys.argv if a.startswith("--voir=")]:
            print(f"\n{n} : {', '.join(h_ex[n][:10])}")
        return

    if rates:
        print(f"{fichiers} sessions lues sur {jours} jours\n")
        affiche_rates(declenchees, chargees, exemples)
        return

    installees = skills_installees()
    print(f"{fichiers} sessions lues sur {jours} jours")
    print(f"{len(installees)} skills installees, {len(compte)} chargees au moins 1 fois\n")
    print("Chargements · sessions · skill")
    for n, c in compte.most_common(None if "--tout" in sys.argv else 40):
        print(f"{c:5d} · {len(sessions[n]):4d} · {n}")
    dormantes = sorted(n for n in installees if n not in compte)
    print(f"\n{len(dormantes)} skills jamais chargees")
    if "--dormantes" in sys.argv:
        for n in dormantes:
            print(f"  {n} ({'+'.join(sorted(installees[n]))})")
    doublons = sorted(n for n, o in installees.items() if len(o) > 1)
    print(f"{len(doublons)} noms presents chez Claude ET Hermes : {', '.join(doublons[:15])}")


if __name__ == "__main__":
    main()
