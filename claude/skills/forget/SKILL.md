---
name: forget
description: "Oublie X, efface de ta mémoire : oubli durable. Efface durablement de la mémoire de Claude ce que l'utilisateur demande d'oublier : mémoire fichier (MEMORY.md + fichiers) et observations/summaries claude-mem."
when_to_use: "L'utilisateur dit « oublie X », « supprime X de ta mémoire », « ne te rappelle plus de X », « efface ce qu'on a fait sur X »."
argument-hint: [sujet ou mot-clé à oublier]
allowed-tools: Bash(~/.claude/skills/forget/forget-mem.sh:*), Read, Edit, Grep, Glob
---

# /forget : Oublier durablement un sujet

Objectif : que le sujet demandé disparaisse des DEUX mémoires, de sorte qu'il ne
réapparaisse ni si l'utilisateur le redemande, ni au redémarrage d'une session.

Les deux mémoires concernées :
1. **Mémoire fichier** : `~/.claude/projects/-home-poste/memory/` : un `MEMORY.md`
   (index, une ligne par fait) + un fichier `.md` par fait.
2. **claude-mem** : base SQLite `~/.claude-mem/claude-mem.db` : tables
   `observations` (IDs numériques type `18356`) et `session_summaries` (les `S…`).
   Les triggers FTS nettoient l'index de recherche tout seuls au `DELETE`.

Un script helper fait la recherche et les suppressions SQL en sécurité :
`~/.claude/skills/forget/forget-mem.sh`.

## Workflow : TOUJOURS confirmer avant de supprimer

### Étape 1 : Rechercher
Lance la recherche avec le sujet fourni en argument (`$ARGUMENTS`) :

```bash
~/.claude/skills/forget/forget-mem.sh search "<sujet>"
```

Cela liste, pour les deux mémoires : les fichiers `.md` concernés, les lignes de
`MEMORY.md`, les `observations` (id/projet/titre) et les `session_summaries`.

Si la recherche renvoie peu ou trop de résultats, ajuste le terme (essaie un
mot-clé plus court ou une variante) et relance. Pour inspecter une observation
avant de trancher : `forget-mem.sh show-obs <id> [<id>...]`.

### Étape 2 : Présenter et faire confirmer
Montre à l'utilisateur, de façon lisible, exactement ce qui sera supprimé :
- les fichiers de mémoire fichier + la/les ligne(s) de `MEMORY.md`,
- les IDs d'`observations` et de `session_summaries`.

Puis **attends une confirmation explicite**. Ne supprime rien avant le « oui ».
Si des résultats appartiennent à un autre projet ou semblent hors-sujet,
signale-le et laisse l'utilisateur restreindre la sélection.

### Étape 3 : Supprimer (seulement après confirmation)

**Mémoire fichier** (fais-le toi-même, le script n'y touche pas) :
- Supprime chaque fichier `.md` concerné : `rm ~/.claude/projects/-home-poste/memory/<fichier>.md`
- Retire sa/ses ligne(s) correspondante(s) dans `MEMORY.md` avec Edit.
- Si un fichier ne doit être que partiellement oublié (un fait parmi d'autres),
  édite le fichier au lieu de le supprimer entièrement.

**claude-mem** (via le script, backup automatique de la DB) :
```bash
~/.claude/skills/forget/forget-mem.sh del-obs <id> [<id>...]
~/.claude/skills/forget/forget-mem.sh del-sum <id> [<id>...]
```

### Étape 4 : Vérifier et rendre compte
Relance `forget-mem.sh search "<sujet>"` pour confirmer qu'il ne reste rien
d'important, puis résume à l'utilisateur ce qui a été effacé (fichiers, nombre
d'observations et de summaries).

## Notes
- **Index vectoriel chroma** (`~/.claude-mem/chroma/`) : c'est un index secondaire
  d'embeddings. Après suppression dans SQLite, le contexte de démarrage de session
  et les recherches FTS (`get_observations`, `search`) ne montrent plus le sujet.
  Un fragment d'embedding peut subsister dans chroma mais il pointe vers une
  observation supprimée. Le mentionner seulement si l'utilisateur veut une purge
  totale ; sinon la suppression SQLite suffit pour « ne plus s'en rappeler ».
- Le script fait une sauvegarde horodatée de `claude-mem.db` avant chaque
  suppression. En cas d'erreur, restaurer le `.bak` le plus récent.
- Le worker claude-mem tourne en tâche de fond ; SQLite gère la concurrence
  (mode WAL), les `DELETE` sont sûrs pendant qu'il tourne.
