# Les deux instances Hermes de USER, et l'ecart de version

Constate le 2026-09-03 en configurant un modele par topic sur l'instance entreprise.

## Chemins

| Instance | Install | HERMES_HOME | Version |
|---|---|---|---|
| perso, hote-1 | `~/.hermes/hermes-agent/` | `~/.hermes/` | **0.12.0** |
| seconde instance (user `exemple`) | `/home/exemple/hermes-agent/` | `/home/exemple/.hermes/` | **0.21.0** |

Les deux tapent sur le meme routeur LLM (port 8010 de hote-1) ; le Pi y accede par
un tunnel SSH inverse, donc `http://127.0.0.1:8010/anthropic` marche des deux cotes.

## L'incident

Objectif : donner a un topic du groupe entreprise le modele
`pyrit-auto-hermes-vs-deepseek`, comme deux topics du groupe perso.

Erreur commise : recopier la methode de hote-1, c'est-a-dire ecrire
`~/.hermes/gateway_model_overrides.json` avec une entree
`agent:main:telegram:group:<chat>:<thread>`. Le service a redemarre sans une
erreur. Le reglage n'a jamais rien fait.

Ce qui l'a revele : `grep -rln gateway_model_overrides` dans l'install du Pi ne
renvoie **rien**, alors que sur hote-1 il renvoie `gateway/run.py`
(`_MODEL_OVERRIDE_PATH = _hermes_home / "gateway_model_overrides.json"`).
En 0.21 il ne reste que `_session_model_overrides`, en memoire seule, et la
persistance passe par `channel_overrides` dans `config.yaml`.

## Lecon

Un fichier de config inerte ne fait aucun bruit. Avant de recopier une methode
d'une instance a l'autre, **verifier que le code de destination lit ce fichier** :

```bash
grep -c 'gateway_model_overrides' <install>/gateway/run.py
```

Et prouver le resultat par la resolution reelle (`scripts/verifier-topic.py`),
pas par « le service a redemarre sans erreur ».

## Autre surprise du meme jour

`channel_prompts` vit sous `platforms.telegram`, **pas** sous `agent`. Une
lecture a l'indentation (4 espaces) laissait croire l'inverse ; un
`yaml.safe_load` + parcours recursif a tranche en une commande.

Note historique : la memoire de l'agent portait « `channel_overrides` de
config.yaml est inerte ». C'etait vrai, mais **seulement en 0.12**. En 0.21 c'est
exactement le contraire. Une note de version manquante avait fait de cette
observation une regle fausse.
