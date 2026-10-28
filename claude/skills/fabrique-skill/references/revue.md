# Revoir une skill existante (ou tout le parc)

Sommaire :
- Ordre de la revue
- 1. La mesure
- 2. La structure
- 3. Le contenu
- 4. Le déclenchement
- 5. La décision
- Revue du parc entier

## Ordre de la revue

La mesure d'abord. Une skill bien écrite que personne ne charge ne vaut rien. Une skill moche chargée 40 fois par semaine mérite le soin en premier.

## 1. La mesure

```bash
python3 ~/.claude/outils/usage-skills.py 30              # chargements réels
python3 ~/.claude/outils/usage-skills.py 30 --rates      # mots tapés sans chargement
python3 ~/.claude/outils/usage-skills.py 30 --dormantes  # jamais chargées
python3 ~/.claude/outils/issue-skills.py 30 --exemples <nom>  # corrigée par USER ?
```

À noter pour chaque skill : chargements, % raté, % de sessions corrigées par USER.

## 2. La structure

```bash
python3 ~/.claude/skills/fabrique-skill/scripts/verifier-skill.py <dossier>
python3 ~/.claude/outils/audit-skills.py --perso
python3 ~/.claude/outils/parc_skills.py            # combien de skills, dont combien a USER
```

Le parc couvre 3 dossiers (`~/.claude/skills`, `~/.agents/skills`, `~/.hermes/skills`, sous-dossiers compris). Une skill est a USER quand elle ne vient d'aucune source tierce (manifestes Hermes et npx skills, historique git d'Hermes, `~/.claude/outils/skills-tierces.txt`), quelle que soit sa langue. Une skill tierce sans manifeste s'ajoute a `skills-tierces.txt`.

- YAML valide, `name` égal au dossier, champs connus.
- Accroche de 57 caractères lisible, mots de USER.
- Corps sous 500 lignes, sommaire au-delà de 100.
- Références à 1 niveau, fichiers cités présents.
- Côté Hermès : lien, pas copie (`ls -la ~/.hermes/skills/*/<nom>`).

## 3. Le contenu

- [ ] Les règles critiques sont-elles dans les 5 000 premiers tokens ?
- [ ] Chaque règle a-t-elle une origine datée ?
- [ ] Une règle périmée (outil retiré, chemin mort) traîne-t-elle ?
- [ ] La skill répète-t-elle ce qu'un modèle sait déjà ?
- [ ] Les corrections de USER relevées par `issue-skills.py` y sont-elles ?
- [ ] Une règle sans exception devrait-elle être un hook ?
- [ ] Une étape refaite à la main à chaque fois devrait-elle être un script ?

## 4. Le déclenchement

- **Raté** (`--rates` élevé) : ajouter les mots de USER à l'accroche et à `when_to_use`, puis à `declencheurs.json`.
- **Chargée à tort** : préciser la frontière « Pas pour … ».
- **Doublon** : 2 skills sur le même sujet. Comparer leurs descriptions côte à côte.
- Doute : test des 20 requêtes (référence « description », même dossier).

## 5. La décision

Une seule par skill, la plus forte :

| Constat | Décision |
|---|---|
| Chargée, peu corrigée, structure propre | **Garder** |
| Ratée ou chargée à tort | **Réécrire la description** |
| Corrigée souvent par USER | **Ajouter ses corrections** en tête, datées |
| 2 skills sur un même sujet | **Fusionner** dans la plus chargée |
| Dormante 30 jours, sujet arrêté | **Proposer de couper** (USER décide) |
| Règle sans exception | **Hook**, la skill la cite |

Rien ne se supprime sans le oui de USER. Une skill coupée passe d'abord par `skillOverrides: "off"`.

## Revue du parc entier

1. Lister les skills perso actives : `audit-skills.py --perso --json`.
2. Classer par chargements sur 30 jours.
3. Revoir les 10 plus chargées, puis les 10 plus ratées.
4. Rendre à USER un tableau : skill, chargements, % raté, % corrigé, décision.
5. Appliquer seulement les décisions qu'il valide.

Pour un parc de plus de 20 skills, confier la mesure et la structure à un sous-agent `sonnet` par lot de 10. Seul le tableau revient.
