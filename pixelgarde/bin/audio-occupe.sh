#!/usr/bin/env bash
# Le telephone est-il deja en train de jouer quelque chose ?
#
# Code 0 : occupe. Code 1 : libre. Code 2 : injoignable, donc on ne sait pas.
#
# On ne veut pas couper la parole a USER. S'il est en appel ou ecoute une note
# vocale Telegram, un rapport qui parle par-dessus est une agression. Musique
# et video, elles, baissent le temps du rapport. Le rapport part quand meme
# dans le QG ; seule la lecture sur l'appareil attend que la voie soit libre.
#
# La source est `dumpsys audio`, section players. Chaque flux y porte un etat
# (started, paused, stopped, idle) et un usage. Seul `started` compte, et
# seulement pour les usages qui occupent vraiment l'oreille : un bip de
# notification ou un retour haptique n'est pas une ecoute.
set -uo pipefail

ADDR="${1:-$(adb devices | awk '/device$/{print $1; exit}')}"
[ -n "$ADDR" ] || exit 2

# Musique et video ne bloquent plus (USER, 2026-10-05) : le service Voix baisse
# leur son le temps du rapport (focus GAIN_TRANSIENT_MAY_DUCK). USAGE_MEDIA et
# USAGE_GAME n'occupent la voie que pour Telegram (une note vocale s'ecoute)
# et pour notre propre voix. Meme regle que audio_occupe() dans pixel-garde.
PROTEGEES='org.telegram.messenger|org.telegram.messenger.web|com.poste.pixelgarde'
SORTIE="$(timeout 12 adb -s "$ADDR" shell \
  "dumpsys audio | grep -E 'AudioPlaybackConfiguration.*state:started'; echo ===; cmd package list packages -U | grep -E '$PROTEGEES'" 2>/dev/null)" || exit 2
FLUX="$(printf '%s\n' "$SORTIE" | sed '/^===$/,$d')"
UIDS="$(printf '%s\n' "$SORTIE" | sed '1,/^===$/d' | grep -oE 'uid:[0-9,]+' | cut -d: -f2 | tr ',' '\n' | paste -sd'|' -)"
[ -n "$FLUX" ] || exit 1

# USAGE_ASSISTANCE_SONIFICATION et USAGE_NOTIFICATION_* sont volontairement
# absents : ce sont des sons courts, et attendre leur fin ne veut rien dire.
OCCUPE="$(printf '%s\n' "$FLUX" | grep -E 'usage=(USAGE_VOICE_COMMUNICATION|USAGE_ALARM|USAGE_ASSISTANT)')"
if [ -n "$UIDS" ]; then
  OCCUPE="$OCCUPE
$(printf '%s\n' "$FLUX" | grep -E "u/pid:($UIDS)/" | grep -E 'usage=(USAGE_MEDIA|USAGE_GAME)')"
fi
OCCUPE="$(printf '%s\n' "$OCCUPE" | sed '/^$/d')"
[ -n "$OCCUPE" ] || exit 1

printf '%s\n' "$OCCUPE" | grep -oE 'u/pid:[0-9]+|usage=[A-Z_]+' | paste -sd' ' -
exit 0
