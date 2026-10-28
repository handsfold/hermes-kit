#!/usr/bin/env bash
# Bouton « Ou j'en suis » : l'etat de tous les chantiers, dit a voix haute.
#
# Le trou que ce bouton comble : la pastille savait annoncer un rapport QUAND
# il en arrivait un, et rien pour demander l'etat a froid. Il fallait ouvrir
# Telegram et lire. Ici, on appuie et on ecoute.
#
# Il ne lit AUCUN transcript : `qg` rend une ligne d'etat par sujet, `focus`
# rend le cap et les taches. C'est ce qui rend l'appel tenable dans la duree,
# quel que soit le nombre de topics ouverts.
#
# La reponse est jouee par le service Voix en action DIRE : il lit et s'eteint,
# sans armer le micro. VOIXREP, lui, rend la parole apres lecture, ce qui
# laisserait le telephone en ecoute alors que USER l'a repose.
set -uo pipefail

ADDR="${1:-$(adb devices | awk '/device$/{print $1; exit}')}"
VOIX_TEL="/sdcard/Android/data/com.poste.pixelgarde/files/voix"
HA="$HOME/.hermes/hermes-agent"
PY="$HA/venv/bin/python"
ENV="$HOME/.hermes/.env"
CHAT="__QG_CHAT__"
THREAD="2923"
VOIX_TTS="fr-FR-RemyMultilingualNeural"
DEBIT="+8%"
LIMITE_TTS=1400

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

TMP="$(mktemp -d)"
journal() { echo "bilan : $*" >&2; }

vibre() { adb -s "$ADDR" shell cmd vibrator_manager synced oneshot "${1:-90}" >/dev/null 2>&1 || true; }
vibre 90

# ------------------------------------------------- 1. on montre qu'on bosse

# Retour immediat, comme toute bonne appli : la bulle passe en « ... » et sa
# tete reflechit tant que le point se prepare. Avant le 2026-10-01, rien ne
# bougeait pendant 35 s apres une vibration de 90 ms : USER croyait le bouton mort.
OCCUPE="/tmp/pixel-occupe"
date +%s > "$OCCUPE"
trap 'rm -rf "$TMP" "$OCCUPE"' EXIT

# ------------------------------------------------------- 2. le point, rapide

# Un seul appel au routeur, par le standard (meme modele que le menu Cerveau),
# sur l'etat deja tenu dans qg.db et sur `focus`. Environ 5 s, contre 35 s par
# la session du QG, qui relisait tout son historique pour 4 phrases.
STANDARD="$HOME/Bureau/Projets/contexte/bin/qg/qg-standard.py"
REP="$(timeout 60 python3 "$STANDARD" bilan 2>/dev/null)"

if [ -z "${REP// }" ]; then
  journal "le standard n a rien rendu"
  vibre 60; sleep 0.2; vibre 60; sleep 0.2; vibre 60
  exit 1
fi
journal "bilan : $(printf '%s' "$REP" | head -c 160)"

# --------------------------------------------- 3. la trace sur Telegram

# Elle part AVANT la voix : si la synthese lache, USER a quand meme son point.
TOKEN="$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$ENV" | cut -d= -f2-)"
if [ -n "$TOKEN" ]; then
  curl -sS --max-time 20 -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
    -d chat_id="$CHAT" -d message_thread_id="$THREAD" \
    --data-urlencode text="Où j'en suis :
$REP" >/dev/null 2>&1 &
fi

# ------------------------------------------------------------ 4. la voix

A_DIRE="$(printf '%s' "$REP" | head -c "$LIMITE_TTS")"
NOM="bilan-$(date +%s%3N).mp3"
# Phrases synthetisees en parallele : 3 s au lieu de 10 pour un point entier.
if "$(dirname "$0")/../tts-rapide.sh" "$A_DIRE" "$TMP/$NOM" "$VOIX_TTS" "$DEBIT" \
   && adb -s "$ADDR" push "$TMP/$NOM" "$VOIX_TEL/$NOM" >/dev/null 2>&1; then
  adb -s "$ADDR" shell am start-foreground-service \
    -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIXDIRE \
    --es fichier "$NOM" >/dev/null 2>&1
  vibre 140
  journal "bilan dit ($NOM)"
else
  # Trois vibrations breves : la voix a lache, le texte est sur Telegram.
  journal "synthese ou transfert impossible, texte seul"
  vibre 60; sleep 0.2; vibre 60; sleep 0.2; vibre 60
fi
