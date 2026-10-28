#!/usr/bin/env bash
# Transcrit n'importe quelle video en ligne a partir de son URL.
# Instagram, TikTok, YouTube, X, Facebook, Reddit, et tout ce que yt-dlp gere.
#
# Usage : transcrire.sh <url> [--lang fr] [--json] [--garder]
#
# Sortie : la transcription sur stdout, et le detail dans
#          /tmp/transcriptions/<id>/  (audio, meta.txt, transcript.txt)
#
# Regle de contexte : ce script n'ecrit JAMAIS les logs de yt-dlp sur stdout.
# Seuls le titre, l'auteur, la duree, la description et le texte sortent.

set -uo pipefail

URL=""; LANG_HINT=""; FORMAT="text"; GARDER=0; LANG_SOURCE="imposee"
while [ $# -gt 0 ]; do
  case "$1" in
    --lang)   LANG_HINT="$2"; shift 2 ;;
    --json)   FORMAT="verbose_json"; shift ;;
    --garder) GARDER=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *)        URL="$1"; shift ;;
  esac
done
[ -z "$URL" ] && { echo "erreur: url manquante" >&2; exit 2; }

command -v yt-dlp  >/dev/null || { echo "erreur: yt-dlp absent" >&2; exit 3; }
command -v ffmpeg  >/dev/null || { echo "erreur: ffmpeg absent" >&2; exit 3; }

# Cle Groq : env d'abord, .bashrc en secours. Jamais affichee.
if [ -z "${GROQ_API_KEY:-}" ]; then
  GROQ_API_KEY=$(grep -hoE 'GROQ_API_KEY=[^ ]*' "$HOME/.bashrc" 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"'")
fi

ID=$(printf '%s' "$URL" | sha1sum | cut -c1-12)
DIR="/tmp/transcriptions/$ID"
mkdir -p "$DIR"
LOG="$DIR/yt-dlp.log"

# --- Cache : deja transcrit, on ressert ---------------------------------
if [ -s "$DIR/transcript.txt" ] && [ "$GARDER" -eq 0 ]; then
  cat "$DIR/meta.txt" 2>/dev/null
  echo
  cat "$DIR/transcript.txt"
  echo "(deja en cache : $DIR, langue $(cat "$DIR/lang.txt" 2>/dev/null || echo ?))" >&2
  exit 0
fi

# --- 0. TikTok : yt-dlp est bloque (2026). On passe par l'API tikwm. -----
TIKTOK_PLAY=""
if printf '%s' "$URL" | grep -qiE 'tiktok\.com'; then
  curl -s --max-time 30 "https://www.tikwm.com/api/?url=$URL" > "$DIR/tikwm.json"
  TIKTOK_PLAY=$(python3 -c '
import json, sys, io
d = json.load(open(sys.argv[1]))
r = d.get("data") or {}
if d.get("code") != 0 or not r.get("play"):
    sys.exit(1)
a = r.get("author") or {}
with io.open(sys.argv[2], "w", encoding="utf-8") as f:
    f.write("TITRE: %s\n" % (r.get("title") or ""))
    f.write("AUTEUR: %s (@%s)\n" % (a.get("nickname") or "", a.get("unique_id") or ""))
    f.write("DUREE: %s s\n" % (r.get("duration") or 0))
    f.write("VUES: %s | LIKES: %s\n" % (r.get("play_count") or 0, r.get("digg_count") or 0))
print(r["play"])
' "$DIR/tikwm.json" "$DIR/meta.txt" 2>>"$LOG")
  if [ -z "$TIKTOK_PLAY" ]; then
    echo "erreur: tikwm n'a pas rendu cette video TikTok (privee ou supprimee)" >&2
    head -c 200 "$DIR/tikwm.json" >&2; echo >&2
    exit 4
  fi
fi

# --- 1. Metadonnees. Champs cibles, jamais --print-json (37 Ko de bruit) --
if [ -z "$TIKTOK_PLAY" ]; then
  yt-dlp --no-warnings --no-playlist --skip-download \
    --print "TITRE: %(title)s" \
    --print "AUTEUR: %(uploader)s" \
    --print "DUREE: %(duration)s s" \
    --print "DATE: %(upload_date)s" \
    --print "DESCRIPTION: %(description)s" \
    "$URL" > "$DIR/meta.txt" 2>"$LOG"
  if [ ! -s "$DIR/meta.txt" ]; then
    echo "erreur: yt-dlp n'a pas pu lire cette URL. Detail : $LOG" >&2
    tail -3 "$LOG" >&2
    exit 4
  fi
fi
DUREE=$(grep -oP '^DUREE: \K[0-9]+' "$DIR/meta.txt" | head -1)
DUREE=${DUREE:-0}

# --- 2. YouTube : les sous-titres d'abord. Gratuit et instantane ----------
if printf '%s' "$URL" | grep -qiE 'youtube\.com|youtu\.be'; then
  yt-dlp --no-warnings --no-playlist --skip-download \
    --write-auto-subs --write-subs \
    --sub-langs "${LANG_HINT:-fr,en}.*" --sub-format vtt \
    -o "$DIR/sub" "$URL" >>"$LOG" 2>&1
  VTT=$(ls "$DIR"/sub*.vtt 2>/dev/null | head -1)
  if [ -n "$VTT" ]; then
    # VTT -> texte plat, sans horodatage ni doublons de lignes roulantes
    sed -e '/-->/d' -e '/^WEBVTT/d' -e '/^Kind:/d' -e '/^Language:/d' \
        -e 's/<[^>]*>//g' -e '/^[0-9]*$/d' "$VTT" \
      | sed 's/[[:space:]]*$//' | grep -v '^$' | awk '!seen[$0]++' \
      > "$DIR/transcript.txt"
    if [ -s "$DIR/transcript.txt" ]; then
      cat "$DIR/meta.txt"; echo; cat "$DIR/transcript.txt"
      echo "(source: sous-titres YouTube, $DIR)" >&2
      exit 0
    fi
  fi
fi

# --- 3. Audio seul, le plus leger possible -------------------------------
if [ -n "$TIKTOK_PLAY" ]; then
  curl -sL --max-time 300 -A "Mozilla/5.0" -e "https://www.tiktok.com/" \
    -o "$DIR/src.mp4" "$TIKTOK_PLAY" 2>>"$LOG"
  [ -s "$DIR/src.mp4" ] || rm -f "${DIR:?}/src.mp4"
else
  yt-dlp --no-warnings --no-playlist -f "ba/b" \
    -o "$DIR/src.%(ext)s" "$URL" >>"$LOG" 2>&1
fi
SRC=$(ls "$DIR"/src.* 2>/dev/null | head -1)
[ -z "$SRC" ] && { echo "erreur: telechargement audio echoue. Detail : $LOG" >&2; tail -3 "$LOG" >&2; exit 5; }

ffmpeg -y -i "$SRC" -vn -ac 1 -ar 16000 -b:a 32k "$DIR/audio.mp3" >>"$LOG" 2>&1
[ -s "$DIR/audio.mp3" ] || { echo "erreur: extraction audio echouee" >&2; exit 6; }

# Instagram ne renvoie pas toujours la duree : on la lit dans l'audio produit.
if [ "$DUREE" = "0" ] && command -v ffprobe >/dev/null; then
  DUREE=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$DIR/audio.mp3" 2>/dev/null | cut -d. -f1)
  DUREE=${DUREE:-0}
fi

# --- 3bis. Detection automatique de la langue ---------------------------
# Sans indice, Whisper change de langue en cours de route sur les videos
# courtes et bruyantes. On identifie d'abord la langue sur 30 s d'extrait,
# puis on force ce code sur toute la transcription.
if [ -z "$LANG_HINT" ] && [ -n "${GROQ_API_KEY:-}" ]; then
  ffmpeg -y -i "$DIR/audio.mp3" -ss 0 -t 30 -c copy "$DIR/echantillon.mp3" >>"$LOG" 2>&1
  ECH="$DIR/echantillon.mp3"
  [ -s "$ECH" ] || ECH="$DIR/audio.mp3"
  curl -s --max-time 120 https://api.groq.com/openai/v1/audio/transcriptions \
    -H "Authorization: Bearer $GROQ_API_KEY" \
    -F model=whisper-large-v3-turbo \
    -F response_format=verbose_json \
    -F file=@"$ECH" > "$DIR/detect.json" 2>>"$LOG"
  LANG_AUTO=$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
print((d.get("language") or "").strip().lower())
' "$DIR/detect.json" 2>>"$LOG")
  # Whisper rend parfois le nom anglais en clair, parfois le code ISO.
  case "$LANG_AUTO" in
    french) LANG_AUTO=fr ;;  english)    LANG_AUTO=en ;;
    thai)   LANG_AUTO=th ;;  japanese)   LANG_AUTO=ja ;;
    korean) LANG_AUTO=ko ;;  chinese)    LANG_AUTO=zh ;;
    spanish) LANG_AUTO=es ;; portuguese) LANG_AUTO=pt ;;
    german) LANG_AUTO=de ;;  italian)    LANG_AUTO=it ;;
    russian) LANG_AUTO=ru ;; arabic)     LANG_AUTO=ar ;;
    vietnamese) LANG_AUTO=vi ;; indonesian) LANG_AUTO=id ;;
    hindi)  LANG_AUTO=hi ;;  dutch)      LANG_AUTO=nl ;;
  esac
  if printf '%s' "$LANG_AUTO" | grep -qE '^[a-z]{2}$'; then
    LANG_HINT="$LANG_AUTO"
    LANG_SOURCE="detectee"
  fi
  rm -f "${DIR:?}/echantillon.mp3"
fi

# --- 4. Transcription ----------------------------------------------------
# Groq plafonne le fichier a 25 Mo. A 32 kbit/s cela fait ~100 minutes.
# Au-dela on decoupe en tranches de 20 minutes.
TAILLE=$(stat -c%s "$DIR/audio.mp3")
transcrire_un() {
  local f="$1"
  curl -s --max-time 600 https://api.groq.com/openai/v1/audio/transcriptions \
    -H "Authorization: Bearer $GROQ_API_KEY" \
    -F model=whisper-large-v3-turbo \
    -F response_format="$FORMAT" \
    ${LANG_HINT:+-F language="$LANG_HINT"} \
    -F file=@"$f"
}

if [ -z "${GROQ_API_KEY:-}" ]; then
  # Secours local : lent (CPU), mais sans reseau ni cle
  command -v whisper >/dev/null || { echo "erreur: ni cle Groq ni whisper local" >&2; exit 7; }
  whisper "$DIR/audio.mp3" --model small --output_format txt --output_dir "$DIR" \
    ${LANG_HINT:+--language "$LANG_HINT"} >>"$LOG" 2>&1
  mv "$DIR/audio.txt" "$DIR/transcript.txt" 2>/dev/null
elif [ "$TAILLE" -gt 24000000 ]; then
  ffmpeg -y -i "$DIR/audio.mp3" -f segment -segment_time 1200 -c copy \
    "$DIR/part%02d.mp3" >>"$LOG" 2>&1
  : > "$DIR/transcript.txt"
  for p in "$DIR"/part*.mp3; do
    transcrire_un "$p" >> "$DIR/transcript.txt"
    echo >> "$DIR/transcript.txt"
  done
else
  transcrire_un "$DIR/audio.mp3" > "$DIR/transcript.txt"
fi

if ! [ -s "$DIR/transcript.txt" ] || grep -q '"error"' "$DIR/transcript.txt"; then
  echo "erreur: transcription vide ou refusee :" >&2
  head -c 300 "$DIR/transcript.txt" >&2; echo >&2
  exit 8
fi

# Menage : on garde l'audio mp3 et le texte, on jette la source brute.
if [ "$GARDER" -eq 0 ]; then
  rm -f "${SRC:?}"
  rm -f "${DIR:?}"/part*.mp3 2>/dev/null
fi

printf '%s\n' "${LANG_HINT:-?}" > "$DIR/lang.txt"

cat "$DIR/meta.txt"
echo
cat "$DIR/transcript.txt"
echo "(source: Groq whisper-large-v3-turbo, langue ${LANG_HINT:-auto} ${LANG_SOURCE}, ${DUREE}s d'audio, $DIR)" >&2
