<p align="center">
  <img src="docs/handsfold-avatar.png" width="96" alt="HandsFold">
</p>

<h1 align="center">hermes-kit</h1>

<p align="center">
  <b>Ton propre agent IA sur Telegram, installé en une commande.</b><br>
  Hermes Agent + Claude Code, réglés et branchés ensemble. Rien à configurer à la main.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-MIT-blue" alt="Licence MIT"></a>
  <img src="https://img.shields.io/badge/tourne%20sur-Linux%20%C2%B7%20macOS%20%C2%B7%20WSL2-lightgrey" alt="Linux, macOS, WSL2">
  <img src="https://img.shields.io/badge/Hermes-v2026.9.14-orange" alt="Hermes v2026.9.14">
</p>

<p align="center">
  <a href="#démarrage-rapide">Démarrage</a> ·
  <a href="#ce-que-tu-obtiens">Ce que tu obtiens</a> ·
  <a href="#comment-ça-marche">Fonctionnement</a> ·
  <a href="#commandes-du-quotidien">Commandes</a> ·
  <a href="#vie-privée">Vie privée</a> ·
  <a href="README.md">English</a>
</p>

---

Tu parles à ton agent dans Telegram. Il répond, travaille sur ta machine et range
ses tâches par sujets. Derrière tournent [Hermes Agent](https://github.com/NousResearch/hermes-agent)
et ton propre abonnement [Claude Code](https://claude.com/claude-code), avec des
skills, des hooks et des garde-fous testés chaque jour.

**Aucune clé d'API à acheter.** Le kit utilise l'abonnement Claude Code que tu paies déjà.

## Démarrage rapide

```bash
curl -fsSL https://raw.githubusercontent.com/handsfold/hermes-kit/master/install/install.sh | HK_LANG=fr bash
```

Puis, dans Telegram :

1. Envoie `/newbot` à [@BotFather](https://t.me/BotFather) et colle le jeton quand l'installateur le demande.
2. Dans @BotFather : ton bot, puis Bot Settings, puis **Topics in private chats** : activé.
3. Ouvre ton bot et appuie sur **Start**.

Un message de test arrive dans ton nouveau sujet QG. C'est tout.

Durée, mesurée en CI : **2 min 30** sur Ubuntu, **4 min 20** sur macOS, **11 min** sur WSL2.
Relancer la commande est sans risque : chaque étape déjà faite est sautée.

## Ce que tu obtiens

- **Un QG privé dans Telegram.** 3 sujets (QG, Coach, Idées), créés par Hermes lui-même. Ni groupe, ni réglage à la main.
- **Le Hermes officiel**, épinglé au tag testé `v2026.9.14`. Son code n'est pas modifié.
- **Un proxy local** qui fait tourner Hermes sur ton abonnement Claude Code ([claude-proxy](https://github.com/handsfold/claude-proxy)).
- **28 skills** prêtes, et un **aiguilleur** qui choisit la bonne avant que le modèle lise ton message.
- **3 plugins** : `telegram-menus` (un `/menu` à boutons), `mode-objectif` (garder un but d'un tour à l'autre), `aiguilleur`.
- **22 hooks Claude Code** : des garde-fous contre les commandes risquées, les secrets qui fuient et les modifications dangereuses.
- **Des outils de mesure** : jetons, coût par modèle, skills qui se déclenchent et ce qu'elles apportent (`hk banc`).
- **Des mises à jour sûres** : essai hebdomadaire de la version suivante de Hermes, tes réglages jamais écrasés.

Anglais par défaut. Français avec `HK_LANG=fr`.

## Comment ça marche

```
 Toi (Telegram)
      │
      ▼
 Passerelle Hermes  ──  skills · aiguilleur · plugins · crons
      │
      ▼
 claude-proxy (local, port 8000)
      │
      ▼
 CLI Claude Code  ──  ton abonnement · hooks · garde-fous
```

Tout tourne sur ta machine. Tes messages vont de Telegram à Hermes, puis à Claude
par ta propre connexion. Le kit n'ajoute aucun serveur à lui au milieu.

## Prérequis

- Un abonnement Claude Code (connexion claude.ai).
- Un compte Telegram.
- Linux, macOS, ou Windows avec WSL2 (`wsl --install`, puis la commande dans Ubuntu).
- L'accès `sudo` pour installer des paquets (git, curl, python3, jq, node 18+).
- Environ 2 Go libres sur le disque (estimation).

## Commandes du quotidien

L'installateur ajoute `hk` :

| Commande | Effet |
|---|---|
| `hk status` | État du proxy et de la passerelle |
| `hk restart` | Relance les deux |
| `hk logs` | Suit les journaux |
| `hk doctor` | Vérifie toute l'installation |
| `hk reparer` | Répare une étape cassée |
| `hk update` | Met le kit à jour |
| `hk audit` | Ta config avant et après le kit, en chiffres |
| `hk annuler` | Défait la dernière migration de skills |
| `hk telemetrie on\|off\|voir` | Statistiques d'installation (voir Vie privée) |
| `hk coauteur on\|off\|voir` | La ligne de co-auteur des commits (voir Vie privée) |

## Options

À passer dans l'environnement, devant la commande. Liste complète : `install/env.exemple`.

| Variable | Effet |
|---|---|
| `HK_LANG=fr` | Menus et messages en français. Défaut `en`. |
| `HK_PATCHES=1` | Applique la série de patchs Hermes sur une branche locale. Coupé par défaut. |
| `HK_TELEGRAM_TOKEN`, `HK_TELEGRAM_USER` | Saute les questions Telegram (installation sans surveillance). |
| `HK_PIXEL_IP=<ip>` | Ajoute Creeper, une bulle Android pilotée par ADB. Jamais obligatoire. |
| `HK_SANS_SERVICES=1` | Saute les services systemd (conteneurs, CI). |

Détail pas à pas : [`install/README.md`](install/README.md).

## Vie privée

- **Tes données restent sur ta machine.** Le dépôt ne contient aucune donnée personnelle : le contenu entre par une liste blanche (`MANIFESTE.txt`), et chaque commit est contrôlé contre les secrets (gitleaks) et les identités privées.
- **Statistiques d'installation** : envoyées seulement si tu as un jeton de membre HandsFold. Une liste fermée d'événements, chacun envoyé une fois : installation finie, chaque étape (réussie ou ratée), Telegram branché, le bot a répondu une fois, le bot est encore actif au 7e jour. Jamais un message, un identifiant Telegram ni une IP. Les voir : `hk telemetrie voir`. Les couper : `hk telemetrie off`.
- **Ligne de co-auteur.** Les commits faits par Claude Code finissent par `Co-Authored-By: HandsFold <hello@handsfold.com>`. La couper : `hk coauteur off`. Une `attribution` que tu as posée toi-même n'est jamais touchée.

## Organisation du dépôt

| Dossier | Contenu |
|---|---|
| `install/` | L'installateur en une commande et les outils `hk` |
| `hermes/` | Modèle de config Hermes, skills, plugins, scripts, patchs optionnels |
| `claude/` | Réglages Claude Code, hooks, agents, outils d'analyse |
| `proxy/` | Le proxy LLM local (sous-module git) |
| `pixelgarde/` | Creeper, la bulle Android optionnelle |
| `docs/` | Guides, par exemple [mettre Hermes à jour sans risque](docs/mise-a-jour-hermes.md) |

## FAQ

**Est-ce que ça modifie Hermes ?** Non. Hermes s'installe depuis son tag officiel. La série de patchs existe, mais seulement avec `HK_PATCHES=1`.

**Je garde mes réglages Claude Code ?** Oui. Le kit fusionne dans `~/.claude/settings.json`, prend une photo avant (`hk audit`) et garde tes propres choix.

**Quelque chose a cassé.** Lance `hk doctor`, puis `hk reparer`. Chaque étape se rejoue.

## Remerciements

Construit sur [Hermes Agent](https://github.com/NousResearch/hermes-agent) de Nous Research,
[Claude Code](https://claude.com/claude-code) d'Anthropic, et [RTK](https://github.com/rtk-ai/rtk).

## Licence

[MIT](LICENSE) · fait par [HandsFold](https://handsfold.com)
