# @@PROJET@@

> Doctrine complète, invariants datés, recettes de déploiement :
> `~/Bureau/Projets/contexte/methodes/socle-projet.md`. Ce fichier-ci ne
> reprend que ce qui est propre à @@PROJET@@. Cible : 200 lignes maximum,
> le reste part en `.claude/rules/` avec un frontmatter `paths:`.

## Avant toute livraison

```bash
scripts/check.sh            # LE filet, à lancer à la main
scripts/check.sh --fast     # sans réseau, ce que le déploiement lance
```

Rien ne le lance tout seul : ni hook git, ni hook Claude Code. Un test rouge
dans un fichier-filet n'est jamais « un test à ajuster », c'est une protection
qui vient de tomber.

Protection réelle du dépôt aujourd'hui : `scripts/check.sh`, lancé à la main.
Pas de CI. Le jour où il y en a une, elle lance exactement ce script.
Ne jamais décrire ici une protection qui n'existe pas.

## Pièges qui coûtent cher, à connaître AVANT d'agir

Une puce par incident réel, avec sa DATE. Critère d'entrée : ce qui doit être su
avant d'ouvrir un fichier, donc non déclenchable par un glob (sinon c'est une
règle paresseuse). Le projet démarre, la liste est vide et c'est normal : elle
se remplit au premier incident, pas par anticipation.

- (rien pour l'instant)

Les trois lignes qui valent partout :
- Une CI qui ne voit pas le code ne vérifie pas le code.
- La production ne tourne pas depuis git.
- Un secret ne s'écrit jamais dans une commande : il reste dans l'historique du
  shell et dans le transcript.

## Portes uniques

Le réflexe anti-doublon, dans l'ordre : ce tableau, puis l'index du code, puis
`grep -rl "def <ce_que_je_veux>"`, puis ajouter un PARAMÈTRE plutôt que forker.
Créer un fichier neuf ne déclenche aucun glob : rien ne t'arrêtera.

| Pour... | LA porte canonique | Ne PAS refaire |
|---|---|---|
| Vérifier avant de livrer | `scripts/check.sh` | un second script de contrôle |
| Bloquer un geste irréversible | `.claude/hooks/bash_guard.py` | une phrase dans ce fichier |
@@LIGNE_DEPS@@
@@BLOC_DEPS@@## Règles paresseuses

`.claude/rules/*.md`, frontmatter `paths:`, chargées seulement quand un fichier
correspondant est touché. Gain mesuré sur DJ le 2026-07-29 : 880 lignes vers
200, soit 17 300 vers 2 500 tokens par session.

> Le déclenchement se fait sur le FICHIER TOUCHÉ, pas sur l'intention. Une règle
> qu'il faut connaître avant d'ouvrir quoi que ce soit reste ici.

| Fichier | Ce qu'elle couvre |
|---|---|
| (aucune pour l'instant) | |

## Rangement, la racine reste propre

| Fichier généré | Destination |
|---|---|
| captures, audio, sorties de session | `artifacts/` (git-ignoré) |
| verdicts, autocritiques, rétros | `reports/` |
| code mort assumé | `archive/` (exclu du lint et de l'index) |
| documentation, index du code | `docs/` |

## Projet et commandes

Trois commandes, pas quarante.

```bash
@@COMMANDES@@```
