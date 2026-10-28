#!/usr/bin/env bash
# Synthese vocale rapide d'un texte de plusieurs phrases.
#
# edge-tts met environ 2,5 s par phrase, en serie : 10 a 12 s pour un point
# de 4 phrases (mesure du 2026-10-01). Ici chaque phrase part en parallele,
# puis les mp3 sont mis bout a bout (meme encodage, la concatenation se lit
# telle quelle). Resultat mesure : 3,4 s pour les memes 4 phrases.
#
# Usage : [TTS_PREMIERE=<deb.mp3>] tts-rapide.sh "<texte>" <sortie.mp3> [voix] [debit]
set -uo pipefail
TEXTE="${1:?texte manquant}"
SORTIE="${2:?fichier de sortie manquant}"
VOIX="${3:-fr-FR-RemyMultilingualNeural}"
DEBIT="${4:-+8%}"
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

mapfile -t PHRASES < <(printf '%s' "$TEXTE" | python3 -c '
import re, sys
for p in re.split(r"(?<=[.!?])\s+", sys.stdin.read().strip()):
    if p.strip():
        print(p.strip().replace("\n", " "))')

i=0
P0=""
for p in "${PHRASES[@]}"; do
  edge-tts --voice "$VOIX" --rate="$DEBIT" --text "$p" \
    --write-media "$D/$(printf '%03d' $i).mp3" >/dev/null 2>&1 &
  [ -n "$P0" ] || P0=$!
  i=$((i+1))
done

# Lecture anticipee (2026-10-03) : avec TTS_PREMIERE=<fichier>, la 1re phrase
# y est deposee des qu'elle est prete, sans attendre les autres. Le telephone
# la joue, puis reprend la reponse complete a la meme position : la complete
# commence par ces octets exacts. Une seule phrase : rien a anticiper.
if [ -n "${TTS_PREMIERE:-}" ] && [ "$i" -gt 1 ] && [ -n "$P0" ]; then
  wait "$P0"
  if [ -s "$D/000.mp3" ]; then
    cp "$D/000.mp3" "$TTS_PREMIERE.part" && mv "$TTS_PREMIERE.part" "$TTS_PREMIERE"
  fi
fi
wait

# Une phrase perdue rendrait le point incomprehensible : tout ou rien.
for j in $(seq 0 $((i-1))); do
  [ -s "$D/$(printf '%03d' $j).mp3" ] || exit 1
done
cat "$D"/*.mp3 > "$SORTIE"
[ -s "$SORTIE" ]
