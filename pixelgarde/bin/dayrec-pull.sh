#!/usr/bin/env bash
# Rapatrie les captures du Pixel 9 Pro XL (komodo) vers cette machine,
# les convertit en JPEG, puis libere le telephone.
#
# Usage : dayrec-pull.sh [--today]
#   --today  rapatrie aussi le jour en cours (fichiers possiblement en ecriture)

set -uo pipefail

ADB="$HOME/.local/platform-tools/adb"
REMOTE_BASE="/sdcard/DayRec"
LOCAL_BASE="$HOME/DayRec"
QUALITE=70
ECHELLE="50%"
LOG="$LOCAL_BASE/pull.log"

mkdir -p "$LOCAL_BASE"
log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

# --- connexion ---------------------------------------------------------------
# Tailscale d'abord : l'IP du LAN depend du bail DHCP et casse le cron sans bruit.
# timeout sur chaque essai : `adb connect` vers une adresse Tailscale hors ligne
# attend la fin du timeout TCP, et le cycle de 2 h y restait plante sans un mot.
PHONE=""
for A in __PIXEL_IP__:5555 __LAN_IP__:5555; do
    timeout 8 "$ADB" connect "$A" >/dev/null 2>&1
    if timeout 8 "$ADB" -s "$A" shell true >/dev/null 2>&1; then
        PHONE="$A"
        break
    fi
done
if [ -z "$PHONE" ]; then
    log "telephone injoignable (Tailscale et LAN), abandon"
    exit 1
fi
log "connecte a $PHONE"

# --- quelles journees rapatrier ? --------------------------------------------
AUJOURDHUI=$(date '+%Y-%m-%d')
JOURS=$("$ADB" -s "$PHONE" shell "su -c 'ls -1 $REMOTE_BASE'" 2>/dev/null \
        | tr -d '\r' | grep -E '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$' | sort)

[ "${1:-}" = "--today" ] || JOURS=$(echo "$JOURS" | grep -v "^${AUJOURDHUI}$")

if [ -z "$JOURS" ]; then
    log "rien a rapatrier"
    exit 0
fi

# --- rapatriement ------------------------------------------------------------
for J in $JOURS; do
    DEST="$LOCAL_BASE/$J"
    mkdir -p "$DEST"

    NB_AVANT=$("$ADB" -s "$PHONE" shell "su -c 'ls -1 $REMOTE_BASE/$J | wc -l'" 2>/dev/null | tr -d '\r')
    log "$J : $NB_AVANT captures a rapatrier"

    # Les fichiers appartiennent a root : les rendre lisibles avant le pull.
    # a+rX et non 644 : X ne rend traversables que les dossiers, et `ui/` en est un.
    "$ADB" -s "$PHONE" shell "su -c 'chmod -R a+rX $REMOTE_BASE/$J'" >/dev/null 2>&1

    # Le telephone renvoie ses .tsv en entier a chaque cycle et adb pull ecrase.
    # On garde donc la copie locale pour la fondre dans la nouvelle : sans cela,
    # la journee du matin disparaissait a chaque passage de l'apres-midi.
    for T in journal.tsv actions.tsv; do
        [ -f "$DEST/$T" ] && cp "$DEST/$T" "$DEST/.$T.avant"
    done

    if ! "$ADB" -s "$PHONE" pull -a "$REMOTE_BASE/$J/." "$DEST/" >/dev/null 2>&1; then
        log "$J : echec du transfert, journee conservee sur le telephone"
        continue
    fi

    # sort -u sur la ligne entiere : elle commence par l'heure, donc l'ordre
    # lexicographique est l'ordre chronologique, et les doublons tombent seuls.
    for T in journal.tsv actions.tsv; do
        if [ -f "$DEST/.$T.avant" ]; then
            sort -u "$DEST/.$T.avant" "$DEST/$T" 2>/dev/null >"$DEST/.$T.fusion" \
                && mv "$DEST/.$T.fusion" "$DEST/$T"
            rm -f "$DEST/.$T.avant" "$DEST/.$T.fusion"
        fi
    done

    NB_LOCAL=$(find "$DEST" -name '*.png' | wc -l)
    if [ "$NB_LOCAL" -eq 0 ]; then
        log "$J : aucun PNG recu, journee conservee"
        continue
    fi

    # conversion JPEG, en parallele
    find "$DEST" -name '*.png' -print0 \
        | xargs -0 -P "$(nproc)" -n 20 magick mogrify \
              -format jpg -quality "$QUALITE" -resize "$ECHELLE" 2>/dev/null

    NB_JPG=$(find "$DEST" -name '*.jpg' | wc -l)
    if [ "$NB_JPG" -lt "$NB_LOCAL" ]; then
        log "$J : conversion incomplete ($NB_JPG/$NB_LOCAL), PNG et telephone conserves"
        continue
    fi

    find "$DEST" -name '*.png' -delete

    # Le jour en cours garde ses .tsv sur le telephone : ils s'y ecrivent encore,
    # et un rm -rf effacerait les gestes des minutes de conversion. Les images et
    # les arbres deja transferes partent, eux : c'est tout le poids.
    if [ "$J" = "$AUJOURDHUI" ]; then
        "$ADB" -s "$PHONE" shell \
            "su -c 'find $REMOTE_BASE/$J -name \"*.png\" -delete; find $REMOTE_BASE/$J/ui -name \"*.tsv\" -mmin +2 -delete'" \
            >/dev/null 2>&1
    else
        "$ADB" -s "$PHONE" shell "su -c 'rm -rf $REMOTE_BASE/$J'" >/dev/null 2>&1
    fi

    POIDS=$(du -sh "$DEST" | cut -f1)
    log "$J : $NB_JPG images, $POIDS, telephone libere"
done

log "fin. total local : $(du -sh "$LOCAL_BASE" | cut -f1)"
