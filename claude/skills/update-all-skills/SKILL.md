---
name: update-all-skills
description: "Mets à jour mes skills, update all : tout actualiser. Met à jour d'un coup toutes les sources de skills installées (gstack, skills npx de ~/.agents/skills, plugins Claude Code et leurs marketplaces)."
when_to_use: "L'utilisateur dit « mets à jour mes skills », « update all skills », « update everything », « tout mettre à jour »."
allowed-tools: Bash
---

# /update-all-skills

Met à jour toutes les sources de skills en une passe :

1. **gstack** : dépôt git global `~/.claude/skills/gstack` (fetch + reset + `./setup`, qui régénère aussi les ~50 skills liés comme `/ship`, `/qa`, `/autoplan`), puis les migrations de version et le marqueur `~/.gstack/just-upgraded-from`.
2. **Skills npx** : `npx skills update` pour tout ce qui vit dans `~/.agents/skills` (find-skills, opencli-*, smart-search, etc.). Puis la **remise au format USER** : `mettre-au-format.py --tout` (skill `trouver-skill`) rejoue l'en-tête français et les retouches de chaque skill du lock, que la mise à jour vient d'écraser.
3. **Plugins Claude Code** : `claude plugin marketplace update` (toutes les marketplaces), puis `claude plugin update` pour chaque plugin de `~/.claude/plugins/installed_plugins.json`.

## Étapes

### 1. Lancer le script

```bash
bash ~/.claude/skills/update-all-skills/scripts/update-all.sh
```

Utiliser un timeout large (600000 ms) : la mise à jour gstack rebuild des binaires et la boucle plugins fait un appel réseau par plugin.

### 2. Résumer pour l'utilisateur

À partir de la sortie du script, produire un résumé court :

- **gstack** : ancienne → nouvelle version, ou « déjà à jour ». Si la version a changé, lire `~/.claude/skills/gstack/CHANGELOG.md` et résumer les entrées entre les deux versions en 3 à 5 puces orientées utilisateur.
- **Skills npx** : combien mis à jour / déjà à jour.
- **Remise au format** : la section « remise au format USER » liste chaque skill du lock avec `ok` ou `ERREUR`. Dire en une ligne combien sont `ok` et lesquelles restent en erreur. Erreurs connues : `opencli-browser` (corps de plus de 500 lignes), `last30days` (tirets longs dans du code tiers, volontairement non touché).
- **Plugins** : lesquels ont changé de version, lesquels ont échoué (avec la raison en une ligne).
- **Skills orphelins** : la section « Skills sans source de mise à jour » liste les dossiers copiés à la main dans `~/.claude/skills` qui ne peuvent pas être mis à jour automatiquement. Les mentionner en une ligne, sans détailler, sauf si l'utilisateur demande.

### 3. Rappels de fin

- Si des plugins ont été mis à jour : rappeler qu'un **redémarrage de Claude Code** est nécessaire pour les charger.
- Si le script signale `ECHEC` quelque part : proposer de diagnostiquer, ne pas masquer l'erreur.

## Notes

- Le script est volontairement tolérant : une section en échec n'empêche pas les suivantes de tourner.
- Ne jamais mettre à jour un skill orphelin en le réécrivant soi-même : signaler seulement qu'il n'a pas de source.
- La remise au format n'écrit que le frontmatter, les tirets des `.md` et `.txt`, et le sommaire. Elle ne touche jamais au code tiers (décision de USER, 2026-10-25). `find-skills` est exclue : tierce, à ne pas modifier.
