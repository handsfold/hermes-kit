#!/usr/bin/env bash
# Bouton « Conversation directe » (2026-11-03) : ouvre le mode full-duplex,
# WebSocket vers relais/creeper-live.py. Voir Direct.java dans l'appli.
#
# Le 2e appui ne passe pas par ici : la bulle ferme le service elle-meme
# (startService DIRECTFIN), le service etant deja au premier plan. Si ce
# script est relance alors que la conversation tourne, le service bascule
# aussi vers l'arret.
set -euo pipefail
ADB="${ADB:-adb}"
ADDR="${1:-$("$ADB" devices | awk '/device$/{print $1; exit}')}"
# start-foreground-service, comme voix.sh : un micro ouvert depuis
# l'arriere-plan rend du silence au lieu de lever une erreur.
"$ADB" -s "$ADDR" shell am start-foreground-service \
  -n com.poste.pixelgarde/.Direct -a com.poste.pixel.DIRECT >/dev/null 2>&1
