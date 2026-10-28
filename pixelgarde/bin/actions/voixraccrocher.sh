#!/usr/bin/env bash
# Bouton « Raccrocher » : ferme la conversation vocale, quel que soit l'etat.
#
# Il n'existe que parce que le bouton principal a change de sens le
# 27/08/2026 : en etat « pret », un appui REPREND la parole au lieu de
# couper. Sans cette seconde porte, USER ne pouvait plus raccrocher sans
# reparler d'abord. Le garde ne l'affiche que pendant une conversation.
set -euo pipefail
ADB="${ADB:-adb}"
ADDR="${1:-$("$ADB" devices | awk '/device$/{print $1; exit}')}"
"$ADB" -s "$ADDR" shell am start-foreground-service \
  -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIXFIN >/dev/null 2>&1
