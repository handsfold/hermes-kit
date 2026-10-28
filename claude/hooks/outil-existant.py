#!/usr/bin/env python3
"""Refuse une commande Bash quand un mecanisme moins cher fait deja le travail.

Sur PreToolUse/Bash. Trois regles, dans cet ordre :
  1. OUTIL      : un script de ~/.claude/outils/ couvre deja l'analyse demandee ;
  2. GROUPAGE   : la commande enchaine 2 lectures ou plus, supertool n'en fait qu'une ;
  3. DELEGATION : la commande balaye tout le disque, un sous-agent Explore le fait
                  dans son propre contexte.

Le gain n'est jamais la compression du texte, c'est le nombre d'allers-retours :
un tour de session principale relit environ 75k de contexte (mediane mesuree sur
7 jours), un tour de sous-agent environ 20k. Mesure du 2026-09-13 : 21 appels
supertool sur 1527 appels Bash (1 %), 934 commandes enchainaient des lectures,
7 appels Agent. Une regle ecrite en Markdown ne change pas ces chiffres, un hook
les change.
"""
import os
import json, sys, os, glob, re, shlex

# ---------------------------------------------------------------- regle 1
# (motifs obligatoires, motifs signal, appel, description)
# Tous les obligatoires, plus AU MOINS DEUX signaux : un seul signal fait des faux
# positifs (lire trois lignes d'une base n'est pas en faire le bilan).
OUTILS = [
    (('.claude/projects', 'jsonl'), ('tool_use', 'assistant', 'thinking'),
     '~/.claude/outils/mes-tokens.py [nb_sessions]',
     "repartition des tokens produits par l'agent"),
    (('.claude/projects', 'jsonl'), ('Bash', 'command'),
     '~/.claude/outils/mes-commandes.py [nb_sessions]',
     'taille et repetition des commandes Bash'),
    (('history.db',), ('saved_tokens', 'savings_pct', 'parse_failures', 'input_tokens'),
     '~/.claude/outils/rtk-bilan.py [nb_jours]',
     'gains RTK par jour et par commande'),
]
SEUIL = 300  # les motifs sont deja tres specifiques : le seuil evite juste les one-liners

# Porte de sortie : reparer l'outillage lui-meme ne doit jamais etre bloque,
# sinon le hook s'interdit sa propre correction.
EXEMPTIONS = ('.claude/hooks/', '.claude/outils/', 'supertool')

# ---------------------------------------------------------------- regle 2
SEPARATEURS = re.compile(r'&&|\|\||;|\|')
# Un tube (a | b) est UNE lecture filtree, pas deux : regle 2 seulement
# (2026-10-28, 19 faux refus sur `sed -n 1,200p f | tail`).
CHAINES = re.compile(r'&&|\|\||;')

def op_supertool(seg):
    """Traduit un segment shell en operation supertool, ou None si ce n'est pas
    une lecture simple. None fait taire le hook : mieux vaut laisser passer que
    proposer une ligne fausse."""
    seg = seg.strip()
    if not seg or any(c in seg for c in '|><`$('):
        return None
    try:
        mots = shlex.split(seg)
    except ValueError:
        return None
    if not mots:
        return None
    verbe = os.path.basename(mots[0])
    opts = [m for m in mots[1:] if m.startswith('-')]
    args = [m for m in mots[1:] if not m.startswith('-')]
    if verbe == 'cat' and len(args) == 1:
        return 'read:%s' % args[0]
    if verbe == 'sed' and '-n' in opts and len(args) == 2:
        return 'read:%s' % args[1]          # sed -i ecrit : exclu par '-n' obligatoire
    if verbe == 'ls':
        return 'ls:%s' % (args[0] if args else '.')
    if verbe == 'wc' and args:
        return 'wc:%s' % args[0]
    if verbe in ('stat', 'file') and args:
        return 'stat:%s' % args[0]
    if verbe in ('head', 'tail') and args:
        return '%s:%s' % (verbe, args[0])
    if verbe == 'tree':
        return 'tree:%s' % (args[0] if args else '.')
    if verbe == 'grep' and len(args) >= 2 and not any(o.startswith('-r') for o in opts):
        return 'grep:%s:%s:3' % (args[0], args[1])
    return None

def lectures_enchainees(cmd):
    """Liste des operations supertool si TOUS les segments sont des lectures
    simples et qu'il y en a au moins 2. Sinon liste vide."""
    if '<<' in cmd or '\n' in cmd.strip():
        return []
    segments = [s for s in CHAINES.split(cmd) if s.strip()]
    if len(segments) < 2:
        return []
    ops = [op_supertool(s) for s in segments]
    return ops if all(ops) else []

# ---------------------------------------------------------------- regle 3
# Racines larges seulement : '.' est souvent un petit projet, ou deleguer
# couterait plus que l'aller-retour direct.
_H = os.path.expanduser('~')
RACINES_LARGES = ('~', '~/', '/', '/home', _H, '/usr', '/etc', '/var',
                  '~/Bureau', '~/Bureau/Projets', _H + '/Bureau',
                  _H + '/Bureau/Projets')

def balayages_larges(cmd):
    """Nombre de recherches recursives sur une racine large."""
    n = 0
    for seg in SEPARATEURS.split(cmd):
        try:
            mots = shlex.split(seg.strip())
        except ValueError:
            continue
        if not mots:
            continue
        verbe = os.path.basename(mots[0])
        args = [m for m in mots[1:] if not m.startswith('-')]
        opts = [m for m in mots[1:] if m.startswith('-')]
        if verbe == 'find' and args and args[0].rstrip('/') in [r.rstrip('/') for r in RACINES_LARGES]:
            # find borne (-maxdepth <= 4) : une recherche ciblee, pas un
            # balayage (62 faux refus sur 89, revue du 2026-10-28).
            if '-maxdepth' in mots:
                try:
                    if int(mots[mots.index('-maxdepth') + 1]) <= 4:
                        continue
                except (ValueError, IndexError):
                    pass
            n += 1
        elif verbe in ('rg', 'ag') and len(args) >= 2 and args[1].rstrip('/') in [r.rstrip('/') for r in RACINES_LARGES]:
            n += 1
        elif verbe == 'grep' and any(o.startswith('-') and ('r' in o or 'R' in o) for o in opts):
            cible = args[1] if len(args) >= 2 else '.'
            if cible.rstrip('/') in [r.rstrip('/') for r in RACINES_LARGES]:
                n += 1
    return n

def commande_precedente(chemin):
    """Derniere commande Bash du transcript, lue par la fin. Vide si illisible."""
    try:
        taille = os.path.getsize(chemin)
        with open(chemin, 'rb') as f:
            f.seek(max(0, taille - 400_000))
            lignes = f.read().decode('utf-8', 'ignore').splitlines()
    except Exception:
        return ''
    for l in reversed(lignes):
        if '"Bash"' not in l:
            continue
        try:
            contenu = json.loads(l).get('message', {}).get('content')
        except Exception:
            continue
        if isinstance(contenu, list):
            for b in reversed(contenu):
                if (isinstance(b, dict) and b.get('type') == 'tool_use'
                        and b.get('name') == 'Bash'):
                    return b.get('input', {}).get('command', '')
    return ''

def est_recherche(cmd):
    """Recherche recursive, quelle que soit la cible."""
    for seg in SEPARATEURS.split(cmd):
        try:
            mots = shlex.split(seg.strip())
        except ValueError:
            continue
        if not mots:
            continue
        verbe = os.path.basename(mots[0])
        opts = [m for m in mots[1:] if m.startswith('-')]
        if verbe in ('find', 'rg', 'ag'):
            return True
        if verbe == 'grep' and any('r' in o.lower() for o in opts):
            return True
    return False

# ----------------------------------------------------------------
def refuser(raison):
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': raison}}))
    sys.exit(0)

def main():
    try:
        charge = json.load(sys.stdin)
    except Exception:
        return
    cmd = charge.get('tool_input', {}).get('command', '')
    # Le controle des tirets longs est exige par CLAUDE.md : jamais refuse.
    if not cmd or any(e in cmd for e in EXEMPTIONS) or r'\x{2013}' in cmd:
        return
    # Un sous-agent repart d'un contexte neuf : lui demander de deleguer encore
    # n'economise rien et l'empeche de faire son travail d'exploration.
    sous_agent = '/subagents/' in charge.get('transcript_path', '')

    # Regle 1 : un outil existe deja.
    if len(cmd) >= SEUIL:
        for oblig, aumoins, appel, quoi in OUTILS:
            if all(m in cmd for m in oblig) and sum(m in cmd for m in aumoins) >= 2:
                dispo = sorted(os.path.basename(p) for p in
                               glob.glob(os.path.expanduser('~/.claude/outils/*.py')))
                refuser(f"Outil deja ecrit pour ca : {appel} ({quoi}). "
                        f"Lance-le au lieu de reecrire le script. "
                        f"Outils disponibles : {', '.join(dispo)}. "
                        f"S'il ne repond pas exactement au besoin, modifie le fichier "
                        f"plutot que d'en ecrire un jetable.")

    # Regle 3 avant la 2 : une exploration large se delegue entiere, la grouper
    # en supertool la ramenerait quand meme dans le contexte principal.
    # 2026-10-28 : ne joue plus que si les DEUX recherches visent une racine
    # large. Sur une cible etroite, 223 refus sur 240 etaient faux.
    if not sous_agent and balayages_larges(cmd) and balayages_larges(
            commande_precedente(charge.get('transcript_path', ''))):
        refuser("2e recherche recursive d'affilee : c'est un balayage, pas une "
                "verification. Delegue-le : outil Agent, subagent_type 'Explore', "
                "en decrivant ce que tu cherches et le format de reponse attendu. "
                "Il essaiera les variantes de nom dans SON contexte, et seul le "
                "resultat reviendra ici. Mesure du 2026-09-14 : 26 appels sur 1567 "
                "partaient en series de ce type.")

    if not sous_agent and balayages_larges(cmd) >= 1:
        refuser("Exploration large du disque depuis la session principale. "
                "Delegue-la : outil Agent, subagent_type 'Explore', en lui donnant "
                "ce que tu cherches et le format de reponse attendu. Seul son "
                "resultat revient ici, pas les fichiers parcourus. "
                "Si la cible est un seul dossier de projet connu, nomme-le au lieu "
                "de partir de la racine, et la commande passera.")

    # Regle 2 : plusieurs lectures dans un seul aller-retour.
    ops = lectures_enchainees(cmd)
    if len(ops) >= 2:
        ligne = ' '.join("'%s'" % o for o in ops)
        refuser(f"{len(ops)} lectures enchainees = {len(ops)} fois le contexte relu. "
                f"supertool les fait en un seul appel :\n  supertool {ligne}\n"
                f"Verifie les chemins et lance cette ligne. Operations disponibles : "
                f"read, grep, ls, stat, wc, head, tail, tree, glob, around, map.")

main()
