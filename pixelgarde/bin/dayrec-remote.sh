#!/usr/bin/env bash
# Enregistre la journee du Pixel SANS root, depuis le PC.
#
# Le telephone n'est plus roote : plus de service embarque. C'est donc le PC qui
# capture, par ADB sur Tailscale ou sur le LAN. Consequence a accepter :
# l'enregistrement ne tourne que si le PC est allume ET le telephone joignable
# ET l'ecran allume. Hors de ca, ces instants ne sont pas captures. C'est le
# prix du non-root.
#
# Ecrit exactement ce que dayrec.py attend : ~/DayRec/<jour>/HHMMSS.png + journal.tsv.
# Lancer en continu (service/tmux) : dayrec-remote.sh
#
# Ecrit AUSSI ~/DayRec/.etat a chaque tour. Sans lui, le tableau de bord ne
# saurait dire que « demarre » et mentirait : le service tourne tres bien en
# bouclant a vide sur un telephone absent. Le fichier dit ce qui est REELLEMENT
# joint, et quand la derniere capture a ete prise.

set -uo pipefail
# Lab a son adb dans platform-tools ; hote-1 utilise celui de la distribution.
# Chercher au lieu de figer evite un script par machine.
ADB="${ADB:-}"
[ -n "$ADB" ] || for c in "$HOME/.local/platform-tools/adb" /usr/bin/adb; do
    [ -x "$c" ] && { ADB="$c"; break; }
done
[ -n "$ADB" ] || ADB="$(command -v adb)" || { echo "adb introuvable" >&2; exit 1; }
BASE="$HOME/DayRec"
INTERVAL="${INTERVAL:-2}"
TMP=/tmp/dayrec-remote.png
LOG="$BASE/remote.log"
mkdir -p "$BASE"
log() { echo "$(date '+%F %T') $*" >>"$LOG"; }

ADRESSES="${PIXEL_ADRESSES:-__PIXEL_IP__:5555 __LAN_IP__:5555}"

resoudre() {   # Tailscale d'abord, LAN en repli ; imprime l'adresse joignable
    for a in $ADRESSES; do
        timeout 6 "$ADB" connect "$a" >/dev/null 2>&1
        timeout 6 "$ADB" -s "$a" shell true >/dev/null 2>&1 && { echo "$a"; return 0; }
    done
    return 1
}

ETAT="$BASE/.etat"
NOTIF="$(dirname "$(readlink -f "$0")")/dayrec-notif.sh"

# Le tableau de bord lit ce fichier. `phone` vide = le telephone n'est pas joint,
# et c'est exactement ce qu'il faut afficher plutot qu'un « demarre » trompeur.
ecrire_etat() {
    printf 'phone=%s\nvu=%s\ncapture=%s\n' "$1" "$(date +%s)" "${2:-0}" >"$ETAT.tmp"
    mv -f "$ETAT.tmp" "$ETAT"
}

# La notification tombe si l'utilisateur la balaie. La reposer periodiquement
# garantit qu'un ecran enregistre le dit toujours, meme apres un balayage.
NOTIF_REPOSE=0
annoncer() {
    [ -x "$NOTIF" ] || return 0
    local now; now=$(date +%s)
    [ $((now - NOTIF_REPOSE)) -ge 300 ] || return 0
    NOTIF_REPOSE=$now
    "$NOTIF" on "$1" >/dev/null 2>&1 &
}

log "demarrage"
ecrire_etat "" 0
LAST=""
PHONE=""
DERNIERE=0
while true; do
    # (re)trouver le telephone s'il a disparu
    if [ -z "$PHONE" ] || ! timeout 5 "$ADB" -s "$PHONE" shell true >/dev/null 2>&1; then
        PHONE=""
        ecrire_etat "" "$DERNIERE"
        PHONE=$(resoudre) || { sleep 10; continue; }
        log "connecte a $PHONE"
        NOTIF_REPOSE=0          # nouvelle connexion : reposer le voyant tout de suite
    fi
    annoncer "$PHONE"
    ecrire_etat "$PHONE" "$DERNIERE"

    # ecran allume seulement
    if timeout 5 "$ADB" -s "$PHONE" shell 'dumpsys power' 2>/dev/null | grep -q 'mWakefulness=Awake'; then
        # /data/local/tmp et non /sdcard : le stockage public est indexe par
        # MediaStore, et la capture de travail apparaissait dans la galerie du
        # telephone. /data/local/tmp est accessible au shell ADB sans root et
        # reste invisible des applications photo.
        if timeout 8 "$ADB" -s "$PHONE" shell 'screencap -p /data/local/tmp/_dr.png' >/dev/null 2>&1 \
           && timeout 8 "$ADB" -s "$PHONE" pull /data/local/tmp/_dr.png "$TMP" >/dev/null 2>&1 \
           && [ -s "$TMP" ]; then
            H=$(md5sum "$TMP" | cut -d' ' -f1)
            if [ "$H" != "$LAST" ]; then
                D=$(date '+%Y-%m-%d'); T=$(date '+%H%M%S')
                mkdir -p "$BASE/$D"
                cp "$TMP" "$BASE/$D/$T.png"
                # app au premier plan, sans root : mCurrentFocus -> paquet/activite
                f=$(timeout 5 "$ADB" -s "$PHONE" shell 'dumpsys window' 2>/dev/null \
                    | tr -d '\r' | grep -m1 mCurrentFocus)
                c=${f##* }; c=${c%\}}
                case "$c" in
                    */*) printf '%s\t%s\t%s\n' "$T" "${c%%/*}" "${c#*/}" >>"$BASE/$D/journal.tsv" ;;
                    *)   printf '%s\t%s\t\n' "$T" "$c" >>"$BASE/$D/journal.tsv" ;;
                esac
                LAST="$H"
                DERNIERE=$(date +%s)
            fi
        fi
    fi
    sleep "$INTERVAL"
done
