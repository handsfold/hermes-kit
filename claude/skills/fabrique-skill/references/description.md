# La description : faire charger la skill au bon moment

Sommaire :
- Comment le modèle choisit
- Anatomie
- Bonnes et mauvaises descriptions
- Tester le déclenchement : 20 requêtes
- Optimiser automatiquement : run_loop
- Après le test

## Comment le modèle choisit

- Le modèle voit la liste des skills : nom et description. Il charge une skill s'il pense en avoir besoin.
- **Une tâche simple en 1 étape ne charge rien**, même avec une description parfaite. Le modèle s'en croit capable seul.
- Le listing Claude a un budget d'environ 1 % du contexte. Quand il déborde, les descriptions des skills peu utilisées sont raccourcies en premier.
- Côté Hermès, seuls les 57 premiers caractères comptent.
- Les modèles **sous-déclenchent** : une description un peu insistante corrige ce biais.

## Anatomie

```yaml
description: "<Accroche de 57 car. au plus : mots de USER : action.> <Ce que fait la skill, 3e personne.> <Ce qu'elle garantit.>"
when_to_use: "USER dit « … », « … ». Aussi quand <situation sans le mot-clé>. Pas pour <voisin> (voir <autre-skill>)."
```

- **Les mots de USER**, pas ceux du domaine. Il dit « mon navigateur », pas « session CDP ».
- **Le cas d'usage clé en premier.** Le listing coupe la fin.
- **3e personne** : « Fabrique… », pas « Je fabrique… » ni « Tu fabriques… ».
- **La frontière** avec la skill voisine évite que 2 skills se volent le déclenchement.

## Bonnes et mauvaises descriptions

Bonnes (accroches réelles du parc) :

- `Mots-clés, SEO, accroche, slogan, pub : étude chiffrée.` : les mots tapés, puis l'action.
- `« Je t'avais dit… » : retrouver un ancien échange.` : la phrase même de USER.
- `1688, Alibaba, usine, sourcing : trouver fournisseurs.`

Mauvaises :

- `Helps with documents.` : vague, aucun mot déclencheur.
- `Skill pour gérer les mails de façon efficace et professionnelle.` : 57 caractères dépensés sans mot que USER tape.
- `Use when…` en anglais pour une skill que USER appelle en français : le rapprochement se fait mal.

## Tester le déclenchement : 20 requêtes

Écrire un fichier `evals/declenchement.json` dans le dossier de la skill :

```json
[
  {"query": "transforme ce qu'on vient de faire pour le Watsons en skill, que la prochaine session le refasse seule", "should_trigger": true},
  {"query": "lance la skill etude-marketing sur le slogan MARQUE-E", "should_trigger": false}
]
```

- **8 à 10 doivent charger** : formulations variées, formelles et orales, fautes de frappe, sans le mot-clé, cas rares.
- **8 à 10 « presque »** : mêmes mots, autre besoin. Une requête hors sujet évidente ne teste rien.
- **Réalistes et détaillées** : un nom de fichier, un client, un chiffre, un bout d'histoire. Comme USER dicte.

Lancer le script de la skill (8 requêtes en parallèle, depuis un dossier vide) :

```bash
python3 ~/.claude/skills/fabrique-skill/scripts/tester-declenchement.py <dossier-skill> --fois 1
```

Il lit le 1er appel d'outil de chaque session `claude -p`. Résultat vécu le 2026-10-24 sur fabrique-skill : 8/8.

Deux pièges vus ce jour-là :

- **`run_eval` du skill-creator rend 0 partout sur hote-1**, même quand le modèle charge la skill. Ne pas s'y fier.
- **Lancé depuis `~`, claude-mem injecte le travail du jour** : le modèle le prend pour des tâches. 2 faux positifs sur 3. Toujours un dossier vide.

## Optimiser automatiquement : run_loop

À éviter tant que `run_eval` rend 0 (il en dépend). Réécrire la description à la main, puis relancer le script.

```bash
cd "$SC" && python3 -m scripts.run_loop \
  --eval-set <dossier-skill>/evals/declenchement.json \
  --skill-path <dossier-skill> --model claude-sonnet-4-6 \
  --max-iterations 5 --results-dir <dossier-skill>/evals/ --report none --verbose
```

- Coupe le jeu en 60 % entraînement, 40 % test.
- Propose une description, la mesure, recommence.
- Rend `best_description`, choisie sur le score **de test** pour éviter le sur-apprentissage.
- Vérifier ensuite que l'accroche de 57 caractères a survécu : la boucle ignore la contrainte Hermès.

## Après le test

- Montrer à USER l'avant, l'après et les 2 scores.
- Ajouter les motifs qui ont raté dans `declencheurs.json`.
- Un raté qui coûte cher (envoi, argent, données) : `"forcer": true`.
