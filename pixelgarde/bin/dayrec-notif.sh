#!/usr/bin/env bash
# Prévient sur le téléphone que son écran est enregistré.
#
# Enregistrer un écran sans que son porteur le voie est inacceptable. Android ne
# montre rien pour `screencap` - pas de point vert comme pour le micro ou la
# caméra - donc c'est à nous de poser le voyant.
#
#   dayrec-notif.sh on [adresse]    pose la notification
#   dayrec-notif.sh off [adresse]   la retire
#
# Sans adresse, la lit dans ~/DayRec/.etat (écrit par dayrec-remote.sh).
#
# ⚠️ `cmd notification` n'a PAS de sous-commande `cancel`. Le seul retrait
# disponible au shell est `snooze` sur une très longue durée, et une notification
# endormie IGNORE les posts suivants : il faut `unsnooze` avant de reposer.
# D'où l'ordre unsnooze → post dans `poser`.
set -uo pipefail

ADB="${ADB:-}"
[ -n "$ADB" ] || for c in "$HOME/.local/platform-tools/adb" /usr/bin/adb; do
    [ -x "$c" ] && { ADB="$c"; break; }
done
[ -n "$ADB" ] || ADB="$(command -v adb)" || exit 0

ACTION="${1:-}"
PHONE="${2:-}"
[ -n "$PHONE" ] || PHONE="$(sed -n 's/^phone=//p' "$HOME/DayRec/.etat" 2>/dev/null)"
# Pas de téléphone joignable : rien à annoncer, et surtout pas d'échec bruyant.
[ -n "$PHONE" ] || exit 0

TAG=dayrec
TITRE="Écran enregistré"
TEXTE="Cet écran est capturé vers hote-1. Coupe-le depuis le tableau de bord."

adbsh() { timeout 12 "$ADB" -s "$PHONE" shell "$@" 2>/dev/null; }

# ⚠️ `cmd notification list` ne montre QUE les notifications visibles. Une
# notification endormie en disparaît - c'est ce qui a cassé la première version :
# après un `off`, `poser` ne trouvait plus de clé, ne réveillait rien, et son
# post était avalé par le sommeil. La clé endormie se lit dans `dumpsys`.
cle() {
    local k
    k="$(adbsh 'cmd notification list' | grep -m1 "|$TAG|")"
    [ -n "$k" ] || k="$(adbsh 'dumpsys notification' \
        | sed -n "s/^ *key: \(.*|$TAG|.*\)$/\1/p" | head -1)"
    printf '%s' "${k//$'\r'/}"
}

poser() {
    local k; k="$(cle)"
    [ -n "$k" ] && adbsh "cmd notification unsnooze '$k'" >/dev/null
    adbsh "cmd notification post -S bigtext -t '$TITRE' $TAG '$TEXTE'" >/dev/null
}

retirer() {
    local k; k="$(cle)"
    [ -n "$k" ] || return 0
    # Un an : la notification ne doit pas réapparaître d'elle-même. `poser`
    # la réveillera au prochain démarrage.
    adbsh "cmd notification snooze --for 31536000000 '$k'" >/dev/null
}

case "$ACTION" in
    on)  poser ;;
    off) retirer ;;
    *)   echo "usage: dayrec-notif.sh on|off [adresse]" >&2; exit 2 ;;
esac
