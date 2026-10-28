# Compte rendu des routines : détails

Quand le lire : brancher `compte-rendu` sur un hôte à plusieurs comptes, sur une
grappe, ou juger d'un signal de panne.

## Hôte où les routines tournent sous d'autres comptes (Pi)

- Unités système avec `User=agent-entreprise` ou `User=entreprise-a` : leur `~` n'est pas celui de `pi`.
- Outil installé en `/usr/local/bin/compte-rendu` (lisible par tous), pas dans `~pi/.local/bin`.
- Dossier commun `/var/lib/routines` en mode 1777 (`sudo install -d -m 1777`),
  et `Environment=COMPTE_RENDU_DIR=/var/lib/routines` dans le drop-in.
- Le cockpit lit ce dossier et `~pi/.local/state/routines` par un seul `ssh ... tail -n +1`.
- Modifier un script d'un autre compte : `sudo`, puis `stat` avant et après pour garder propriétaire et droits.
- La commande d'origine garde son `WorkingDirectory` : l'outil lance le sous-processus dans le même dossier.

## Arrêt par systemd

`TimeoutStartSec` envoie SIGTERM à tout le groupe. L'outil capte SIGTERM et SIGINT,
termine l'enfant et écrit `ko` « arrêtée par le signal 15 » avant de sortir.
Sans cela, une routine tuée par délai ne laisse aucune trace.

## Grappes (`~/.hermes/scripts/grappe.py`)

Un service par membre (`ok`, `ko <erreur>`, `inconnu jamais lance`). Un membre en
ko, même ancien, met la grappe en ko. Les lignes `CR: donnee` des membres
remontent préfixées `membre.cle`.

## Signaux à ne pas utiliser

- **Âge du dernier écrit dans le journal d'une crontab** : faux 3 fois sur 3. Ces
  scripts n'écrivent que sur un événement. Le silence n'y est pas une panne.
- Une routine sans compte rendu reste affichée « ne rend pas compte d'elle-même »,
  jamais supprimée ni marquée en panne. Ne rien retirer de la page Routines.
- Alerte d'absence de compte rendu : au-delà de `max(2 périodes, période + 2 h)`.
