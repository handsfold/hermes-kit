#!/usr/bin/env python3
"""Prouve quel override de modele s'applique a quel thread Telegram.

A lancer depuis la racine de l'install Hermes concernee, avec son venv et son
HERMES_HOME. Exemple pour l'seconde instance :

    cd /home/exemple/hermes-agent && \
      HERMES_HOME=/home/exemple/.hermes ./venv/bin/python \
      <skill>/scripts/verifier-topic.py -1001234567890 81 10

Sortie attendue : le thread cible porte le modele voulu, le thread temoin None.
Un `None` sur le thread cible = reglage inerte, pas un probleme de redemarrage.
"""
import sys

from gateway.config import Platform
from gateway.run import _get_channel_override, load_gateway_config_for_runner

if len(sys.argv) < 3:
    sys.exit("usage: verifier-topic.py <chat_id> <thread_id> [<thread_id>...]")

chat_id = sys.argv[1]
config = load_gateway_config_for_runner()
for thread_id in sys.argv[2:]:
    override = _get_channel_override(
        config, Platform.TELEGRAM, chat_id, thread_id=thread_id
    )
    print(f"{thread_id}: {override}")
