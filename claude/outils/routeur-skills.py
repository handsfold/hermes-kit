#!/usr/bin/env python3
"""Catalogue Pi reel, recherche bornee et generation du petit routeur.

Aucun appel LLM, aucune modification des skills partagees. La decouverte est
celle de Pi (liens, exclusions, frontmatter et collisions compris).
Usage : routeur-skills.py --chercher 'conversion page' [--limite 5]
        routeur-skills.py --json
        routeur-skills.py --generer
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import unicodedata

HOME = Path.home()
SORTIE = HOME / '.agents/skills/routeur-skills/SKILL.md'
MODULE = HOME / '.npm-global/lib/node_modules/@earendil-works/pi-coding-agent/dist/core/resource-loader.js'
NODE = r'''
import { DefaultResourceLoader } from MODULE;
const loader = new DefaultResourceLoader({cwd:process.cwd(),
 agentDir:process.env.HOME + '/.pi/agent', noExtensions:true,
 noThemes:true, noPromptTemplates:true, noContextFiles:true});
await loader.reload();
const result = loader.getSkills();
console.log(JSON.stringify(result.skills.filter(s => s.name !== 'routeur-skills')
 .map(s => ({name:s.name, description:s.description, path:s.filePath,
 explicitOnly:s.disableModelInvocation}))));
'''
SKILL = '''---
name: routeur-skills
description: "Cherche une skill specialisee dans le catalogue local. Documents, SEO, Android, audio ou autre metier absent du socle : recherche bornee a la demande, sans appel LLM."
---

# Chercher une skill a la demande

Origine : demande de USER du 2026-11-10, alleger Pi sans supprimer ses skills.

Le petit socle visible suffit pour les taches habituelles. Pour un metier absent,
chercher les skills disponibles avec cette commande, sans lire tout le catalogue :

```bash
python3 $HOME/.claude/outils/routeur-skills.py --chercher "conversion page"
```

Remplacer les mots par 2 a 5 termes du besoin. La sortie donne au plus 5 noms,
descriptions et chemins. Lire ensuite le SKILL.md pertinent avec read. Si aucun
resultat ne convient, reformuler la recherche ou travailler sans skill.

Les fichiers marques explicitOnly conservent leur restriction d'origine : ne pas
les charger automatiquement. USER peut les invoquer par `/skill:nom`. Les autres
sont simplement masques par le profil Pi, pas interdits. Toute regle de validation
(envoi, publication, achat, compte) reste applicable apres chargement.

Exemples de recherche : "test A/B", "conversion page", "SEO IA", "nom marque",
"pdf document", "Android APK", "audio transcription".
'''


def catalogue():
    source = NODE.replace('MODULE', json.dumps(MODULE.as_uri()), 1)
    result = subprocess.run(['node', '--input-type=module', '-e', source],
                            capture_output=True, text=True, timeout=20, check=True)
    return json.loads(result.stdout)


def normaliser(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower())
                   if not unicodedata.combining(c))


def chercher(skills, query, limite=5):
    terms = set(re.findall(r'[a-z0-9]+', normaliser(query)))
    terms -= {'de', 'des', 'du', 'le', 'la', 'les', 'un', 'une', 'pour', 'et'}
    scored = []
    for skill in skills:
        name = normaliser(skill['name'])
        text = normaliser(skill['description'])
        score = sum((8 if term in name else 0) + (2 if term in text else 0)
                    for term in terms)
        if normaliser(query).strip() == name:
            score += 100
        if score:
            scored.append((score, skill))
    scored.sort(key=lambda pair: (-pair[0], pair[1]['name']))
    return [skill for _, skill in scored[:limite]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--chercher')
    group.add_argument('--json', action='store_true')
    group.add_argument('--generer', action='store_true')
    parser.add_argument('--limite', type=int, choices=range(1, 11), default=5)
    args = parser.parse_args()
    if args.generer:
        SORTIE.parent.mkdir(parents=True, exist_ok=True)
        SORTIE.write_text(SKILL)
        print(f'Routeur ecrit : {SORTIE}')
        return
    skills = catalogue()
    if args.json:
        print(json.dumps(skills, ensure_ascii=False, indent=2))
        return
    results = chercher(skills, args.chercher, args.limite)
    for skill in results:
        label = ' [invocation explicite seulement]' if skill['explicitOnly'] else ''
        print(f"{skill['name']}{label}\n  {skill['description'][:500]}\n  {skill['path']}")
    if not results:
        print('Aucune skill correspondante. Reformuler les termes ou travailler sans skill.')


if __name__ == '__main__':
    main()
