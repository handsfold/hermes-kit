#!/usr/bin/env bash
# Bouton « Parler au QG » : ouvre Telegram sur le topic de l'orchestrateur.
#
# Il n'arme pas le micro de Telegram : la position de ce bouton depend du
# clavier affiche. Pour parler au QG, le bouton est « Conversation vocale »
# (voix.sh) : il n'ouvre meme pas Telegram. Un appui de plus au
# pouce coute moins cher qu'un tap aux coordonnees devinees, qui envoie le
# message a moitie ecrit une fois sur trois.
set -euo pipefail
ADDR="${1:-$(adb devices | awk '/device$/{print $1; exit}')}"
CHAT="__QG_CHAT__"
CHAT_BRUT="${CHAT#-100}"  # le -100 du chat_id est un prefixe d'API, pas de lien
TOPIC="__QG_THREAD__"     # le sujet QG dans le forum
PAQUET="org.telegram.messenger"

adb -s "$ADDR" shell cmd vibrator_manager synced oneshot 120 >/dev/null 2>&1 || true
# tg://openmessage ne sait pas viser un sujet : il ouvre la liste du forum.
# Seul le lien https://t.me/c/<chat>/<topic> entre dans le sujet lui-meme.
adb -s "$ADDR" shell am start -a android.intent.action.VIEW \
  -d "https://t.me/c/$CHAT_BRUT/$TOPIC" >/dev/null 2>&1 \
  || adb -s "$ADDR" shell am start -a android.intent.action.VIEW \
       -d "tg://openmessage?chat_id=$CHAT_BRUT" >/dev/null 2>&1 \
  || adb -s "$ADDR" shell monkey -p "$PAQUET" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
