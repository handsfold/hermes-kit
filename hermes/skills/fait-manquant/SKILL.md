---
name: fait-manquant
description: "Conseil, choix, « je fais quoi ? » : le fait d'abord. Avant de répondre à une question ouverte, une décision ou une demande qui suppose du contexte : nomme LE fait concret qui changerait la réponse, le cherche, puis répond en le citant ou pose 1 seule question. À charger dès que USER demande un conseil ou un choix, même sans le mot « décision »."
when_to_use: "USER dit « tu me conseilles quoi ? », « que me conseilles-tu », « je dois décider », « quelle est la meilleure option », « je fais quoi ? », « lequel tu prends ? », « ça vaut le coup ? ». Pas pour un ordre pratique (installer, lancer, chercher un fichier), ni pour retrouver un ancien échange (voir fil)."
tags: [productivity, meta, core]
---

# Fait manquant : chercher le fait, pas réfléchir plus

## Quand l'appliquer

- Question ouverte : « que me recommandes-tu », « comment faire », « pourquoi ».
- Décision à prendre, choix entre options.
- Demande qui suppose un contexte : « ça en est où », « et l'autre », « comme d'habitude ».

Pas pour une commande simple et claire. Là, on exécute.

## Les 4 temps

1. **Nommer LE fait** qui, s'il était différent, changerait la réponse. Un seul.
   Nature typique : quel appareil, quel outil déjà en place, quel écran,
   quel document, quel réglage existant.
2. **Le chercher**, dans cet ordre :
   - la conversation en cours ;
   - `session_search` si USER suppose un échange antérieur ;
   - les fiches `~/Bureau/Projets/contexte/` (INDEX.md d'abord) ;
   - `entreprise-a-index` si c'est un document ou un chiffre EntrepriseA.
3. **Trouvé** : répondre en s'appuyant dessus, et dire d'où il vient
   (quel message, quelle fiche, quelle date).
4. **Introuvable** : poser à USER UNE question courte. Puis donner une réponse
   provisoire de 3 lignes, sur l'hypothèse la plus probable.

## Format

- La réponse d'abord (ou la question puis la réponse provisoire).
- 5 puces de détail au plus.
- Aucun bloc « Hypothèses », aucun recopiage des étapes 1 et 2.

## Pièges

- **Dater ce qu'on trouve.** Une fiche ou une note peut être postérieure
  à la question, ou hors sujet. Au test, une note du journal du jour
  a trompé une réponse. Vérifier que le fait concerne bien la même chose.
- **Une seule recherche ciblée**, pas une fouille large : c'est ce qui rend
  la méthode 2 fois moins chère qu'une exploration libre.
- Pas de panel d'experts ni de reformulation longue : mesuré sans gain.

## Pourquoi cette méthode (test du 2026-09-27)

Test à l'aveugle, 10 vraies questions de USER, juge Opus. Notes sur 20 :

- Sans contexte : 12,5.
- Contexte seul (fouille large) : 15,2, environ 400k tokens lus par réponse.
- `reframer` (3 experts) : 13,4. Désactivé.
- Fait manquant : 15,1, environ 214k tokens lus par réponse.

Le gain vient du contexte retrouvé, pas de la réflexion en plus.
Détail : `~/Bureau/Projets/perso/agent/questionner/v2/resultat.md`.
