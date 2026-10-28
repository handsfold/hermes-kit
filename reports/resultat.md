# Test Telegram réel des menus bilingues (2026-10-11)

Verdict : 6 points OK, 1 partiel (point 1), 1 KO corrigé dans le dépôt (point 4, bouton Banc). Le point 7 (R11) est OK avec un faux modèle.

Bot de test `Testttttnrbot`, HOME jetable `/var/tmp/hk-test-tg` (conservé), gateway de test arrêtée, Chrome 9333 laissé ouvert.

## Les 8 points

1. **Liste native : PARTIEL.** `getMyCommands` renvoie `menu, supp, personality, new, sessions, resume, status, model`. /menu et /supp sont en tête, dans l'ordre. /mwbot est absent : le kit le retire exprès (`outils/retirer-mwbot.py`). Preuve : texte API, `/tmp/tg-test-00.png`.
2. **/menu et bouton Langue : OK.** 9 boutons. fr vers en ("Hermes menu, tap a category:", "Settings", "Bench · compare models", "Goal mode · tool relay") puis retour fr. Preuves : `/tmp/tg-test-02.png`, `03`, `04`.
3. **Mode objectif : OK en topic QG.** Texte "Mode objectif dans ce topic : coupe." puis "ACTIVE", boutons Activer / Retour. Dans le chat général, seul un toast "seulement en topic" (prévu). Preuves : `/tmp/tg-test-05.png`, `06`.
4. **Sous-menu Banc : KO avant correctif, OK après.** Le bouton ne menait qu'à un toast "Banc indisponible" (projet `~/Projets/perso/agent/banc-modeles` absent du kit). Corrigé dans le dépôt, le bouton disparaît : vérifié dans le menu (`/tmp/tg-test-14.png`).
5. **/supp : OK.** Liste vide d'abord ("Aucune session Telegram à supprimer."). Puis liste à boutons, confirmation "Supprimer cette session ?" avec Supprimer / Annuler, suppression d'une session de test. Preuves : `/tmp/tg-test-08.png`, `09`.
6. **/mwbot : noté.** Réponse : "Unknown command /mwbot. Type /commands to see what's available..." (en anglais malgré HK_LANG=fr). Preuve : `/tmp/tg-test-10.png`.
7. **Point d'étape R11 : OK.** Message "Toujours dessus, 0 min (en cours : starting API call #1)", puis "Toujours dessus, 1 min (en cours : waiting on claude-opus-5-5 : no stream output for 90s)". Le 2e message envoyé pendant le tour reçoit sa réponse après la fin du tour. Pas de message d'attente séparé. Preuves : `/tmp/tg-test-12.png`, `13.png`. Faux modèle local (délai 100 s, cadence 30 s), pas de vrai modèle.
8. **Tracebacks : OK.** `gateway.log` : 0. `agent.log` : 4 Traceback, tous des 401 du faux fournisseur avant le branchement du faux modèle (dernier 23:35). Aucun après.

## Bugs

- **a. `install/poser.py` posait les plugins dans `plugins-essai/`**, dossier que Hermes ne charge pas. Cause : `MANIFESTE.txt` ligne 17 nomme la source `~/.hermes/plugins-essai/`. Correctif appliqué dans le dépôt : `cible_de` mappe vers `plugins/`. Sans commit.
- **b. Bouton Banc mort** (`hermes/plugins/telegram-menus/menu.py`, vers la ligne 141). Cause : `DOSSIER_BANC` n'existe pas dans une installation du kit. Correctif appliqué : bouton ajouté seulement si `fichier_questions.py` existe. Sans commit.
- **c. /mwbot absent du kit** : l'ordre demandé "menu, supp, mwbot" n'est pas atteignable tel quel. À trancher par le propriétaire du kit.
- **d. Erreur /mwbot en anglais** malgré HK_LANG=fr (message du coeur Hermes, hors plugin).
- **e. Libellés FR sans accents** ("Reglages", "Outils et skills") et bouton "PyRIT" possiblement propre à l'auteur.
- **f. Bouton "Desactiver" du mode objectif** non retrouvé par mon libellé : mode resté actif dans le HOME jetable.

Rien n'a été appliqué à `~/.hermes/plugins`.

## Ce qui reste

- Aucun commit fait. Fichiers modifiés dans le dépôt : `install/poser.py`, `hermes/plugins/telegram-menus/menu.py` (et ce rapport).
- Topics Coach et Ideas non testés (seul QG l'a été).
- Liste native non vue dans l'interface Telegram (bouton "/"), seulement par l'API.
- Réglages du HOME jetable pour le faux modèle : `config.yaml` (provider custom, `config.yaml.avant-mock` = copie d'origine), `gateway_model_overrides.json` (`.orig` conservé), `ANTHROPIC_BASE_URL` ajouté au `.env`. À ne pas réutiliser tels quels.
- Constat hors test : la gateway de production (ancien PID 3355266) a été redémarrée à 23:41 (nouveau PID 3428499, `active`). Je n'ai lancé aucun `systemctl` ni aucun `kill` sur elle. Cause non établie.
- Le jeton du bot n'apparaît nulle part.
