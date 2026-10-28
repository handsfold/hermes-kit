#!/usr/bin/env python3
"""Stop : refuse « c'est corrige / en ligne / ca marche » quand rien n'a ete execute apres la derniere modification de code.

Cree le 2026-10-07. Regle portee : « jamais d'annonce de livraison sans avoir
execute le resultat » (skill verifier-avant-livraison, regles apprises r005,
r006, r008, r011 dans ~/.hermes/apprentissage/regles.json). Ecrite en texte,
elle a ete violee : 58 messages de USER depuis le 2026-09-01 disent « ne marche
pas / toujours pas / pas accessible » (15 depuis le 2026-10-03), apres des
annonces de reussite. La consigne texte ne tient pas, ce hook la rend
objective : le journal d'outils du tour doit montrer une execution APRES la
derniere modification.

Declencheur (les 3 conditions ensemble) :
  1. le tour a modifie du code (Edit/Write sur .py .js .sh .html .css ...,
     ou `sed -i`) ;
  2. la reponse finale annonce une reussite (« c'est corrige », « ca marche
     maintenant », « est en ligne », « j'ai repare »...) ;
  3. aucune commande (hors lecture/git) ni outil MCP n'a tourne apres la
     derniere modification.
Durci le 2026-10-13 (rejeu de 5 affaires : 4 fois sur 5, un correctif annonce
avec une preuve partielle). Meme quand une commande a tourne, l'annonce est
refusee si :
  4. la commande n'est qu'une preparation (redemarrage, controle de syntaxe,
     installation, copie) : elle ne prouve pas que ca marche ;
  5. la derniere verification apres la modification a ECHOUE (code de sortie,
     Traceback, Parse error) : cas du [SILENT], annonce sur un script plante ;
  6. USER a cite un site ou une adresse (URL, domaine) et aucune verification ne
     l'a touche : cas du focus, verifie sous X11 quand son PC est sous Wayland ;
  7. la reponse ne dit pas comment ni ou c'est verifie (regle apprise :
     « dis ou tu as verifie »).
  8. la reponse annonce « regle » ET avoue « pas encore verifie » : USER lit la
     tete (cas du [SILENT] du 13/10, 19:07).
Echappatoire : dire que ce n'est pas verifie SANS annoncer de reussite
(« correctif pose, non verifie »), ou VERIF_ANNONCE_OFF=1. Un seul refus par tour
(stop_hook_active), fail-open sur toute erreur. Journal : ~/.claude/hooks/refus.log
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CODE = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".bash", ".html",
        ".css", ".service", ".timer", ".sql", ".go", ".rs", ".php")
MODIFS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# annonce de reussite, a la premiere personne ou au constat
ANNONCE = re.compile(
    r"\bc'est (?:maintenant )?(?:corrig[ée]|r[ée]gl[ée]|r[ée]par[ée]|livr[ée]|d[ée]ploy[ée]|en ligne|fix[ée])\b"
    r"|\b(?:j'ai|je viens de) (?:corrig[ée]|r[ée]par[ée]|r[ée]gl[ée]|d[ée]ploy[ée]|livr[ée]|fix[ée])\b"
    r"|\b(?:le|ce|cet|la|l') ?(?:bug|probl[èe]me|erreur|souci|panne|d[ée]faut)(?: \w+){0,3} est (?:corrig[ée]|r[ée]solu|r[ée]gl[ée]|r[ée]par[ée])\b"
    r"|\b[çc]a (?:marche|fonctionne) (?:maintenant|d[ée]sormais|bien maintenant)\b"
    r"|\bfonctionne (?:maintenant|d[ée]sormais)\b"
    r"|\b(?:est|sont) (?:maintenant |d[ée]sormais )?(?:en ligne|d[ée]ploy[ée]e?s?|livr[ée]e?s?|corrig[ée]e?s?|op[ée]rationnel(?:le)?s?)\b"
    r"|\bcorrection (?:livr[ée]e|appliqu[ée]e|en place)\b",
    re.I)
# la reponse reconnait elle-meme que ce n'est pas verifie : honnete, on laisse passer
AVEU = re.compile(
    r"\b(?:non|pas|jamais) (?:encore |pu )?(?:v[ée]rifi|test|lanc|ex[ée]cut|relanc|essay)"
    r"|\bn'(?:ai|est|ont) pas (?:encore |pu )?(?:v[ée]rifi|test|lanc|ex[ée]cut|relanc|essay)"
    r"|\bsans (?:l'avoir |avoir )?(?:v[ée]rifi|test|lanc|ex[ée]cut)"
    r"|\b[àa] v[ée]rifier\b|\breste [àa] (?:v[ée]rifier|tester|lancer)\b|\bnon v[ée]rifi",
    re.I)
# commandes qui ne prouvent rien : lecture, git, affichage
INERTE = re.compile(
    r"^\s*(?:rtk\s+)?(?:cd [^;&|]+(?:&&|;)\s*)?(?:ls|cat|head|tail|wc|grep|rg|find|stat|pwd|echo|printf|"
    r"sed -n|git (?:status|diff|log|show|add|commit|stash|branch|checkout|restore)|supertool|which|"
    r"file|tree|du|df|date|true|sqlite3\s[^\n]*[\"']\s*(?:select|\.schema|\.tables)|jq|python3? -c [\"']import json)\b", re.I)
EXT = "|".join(e.lstrip(".") for e in CODE)
# modification de code depuis le terminal (2026-10-13, cas du [SILENT]) :
# open(..., "w") dans un heredoc python, ou redirection shell vers un fichier de code
ECRIT_PY = re.compile(r"open\([^)]*,\s*[\"'][wa]\+?[\"']|\.write_text\(")
NOM_CODE = re.compile(r"[\"']([^\"'\s]+\.(?:" + EXT + r"))[\"']")
REDIR = re.compile(r"(?:^|[^<>&\d])>>?\s*([^\s;&|<>]+\.(?:" + EXT + r"))\b|\btee\s+(?:-a\s+)?([^\s;&|]+\.(?:" + EXT + r"))\b")


# commandes qui preparent mais ne verifient pas (2026-10-13)
PREPA = re.compile(
    r"^\s*(?:rtk\s+)?(?:sudo\s+)?(?:systemctl(?:\s+--user)?\s+(?:restart|start|stop|reload|enable|disable|daemon-reload|reset-failed)"
    r"|python3? -m (?:py_compile|compileall|pip)|pip3? install|uv (?:pip|add|sync)|npm (?:i|install|ci)\b|bash -n|sh -n|node --check"
    r"|cd|cp|mv|rm|ln|mkdir|chmod|chown|touch|tee|kill|sleep|source|export|\S+ --(?:help|version))\b")
ECHEC = re.compile(r"Traceback \(most recent call last\)|Parse error|command not found|"
                   r"No such file or directory|^Error\b|\bSyntaxError\b|Exit code [1-9]", re.M)
# un site cite par USER : URL, ou domaine nu
LIEU = re.compile(r"https?://([\w.-]+)|\b((?:[\w-]+\.)+(?:com|co\.th|net|org|io|app|dev|fr|th))\b", re.I)
# la reponse dit comment elle a verifie
PREUVE = re.compile(r"v[ée]rifi|test|lanc[ée]|capture|sortie|preuve|rejou|reprodui|essai|mesur|constat", re.I)


# sites de contenu que USER partage (une video, un article) : pas le lieu d'un bug
CONTENU = ("youtube.com", "youtu.be", "tiktok.com", "facebook.com", "instagram.com", "x.com",
           "twitter.com", "reddit.com", "amazon.com", "google.com", "github.com", "wikipedia.org")


def lieux(demande):
    """Domaines cites par USER, hors blocs injectes (memoire, regles, notes systeme).

    Un resume de compaction n'est pas une demande de USER : on n'en tire rien."""
    if (demande or "").lstrip().startswith("This session is being continued"):
        return set()
    t = re.sub(r"<(memory-context|regles-apprises)>.*?</\1>", " ", demande or "", flags=re.S)
    t = re.sub(r"\[System[^\]]*\]", " ", t)
    out = set()
    for m in LIEU.finditer(t):
        d = (m.group(1) or m.group(2) or "").lower().strip(".")
        if d and not d.endswith((".py", ".sh", ".md", ".js")) and not d.endswith(CONTENU):
            out.add(d[4:] if d.startswith("www.") else d)
    return out


# un script de test jetable n'est pas du code livre
JETABLE = ("/tmp/", "/cache/scratch/", "/.cache/")
# lancer en arriere-plan, c'est ne pas lire le resultat : pas une verification
FOND = re.compile(r"\b(?:nohup|setsid|disown)\b|&\s*$")


def modifs_code(outils):
    """Indices des modifications de code dans le tour, et le nom du dernier fichier."""
    idx, fichier = _modifs(outils)
    garde = [(i, f) for i, f in zip(idx, fichier) if not any(j in f for j in JETABLE)]
    return [i for i, _ in garde], (garde[-1][1] if garde else "")


def _modifs(outils):
    """Toutes les modifications : (indices, fichiers), fichiers temporaires compris."""
    idx, fichiers = [], []
    for i, (nom, entree) in enumerate(outils):
        if nom in MODIFS:
            chemin = str(entree.get("file_path") or entree.get("notebook_path") or "")
            if chemin.endswith(CODE):
                idx.append(i)
                fichiers.append(chemin)
        elif nom == "Bash":
            cmd = str(entree.get("command", ""))
            if ECRIT_PY.search(cmd) and NOM_CODE.search(cmd):
                idx.append(i)
                fichiers.append(NOM_CODE.search(cmd).group(1))
            m = REDIR.search(cmd)
            if m:
                idx.append(i)
                fichiers.append(m.group(1) or m.group(2))
            for seg in re.split(r"&&|;|\|\||\||\n", cmd):
                if re.match(r"\s*sed\s+(?:-\w+\s+)*-\w*i", seg):
                    cible = seg.split()[-1].strip("'\"") if seg.split() else ""
                    if cible.endswith(CODE):
                        idx.append(i)
                        fichiers.append(cible)
    return idx, fichiers


HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\s*(?=\n|$)", re.S)
AFFECT = re.compile(r"^\s*\w+=(?!\$\()\S*\s*$")


def segments(cmd):
    """Commandes reelles d'une ligne Bash : le texte d'un heredoc n'en est pas."""
    cmd = HEREDOC.sub(" ", cmd)
    return [x for x in re.split(r"&&|;|\|\||\||\n", cmd) if x.strip()]


def verifications(outils, debut):
    """Indices des outils qui verifient vraiment apres la modification."""
    out = []
    for i in range(debut + 1, len(outils)):
        nom, entree = outils[i]
        if nom.startswith("mcp__") or nom in ("Agent", "Task"):
            out.append(i)
        # une capture d'ecran regardee est une verification visuelle
        elif nom == "Read" and str(entree.get("file_path", "")).lower().endswith(
                (".png", ".jpg", ".jpeg", ".webp")):
            out.append(i)
        elif nom == "Bash":
            cmd = str(entree.get("command", ""))
            # une commande qui lit ou prepare seulement ne prouve rien
            segs = segments(cmd)
            if any(not INERTE.match(x) and not PREPA.match(x) and not FOND.search(x)
                   and not AFFECT.match(x) for x in segs):
                out.append(i)
    return out


def execute_apres(outils, debut):
    return bool(verifications(outils, debut))


REPARE = re.compile(r"\b(corrig[ée]e?s?|r[ée]gl[ée]e?s?|r[ée]solue?s?|r[ée]par[ée]e?s?)\b", re.I)


def decision(texte, outils, resultats=None, demande=""):
    """Renvoie (annonce, fichier, motif) si le tour doit etre refuse, sinon None."""
    if not texte:
        return None
    m = ANNONCE.search(texte)
    if not m:
        return None
    idx, fichier = modifs_code(outils)
    if not idx:
        return None
    # « C'est regle » en tete, « pas encore verifie » plus bas : USER lit la tete
    # (cas reel du [SILENT], 2026-10-13 19:07). L'aveu ne couvre plus l'annonce.
    # Seules les annonces de reparation : « en ligne » + « prix non verifie »
    # porte sur une donnee, pas sur le correctif (8205340c, rejeu du 13/10).
    if AVEU.search(texte):
        rep = REPARE.search(texte)
        if rep:
            return rep.group(0), fichier, "contradiction"
        return None
    verifs = verifications(outils, idx[-1])
    if not verifs:
        return m.group(0), fichier, "rien"
    err, sortie = (resultats or {}).get(verifs[-1], (False, ""))
    if err or ECHEC.search(sortie or ""):
        return m.group(0), fichier, "echec"
    voulus = lieux(demande)
    if voulus:
        # le site peut etre vise par un script de test ecrit plus tot dans le tour,
        # ou apparaitre dans la sortie de la verification
        touche = " ".join(json.dumps(e, ensure_ascii=False).lower()
                          for n, e in outils if n in ("Bash", "Write", "Agent", "Task") or n.startswith("mcp__"))
        touche += " ".join(str((resultats or {}).get(i, (0, ""))[1]).lower() for i in verifs)
        if not any(d in touche for d in voulus):
            return m.group(0), fichier, "lieu:" + ", ".join(sorted(voulus))
    if not PREUVE.search(texte):
        return m.group(0), fichier, "muet"
    return None


def main():
    if os.environ.get("VERIF_ANNONCE_OFF"):
        return 0
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    if d.get("stop_hook_active"):
        return 0
    try:
        from _tour import lire_tour
        res = {}
        texte, outils, demande = lire_tour(d.get("transcript_path", ""), res)
        texte = d.get("last_assistant_message") or texte
        r = decision(texte, outils, res, demande)
    except Exception:
        return 0
    if not r:
        return 0
    annonce, fichier, motif = r
    try:
        with open(os.path.expanduser("~/.claude/hooks/refus.log"), "a") as j:
            j.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} verif-avant-annonce {motif} {annonce!r} {fichier}\n")
    except OSError:
        pass
    base = os.path.basename(fichier)
    pourquoi = {
        "rien": f"aucune commande de verification n'a ete executee apres ta derniere "
                f"modification de code ({base}). Redemarrer, compiler ou copier ne prouve rien.",
        "echec": f"ta derniere verification apres la modification de {base} a ECHOUE "
                 "(code de sortie, Traceback ou Parse error). Une verification plantee ne prouve rien.",
        "contradiction": "tu ecris aussi que ce n'est pas verifie. USER lit la premiere phrase : "
                         "ne dis pas « regle » avant la preuve. Ecris « correctif pose, pas encore "
                         "verifie : <ce qui manque> », ou verifie d'abord.",
        "muet": "ta reponse ne dit pas comment ni ou tu l'as verifie. "
                "Regle apprise : dis ou tu as verifie (commande, resultat, endroit).",
    }.get(motif) or (
        f"USER a vu le probleme sur {motif[5:]}, et aucune de tes verifications ne touche "
        "cet endroit. Verifie la ou il l'a vu (curl, verif-ui.sh, sous-agent sur ce site).")
    sys.stderr.write(
        f"Tu annonces une reussite (« {annonce} ») mais {pourquoi} "
        "USER a signale 58 fois depuis le 2026-09-01 que ce qu'on lui disait fait ne marchait pas.\n"
        "Remede, au choix :\n"
        "  1. Executer le resultat (test, curl, script, capture d'ecran), lire la sortie, "
        "puis annoncer avec la preuve (commande et resultat).\n"
        "  2. Si l'execution est impossible ici, l'ecrire : « non verifie : <pourquoi> », "
        "et ne pas dire que c'est corrige.\n"
        "Puis reecris ta reponse finale en entier.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
