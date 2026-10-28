---
name: retro-agent
description: "Fais la rétro, où tu t'es planté : bilan de l'agent. Rétrospective hebdomadaire de l'agent Hermès sur ses propres sessions : répétitions imposées à USER, boucles d'outils stériles, échecs récurrents. Produit un rapport court et applique les corrections (mémoire, skills, contexte)."
when_to_use: "USER dit « fais la rétro », « où tu t'es planté », ou par le cron hebdomadaire. Pas pour analyser le code d'un projet."
version: 2.0.0
metadata:
  hermes:
    tags: [meta, qualite, retrospective, auto-amelioration]
    related_skills: [verifier-avant-livraison, r]
---

# Rétro agent : apprendre de ses propres sessions

Sommaire :
- 0. Deux cadences, deux objets
- 0bis. Le principe
- 1. Extraire les signaux (déterministe, 0 token)
- 1bis. Contrôle hebdo des skills corrigées par USER
- 2. Lire les 2-3 sessions les plus chaudes
- 3. Qualifier chaque friction
- 3bis. Le test du levier : la question la plus importante
- 4. Appliquer les corrections : obligatoire
- 5. Journaliser
- 6. Livrer à USER
- Pièges

L'agent lit ses transcripts de la semaine, trouve **où USER a dû reprendre la main**,
et transforme chaque friction en correction durable. Un rapport qui ne change rien
au système est un rapport raté : la sortie utile, c'est le diff.

## 0. Deux cadences, deux objets

| Passe | Quand | Fenêtre | Objet |
|---|---|---|---|
| **Friction** | tous les lundis 8h47 (`fe10c91539e7`) | 7 jours | corriger les règles, patcher les skills |
| **Levier** | le 3 de chaque mois 9h23 (`090d2e809470`) | 30 jours | ajouter une capacité : §3bis uniquement |

La semaine est la bonne maille pour attraper une friction avant qu'elle
devienne une habitude. Elle est **trop courte pour un levier** : il faut du
recul pour voir qu'un manque revient, et un chantier d'infra par semaine ne
se finit jamais. D'où la passe mensuelle, qui ne patche rien et ne fait que
chercher la capacité absente.

## 0bis. Le principe

Le signal le plus précieux n'est pas l'erreur technique : c'est **la répétition
humaine**. Chaque fois que USER redemande, reformule ou relance, l'agent a coûté un
tour de trop. C'est ça qu'on chasse, pas les tracebacks.

## 1. Extraire les signaux (déterministe, 0 token)

```bash
python3 ~/.hermes/scripts/retro-extract.py --jours 7 > /tmp/retro.json
```

Ne jamais lire les sessions à la main en premier : le script fait le tri.
Il renvoie, par session, un `score_friction` et le détail :

- `frictions` : les messages de USER classés : *repetition, echec, correction,
  relance, agacement, verification*
- `boucles` : même outil appelé ≥ 4 fois d'affilée : signe d'acharnement
- `outils_en_erreur` : échecs francs seulement (pas le mot « error » en passant)
- `tours_agent` vs `tours_user` : un ratio > 15 sur une tâche simple est suspect

Options : `--jours N` (fenêtre), `--min-score N` (seuil de sélection).

## 1bis. Contrôle hebdo des skills corrigées par USER

Même passe du lundi, 0 token, deux commandes :

```bash
~/.claude/outils/issue-skills.py 7
~/.claude/outils/usage-skills.py 7 --rates
```

Toute skill **corrigée par USER dans plus de 25 % des sessions suivies** (3 sessions
suivies au moins) se traite comme suit :

1. `~/.claude/outils/issue-skills.py 30 --exemples <skill>` : lire les corrections et
   **remonter au contexte** (la session est dans `~/.claude/projects/`). Beaucoup de
   corrections sont du bruit (la skill était chargée, la correction portait sur autre chose) :
   ne retenir que celles qu'une règle de la skill aurait évitées.
2. Chercher le motif : règle absente, ambiguë, ou présente mais trop bas dans le fichier.
3. Trouver la vraie source (`readlink -f`). **Sauvegarder le dossier avant toute modif** :
   `/tmp/skills-avant-retours/<skill>/`.
4. Corriger la source, règles courtes et datées, en tête de la section concernée, sans
   doublon. Un paquet tiers (ex. `opencli-browser`, npm `@jackwener/opencli`) ne se modifie
   pas : écrire un fichier à nous (ex. `opencli-browser-poste`) et dire où il est appelé.
5. Vérifier : `~/.claude/outils/audit-skills.py --perso` reste à « 0 avec au moins un
   ecart ».

Ces corrections comptent dans la limite de 3 du §4.
`~/.claude/outils/controle-skills.py` (timer systemd, lundi 8 h) dépose déjà l'alerte au
QG : cette étape est le traitement, pas la détection.

## 2. Lire les 2-3 sessions les plus chaudes

Depuis le 14/09/2026, Hermes n'écrit plus de `.jsonl` : tout est dans
`~/.hermes/state.db`. Le champ `fichier` vaut `db:<session_id> [source/topic] titre`.

```bash
python3 - <<'PY'
import sqlite3
con = sqlite3.connect("file:$HOME/.hermes/state.db?mode=ro", uri=True)
for r, c in con.execute("select role, substr(replace(content,char(10),' '),1,300) "
    "from messages where session_id=? and role in ('user','assistant') and content<>'' "
    "order by id", ("<session_id>",)):
    print(f"{r}: {c}")
PY
```

Pour une friction précise, lire les 2 messages qui la précèdent (`id <= ?`,
`order by id desc limit 3`) : c'est là que se voit la promesse non tenue.

Se limiter à 3 sessions maximum. Au-delà, le contexte explose et l'analyse
se dilue : mieux vaut trois causes racines qu'une liste de vingt symptômes.

## 3. Qualifier chaque friction

Pour chaque point chaud, répondre à trois questions, dans cet ordre :

1. **Qu'est-ce que USER voulait vraiment ?** (souvent plus court que ce qui a été fait)
2. **Au bout de combien de tours l'agent aurait-il dû pivoter ?** Nommer le tour exact.
3. **Quelle règle aurait évité ça ?** Elle doit tenir en une phrase impérative.
4. **Une règle suffit-elle ?** Si la friction vient de ce que l'agent *ne pouvait
   pas* faire mieux avec les outils qu'il a, passer directement au §3bis.

Puis classer la cause dans une de ces cinq familles : le classement détermine
le correctif :

| Famille | Symptôme typique | Où corriger |
|---|---|---|
| **Persévération** | 10 tours sur une voie sans issue | Skill du domaine : ajouter une règle de pivot chiffrée |
| **Livraison non vérifiée** | « c'est fait » puis USER constate le contraire | `dev/verifier-avant-livraison` |
| **Connaissance manquante** | l'agent a re-cherché un fait déjà connu | `memory` ou fiche `~/contexte/` |
| **Outil mal utilisé** | mêmes erreurs d'appel qui se répètent | Skill de l'outil, section Pièges |
| **Malentendu de cadrage** | l'agent a répondu à côté | `SOUL.md` ou skill de style |
| **Capacité manquante** | l'agent a bien joué, avec de mauvais outils | **Nouvel outil** : voir §3bis |

La dernière famille est la plus rentable et la plus facile à rater : rien n'a
« bugué », l'agent a simplement fait de son mieux dans un espace trop étroit.

## 3bis. Le test du levier : la question la plus importante

Avant d'écrire la moindre règle, poser cette question sur l'ensemble des
frictions de la semaine, pas une par une :

> **Existe-t-il une capacité que l'agent n'a pas, et dont l'ajout rendrait
> plusieurs de ces frictions structurellement impossibles ?**

Si oui, c'est ça le livrable de la rétro. Les règles de pivot attendront.

**Pourquoi cette règle existe.** À la première rétro (août 2026), l'agent a
produit trois patchs de skills honnêtes : règle de pivot, mémoire compactée,
routage signalé. Utile, marginal. Le vrai problème était que l'agent cherchait
avec un seul moteur, indexé et censuré. Brancher SearXNG, Tor, l'archivage et
les réseaux sociaux a démultiplié ce qu'il peut trouver : sans toucher une
seule règle de comportement. **Une capacité nouvelle vaut plus que dix
optimisations de l'existant.** USER a dû le dire lui-même : c'est cet oubli-là
que la présente section corrige.

### Comment le chercher

1. **Regrouper les frictions par ce qui manquait**, pas par ce qui a raté.
   Trois échecs différents qui butent tous sur « je n'ai pas accès à X »
   forment un seul levier, pas trois correctifs.
2. **Reformuler chaque friction en manque de capacité.** « L'agent s'acharne
   à chercher » → « l'agent n'a qu'un canal de recherche ». « L'agent devine
   l'état d'un service » → « l'agent n'a pas de sonde ». « USER doit rappeler
   le contexte » → « l'agent n'a pas de mémoire de projet ».
3. **Chercher l'outil qui existe déjà dehors.** Utiliser `recherche` et
   `agent-reach-hermes` : ce manque est presque toujours résolu par un CLI, un MCP,
   une API ou une skill publique. Ne pas concevoir avant d'avoir cherché.
4. **Estimer la démultiplication.** Un levier valide n'améliore pas une tâche :
   il ouvre une classe de tâches. Si le gain se chiffre en « un peu mieux »,
   ce n'est pas un levier, c'est une optimisation : elle repasse en §4.
5. **Le construire et le tester en vrai**, dans la rétro même. Une capacité
   annoncée mais non branchée ne compte pas.

### Les axes où chercher, par ordre de rendement observé

- **Perception** : ce que l'agent peut voir : moteurs, index, archives,
  sources fermées, capteurs, journaux, écrans.
- **Action** : ce qu'il peut faire : navigateur piloté, machines distantes,
  appareils, API en écriture.
- **Mémoire** : ce qu'il retient : fiches contexte, index de sessions, corpus.
- **Calcul** : ce qu'il peut lancer : GPU, exécution parallèle, sous-agents.
- **Vérification** : ce qu'il peut prouver : tests, sondes, captures d'écran.

### Garde-fou

Un levier ne dispense pas de la discipline : il s'installe, se teste, se
documente dans la skill concernée et se commite. Une capacité ajoutée mais
non câblée dans une skill n'existe pas : l'agent ne la retrouvera pas.
Et **maximum un levier par rétro** : deux chantiers d'infra la même semaine,
aucun des deux n'est fini.

## 4. Appliquer les corrections : obligatoire

Une rétro produit **au moins un changement écrit**. Par ordre de préférence -
et le levier du §3bis passe avant tout le reste :

- **Installer et câbler la capacité manquante** identifiée au §3bis, si elle existe.

- **Patcher une skill existante** (`skill_manage action=patch`) : ajouter le piège
  découvert à sa section « Pièges ». C'est le correctif le plus durable.
- **Créer une skill** seulement si le sujet est nouveau et reviendra.
- **Écrire un fait en mémoire** si c'est un état du monde, pas une procédure.
  Fait déclaratif, jamais un impératif.
- **Mettre à jour `~/contexte/`** si c'est un ancrage infra (chemin, port, machine).

Règle de proportion : **maximum 3 corrections par rétro**. Une règle qu'on
n'applique pas vaut moins que pas de règle : la dilution tue l'adhérence.

## 5. Journaliser

Ajouter le compte rendu dans `~/.hermes/retro/JOURNAL.md`, en tête de fichier :

```markdown
## Semaine du <date> : score <total>

- **Angle mort** : <une phrase>
- **Cause** : <famille> : <où exactement>
- **Corrigé** : <fichier patché ou fait mémorisé>
- **Levier** : <capacité ajoutée, ou « aucun : pas de manque structurel »>
- **À surveiller** : <ce qui devrait baisser la semaine prochaine>
```

Puis, en fin de rapport, **comparer avec la semaine précédente** : les frictions
d'il y a une semaine ont-elles disparu ? Si une même cause revient trois rétros
de suite, c'est que le correctif est au mauvais endroit : le remonter d'un cran
(d'une skill vers `SOUL.md`, d'un fait mémoire vers une fiche contexte).

## 6. Livrer à USER

Message Telegram court, format imposé : la réponse d'abord, le détail ensuite :

```
Rétro semaine : <N> frictions, <M> sessions analysées.

**L'angle mort** : <une phrase>

**Levier** : <capacité ajoutée et testée, ou rien>

- <correction 1 appliquée>
- <correction 2 appliquée>

Tendance : <en baisse / stable / en hausse> vs semaine dernière.
```

Pas de tableau, pas de préambule, pas de liste de vingt points. Si la semaine
est propre, le dire en deux lignes et s'arrêter là.

## Pièges

- **Ne pas confondre volume et problème.** Une session à 200 appels d'outils
  peut être saine ; une session à 12 tours où USER répète trois fois ne l'est pas.
- **Le script ne juge pas, il compte.** Un `score_friction` élevé sur une session
  d'exploration voulue est un faux positif : vérifier le contexte avant d'accuser.
- **Ne jamais réécrire une skill en entier** sur la base d'une seule session.
  Patcher, ajouter un piège, c'est tout.
- **Les sessions du jour même sont incomplètes.** Une conversation encore ouverte
  peut voir sa friction résolue dans l'heure : ne pas la compter comme un échec.
- **Le piège principal : la rétro paresseuse.** Patcher trois skills est facile,
  visible et presque toujours insuffisant. Si la rétro ne contient aucune
  recherche de levier, elle est incomplète : même si les patchs sont bons.
- **Un levier n'est pas une lubie.** Il doit sortir d'une friction réelle et
  datée du journal, pas d'une envie d'installer un outil à la mode.
- **`sessions_analysees: 0` n'est jamais une semaine propre.** Le 28/09/2026
  le script rendait 0 session depuis 2 semaines : il lisait un dossier de `.jsonl`
  figé depuis le passage à `state.db`. 684 messages de USER étaient invisibles.
  Avant de répondre `[SILENT]`, compter les messages `user` de la semaine dans
  `state.db` : s'il y en a, c'est l'extracteur qui est cassé.
- **Ne pas mémoriser le contenu des tâches** (« a téléchargé la saison 3 »).
  On mémorise des règles et des états stables, pas un journal d'activité.
