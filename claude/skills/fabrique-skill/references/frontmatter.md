# Frontmatter : tous les champs et leurs pièges

Sommaire :
- Lecture du frontmatter
- Champs Claude Code
- Champs Hermès
- Combinaisons utiles
- Pièges vécus

## Lecture du frontmatter

- Lu seulement si `---` ouvre la **1re ligne**, sans ligne vide ni BOM avant.
- YAML cassé : Claude Code charge le corps **sans** métadonnées. La skill existe, mais ne se déclenche plus.
- Un « : » suivi d'un espace dans une valeur casse le YAML. Mettre la valeur entre guillemets, ou utiliser `>-`.
- Booléens acceptés : `true`, `false`, `yes`, `no`, `on`, `off`, `1`, `0`.
- Champ inconnu : ignoré **sans erreur**. Une faute de frappe (`disable-model-invokation`) passe inaperçue. `scripts/verifier-skill.py` la signale.

## Champs Claude Code

| Champ | Quand l'utiliser |
|---|---|
| `name` | Toujours. `[a-z0-9-]`, 64 caractères au plus, égal au dossier. Sans « anthropic » ni « claude » |
| `description` | Toujours. 3e personne, quoi et quand, 1 024 caractères au plus |
| `when_to_use` | Phrases déclencheuses. Ajouté à `description` dans le listing, plafond commun 1 536 |
| `argument-hint` | Indice affiché après `/nom`, ex. `[url]` |
| `arguments` | Noms d'arguments pour `$nom` dans le corps |
| `disable-model-invocation` | `true` : seul USER la lance. La description sort du contexte. Pour envoi, déploiement, achat |
| `user-invocable` | `false` : absente du menu `/`. Savoir de fond seulement |
| `allowed-tools` | Outils permis sans demande pendant la skill, ex. `Bash(git:*) Read` |
| `disallowed-tools` | Outils interdits pendant la skill |
| `model` | Modèle imposé pendant la skill (`sonnet`, `haiku`, `opus`) |
| `effort` | `low` à `max` |
| `context` | `fork` : la skill tourne dans un sous-agent, sans l'historique |
| `agent` | Type de sous-agent avec `context: fork` (défaut `general-purpose`) |
| `background` | Avec `fork`, défaut `true`. Mettre `false` si la skill a besoin d'outils réduits en arrière-plan |
| `hooks` | Hooks actifs seulement pendant la skill |
| `paths` | Globs : la skill ne s'active que sur ces fichiers |
| `shell` | `bash` (défaut) ou `powershell` pour les blocs `` !`commande` `` |
| `license`, `compatibility`, `metadata` | Informatifs |

## Champs Hermès

Hermès lit `name`, `description`, et en option `version`, `author`, `license`, `platforms`, `metadata.hermes.tags`, `metadata.hermes.related_skills`.

- Il **ignore** `when_to_use` : tout ce qui doit déclencher côté Hermès tient dans les 57 premiers caractères de `description`.
- Les champs Claude (`context`, `allowed-tools`...) ne gênent pas Hermès : il les ignore.
- Validateur Hermès : `tools/skill_manager_tool.py::_validate_frontmatter` (1re ligne `---`, `name` et `description` présents, corps non vide).

## Combinaisons utiles

| Cas | Frontmatter |
|---|---|
| Méthode métier, déclenchée seule | `name`, `description`, `when_to_use` |
| Action risquée lancée par USER | + `disable-model-invocation: true`, `argument-hint` |
| Tâche lourde autonome | + `context: fork`, `agent: general-purpose`, `model: sonnet` |
| Règles d'un type de fichier | + `paths: ["**/*.sql"]` |
| Savoir préchargé dans un sous-agent | + `user-invocable: false` |

## Pièges vécus

- `context: fork` : le sous-agent ne voit ni la conversation ni les corrections de USER. Les agents `Explore` et `Plan` démarrent même sans `CLAUDE.md`. Ne pas l'utiliser pour une skill qui dépend du contexte du tour.
- `skillOverrides` ne coupe pas les skills de plugin : parade `~/.claude/hooks/plugins-skills-off.py` (`methodes/claude-code.md`).
- `quick_validate.py` du skill-creator refuse `when_to_use`, `paths` et d'autres champs valides : ne pas s'en servir comme barrière. Utiliser `scripts/verifier-skill.py`.
