---
name: mesure-partout
description: "Coût non mesuré, routine sans coût, conso inconnue : tout mesurer. Rend mesurable tout ce qui appelle un modèle (timer, crontab, script, app, agent) pour que sa conso sorte dans le dashboard : repère par la sonde, corrige la routine pour qu'elle se nomme au proxy, annote les faux positifs, revérifie. À charger dès qu'une ligne de coût est vide ou « non mesuré », ou avant de livrer quelque chose qui appelle un LLM."
when_to_use: "USER dit « pourquoi ce coût n'est pas mesuré », « ça coûte combien cette routine », « mesure tout », « tout traquer », « on ne voit pas la conso », « non mesuré », « à corriger : skill mesure-partout », ou le contrôle controle-mesure dépose un écart au QG. Aussi quand une routine plante sans que ça se voie : « elle ne dit pas qu'elle ne fonctionne pas », « le service n'est pas accessible », « elle n'a pas été déclenchée », « les routines ne sont pas intelligentes », « qu'elles rendent compte ». Aussi avant de livrer un timer, un script ou une app qui appelle un modèle. Pas pour lire la conso déjà mesurée (outils conso-hermes.py, cout-modeles.py)."
tags: [devops, mesure, core]
---

# Mesure partout : aucune conso sans nom

Principe : un appel de modèle qui ne dit pas qui il est devient un coût sans
propriétaire. Le proxy ne peut l'attribuer qu'à un nom qu'on lui donne.

## 1. Repérer

```bash
python3 ~/.claude/outils/controle-mesure.py --sec   # écarts, sans dépôt au QG
python3 ~/.claude/outils/sonde_mesure.py | python3 -m json.tool | less   # détail local
```

Hôtes distants : `~/.config/controle-mesure.conf`, une ligne `alias proprio1,proprio2`.
La sonde lit la commande puis les fichiers lancés, sur 2 niveaux.

## 2. Corriger, selon le cas

| Cas | Correction |
|---|---|
| Appel HTTP au proxy (`/v1/messages`) | `"metadata": {"user_id": "systemd:<unité>"}` dans le corps. Le nom littéral `appelant_systemd` en commentaire aide la sonde |
| `claude -p` hors proxy | `claude -p ... --output-format json \| ~/.hermes/scripts/usage-timer.py` |
| Clé OpenRouter ou Anthropic en direct | Passer par le proxy ou le routeur, puis cas 1 |
| Modèle local (ollama, whisper) | Rien : compté 0 $ par la sonde |
| Faux positif vérifié (curl de test, URL citée) | Commentaire `# mesure: aucun-modele (raison)` dans le script |
| Hôte distant (Pi) | Même `metadata` : le proxy du Pi a son journal depuis le 26/10/2026. Le cockpit le lit par ssh. Hôte neuf : son journal en 3e colonne de `~/.config/controle-mesure.conf` |

Le nom donné doit être l'unité systemd exacte (`x.service`) : le cockpit
rattache le coût par ce nom.

## 3. Revérifier

- `controle-mesure.py --sec` ne liste plus la routine.
- Après un passage réel : `conso-hermes.py 1` montre l'unité en source `systemd`.
- Page Routines du dashboard : la ligne a un coût ou un 0 justifié.

## 4. L'état : chaque routine rend compte d'elle-même

Le coût ne dit pas si la routine marche. Une routine qui avale une erreur réseau
sort en 0 et paraît verte. Outil : `~/Bureau/Projets/contexte/bin/compte-rendu`
(écrit `<dossier>/<cle>.json`, lu par la page Routines du cockpit).

1. **Envelopper sans toucher au script** : drop-in `20-compte-rendu.conf`
   (`ExecStart=` vide puis `ExecStart=<outil> <cle> -- <commande d'origine>`),
   `daemon-reload`, puis `systemctl show <u> -p ExecStart` pour relire.
   `<cle>` = nom de l'unité sans `.service` : le cockpit rattache par ce nom.
2. **Faire parler le script** : lignes `CR: resume|service nom=ok/ko raison|donnee k=v|etat warn`
   sur stdout. Chercher d'abord chaque `try/except` ou `return` qui avale une panne
   de service (API, IMAP, Telegram, ntfy, clé absente) : c'est là que va `service=ko` + `etat warn`.
   Copie `<fichier>.bak-cr` avant, ajouts minimaux, `print(..., flush=True)`.
3. **Revérifier par systemd**, pas à la main : un lancement manuel ne charge pas
   `EnvironmentFile` et donne un faux warn. Lancer seulement les routines sans
   envoi de message ; les autres se vérifient à leur passage naturel.
4. **Rafraîchir la vue** : le dash du Pi lit une photo. `cockpit/instantane.py`
   puis `dashboard/deposer-stack.sh`, et ne conclure qu'après lecture de la photo
   (un `cr` absent de la photo = photo prise avant le redémarrage du cockpit).

Détail (hôtes à plusieurs comptes, signal d'arrêt, signaux rejetés) : `references/compte-rendu.md`.

## Pièges

- Un timer coupé non nommé n'apparaît pas en coût : il le sera le jour où on le relance. Le corriger avant.
- Le mot « claude » dans un chemin (dossier `.claude/`, nom de compte) n'est pas un appel : la sonde cherche `claude -p`.
- Le proxy du Pi (`:8020`) journalise l'appelant depuis le 26/10/2026 (`/home/agent-entreprise/.hermes/proxy-usage.jsonl`). Un proxy d'hôte sans journal laisse ses routines non mesurées.

Fiche : `~/Bureau/Projets/contexte/methodes/tracage.md`.
