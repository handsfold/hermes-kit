---
name: fabrique-skill
description: "Créer, revoir ou améliorer une skill : la bonne méthode. Fabrique une skill de qualité pour Claude Code, Hermès et Prime : intention tirée de la conversation, description qui déclenche, corps court, références à 1 niveau, scripts, essai avec et sans la skill, puis mesure (declencheurs.json, usage-skills, issue-skills). Sert aussi à auditer une skill qui ne se charge pas, se charge à tort ou que USER a dû corriger."
when_to_use: "USER dit « fais un skill », « crée une skill », « transforme ça en skill », « capitalise », « retiens la méthode pour la prochaine fois », « améliore la skill », « revois les skills », « pourquoi la skill ne s'est pas chargée », « review des skills ». Aussi après une manip réussie qu'il faudra refaire, même sans le mot skill. Pas pour exécuter une skill existante, ni pour une simple règle de mémoire."
argument-hint: "[nom-de-skill | revue <nom>]"
---

# Fabriquer une skill

Sommaire :
- Les 6 règles qui priment
- Étape 0 : skill, hook, script ou mémoire ?
- Étape 1 : capter l'intention
- Étape 2 : écrire la description
- Étape 3 : écrire le corps
- Étape 4 : le frontmatter
- Étape 5 : placer et brancher
- Étape 6 : tester
- Étape 7 : livrer et suivre
- Revoir une skill existante
- Checklist finale

## Les 6 règles qui priment

1. **Une skill dit ce que le modèle ignore.** Chemins, commandes qui marchent, corrections de USER, pièges vécus. Ce qu'un modèle sait déjà (« sois clair », « vérifie ton travail ») coûte des tokens à chaque chargement et ne change rien.
2. **La description décide du chargement.** Le modèle ne voit qu'elle avant de choisir. Un corps parfait derrière une description floue ne sert jamais.
3. **Une skill neuve ou modifiée se teste.** `scripts/verifier-skill.py` sans erreur, puis un essai réel avec et sans la skill. Sans écart mesuré, la skill n'apporte rien.
4. **Elle naît mesurée.** Entrée dans `~/.claude/outils/declencheurs.json`, suivie par `usage-skills.py` et `issue-skills.py` (règle de `methodes/tracage.md`).
5. **Chaque règle porte son origine.** « (retour de USER, 2026-10-07 : « … ») ». Une règle datée se défend et se retire quand elle périme.
6. **Français, aucun tiret long** (U+2013, U+2014), phrases courtes : USER relit ses skills.

## Étape 0 : skill, hook, script ou mémoire ?

Une skill est une consigne que le modèle **choisit** de suivre. Pour une règle qui doit tenir à chaque fois, ce choix est un risque.

| Le besoin | Le bon outil |
|---|---|
| Règle sans exception (refuser un envoi, une commande) | **Hook** dans `~/.claude/hooks/`, ou `hooks:` du frontmatter |
| Fait vrai dans toutes les sessions | Mémoire ou `CLAUDE.md` |
| Calcul ou commande répétée à l'identique | **Script** (`~/.claude/outils/`, `bin/`), que la skill cite |
| Méthode avec jugement, enchaînement d'étapes, savoir métier | **Skill** |
| Une skill couvre déjà le sujet | **L'améliorer.** 2 skills voisines se volent le déclenchement |

Chercher l'existante avant d'écrire : `ls ~/.claude/skills ~/.hermes/skills/*/` puis `grep -il "<mot>" ~/.claude/skills/*/SKILL.md`.

## Étape 1 : capter l'intention

La conversation contient souvent déjà la skill. L'extraire avant de questionner :

- les outils lancés et leur ordre, ce qui a échoué puis marché ;
- **les corrections de USER, mot pour mot, avec la date** : c'est le cœur de la skill ;
- le format de sortie qu'il a accepté ;
- les anciennes corrections sur le sujet : `fil cherche "<sujet>"` et `issue-skills.py --exemples <nom>`.

Poser une question seulement si 2 réponses changent le travail. Une à la fois.

## Étape 2 : écrire la description

Elle se lit dans 2 index qui coupent différemment :

- **Hermès** montre les **57 premiers caractères** (`skill_utils.py`, limite 60 avec « ... »). Il ignore `when_to_use`.
- **Claude Code** montre `description` + `when_to_use`, coupés à **1 536 caractères**.

D'où l'ordre fixe :

1. **Accroche de 57 caractères au plus** : les mots que USER tape, puis « : » et l'action. Ex. `Mots-clés, SEO, accroche, slogan, pub : étude chiffrée.`
2. **Ce que fait la skill**, à la 3e personne.
3. **Quand la charger** : les phrases réelles de USER entre « », dans `when_to_use`.
4. **Un peu insistante** : « même sans le mot X ». Les modèles sous-déclenchent.
5. **La frontière** : « Pas pour … (voir <autre-skill>) ».

`description` sous 500 caractères (seuil de `audit-skills.py`), 1 024 au plus. Entre guillemets dès qu'elle contient « : ». Exemples, contre-exemples et optimisation par 20 requêtes : `references/description.md`.

## Étape 3 : écrire le corps

- **Les règles critiques en tête.** Après compaction, seuls les 5 000 premiers tokens d'une skill restent en contexte.
- **100 à 200 lignes visées**, 500 au plus. Sommaire en tête au-delà de 100 lignes.
- **Le pourquoi en 1 ligne** plutôt que des MAJUSCULES. Un modèle qui comprend la raison couvre aussi les cas non écrits.
- **Degré de liberté selon la fragilité.** Opération fragile (base, paiement, envoi) : la commande exacte. Jugement : des principes.
- **Une option par défaut**, pas un menu. Une alternative seulement pour un cas nommé.
- **Un exemple concret** quand le format de sortie compte : entrée réelle, sortie attendue.
- **Flux à plusieurs étapes** : une checklist à cocher et une boucle « vérifier, corriger, recommencer ».
- **Références à 1 niveau** depuis `SKILL.md`, chacune avec quand la lire. Un renvoi de référence en référence se lit à moitié.
- **Scripts** pour le déterministe et le répété. Dire « lancer » ou « lire ». Le script gère ses erreurs, sans constante inexpliquée.
- **Rien de daté dans le texte courant** (« depuis août »). L'ancien va sous un titre « Ancienne méthode ».
- **Aucun secret en clair.** Le chemin du coffre ou `infisical run`, jamais la valeur.

Gabarit prêt : `assets/modele-SKILL.md`.

## Étape 4 : le frontmatter

`name` en `[a-z0-9-]`, 64 caractères au plus, égal au nom du dossier. Puis seulement les champs utiles :

- `disable-model-invocation: true` : action à effet de bord (envoi, déploiement, achat). USER la lance lui-même.
- `user-invocable: false` : savoir de fond, absent du menu `/`.
- `allowed-tools` : outils sans demande de permission pendant la skill.
- `context: fork` + `agent` + `model: sonnet` : tâche autonome lourde, qui n'a pas besoin de l'historique.
- `paths` : skill liée à certains fichiers.
- `argument-hint` : ce que USER tape après `/nom`.

Un champ inconnu est ignoré **sans erreur** par Claude Code. Tous les champs et leurs pièges : `references/frontmatter.md`.

## Étape 5 : placer et brancher

1. **Source unique** : `~/.claude/skills/<nom>/`.
2. **Hermès** : un lien, jamais une copie. `ln -s ~/.claude/skills/<nom> ~/.hermes/skills/<catégorie>/<nom>`. Une copie diverge (cas `coffre-identifiants`, 2 descriptions différentes).
3. **Prime**, si utile : `ln -s ~/.claude/skills/<nom> ~/.agents/skills/<nom>`.
4. **Skill propre à un projet** : `<projet>/.claude/skills/<nom>/`, sans lien Hermès.
5. **Mesure** : ajouter l'entrée à `~/.claude/outils/declencheurs.json`. `"forcer": true` seulement si un oubli coûte cher (argent, envoi, données) : le hook `skills-forcees.py` impose alors la skill.

## Étape 6 : tester

1. **Structure** : `python3 ~/.claude/skills/fabrique-skill/scripts/verifier-skill.py <dossier>`. Zéro erreur. Les avertissements se lisent un par un.
2. **Avec et sans** : 2 ou 3 tâches réalistes, chacune lancée par un sous-agent `sonnet` neuf avec la skill, puis sans. Comparer le résultat et le chemin suivi. Protocole : `references/evals.md`.
3. **Déclenchement** : 10 requêtes qui doivent charger, 10 « presque » qui ne doivent pas. `scripts/tester-declenchement.py <dossier>` (jamais `run_eval`, qui rend 0 sur hote-1). Détail : `references/description.md`.
4. **Lire les transcripts**, pas seulement le résultat. Une étape que tous les essais refont à la main devient un script.

## Étape 7 : livrer et suivre

- Dire à USER : le nom, les phrases qui la déclenchent, l'écart avec et sans en 1 ligne.
- 7 jours après : `usage-skills.py 7 --rates` et `issue-skills.py 7 --exemples <nom>`.
- USER corrige pendant l'usage : patcher la skill tout de suite, règle datée.

## Revoir une skill existante

La mesure d'abord, la lecture ensuite. Grille complète et décisions (garder, fusionner, réécrire la description, couper) : `references/revue.md`.

## Checklist finale

```
- [ ] Étape 0 faite : ni hook, ni script, ni doublon d'une skill existante
- [ ] Accroche de 57 caractères au plus, avec les mots de USER
- [ ] when_to_use cite ses phrases réelles, et la frontière avec la skill voisine
- [ ] Règles critiques en tête, chacune datée avec son origine
- [ ] verifier-skill.py : 0 erreur
- [ ] Essai avec et sans : écart constaté et noté
- [ ] Lien Hermès créé, entrée declencheurs.json ajoutée
- [ ] grep -rP '[\x{2013}\x{2014}]' sur le dossier : vide
```
