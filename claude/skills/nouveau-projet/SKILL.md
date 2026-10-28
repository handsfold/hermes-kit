---
name: nouveau-projet
description: "Nouveau projet, scaffold, squelette : socle d'un dossier. Pose le socle d'un projet neuf sur le disque, à partir d'un dossier VIDE."
when_to_use: "USER dit « nouveau projet », « démarre un projet », « initialise un projet », « scaffold », « crée le squelette », « je commence un truc ». Aussi, sans le mot projet, dès qu'un dossier neuf va naître : « fais une landing page », « fais un site », « configure le domaine et fais une page », « j'ai acheté le domaine » (raté du 2026-10-28 : realvoxai créé sans socle, posé après coup avec SOCLE_FORCE=1). Pas pour reprendre un projet existant."
argument-hint: "[nom-du-projet] [python-api|python-cli|js-web|mixte]"
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

# Nouveau projet

Un socle EXÉCUTÉ, pas une doctrine à lire. Une commande pose le squelette et
dépose les garde-fous : USER n'a rien à retenir.

La doctrine derrière chaque choix est dans
`~/Bureau/Projets/contexte/methodes/socle-projet.md`. La lire dès qu'un jugement
se pose au fil de l'eau (faut-il un hook ? quel jeu de règles ruff ? comment
déployer ?), et ne rien inventer qui n'y soit pas.

## 1. Au plus deux questions

Ne rien demander de plus. Si l'argument est déjà donné, ne pas reposer la question.

1. **Le nom du projet.** Il devient le nom du dossier, sous
   `~/Bureau/Projets/<univers>/<famille>/`, jamais a la racine ni sous un univers
   seul (hook `projet-sans-famille.py` et refus du script). Univers : `business`
   (amazon, entreprise-a, sites, contenu) ou `perso` (agent, outils, musique, vie).
   Ni l'univers ni la famille ne se demandent : les choisir d'apres ce que USER
   decrit, parmi ceux de `~/Bureau/Projets/INDEX.md`, et les dire en 1 ligne.
2. **Le type**, parmi :

| Type | Pour quoi | Ce qui est posé en plus |
|---|---|---|
| `python-api` | service HTTP, back | `pyproject.toml`, paquet, `tests/`, filet Python |
| `python-cli` | outil en ligne de commande | idem |
| `js-web` | front, site, application web | `package.json`, filet front, nettoyage Playwright |
| `mixte` | back Python et front web | les deux |

Si USER hésite, proposer le type au vu de ce qu'il décrit, et demander une
confirmation d'un mot. Ne pas ouvrir de troisième question.

## 2. Exécuter le scaffold

```bash
bash ~/.claude/skills/nouveau-projet/scaffold.sh <chemin-du-projet> <type>
```

Le script refuse un dossier existant non vide : c'est voulu, USER part toujours
d'un dossier vide, jamais de la copie d'un projet existant. Pour compléter un
projet déjà commencé, et seulement dans ce cas :
`SOCLE_FORCE=1 bash ... ` (aucun fichier existant n'est jamais écrasé).

Variable utile : `PY_PROD_VERSION=3.12` si la production ne tourne pas en 3.11.

Le script regenere `~/Bureau/Projets/INDEX.md`. Ajouter ensuite au projet un
`CLAUDE.md` dont la 1re phrase dit ce qu'il fait : c'est elle que l'index et le
`LISEZMOI.md` de la famille affichent.

### Site sur Cloudflare (landing, vitrine, domaine acheté)

Lire `templates/cloudflare/LISEZMOI.md` et le suivre dans l'ordre : DNS, zone
durcie par `durcir-zone.sh <domaine>`, `deployer.sh` copié dans `scripts/`,
SEO de base, preuve visuelle. Une zone neuve garde sinon cache 4 h, https off
et TLS 1.0 (vu sur realvoxai le 2026-10-28).

Le hook `projet-sans-socle.py` refuse de créer un dossier neuf sous une famille
sans ce script (laissez-passer `SANS_SOCLE=1`, sur demande de USER seulement).

## 3. Rendre compte

Reprendre le résumé du script, puis dire en clair :

- **Le filet** : `check.sh` du dossier `scripts` du projet neuf (posé par scaffold.sh depuis `~/.claude/skills/nouveau-projet/templates/check.base.sh`), lancé à la main avant toute livraison.
  Rien ne le lance tout seul. Cibles : `--fast`, `py`, `web`, `sec`, `reg`,
  `slow`, `--strict`. Sorties : 0 vert, 1 rouge, 2 une autre vérification tourne.
- **Les hooks posés** : `bash_guard.py` (PreToolUse, bloque pkill, les rm
  catastrophiques et les secrets en clair), `stuck_detector.py`
  (UserPromptSubmit, prise de hauteur quand la session patine),
  `deploy_report.sh` (posé mais NON branché, il se branche le jour où un script
  de déploiement écrit `.claude/deploy_status.json`), et pour les types web
  `playwright_cleanup.sh` (SessionStart et Stop).
- **Ce qui reste à faire** : installer les dépendances, écrire le premier test,
  remplir « Projet et commandes » dans le CLAUDE.md.

Puis lancer le `check.sh` du projet neuf une fois et montrer le verdict. Un rouge dû à un
outil absent est normal sur un dossier neuf, et le message porte le remède.

## 4. Ce que la skill ne fait PAS

Elle pose ce qui vaut pour tout projet. Ce qui suit s'écrit quand le projet
existe vraiment, jamais par anticipation, et toujours daté :

- les **pièges** du CLAUDE.md : une puce par incident réel, avec sa date ;
- les **règles propres au projet** dans `bash_guard.py` : le bloc est en place,
  commenté, avec les modèles éprouvés (systemctl, docker compose down, alembic
  downgrade, rsync --delete, ancienne IP réattribuée) ;
- le **déploiement** : bleu-vert ou Docker avec rollback, section 5 du socle ;
- la **parité poste vers prod**, l'index du code, le cliquet de dette design :
  section 6 du socle, à poser quand il y a une prod et une UI à protéger.

Ne pas créer de fichier vide « pour plus tard » : un fichier qui ne fait rien
apprend à ignorer le dossier qui le contient.
