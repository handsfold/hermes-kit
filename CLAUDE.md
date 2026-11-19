# hermes-kit

@~/Bureau/Projets/contexte/methodes/socle-commun.md

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

- (rien pour l'instant)

## Portes uniques

| Pour... | LA porte canonique | Ne PAS refaire |
|---|---|---|
| Vérifier avant de livrer | `scripts/check.sh` | un second script de contrôle |
| Bloquer un geste irréversible | `.claude/hooks/bash_guard.py` | une phrase dans ce fichier |

## Règles paresseuses

| Fichier | Ce qu'elle couvre |
|---|---|
| (aucune pour l'instant) | |

## Rangement, la racine reste propre

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
