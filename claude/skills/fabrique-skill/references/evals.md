# Essais : prouver que la skill change le résultat

Sommaire :
- Le principe
- Protocole court (toute skill)
- Protocole banc (skill qui compte)
- Comparaison à l'aveugle
- Lire les résultats

## Le principe

Une skill se juge à l'**écart** entre une session qui l'a et une session qui ne l'a pas. Sans écart, elle coûte des tokens pour rien. Le score seul ment : le transcript dit si le modèle a suivi le bon chemin.

Exemple vécu (banc `entreprise-a-index`, 2026-10-05) : sans la skill, Haiku trouvait la réponse 19 fois sur 20, mais en balayant le drive 12 fois. Le résultat était juste, le chemin était mauvais.

## Protocole court (toute skill)

1. Écrire 2 ou 3 tâches que USER pourrait vraiment demander, avec ses mots.
2. Pour chaque tâche, lancer 2 sous-agents `sonnet` dans le même message :
   - **avec** : « Lis `~/.claude/skills/<nom>/SKILL.md` et suis-la. Tâche : … »
   - **sans** : la même tâche, avec « N'utilise aucune skill ».
3. Demander à chacun un rendu court : résultat, commandes lancées, fichiers lus.
4. Comparer sur 3 axes : résultat juste, chemin attendu, coût (nombre d'appels).
5. Noter l'écart en 1 ligne dans le rapport à USER.

Si la tâche a un effet externe (envoi, achat, publication), l'essai s'arrête au brouillon.

## Protocole banc (skill qui compte)

Pour une skill souvent chargée ou qui touche l'argent, reprendre le banc existant :

- Dossier : `~/Bureau/Projets/perso/agent/bancs/skill-bench/` (`CONSIGNE.md`, `lancer.py`, `noter.py`, `agreger.py`).
- Questions tirées de données réelles, notées **par script**, sans juge LLM.
- Croiser 3 modèles (haiku, sonnet, opus), avec et sans skill.
- Résultat consigné en bas de la skill, daté (modèle : section « Quel modèle » de `entreprise-a-index`).

Couper la skill pour la branche « sans » : `skillOverrides` à `"off"` dans `~/.claude/settings.json` pendant l'essai, ou une session `claude -p` lancée hors du dossier. Remettre le réglage après.

## Comparaison à l'aveugle

Pour trancher entre 2 versions d'une skill, les agents du skill-creator servent tels quels :

- `agents/comparator.md` : un juge reçoit 2 sorties A et B sans savoir laquelle vient de quelle version.
- `agents/analyzer.md` : explique pourquoi la gagnante gagne.
- `agents/grader.md` : note une sortie contre des attentes écrites.

Chemin : `~/.claude/skills/synced/3135e31b-59bc-41e9-9028-b843018f51f7_4ee36d21-2703-4398-b0ac-6af22175b5ff/skill-creator/agents/`.

Les lancer en sous-agent `sonnet` avec le contenu du fichier en consigne.

## Lire les résultats

- **Tous les essais réécrivent le même bout de code** : il devient un script dans `scripts/`.
- **Le modèle hésite ou relit 2 fois une référence** : la consigne est ambiguë, la réécrire.
- **Le modèle ignore une section** : elle ne sert pas, la couper.
- **Écart nul** sur les 3 tâches : la skill dit ce que le modèle sait déjà. La réduire aux corrections de USER, ou la retirer.
- Itération suivante dans `evals/iteration-N/` : garder les anciennes pour comparer.
