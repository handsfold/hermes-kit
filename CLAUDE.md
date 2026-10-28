# hermes-kit

> Doctrine complète, invariants datés, recettes de déploiement :
> `~/Bureau/Projets/contexte/methodes/socle-projet.md`. Ce fichier-ci ne
> reprend que ce qui est propre à hermes-kit. Cible : 200 lignes maximum,
> le reste part en `.claude/rules/` avec un frontmatter `paths:`.

## Avant toute livraison

```bash
scripts/check.sh            # LE filet, à lancer à la main
scripts/check.sh --fast     # sans réseau, ce que le déploiement lance
```

Depuis le 2026-10-24, la chaîne tourne seule (`outils/synchroniser.sh`, timer
utilisateur `hermes-kit-sync`, toutes les 3 h, au plus 1 CI complète par 20 h) :

1. `outils/importer.sh` : copie du MANIFESTE, désidentification, audit.
2. Rien de changé : arrêt silencieux.
3. `scripts/check.sh --fast` puis `outils/audit.sh` (identités, clés, fichiers
   interdits par nom/taille/lien, gitleaks).
4. Commit sur une branche `sync/AAAAMMJJ-HHMM`, push (dépôt privé).
5. CI : `audit` puis `installation` (ubuntu, macos et windows-wsl exigés verts ;
   windows-wsl réparé le 2026-10-24 : un prompt figeait WSL, 7 min au lieu de 40).
6. Seulement si tout est vert : fast-forward de `master`. Sinon `master` ne
   bouge pas et le motif part au QG (`qg-attente`, une fois par motif).

`master` n'avance QUE par cette chaîne. Essai à blanc : `outils/synchroniser.sh
--essai`. Journal : `~/.local/state/hermes-kit-sync/dernier.log`.
Un test rouge dans un fichier-filet n'est jamais « un test à ajuster », c'est
une protection qui vient de tomber.

Le filet à la main reste `scripts/check.sh` (`--fast` : sans réseau).

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

## Règles paresseuses

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

But : publier la configuration Hermes + Claude Code + proxy + pastille Android
sous un seul depot, installable en 1 commande, sans aucune donnee personnelle.

- `outils/importer.sh` : copie ce que `MANIFESTE.txt` autorise, puis audite.
- `outils/audit.sh [--staged]` : identites privees (liste hors depot,
  `contexte/infra/identites-privees.txt`) puis gitleaks. Branche en pre-commit.
- `outils/installer-hooks.sh` : a relancer sur un clone neuf.
- `outils/verifier-interdits.py` : aucun fichier au nom, a la taille ou a la nature interdits (appele par audit.sh).
- `outils/synchroniser.sh` : la chaine automatique ci-dessus.
- Regle : rien n'entre dans le depot sans passer par le manifeste. Jamais de
  copie a la main, jamais d'expurgation d'un dossier vivant.
- CI `.github/workflows/audit.yml` : gitleaks + identites via le secret
  `HK_IDENTITES_REGEX`. Les journaux CI ne montrent que chemin et ligne.
