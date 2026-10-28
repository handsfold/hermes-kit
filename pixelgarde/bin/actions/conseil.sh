#!/usr/bin/env bash
# Bouton « Conseil » de la pastille (demande de USER le 2026-10-02).
#
# Ouvre une seance du Conseil : des grands entrepreneurs (Musk, Bezos, Jobs,
# Munger...) posent a USER une question a la fois sur son cap, jusqu'a un
# engagement « quand X, je fais Y ». Le cerveau est bin/qg/qg-conseil.py.
#
# 1. qg-conseil.py ouvrir : la 1re question, et le marqueur /tmp/pixel-conseil.
# 2. La question part en voix, et ouvre la conversation sur le telephone
#    (action VOIX avec un fichier : la voix joue, puis la parole revient).
# 3. Tant que le marqueur existe, voixtour.sh envoie les reponses au Conseil.
set -uo pipefail

ADDR="${1:-$(adb devices | awk '/device$/{print $1; exit}')}"
VOIX_TEL="/sdcard/Android/data/com.poste.pixelgarde/files/voix"
ENV="$HOME/.hermes/.env"
CHAT="__QG_CHAT__"
THREAD="2923"
VOIX_TTS="fr-FR-RemyMultilingualNeural"
DEBIT="+8%"
CONSEIL="$HOME/Bureau/Projets/contexte/bin/qg/qg-conseil.py"
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

TMP="$(mktemp -d)"
OCCUPE="/tmp/pixel-occupe"
date +%s > "$OCCUPE"
trap 'rm -rf "$TMP" "$OCCUPE"' EXIT
journal() { echo "conseil : $*" >&2; }
vibre() { adb -s "$ADDR" shell cmd vibrator_manager synced oneshot "${1:-90}" >/dev/null 2>&1 || true; }

vibre 90
Q="$(timeout 90 python3 "$CONSEIL" ouvrir 2>>"$HOME/.hermes/logs/qg-conseil.log")"
if [ -z "${Q// }" ]; then
  journal "le Conseil n a rien rendu"
  vibre 60; sleep 0.2; vibre 60; sleep 0.2; vibre 60
  exit 1
fi
journal "question : $(printf '%s' "$Q" | head -c 160)"

TOKEN="$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$ENV" | cut -d= -f2-)"
if [ -n "$TOKEN" ]; then
  curl -sS --max-time 20 -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
    -d chat_id="$CHAT" -d message_thread_id="$THREAD" \
    --data-urlencode text="Conseil :
$Q" >/dev/null 2>&1 &
fi

NOM="conseil-$(date +%s%3N).mp3"
if "$(dirname "$0")/../tts-rapide.sh" "$Q" "$TMP/$NOM" "$VOIX_TTS" "$DEBIT" \
   && adb -s "$ADDR" push "$TMP/$NOM" "$VOIX_TEL/$NOM" >/dev/null 2>&1; then
  adb -s "$ADDR" shell am start-foreground-service \
    -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIX \
    --es fichier "$NOM" >/dev/null 2>&1
  journal "question dite ($NOM)"
else
  journal "synthese ou transfert impossible, seance close"
  python3 "$CONSEIL" clore 2>/dev/null
  vibre 60; sleep 0.2; vibre 60; sleep 0.2; vibre 60
  exit 1
fi
