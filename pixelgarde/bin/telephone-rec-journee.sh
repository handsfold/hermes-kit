#!/system/bin/sh
# Enregistre la journee : une capture toutes les INTERVAL secondes, ecran allume
# seulement, ecrans identiques ignores.
#
# Chaque capture retenue ecrit AUSSI une ligne dans journal.tsv :
#     HHMMSS <TAB> paquet <TAB> activite
# Sans cette ligne, une image n'est qu'un tas de pixels : c'est elle qui permet
# de classer la journee par application sans rien deviner.
#
# Copie de reference ; l'original tourne en /data/adb/rec-journee.sh

INTERVAL="${INTERVAL:-2}"
BASE="${BASE:-/sdcard/DayRec}"
TMP=/data/local/tmp/_dayrec.png
LAST=""

# Application au premier plan, sous la forme "paquet<TAB>activite".
# Coute ~60 ms contre ~450 ms pour la capture : negligeable.
app_active() {
    f=$(dumpsys window 2>/dev/null | grep -m1 mCurrentFocus)
    case "$f" in
        *Window\{*) ;;
        *) echo "inconnu	inconnu"; return ;;
    esac
    c=${f##* }          # "paquet/activite}"
    c=${c%\}}
    case "$c" in
        */*) echo "${c%%/*}	${c#*/}" ;;
        *)   echo "$c	" ;;   # ecran de verrouillage, boite de dialogue systeme
    esac
}

while true; do
    if dumpsys power 2>/dev/null | grep -q 'mWakefulness=Awake'; then
        screencap -p "$TMP" 2>/dev/null
        if [ -s "$TMP" ]; then
            H=$(md5sum "$TMP" | cut -d' ' -f1)
            if [ "$H" != "$LAST" ]; then
                D=$(date '+%Y-%m-%d')
                T=$(date '+%H%M%S')
                mkdir -p "$BASE/$D"
                cp "$TMP" "$BASE/$D/$T.png"
                printf '%s\t%s\n' "$T" "$(app_active)" >>"$BASE/$D/journal.tsv"
                LAST="$H"
            fi
        fi
    fi
    sleep "$INTERVAL"
done
