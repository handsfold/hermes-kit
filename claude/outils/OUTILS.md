# Outils d'analyse et supertool

Deplace de ~/.claude/CLAUDE.md le 2026-10-27 (2 250 tokens relus a chaque tour, lus ici a la demande).

## Outils d'analyse deja ecrits : les lancer, ne pas les reecrire

`~/.claude/outils/` contient les analyses que je refaisais en heredoc a chaque fois.
Un hook `PreToolUse` refuse une commande Bash quand l'un d'eux couvre deja le besoin.

| Outil | Ce qu'il donne |
|---|---|
| `mes-tokens.py [n]` | Repartition de ce que l'agent produit, par categorie |
| `jetons-bilan.py [jours]` | Etat des jetons OAuth et API (veilleur-jetons, 7 h 30) : dernier passage et pannes sur n jours |
| `mes-commandes.py [n]` | Taille, heredocs et repetition des commandes Bash |
| `rtk-bilan.py [jours]` | Gains RTK par jour, par commande, et ce qui passe a cote |
| `cache-bilan.py [jours]` | Budget par projet (sous-agents rendus au parent), contexte relu, cache repaye, equivalent $ par jour et sessions les plus cheres |
| `cout-modeles.py [jours]` | Mix de tokens par modele et cout API equivalent du meme mix sous chaque grille |
| `estimations.py [jours] [--liste N]` | Justesse des delais annonces : ratio reel / annonce par tranche |
| `mes-sorties.py [jours] [famille]` | Poids des sorties d'outils (captures comprises, sous-agents inclus) ; `opencli` detaille par sous-commande, plus commandes par run, echecs, doublons et enchainements |
| `conso-prime.py [jours] [--liste N]` | Consommation de **Prime Agent** : part ecriture / relecture / sortie, effort reel par modele, cache froid par tour, par jour, par modele, tours les plus chers |
| `conso-hermes.py [jours] [--topic N]` | Consommation REELLE d'Hermes en tokens via le proxy (`~/.hermes/proxy-usage.jsonl`) : par topic, cron, skill, modele, appels a cache froid |
| `aiguilleur-bilan.py [jours]` | Aiguilleur de skills (Sonnet choisit la skill avant le modele), Hermes (plugin `aiguilleur`) et Claude Code (hook `hooks/aiguilleur-cc.py`) : tours vus, part injectee, voies (llm, cache, court, repli, muet, panne), latence ajoutee, skills choisies, et cout des appels `hk-aiguilleur` et `hk-aiguilleur-cc` au proxy |
| `pyrit-bilan.py [jours]` | Bilan du mode PyRIT, sans aucun contenu : duels, percees par technique, issue des duels, erreurs par type, et ou partent les tokens (backend=pyrit, par fournisseur et modele). Lit `pyrit-events.jsonl` (points de check poses par `pyrit_events.py` cote routeur-llm) + `conso.jsonl` |
| `audit-skills.py [--perso] [--tout]` | Skills actives (Claude, Hermes, Prime) contre le guide Anthropic : SKILL.md > 500 lignes, fichier > 100 lignes sans sommaire, renvoi au 2e niveau, description trop longue. `--perso` lit le parc de `parc_skills.py` (3 dossiers, tri par source : `parc_skills.py` seul donne le compte). Page visuelle (Tailscale) : http://__HOST_IP__:8740/, unite `skills-audit.service` |
| `usage-skills.py [jours] [--dormantes] [--rates] [--hors-aiguilleur]` | Usage reel des skills (outil Skill, skill_view, lecture de SKILL.md) : les plus chargees, les dormantes, les doublons Claude et Hermes. `--rates` : sessions ou un mot de `declencheurs.json` est tape par USER sans que la skill soit chargee (% rate par skill). `--hors-aiguilleur` : sessions Hermes ou l agent charge seul une skill que l aiguilleur n avait pas injectee (`--voir=SKILL` pour les sessions) |
| `issue-skills.py [jours] [--remplir] [--relire] [--exemples SKILL]` | Issue de chaque skill (journal du hook `journal-skills.py`) : sessions suivies, part corrigee par USER (signal regex), confirmees par relecture, echecs d outils. `--remplir` reconstruit le passe depuis les transcripts. `--relire` fait juger chaque correction signalee par Sonnet (skill, agent ou aucune), verdicts dans `journal-skills/relu.jsonl` |
| `utilite-routines.py [jours] [--json]` | Utilite des routines sur 7 jours : cout, resultats produits, resultats repris par USER (message dans le topic de livraison sous 12 h, compare a l attendu au hasard), passages vides et leur cout. Timers : `usage non mesure` avec la raison. Alimente les Conseils de la semaine du cockpit (`donnees/blocs/conseils.py`) |
| `controle-skills.py [--sec]` | Controle hebdo (timer lundi 8 h) : format, liens casses, doublons, rates, skills corrigees ; depose au QG seulement s'il y a un ecart |
| `controle-mesure.py [--sec]` | Toute routine (timer, crontab, hote-1 et hotes de `~/.config/controle-mesure.conf`) qui appelle un modele sans se nommer au proxy, timers coupes dans le meme cas, part du journal proxy sans appelant, tours dont le cout depasse ce que valent leurs tokens (cumul de session compte comme un tour, ne le 27/10). Timer 8 h 30, QG seulement si l ecart change. Reparer : skill `mesure-partout` |
| `sonde_mesure.py` | Reperage commun (cockpit et controle) : drapeaux modele, local, se_nomme par routine, en JSON, sans commande ni secret. A distance : `ssh hote python3 - --crontabs a,b < sonde_mesure.py` |
| `sentinelle-revue.py [--sec] [--essai]` | Les 10 systemes de revue produisent-ils encore ? Age du fichier temoin, dernier passage des crons et timers. Timer 9 h chaque jour, alerte au QG seulement sur une panne nouvelle (nee de la collecte aveugle du 14/09 au 13/10) |
| `aiguillage-rejeu.py rejouer\|noter\|regle\|etapes\|boutons` | Aiguillage du standard vocal du QG : rejoue a blanc les 30 phrases de `~/.hermes/cache/aiguillage/corpus.jsonl` (faux HOME, rien ne part), note le bon topic, la regle « une question fermee » et le temps des etapes de `voixtour.log`. `--corpus controle` rejoue les 10 phrases neuves (`controle.jsonl`), `--modele <nom>` passe `QG_STANDARD_MODELE`, `AIG_SCRIPT=<chemin>` rejoue une autre version du standard. `boutons` rejoue 4 gestes sous rapport et compte les appels au modele (doit etre 0). Un « envoi reel : OUI » peut venir d un geste de USER en parallele : verifier la ligne. Fiche : `projets/qg.md` (section 2026-10-22) |

S'ils ne repondent pas exactement au besoin : **modifier le fichier**, jamais en
ecrire un jetable. Un nouvel outil d'analyse se pose ici et s'ajoute au tableau.

