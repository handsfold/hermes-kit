#!/usr/bin/env python3
"""Stop : sous le proxy Hermes, refuse une promesse de retour que rien ne tiendra.

Cause, mesuree le 2026-10-04 (topic Sparring) : sur 14 jours, 2 relances de USER
(« Alors ? ») suivaient une phrase comme « je t'envoie le classement des la fin
du test ». Le tour finit, le process `claude` sort, et plus rien ne reveille
l'agent : seul un nouveau message de USER le fait. Attente perdue : 69 min.

Une promesse est tenable si le tour a lance un mecanisme qui parlera seul :
  - `agent-fond lancer ...` (le rapport arrive dans le topic d'origine)
  - `hermes cron create|add ...` (tache planifiee, livree dans le topic)
Sinon : exit 2, le tour continue, l'agent lit 3 remedes. Une fois par tour.

Une promesse conditionnee a USER (« si tu dis oui, je ... ») n'est pas visee :
c'est son prochain message qui relancera l'agent.
"""
import json
import os
import re
import sys

VERBE = re.compile(
    r"\bje (?:t'|te |vous )?(?:envoie|enverrai|pr[ée]viens|pr[ée]viendrai|donne|donnerai|"
    r"transmets|transmettrai|reviens|reviendrai|tiens au courant|tiendrai au courant|"
    r"fais signe|ferai signe|poste|posterai|dis|dirai|partage|partagerai|livre|livrerai)\b"
    r"|\b(?:arrivera|tombera|sera post[ée]e?) (?:dans|ici|au)\b"
    r"|\bje reviens vers toi\b|\bje te tiens au courant\b",
    re.I)
QUAND = re.compile(
    r"\bd[èe]s (?:que|qu'|la fin|le r[ée]sultat|la sortie)|\bquand (?:ce sera|il sera|elle sera|le |la |les |[çc]a )"
    r"|\bune fois (?:que|qu'|fini|termin)|\bd'ici\b|\bdans (?:\d+|quelques|une|un) ?(?:min|h|heure|seconde)"
    r"|\bplus tard\b|\btout [àa] l'heure\b|\b[àa] la fin\b|\bau retour\b|\bdans ce (?:fil|topic)\b"
    r"|\benviron \d+ ?(?:min|h)|\bvers \d+ ?[h:]\d*"
    r"|\bje te tiens au courant\b",
    re.I)
SI_VJ = re.compile(
    r"\bsi tu\b|\bd[èe]s que tu\b|\bquand tu\b|\bune fois que tu\b|\bd[èe]s ton\b|\bsur ton\b"
    r"|\bdis[ -]moi\b|\br[ée]ponds\b|\bdis [«\"]|\bton (?:feu vert|accord|oui)\b|\bapr[èe]s ton\b"
    r"|\btu avais dit\b"
    # la phrase nomme le mecanisme qui tient deja la promesse
    r"|\bguetteur\b|\bagent-fond\b|\bcron\b|\bveilleur\b|\bminuterie\b",
    re.I)
MECANISME = re.compile(r"\bagent-fond\s+lancer\b|\bhermes\s+cron\s+(?:create|add)\b"
                       r"|\bsystemd-run\b|systemctl --user (?:enable|start)[^\"]*\.timer")


def promesses(texte):
    phrases = re.split(r"(?<=[.!?])\s+|\n+", texte)
    return [p.strip() for p in phrases
            if VERBE.search(p) and QUAND.search(p) and not SI_VJ.search(p)]


def tour(transcript):
    """Dernier texte de l'agent et commandes Bash depuis le dernier message de USER."""
    lignes = []
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            lignes = f.readlines()
    except OSError:
        return "", []
    textes, cmds = [], []
    for l in reversed(lignes):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        msg = e.get("message") or {}
        contenu = msg.get("content")
        if e.get("type") == "user":
            # un vrai message de USER (texte), pas un retour d'outil
            if isinstance(contenu, str) or any(
                    isinstance(c, dict) and c.get("type") == "text" for c in contenu or []):
                break
            continue
        if e.get("type") != "assistant" or not isinstance(contenu, list):
            continue
        for c in contenu:
            if c.get("type") == "text" and not textes:
                textes.append(c.get("text", ""))
            elif c.get("type") == "tool_use":
                cmds.append(json.dumps(c.get("input", {}), ensure_ascii=False))
    return (textes[0] if textes else ""), cmds


def main():
    if not (os.environ.get("HERMES_TOPIC_DIR") or os.environ.get("CLAUDE_TIMEOUT_MS")):
        return 0
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    if d.get("stop_hook_active"):
        return 0
    texte, cmds = tour(d.get("transcript_path", ""))
    texte = d.get("last_assistant_message") or texte
    trouvees = promesses(texte or "")
    if not trouvees:
        return 0
    if any(MECANISME.search(c) for c in cmds):
        return 0
    sys.stderr.write(
        "Ta reponse promet un retour que rien ne tiendra. A la fin de ce tour, "
        "plus rien ne te reveille : seul un message de USER le fera (2 relances "
        "« Alors ? » en 14 jours, 69 min perdues le 2026-10-04).\n"
        + "\n".join(f"  « {p[:160]} »" for p in trouvees[:3]) + "\n"
        "Remede, au choix :\n"
        "  1. Attendre le resultat dans ce tour, puis repondre avec.\n"
        "  2. Confier le retour a un mecanisme qui parlera seul : "
        "`agent-fond lancer \"attends <pid|fichier>, lis <resultat>, fais le rapport\"` "
        "(rapport poste dans ce topic), ou `hermes cron create`.\n"
        "  3. Retirer la promesse : dire ou lire le resultat, et que USER devra demander.\n"
        "Puis reecris ta reponse finale en entier.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
