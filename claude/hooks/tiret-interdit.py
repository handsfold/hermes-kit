#!/usr/bin/env python3
"""Stop : refuse une reponse finale qui contient un tiret cadratin ou demi-cadratin.

Cree le 2026-10-07. Regle portee : « Les tirets longs sont interdits partout »
(~/.claude/CLAUDE.md, regle ferme). Ecrite en texte, avec pour seul controle un
grep a la main, elle est violee : sur les reponses finales Telegram d'Hermes,
132 sur 3491 depuis le 2026-09-01 (3,8 %), dont 7 sur 847 depuis le
2026-10-03 (state.db, role assistant sans appel d'outil).

Declencheur : U+2013 ou U+2014 dans le texte final, HORS blocs de code, code en
ligne, citations (« ... », "...", lignes `>`) : un tiret cite d'un document n'est pas
une faute de l'agent. Remplacement impose par la regle : `:` `.` `,` `( )` `·`
selon le role du tiret, `-` entre deux nombres ou deux mots.
Echappatoires : TIRET_OK=1, ou une reponse qui parle du caractere sans l'ecrire.
Un seul refus par tour (stop_hook_active), fail-open sur toute erreur.
Journal : ~/.claude/hooks/refus.log
"""
import json
import os
import re
import sys
import time

TIRET = re.compile(r"[\u2013\u2014]")
CODE_BLOC = re.compile(r"```.*?```|~~~.*?~~~", re.S)
CODE_LIGNE = re.compile(r"`[^`\n]*`")
CITATION = re.compile(r"«[^»]*»|^>.*$", re.M)


def fautes(texte):
    """Extraits de texte autour des tirets, apres retrait du code et des citations."""
    propre = CODE_BLOC.sub(" ", texte)
    propre = CODE_LIGNE.sub(" ", propre)
    propre = CITATION.sub(" ", propre)
    sorties = []
    for m in TIRET.finditer(propre):
        a, b = max(0, m.start() - 25), min(len(propre), m.end() + 25)
        sorties.append(propre[a:b].replace("\n", " "))
    return sorties


def main():
    if os.environ.get("TIRET_OK"):
        return 0
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    if d.get("stop_hook_active"):
        return 0
    try:
        texte = d.get("last_assistant_message")
        if not texte:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from _tour import lire_tour
            texte = lire_tour(d.get("transcript_path", ""))[0]
        trouvees = fautes(texte or "")
    except Exception:
        return 0
    if not trouvees:
        return 0
    try:
        with open(os.path.expanduser("~/.claude/hooks/refus.log"), "a") as j:
            j.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} tiret-interdit {len(trouvees)} tiret(s)\n")
    except OSError:
        pass
    sys.stderr.write(
        f"Ta reponse contient {len(trouvees)} tiret(s) cadratin ou demi-cadratin (U+2014, U+2013). "
        "Regle ferme de USER : aucun, nulle part. Extraits :\n"
        + "\n".join(f"  ...{t}..." for t in trouvees[:4]) + "\n"
        "Remplacement selon le role du tiret : explication `:`, deux idees `.` ou `,`, incise "
        "`( )` ou deux virgules, liste en ligne `·`, deux mots ou deux nombres `-` (U+002D).\n"
        "Reecris ta reponse finale en entier, sans aucun de ces deux caracteres.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
