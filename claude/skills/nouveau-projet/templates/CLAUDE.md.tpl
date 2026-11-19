# @@PROJET@@

@~/Bureau/Projets/contexte/methodes/socle-commun.md

## Avant toute livraison

```bash
scripts/check.sh            # LE filet, à lancer à la main
scripts/check.sh --fast     # sans réseau, ce que le déploiement lance
```

## Pièges qui coûtent cher, à connaître AVANT d'agir

- (rien pour l'instant)

## Portes uniques

| Pour... | LA porte canonique | Ne PAS refaire |
|---|---|---|
| Vérifier avant de livrer | `scripts/check.sh` | un second script de contrôle |
| Bloquer un geste irréversible | `.claude/hooks/bash_guard.py` | une phrase dans ce fichier |
@@LIGNE_DEPS@@
@@BLOC_DEPS@@## Règles paresseuses

| Fichier | Ce qu'elle couvre |
|---|---|
| (aucune pour l'instant) | |

## Rangement, la racine reste propre

## Projet et commandes

Trois commandes, pas quarante.

```bash
@@COMMANDES@@```
