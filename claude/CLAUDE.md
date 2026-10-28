# Claude Code : bonnes pratiques globales

Reusable patterns and references. Adapted from `shanraisshan/claude-code-best-practice`.

## Les tirets longs sont interdits partout : règle ferme

**Aucun tiret cadratin `-` (U+2014), aucun tiret demi-cadratin `-` (U+2013)**,
nulle part. Ni dans une réponse de chat, ni dans un commentaire de code, ni dans
une docstring, ni dans une chaîne de caractères, ni dans un message de commit,
ni dans un fichier Markdown, ni dans une page HTML, ni dans le corps d'un email,
ni dans un texte d'interface. Aucune exception, aucun projet, aucune langue.

Seul le trait d'union du clavier `-` (U+002D) est autorisé.

Ce qui les remplace, selon ce que le tiret faisait :

| Il servait à | Écrire |
|---|---|
| Introduire une explication | `:` |
| Séparer deux idées | `.` ou `,` |
| Marquer une incise | `(` `)` ou deux virgules |
| Séparer des éléments d'une liste en ligne | `·` |
| Joindre deux mots ou deux nombres | `-` |

Cela vaut aussi pour le texte **existant** : quand un fichier est ouvert pour
une autre raison et qu'il en contient, les corriger au passage.

Contrôle : `grep -rP '[\x{2013}\x{2014}]'` doit ne rien renvoyer.

## Context Delegation (token economy)

Mesuré le 2026-07-31 : un tour de session principale relit **~184k de contexte** (67 % des appels > 150k). Un tour de sous-agent repart d'un contexte neuf (~20k). Le coût dominant est la **relecture**, pas la production.

- **Déléguer toute exploration large** à un sous-agent `Explore` : localiser du code, lister les usages d'un symbole, cartographier un module, balayer plusieurs conventions de nommage. Seul le résultat revient dans le contexte principal.
- **Ne pas déléguer** une lecture ciblée dont le fichier est déjà connu, ni une vérification en une commande : l'aller-retour coûte plus que le gain.
- **Ne jamais doubler** une délégation par la même recherche en direct : attendre le résultat du sous-agent.
- Lancer les sous-agents indépendants **dans un seul message** pour qu'ils tournent en parallèle.

@RTK.md


## Outils d'analyse deja ecrits : les lancer, ne pas les reecrire

`~/.claude/outils/` contient les analyses deja faites (conso par topic, modele, skill, cache, sorties d'outils, aiguilleur, usage et issue des skills, controles). **Avant toute analyse de logs, de tokens, de couts ou de skills : lire `~/.claude/outils/OUTILS.md`** (tableau complet, et `supertool` pour grouper plusieurs lectures en un appel). Un hook refuse la commande qui refait un outil existant. Un outil qui ne couvre pas le besoin se modifie, un nouvel outil s'ajoute a `OUTILS.md`.
