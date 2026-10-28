---
name: r
description: "/r, résume, où j'en suis ? : une seule phrase. Résume en UNE seule phrase simple le dernier message de USER (Claude Code, Hermès, Telegram, tous topics), ou la session si elle vient de commencer, pour qu'il sache où il en est et décide."
when_to_use: "USER tape « /r », ou dit « où j'en suis ? », « résume », « en une phrase », « qu'est-ce qu'on a fait ? », « on en est où ? ». Pas pour un bilan de plusieurs jours (voir retro-agent), ni pour un rapport détaillé."
---

# /r : une phrase, jamais un pavé

USER lit cette phrase et prend UNE décision : continuer cette session, ou la
fermer et repartir propre. Tout ce qui l'oblige à lire un deuxième paragraphe
rate la cible.

Skill GLOBALE : elle vaut dans tous les projets, pas seulement DJ. La phrase
produite sert aussi de NOM à la conversation (hook `cc-rename-from-r.sh`), d'où
l'importance du gabarit ci-dessous : ce qui a été fait d'abord, le reliquat après
« ; reste », car seule la première partie donne le nom.

## Ce que /r résume (retour de USER, 2026-10-24)

**Par défaut : TON DERNIER MESSAGE**, celui qu'il vient de lire, quel que soit
l'endroit : Claude Code, Hermès, un topic Telegram, le QG. Il le veut en 1 phrase
pour décider sans relire le pavé. Si `/r` arrive avec du texte (« /r le rapport
d'avant »), c'est ce texte qui désigne la cible. Pas de dernier message utile
(session vide ou tout juste compactée) : retomber sur la session entière.
Dans Hermès, aucun outil non plus : le message est déjà dans le contexte.

## Règles fermes

1. **Exactement une phrase.** Pas de titre, pas de liste, pas de préambule
   (« Voici… »), pas de question à la fin, rien après le point.
2. **35 mots maximum.** Si ça ne tient pas, c'est que la phrase raconte le
   chemin au lieu du résultat.
3. **Ce que ça change pour USER**, pas le chemin technique : « Nada se déplace où
   tu veux » et non « ajout d'un handler pointer + persistance localStorage ».
   Un nom de fichier ou de fonction seulement s'il EST le sujet.
4. **L'état réel, sans le gonfler** : vérifié en live / fait mais pas encore
   testé / en cours / bloqué. Un « c'est livré » faux coûte une session entière.
5. **Ce qui reste**, uniquement si c'est ce qui décide de la suite, collé à la
   même phrase après « ; » ou « , reste ».
6. **Aucun appel d'outil** : la réponse est déjà dans le contexte, et /r doit
   être instantané. Deux exceptions, un seul outil chacune :
   - contexte vide ou fraîchement compacté → `git log --oneline -5` ;
   - doute sur ce qui a réellement été livré → `git status --short`.
7. **Pas de tiret cadratin** (règle ferme) : « · », « : » ou une virgule.
8. Plusieurs chantiers dans la session → garder **le fil principal** et coller
   le second après « ; », jamais une énumération de tout ce qui a été touché.
9. Rien n'a encore été fait → le dire franchement en une phrase, ne rien inventer.

## Gabarit

> J'ai ‹ce qui a changé pour toi›, ‹état de vérification› ; reste ‹la suite› .

## Exemples

**Bon** : « J'ai rendu Nada déplaçable : tu la glisses où tu veux, elle reste là
sur toutes les pages et après rechargement, vérifié en live sur PC et mobile. »

**Bon** : « J'ai calé le mix du morceau de méditation, mais rien n'est encore
jugé ni écouté ; reste à le faire trancher par le juge avant de le publier. »

**Bon (rien fait)** : « On n'a rien produit pour l'instant : la session a servi à
lire le code du générateur, aucune modification n'est en cours. »

**Mauvais** : un paragraphe, une liste à puces, « Résumé de la session : … », des
noms de fonctions, ou « Veux-tu que je continue ? » après la phrase.
