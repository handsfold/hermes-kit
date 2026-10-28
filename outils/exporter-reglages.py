#!/usr/bin/env python3
"""Ecrit hermes/maj/reglages-proteges.exemple.yaml, la version neutre des reglages proteges.

Le fichier vivant (~/.hermes/maj/reglages-proteges.yaml) contient le modele, les adresses
et les plugins de la machine d'origine. On n'en garde que des cles neutres (liste blanche
ci-dessous), lues telles quelles dans le fichier vivant, sans bibliotheque YAML. Les
plugins et le menu Telegram sont ecrits pour le kit.
"""

import pathlib
import re

SOURCE = pathlib.Path.home() / ".hermes/maj/reglages-proteges.yaml"
SORTIE = pathlib.Path("hermes/maj/reglages-proteges.exemple.yaml")

# Cles de premier niveau reprises du fichier vivant (ligne seule ou bloc indente)
GARDER = (
    "agent.max_turns",
    "agent.restart_drain_timeout",
    "agent.gateway_notify_interval",
    "agent.gateway_timeout",
    "compression",
)

KIT = """\
plugins:
  enabled:
  - telegram-menus
  - mode-objectif
platforms.telegram.extra.command_menu:
  max_commands: 20
  priority_mode: replace
  priority:
  - menu
  - supp
  - new
  - sessions
  - resume
  - status
  - model
  - reasoning
  - usage
  - stop
  - help
"""

ENTETE = """\
# Reglages proteges (exemple) : ce que la migration de config d'Hermes ne doit jamais changer.
# Cle pointee -> valeur attendue. Aucun secret, aucun modele, aucune adresse.
# hermes-verif.sh compare, hermes-maj-sure.sh reapplique apres chaque migration.
# Copie ce fichier en ~/.hermes/maj/reglages-proteges.yaml, puis ajoute TES reglages
# (modele, personnalite...). L'installateur le fait une fois, sans jamais l'ecraser ensuite.
"""

# Un bloc = une ligne de premier niveau, plus les lignes indentees ou en tirets qui la suivent
blocs, courant = {}, None
for ligne in SOURCE.read_text().splitlines():
    if ligne.startswith("#") or not ligne.strip():
        continue
    if not ligne.startswith((" ", "-")):
        courant = re.split(r"[: ]", ligne, maxsplit=1)[0]
        blocs[courant] = []
    if courant:
        blocs[courant].append(ligne)

manque = [k for k in GARDER if k not in blocs]
if manque:
    raise SystemExit(f"exporter-reglages : cles absentes du fichier vivant : {manque}")

SORTIE.parent.mkdir(parents=True, exist_ok=True)
SORTIE.write_text(ENTETE + "\n".join("\n".join(blocs[k]) for k in GARDER) + "\n" + KIT)
print(f"reglages : {SORTIE} ({len(GARDER)} cles reprises)")
