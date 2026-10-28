---
name: verifier-avant-livraison
description: "Avant « c'est fait/c'est bon » sur du code : tester. Protocole obligatoire avant d'annoncer qu'un travail de code, d'interface, d'API ou de script est fini : exécuter le résultat, regarder la sortie, puis seulement annoncer. Encode les pièges appris sur le projet DJ. À charger dès qu'une tâche de code touche à sa fin, même si USER ne demande aucun test."
when_to_use: "USER dit « corrige ce bug », « ajoute cette fonction », « refais l'UX », « livre-moi ça », « c'est bon ? », « c'est en ligne ? ». Aussi juste avant d'écrire « c'est fait », « corrigé » ou « déployé ». Pas pour les règles d'interface elles-mêmes (voir charte-ux)."
version: 1.2.0
metadata:
  hermes:
    tags: [dev, qualite, verification, ui, livraison]
    related_skills: [charte-ux, android-media3-auto, pixel-pilotage]
---

# Vérifier avant de livrer

Sommaire :
- 1. Avant de toucher au code
- 2. Après avoir écrit : la preuve, dans cet ordre
- 3. Si c'est une interface
- 4. Nettoyage
- 5. Ce que tu écris à la fin
- 6. Quand tu diagnostiques (pas quand tu répares)
- 6bis. Quand le travail va durer plus de 5 minutes
- 7. Quand tu as raté
- 8. Un défaut que tu as trouvé : corrige, ne demande pas

La règle tient en une phrase : **tu n'annonces jamais un travail fini sans avoir vu
le résultat tourner.** Un diff qui compile n'est pas une preuve. Une capture, une
sortie de test, un code de retour : ça, c'est une preuve.

## 1. Avant de toucher au code

- **Reproduis le problème d'abord.** Si tu ne sais pas le déclencher, tu ne sauras
  pas non plus prouver qu'il est réglé.
- **Cherche l'existant avant de créer.** `grep -rl "def <ce_que_je_veux>"` ou
  l'équivalent. Le doublon coûte plus cher que la recherche.
- **Note l'état de départ** : erreurs déjà présentes dans la console, tests déjà
  rouges. Sans ça, tu ne sauras pas distinguer ta régression de l'existant.

## 2. Après avoir écrit : la preuve, dans cet ordre

Chaque étape produit une trace. Si une étape est impossible, tu le dis, tu ne la
sautes pas en silence.

1. **Ça démarre ?** Lance vraiment le programme, le serveur, le script.
2. **Ça compile / type-check ?** `npm run build`, `tsc`, `python -m py_compile`,
   selon le projet.
3. **Les tests passent ?** Lance-les. Un test rouge annoncé comme vert est la pire
   des livraisons.
4. **Le comportement demandé existe ?** Exécute le cas exact de la demande, pas un
   cas voisin plus commode.
5. **Rien d'autre n'a cassé ?** Console sans nouvelle erreur, tests voisins verts.

## 3. Si c'est une interface

Voir aussi la skill `charte-ux` pour les règles de goût. Ici, la mécanique :

- **Deux tailles d'écran, toujours** : 1440×860 puis 390×844. USER regarde d'abord
  sur téléphone. Une UI vérifiée seulement en grand format n'est pas vérifiée.
- **Console navigateur** : zéro erreur nouvelle. Les erreurs à l'arrêt du serveur
  sont du bruit, pas ton code.
- **Captures en JPEG**, jamais PNG (1,6× plus cher pour rien).
- **Ne relis JAMAIS une capture** que tu viens de prendre : tu l'as déjà vue, la
  relire double la facture.
- **Pour vérifier une structure** (un onglet est actif, un texte est bon), un
  snapshot du DOM suffit et coûte 31× moins qu'une capture. La capture ne sert
  qu'à juger du visuel : densité, alignement, contraste.
- **Ferme le navigateur en fin de tâche**, même si la vérification a échoué.
  Sinon les process s'accumulent et mangent la RAM.

### Si c'est de l'audio ou de la voix

Un correctif audio ne se prouve pas à l'oeil. Une capture, un HTTP 200, une
ligne de log : ça ne dit rien du son. Il faut jouer le flux réel sur l'appareil.

- **Lecture, dictée, réécoute, pause, baisse de volume** : la seule preuve est
  de lancer le son, d'appuyer sur pause, de réécouter, de parler, et de regarder
  ce que ça fait. Pas « le code route bien l'audio ». Pas « le bouton appelle la
  bonne fonction ». Le comportement sonore, mesuré.
- **Les pièges se nichent dans les états** : réécouter après une pause, cliquer
  plusieurs fois vite, baisser au lieu de couper, un silence trop long avant
  l'envoi. Chaque état se teste à la main, un par un.
- Né des frictions du Creeper (28/09 au 05/10) : « réécouter ne fonctionne pas »,
  « ça coupe la musique au lieu de la baisser », « la voix n'envoie rien quand je
  parle », « pause puis clics multiples ça bascule ». Tous livrés comme réglés,
  tous cassés sur le téléphone : le flux audio n'avait jamais été joué.

### Le cache : ta preuve est vraie, et elle ne prouve rien

Ton navigateur de test est neuf à chaque fois. Celui de USER, non. Il arrive avec
l'ancien `app.js` en mémoire. La page neuve s'affiche, les boutons neufs ne
répondent pas au clic, et toi tu as écrit « retesté, 0 erreur ».

Le 14/09 sur `exemple.tld` : « Preuve visuelle », « API validée ». USER, au
tour suivant : « Pourquoi ça fonctionne pas que je clique sur choisir ni mon
profil ». Le code était juste. La vérification aussi. Le cache ne l'était pas.

- **Avant de livrer une UI servie par toi : le HTML doit référencer ses `.js` et
  `.css` avec un `?v=` calculé à la requête**, jamais posé à la main. Un `?v=6`
  écrit en dur se désynchronise au premier oubli. Motif de référence :
  `projet-x/serveur/app.py` (`_index_versionne`, mtime) ou
  `projet-y/app/main.py` (`empreinte`, hash sha256).
- **`Cache-Control: no-store` sur le document HTML seulement.** Les assets
  restent cachables : leur URL change quand leur contenu change.
- **`bin/verif-ui.sh` le vérifie tout seul depuis le 14/09** : il refuse de
  capturer, et sort en erreur, tant qu'un `.js` ou `.css` local est servi sans
  version. Il affiche `cache: ok (assets versionnes)` quand c'est bon. Si c'est
  volontaire (bundler à noms hachés, site tiers) : `VERIF_UI_CACHE=ignore`.
- Si le site est déjà en ligne sans ça, donne à USER l'URL de déblocage
  (`?neuf=1`) EN MÊME TEMPS que le correctif serveur. Il ne doit pas avoir à
  vider son cache lui-même.

## 4. Nettoyage

- Supprime les scripts jetables que tu as créés.
- Aucun fichier généré à la racine du projet : captures, rendus et rapports vont
  dans leur dossier dédié, git-ignoré.
- Ne laisse pas de serveur de test allumé sans le dire.

## 5. Ce que tu écris à la fin

Trois lignes, pas un roman :

1. **Ce qui est fait**, en une phrase.
2. **Ce qui a été vérifié**, concrètement : « build OK, 12 tests verts, capture
   mobile relue ». Pas « ça devrait marcher ».
3. **Ce qui n'a PAS été vérifié**, franchement. Une limite annoncée vaut mieux
   qu'une bonne surprise ratée.

**Interdit** : « ça devrait fonctionner », « normalement c'est bon », « je pense
que ». Soit tu as exécuté et tu le dis, soit tu écris « non vérifié » et tu dis
pourquoi.

**Interdit aussi : annoncer une action que tu n'as pas encore lancée.** « Je relance
l'agent », « je lance la compilation », « c'est parti » ne s'écrivent qu'APRÈS l'appel
d'outil, jamais à sa place. Le 31/08 j'ai écrit avoir relancé un agent sans le faire,
et j'ai dû me dédire au message suivant : USER a perdu trente minutes d'attente pour
rien.

## 6. Quand tu diagnostiques (pas quand tu répares)

Un diagnostic est une livraison comme une autre : il s'annonce avec sa preuve.

- **Une cause s'annonce avec son chiffre, jamais avec un raisonnement.** « AVRCP est
  à 0 appareil connecté » tient. « Android Auto doit bloquer les touches » ne tient
  pas, même si c'est vrai.
- **Ne retourne pas une conclusion parce que USER la conteste.** Sa contestation est une
  hypothèse à mesurer, pas une correction. Réponds « je vérifie », lance la commande,
  puis tranche avec la sortie. Le 31/08 j'ai donné trois causes successives et
  contradictoires sur le même problème, dont une reprise à son avis, fausse : une
  seule commande `dumpsys` les départageait dès le début.
- **Une cause déjà connue se remesure avant d'être resservie.** Le 14/09 j'ai
  expliqué que les sous-agents mouraient parce que le proxy redémarrait : c'était
  vrai en août, et corrigé depuis. USER a dû me reprendre (« tu es sûr de ça ? »),
  et j'ai envoyé le travail vers systemd pour rien. Un souvenir n'est pas une
  mesure. `systemctl show -p NRestarts` tranchait en une commande.
- **Deux diagnostics faux d'affilée = arrête de raisonner, va lire l'état réel.**
- Quand tu t'es trompé : une phrase, la cause, la suite. Pas de récit.

## 6bis. Quand le travail va durer plus de 5 minutes

USER n'a pas à sonder. S'il écrit « ça en est où ? », c'est déjà raté : le 14/09
il l'a écrit **8 fois dans une seule session**, alors que j'avais les chiffres
à chaque fois. Ce qui manquait n'était pas l'info, c'était la poussée.

- **Pose un jalon AVANT de lancer**, pas pendant :
  `jalon poser "<ce qui doit finir>" --fin "<commande qui sort 0>" --sujet <sujet> --max <min>`
- Le critère de fin est **une commande**, jamais une impression. `curl ... | grep -q 200`
  tient. « quand les agents auront fini » ne tient pas.
- Un timer systemd le teste toutes les 2 min et prévient USER tout seul, au vert
  comme au blocage. Aucun token consommé : l'envoi est direct par l'API Telegram.
- `chantiers` affiche les jalons en cours. `jalon retirer <id>` si la tâche change.

## 7. Quand tu as raté

Une phrase, la cause, la suite. Pas d'excuses, pas le récit de ta recherche, pas
la liste de tes erreurs passées.

## 8. Un défaut que tu as trouvé : corrige, ne demande pas

Quand tu constates toi-même qu'un morceau en production est cassé (code, réglage, compte de service, donnée de test oubliée) et que la réparation reste dans ton périmètre et se défait, **tu corriges, tu déploies, tu vérifies, puis tu rends compte.** Poser la question « je le répare ? » coûte un tour à USER pour une réponse qui est toujours oui.

- Reste soumis au « oui » de USER : tout message externe, toute dépense, toute publication, tout réglage de sécurité d'un compte (règles fermes du `CLAUDE.md` global). Le correctif d'un bug n'ouvre aucune de ces portes.
- Après la réparation, refais le parcours qui échouait (pas seulement le test du correctif) et cite ce que tu as vu.
