#!/usr/bin/env bash
# La phrase dite APRES un rapport en mains libres : « Tu peux dire : Oui, ou
# Non. », d'apres ses boutons devines (<id>.choix). Sans boutons : « Je
# t'ecoute. » Le telephone la joue puis ouvre le micro (Voix.java 2.37,
# suffixeChoix) : en voiture, USER ne voit pas les boutons (2026-10-12).
#
# Fabriquee a cote de la voix du rapport (qg-prevoix.sh) et poussee sous
# voix/ml-<id>.mp3. Rejouer ce script ne refait rien.
set -euo pipefail
ID="${1:?usage: qg-dire-choix.sh <id> [addr]}"
ADDR="${2:-}"
CACHE="$HOME/.hermes/qg-voix"
TEL_VOIX="/sdcard/Android/data/com.poste.pixelgarde/files/voix"
eval "$("$HOME/.hermes/scripts/qg-config.py" env)"

exec 8>"${PIXEL_TMP:-/tmp}/qg-dire-choix-$ID.lock"
flock -n 8 || exit 0

if [ ! -s "$CACHE/$ID.ml.mp3" ]; then
  LIBS=""
  if [ -s "$CACHE/$ID.choix" ]; then
    # Meme phrase que voixtour.sh dit apres une reponse du QG.
    LIBS="$(head -1 "$CACHE/$ID.choix" | tr -d "'\n" | tr '|' '\n' | cut -d: -f2- \
      | sed 's/[ ?.!]*$//' | paste -sd'|' | sed 's/|/, ou /g')"
  fi
  if [ -n "$LIBS" ]; then PHRASE="Tu peux dire : $LIBS."; else PHRASE="Je t'écoute."; fi
  edge-tts --voice "$QGC_VOIX" --rate="$QGC_DEBIT" --text "$PHRASE" \
    --write-media "${CACHE:?}/$ID.ml.mp3.part" >/dev/null 2>&1 \
    || { rm -f "${CACHE:?}/$ID.ml.mp3.part"; exit 0; }
  [ -s "$CACHE/$ID.ml.mp3.part" ] && mv "$CACHE/$ID.ml.mp3.part" "$CACHE/$ID.ml.mp3"
  rm -f "${CACHE:?}/$ID.ml.pousse"
fi

if [ -n "$ADDR" ] && [ -s "$CACHE/$ID.ml.mp3" ] && [ ! -e "$CACHE/$ID.ml.pousse" ] \
   && [ ! -e "${PIXEL_TMP:-/tmp}/pixel-stop" ]; then
  "${ADB:-adb}" -s "$ADDR" push "$CACHE/$ID.ml.mp3" "$TEL_VOIX/ml-$ID.mp3" >/dev/null 2>&1 \
    && touch "$CACHE/$ID.ml.pousse"
fi
