---
name: boite-mail
description: Repondre a une question sur les mails du membre depuis sa base locale (hk-boite), avec le mail source. Lecture seule.
version: 1.0.0
metadata:
  hermes:
    tags: [mail, gmail, outlook, recherche, base-locale, lecture-seule]
---

# Boite mail : repondre depuis la base locale

La boite mail du membre est copiee, en lecture seule, dans une base SQLite
locale (`~/.local/share/hermes-kit/boite.db`) par `hk-boite`. Rien ne quitte
sa machine.

## Quand l'utiliser

Le membre pose une question sur ses mails : qui lui a ecrit, ce qu'attend
quelqu'un, une facture, un fournisseur, un echange a resumer.

## Comment

1. Chercher : `hk-boite cherche "<mots cles de la question>" --n 5`
   (ajouter `--json` pour lire les champs : date, de_nom, sujet, extrait, corps, lien).
2. Repondre en 3 a 6 lignes, dans la langue du membre.
3. Toujours citer la source : sujet, expediteur, date, et le lien `source`.
4. Rien trouve : le dire, et proposer `hk-boite indexer --jours 365` pour lire plus loin.

Autres commandes : `hk-boite bilan --sec` (le bilan de la boite), `hk-boite stats`.

## Regles fermes

- Lecture seule. Ne jamais envoyer, repondre, supprimer, archiver, marquer lu
  ou deplacer un mail. Pas de clic dans la boite.
- Un brouillon de reponse se montre au membre ; il l'envoie lui-meme.
- Ne jamais copier le contenu d'un mail hors de la machine (pas de service en ligne).
