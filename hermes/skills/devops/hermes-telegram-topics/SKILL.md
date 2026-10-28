---
name: hermes-telegram-topics
description: "Topic Telegram : créer, renommer, muet, modèle, icône. Configure les topics d'un groupe Telegram forum piloté par Hermes : créer ou renommer un topic, le rendre muet, lui donner un modèle différent, un prompt propre, une session isolée, une icône native. Pas pour le topic Prime Agent (voir prime-agent)."
when_to_use: "USER dit « créer un topic nommé », « crée un topic pour », « renomme ce topic », « mets ce topic en muet », « fais taire ce topic », « un autre modèle pour ce topic ». Aussi pour dédoublonner ou re-router un topic, même sans le mot Telegram. Pas pour l'état du topic Prime Agent (voir prime-agent)."
---

# Topics Telegram d'une instance Hermes

Sommaire :
- Verifier AVANT d'ecrire : la version change tout
- Modele different sur un topic (0.21)
- Rendre un topic muet (l'equipe parle entre elle)
- Prompt et session par topic
- Icones natives, jamais un emoji dans le nom
- Pieges de la Bot API
- Support

Un groupe forum Telegram + Hermes, c'est N conversations dans un seul processus.
Chaque `message_thread_id` peut porter son propre prompt, son propre modele, sa
propre session, et peut etre muet. Tout se regle dans `config.yaml` et le `.env`,
sous `platforms.telegram`.

## Verifier AVANT d'ecrire : la version change tout

⚠️ Le mecanisme de modele par topic **a change entre 0.12 et 0.21**. Ecrire dans
le mauvais fichier ne produit aucune erreur, juste un reglage inerte.

| Version | Modele par topic | Fichier |
|---|---|---|
| **0.12** | `gateway_model_overrides.json` (ecrit par `/model`) | `~/.hermes/gateway_model_overrides.json` |
| **0.21** | `platforms.telegram.channel_overrides` | `config.yaml` |

En 0.21, `gateway_model_overrides.json` **n'est plus lu du tout**. Le test qui
tranche, sans deviner :

```bash
grep -m1 version <install>/pyproject.toml
grep -c 'gateway_model_overrides' <install>/gateway/run.py   # 0 => 0.21, sinon 0.12
```

Deux instances de USER, deux versions differentes : hote-1 en 0.12, la seconde instance en 0.21.
Ne jamais recopier la config de l'une dans l'autre sans ce controle.

## Modele different sur un topic (0.21)

```yaml
platforms:
  telegram:
    channel_overrides:
      '81':
        model: pyrit-auto-hermes-vs-deepseek
```

Precedence : session `/model` > `channel_overrides` > defaut global.
La cle est cherchee dans l'ordre `chat_id`, puis `thread_id`, puis `parent_id`.

⚠️ `ChannelOverride` ne porte que **`model`, `provider`, `system_prompt`**. Pas de
`base_url`, pas d'`api_key` : le modele nomme doit etre servi par le provider
global. Si le modele vient d'un proxy local (routeur 8010), c'est le
`model.base_url` global qui doit deja pointer dessus.

Verification qui prouve, plutot que le redemarrage qui rassure :

```bash
scripts/verifier-topic.py <chat_id> <thread_ok> <thread_defaut>
```

## Rendre un topic muet (l'equipe parle entre elle)

```bash
echo TELEGRAM_IGNORED_THREADS=1 >> ~/.hermes/.env
```

- Dans un forum, un message **sans** `message_thread_id` vaut le thread **`1`** :
  c'est General (`_GENERAL_TOPIC_THREAD_ID`).
- Lu par `_telegram_ignored_threads()`, qui coupe le chemin de reponse
  (`return False`). L'agent lit toujours, il ne repond plus.
- Equivalent en config : `platforms.telegram.ignored_threads`.

**Preferer `ignored_threads` a `allowed_topics`.** Une liste blanche fait naitre
muet tout topic cree plus tard, sans erreur ni trace. La liste noire ne bloque
que ce qu'on a nomme.

## Prompt et session par topic

- `platforms.telegram.channel_prompts['<thread_id>']` : la persona du topic.
  ⚠️ C'est sous **`platforms.telegram`**, pas sous `agent`. Verifier par parcours
  du YAML, pas a l'indentation lue a l'oeil.
- `group_sessions_per_user: false` : une session par topic, partagee par l'equipe.
- Cles de `sessions/sessions.json` : `agent:main:telegram:group:<chat>:<thread>`.
  Un topic ne voit jamais le fil d'un autre.
- Apres toute recreation de topic, **remapper** les cles de `channel_prompts` et
  `channel_overrides` : ce sont des `message_thread_id`, pas des noms.

## Icones natives, jamais un emoji dans le nom

USER l'a corrige explicitement : il veut l'attribut d'icone du topic.

```bash
curl -s "https://api.telegram.org/bot$T/getForumTopicIconStickers"   # 112 icones, pas plus
curl -s "https://api.telegram.org/bot$T/createForumTopic" \
  -d "chat_id=$CHAT" -d "name=War Room" -d "icon_custom_emoji_id=5312241539987020022"
```

## Pieges de la Bot API

- ⚠️ **Aucune API ne liste les topics.** Un topic absent de l'ecran peut n'etre
  que masque ou ferme, pas supprime. Le recreer fabrique des doublons.
- Sonder avant d'agir : `sendMessage` puis `deleteMessage` sur chaque
  `message_thread_id` ; `message thread not found` = inexistant.
  `sendChatAction` ne sert a rien, il repond `ok` meme sur un thread mort.
- `editForumTopic` qui renvoie `TOPIC_NOT_MODIFIED` prouve que nom et icone sont
  deja les bons : c'est un test, pas un echec.
- Menage : `deleteForumTopic`.
- **Telegram ne sait pas reserver un topic a une personne.** Tout membre du
  groupe voit tous les topics. Un espace vraiment prive demande un autre groupe.

## Support

- `references/deux-instances.md` : l'ecart 0.12/0.21 en detail, les chemins
  exacts des deux instances de USER, et l'incident du fichier inerte.
- `scripts/verifier-topic.py` : prouve quel override s'applique a quel thread.
