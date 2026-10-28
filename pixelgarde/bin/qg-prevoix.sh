#!/usr/bin/env bash
# Fabrique la voix d'un rapport A L'AVANCE, avant que USER appuie sur son bouton.
#
# Le 2026-08-29, USER a chronometre l'appui : quatre a dix secondes entre le doigt
# et le son. Le rapport etait pourtant deja ecrit et en base. Tout ce temps
# partait dans edge-tts, appele au moment de l'appui : 4 s pour trois phrases,
# davantage pour un vrai rapport, plus un aller-retour reseau.
#
# On paye donc ce cout des l'arrivee du rapport en file, pendant que USER fait
# autre chose. A l'appui, il ne reste qu'un `am start` : 0,3 s. Le mp3 est meme
# POUSSE sur le telephone d'avance, pour que l'appui n'attende pas non plus adb.
#
# Le prix : quelques secondes de CPU et un appel reseau pour un rapport que USER
# n'ecoutera peut-etre jamais. C'est le marche qu'il a demande, et le garde ne
# prefabrique que les cinq rapports visibles dans son menu.
set -euo pipefail

ID="${1:?usage: qg-prevoix.sh <id> [addr]}"
ADDR="${2:-}"
FILE="$HOME/.hermes/scripts/qg-attente.py"
CACHE="$HOME/.hermes/qg-voix"
TEL_VOIX="/sdcard/Android/data/com.poste.pixelgarde/files/voix"
# Tous les reglages du QG en un seul appel : voix, debit, modele, salon, delais.
# Ils se changent dans ~/.hermes/qg-config.json, jamais ici. `qg-config.py` sans
# argument les affiche tous avec leur origine.
eval "$("$HOME/.hermes/scripts/qg-config.py" env)"
VOIX="$QGC_VOIX"
DEBIT="$QGC_DEBIT"
# La bulle Telegram, elle, sort toujours de bin/voix-telegram.sh (debit naturel).
VOIX_TG="$(dirname "$(readlink -f "$0")")/../voix-telegram.sh"

mkdir -p "$CACHE"
# Deja fait : on ne refabrique pas.
[ -s "$CACHE/$ID.ogg" ] && [ -s "$CACHE/$ID.mp3" ] && exit 0

# Un seul prefabricant par rapport. Le garde relance sa boucle chaque seconde :
# sans ce verrou, dix edge-tts partiraient en parallele sur le meme texte.
exec 9>"${PIXEL_TMP:-/tmp}/qg-prevoix-$ID.lock"
flock -n 9 || exit 0

# « voix » et pas « texte » : le markdown est retire, sinon la synthese recite
# les asterisques du gras, une par une, a chaque rapport.
TXT="$("$FILE" voix "$ID" 2>/dev/null || true)"
[ -n "$TXT" ] || exit 0
# Le nom du topic ouvre la voix : sans lui, USER ne sait pas de quel chantier
# on lui parle (2026-10-03). Il est note a cote du mp3 : rapport.sh refait la
# voix si USER renomme le topic avant d'ecouter.
SUJET="$("$FILE" sujet "$ID" 2>/dev/null || true)"
DIT="$TXT"
[ -n "$SUJET" ] && DIT="Rapport $SUJET. $TXT"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# 2 syntheses en parallele : le mp3 au debit du telephone, la bulle Telegram
# par le script commun, au debit naturel.
edge-tts --voice "$VOIX" --rate="$DEBIT" --text "$DIT" \
  --write-media "$TMP/r.mp3" >/dev/null 2>&1 &
P1=$!
printf '%s' "$DIT" | "$VOIX_TG" "$TMP/r.ogg" 2>/dev/null &
P2=$!
# Et les boutons devines pour ce rapport, d'apres le profil de USER : <id>.choix
# et <id>.libelles, que rapport.sh passe au telephone a l'ecoute. Un echec
# laisse Oui Non Detail, rien ne l'attend.
STANDARD="$(dirname "$(readlink -f "$0")")/../qg/qg-standard.py"
printf '%s' "$TXT" | timeout 60 python3 "$STANDARD" rapport "$ID" >/dev/null \
  2>>"$HOME/.hermes/logs/qg-standard.log" &
P3=$!
wait "$P2" || exit 0
wait "$P1" || exit 0
[ -s "$TMP/r.mp3" ] && [ -s "$TMP/r.ogg" ] || exit 0

# Ecriture atomique : rapport.sh lit ce dossier sans verrou, il ne doit jamais
# tomber sur un mp3 a moitie ecrit.
mv "$TMP/r.mp3" "$CACHE/$ID.mp3.part" && mv "$CACHE/$ID.mp3.part" "$CACHE/$ID.mp3"
mv "$TMP/r.ogg" "$CACHE/$ID.ogg.part" && mv "$CACHE/$ID.ogg.part" "$CACHE/$ID.ogg"
printf '%s' "$SUJET" > "$CACHE/$ID.nom"

# Et sur le telephone, d'avance. L'arret d'urgence est souverain : on ne touche
# pas au telephone tant qu'il est arme.
if [ -n "$ADDR" ] && [ ! -e "${PIXEL_TMP:-/tmp}/pixel-stop" ]; then
  if adb -s "$ADDR" push "$CACHE/$ID.mp3" "$TEL_VOIX/qg-pre-$ID.mp3" >/dev/null 2>&1; then
    touch "$CACHE/$ID.pousse"
  fi
fi
# Puis, les boutons devines, la phrase qui les dit en mains libres.
wait "$P3" || true
"$(dirname "$(readlink -f "$0")")/qg-dire-choix.sh" "$ID" "$ADDR" || true
echo "voix prete pour le rapport $ID ($(stat -c%s "$CACHE/$ID.mp3") octets)" >&2
