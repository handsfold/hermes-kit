#!/usr/bin/env bash
# Lit un texte a voix haute sur le Pixel, en accelere, via edge-tts et le
# service .Voix de pixelgarde (action VOIXDIRE : joue un mp3 puis s'eteint).
#
#   lire-voix.sh <addr> <fichier-texte> <etiquette>
#
# Un appel pendant qu'une lecture est en cours l'ARRETE (VOIXFIN) et sort :
# c'est ce qui fait qu'un second appui sur le bouton coupe la voix.
# Le debit vient de la cle `debit` de ~/.hermes/qg-config.json (menu Vitesse)
# (defaut +75%). La voix est celle du QG.
set -uo pipefail
ADDR="${1:?addr}"; SRC="${2:?fichier texte}"; ETIQ="${3:-lecture}"
ETAT=/tmp/pixel-lecture.etat
TEL_VOIX="/sdcard/Android/data/com.poste.pixelgarde/files/voix"
eval "$("$HOME/.hermes/scripts/qg-config.py" env)"
VOIX="${QGC_VOIX:-fr-FR-HenriNeural}"
DEBIT="${QGC_LECTURE_DEBIT:-+75%}"

couper() {
  adb -s "$ADDR" shell am start-foreground-service \
    -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIXFIN >/dev/null 2>&1
  rm -f "${ETAT:?}"
}

# Lecture en cours ? (debut + duree encore devant nous) : on coupe, on sort.
if [ -s "$ETAT" ]; then
  read -r DEBUT DUREE _ < "$ETAT"
  if [ "$(date +%s)" -lt $((DEBUT + DUREE + 1)) ]; then
    couper; echo "lecture coupee par un second appui"; exit 0
  fi
  rm -f "${ETAT:?}"
fi

# Le texte, borne : au-dela de 6000 caracteres, edge-tts met plus d'une minute.
TXT="$(head -c 6000 "$SRC" | tr -s ' \t' ' ' | sed '/^\s*$/d')"
if [ -z "$TXT" ]; then
  TXT="$ETIQ : rien a lire."
fi

TMP="$(mktemp -d)"; trap 'rm -rf "${TMP:?}"' EXIT
printf '%s\n' "$TXT" > "$TMP/t.txt"
if ! timeout 90 edge-tts --voice "$VOIX" --rate="$DEBIT" -f "$TMP/t.txt" \
     --write-media "$TMP/r.mp3" >/dev/null 2>&1 || [ ! -s "$TMP/r.mp3" ]; then
  echo "edge-tts a echoue ($(wc -c < "$TMP/t.txt") octets)"; exit 1
fi
DUREE="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMP/r.mp3" 2>/dev/null | cut -d. -f1)"
DUREE="${DUREE:-60}"
NOM="lecture-$(date +%s).mp3"
adb -s "$ADDR" push "$TMP/r.mp3" "$TEL_VOIX/$NOM" >/dev/null 2>&1 || { echo "push impossible"; exit 1; }
adb -s "$ADDR" shell am start-foreground-service \
  -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIXDIRE --es fichier "$NOM" >/dev/null 2>&1 \
  || { echo "service Voix injoignable"; exit 1; }
printf '%s %s %s\n' "$(date +%s)" "$DUREE" "$NOM" > "$ETAT"
echo "$ETIQ : $(wc -c < "$TMP/t.txt") octets, $DUREE s a $DEBIT ($NOM)"
