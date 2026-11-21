# Claude Code : règles globales de USER

## Exécuter et vérifier

- Exécuter la demande jusqu'au résultat prouvé, sans redemander à chaque étape.
- Attendre le oui de USER avant d'engager de l'argent, contacter un tiers non prévu ou modifier la sécurité d'un compte.
- Vérifier le résultat réel avant de l'annoncer. Signaler les limites et les parties bloquées.
- Respecter les conventions du dépôt. Ne pas committer, pousser ou déployer sans demande.

## Règles permanentes

- Livraison : vérifier l'adresse de production et fournir la preuve visuelle pertinente. Respecter les portes du dépôt (`check.sh`, `deployer.sh --verifier`).
- Accès : CLI installé, puis coffre/Infisical et API documentée. Navigation connectée en dernier, via le sous-agent `portail`. Ne jamais afficher les secrets.
- Messages externes : montrer brouillon, destinataire et adresse ; attendre le oui. `ENVOI_AUTORISE_PAR_VJ=1` exige son ordre écrit. Exception existante : négociations fournisseurs 1688/Alibaba/WeChat, sans engagement d'argent.
- Publication sociale : montrer le fichier final et la légende. Attendre le oui visant la publication ; l'accord au montage ne suffit pas.
- Attribution : aucune signature d'IA dans les commits, demandes de fusion ou tickets.
- Services de USER (`cockpit.service`, `wol-web-pc.service`, dashboard) : les redémarrer sans demander quand un changement l'exige, puis prouver qu'ils répondent (USER, 16/11). Le gateway Hermes reste exclu : il tue la réponse en cours.
- Fermer les processus ouverts pour un essai. `# garder` réserve explicitement un processus à conserver.

## Économie de contexte

- Exploration large : sous-agent `Explore`. Lecture ciblée : outil direct. Grouper les opérations indépendantes, sans refaire la recherche déléguée.
- Avant une analyse de logs, tokens ou coûts, consulter `~/.claude/outils/OUTILS.md`. Employer les outils existants et borner leurs sorties.
- Pour les réglages Claude Code, consulter `~/Bureau/Projets/contexte/methodes/claude-code.md` au besoin.
- Le style `Clair` est désactivé (13/11, demande de USER). La rédaction suit caveman : français lisible, sens intact.
- Caveman actif (`.caveman-active`) : il l'emporte sur la longueur et la structure du style `Clair`. Réponse finale 8 lignes max, sans récapitulatif. Aucun texte entre deux appels d'outils, sauf 1 ligne au changement de phase. Pied « Prochaine étape » en 1 ligne. Retour de USER du 13/11 : 3 réponses trop longues d'affilée.

<!-- SOCLE-AGENTS:DEBUT -->
## Contexte projet à la demande

Le contexte est dans `CONTEXTE_ROOT`, sinon `~/Bureau/Projets/contexte`.
Consulter `INDEX.md` uniquement si une information de contexte manque ; ne pas le charger automatiquement.
Pour cadrer un projet, utiliser `python3 <contexte>/bin/contexte-projet <id>`.
Lire son `CLAUDE.md` ou l'autorité indiquée par sa fiche. Le guide `methodes/agents-portables.md` détaille le socle si nécessaire.
Les règles métier partagées restent dans le contexte, sans copie ici. Ne pas présumer des hooks d'un autre moteur.
<!-- SOCLE-AGENTS:FIN -->

<!-- LIVRAISON-AGENTS:DEBUT -->
## Livraison complete, tous projets

Une modification demandee inclut tests, compilation, mise en service sur la cible
existante et verification apres installation, sans nouveau oui. Ne pas s'arreter
au code local, au plan ni au rapport d'un sous-agent. Verifier la version reellement
servie ou installee, puis le geste demande sur la cible ; traiter cache et rechargement.
Une etape rouge bloque la livraison : corriger et poursuivre, ou annoncer le blocage
precis sans attendre une relance de USER. Un point d'etape n'est pas une fin de travail.
Dire distinctement fait, verifie et non verifie ; jamais « livre » pour du local seul.
Respecter les portes du projet et les exceptions : pas de commit/push, suppression,
depense, message externe ou changement de securite sans accord specifique ; ne pas
interrompre un appel, une conversation ou le gateway qui porte la reponse.
Cette regle est une consigne globale, pas la preuve d'un verrou technique universel.
<!-- LIVRAISON-AGENTS:FIN -->
