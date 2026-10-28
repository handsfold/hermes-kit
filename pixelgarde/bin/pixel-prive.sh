#!/usr/bin/env bash
# Deverrouille l'espace prive (user 10) du Pixel, de bout en bout et sans tatonner.
#
# Pourquoi un script a part et pas quelques `input tap` : la sequence est fragile,
# et chaque piege ci-dessous a coute des essais rates avant d'etre compris.
#
#  1. L'ECRAN SE REMET EN VEILLE au milieu de la sequence, qui est longue. On force
#     donc `stayon true` + un long timeout au debut, restaures a la fin.
#  2. La barre de recherche du tiroir GARDE un texte residuel ("gt GT GT..."), ce qui
#     force le mode recherche et fait atterrir les taps a cote. On l'efface.
#  3. La ligne "Prive, verrouille" n'apparait qu'apres avoir DEROULE tout le tiroir,
#     et seulement si `hide_privatespace_entry_point=0` ET le launcher a rele le reglage
#     (force-stop). On defile jusqu'a la trouver, on ne devine pas sa position.
#  4. Le pave de code NE SE VALIDE PAS tout seul : il faut appuyer sur la touche
#     `key_enter`. C'est l'erreur qui faisait croire que le code etait faux.
#
# Le code de l'espace prive est celui de l'appareil (PIXEL_PIN / ~/.config/pixel/pin).
# Usage : pixel-prive.sh [deverrouille|etat]

set -uo pipefail
ADB="$HOME/.local/platform-tools/adb"
TMP=/tmp/pixel-prive-ui.xml
LANCEUR=com.google.android.apps.nexuslauncher

PHONE="${PIXEL_ADDR:-}"
if [ -z "$PHONE" ]; then
    for a in __PIXEL_IP__:5555 __LAN_IP__:5555; do
        "$ADB" connect "$a" >/dev/null 2>&1
        "$ADB" -s "$a" shell true >/dev/null 2>&1 && { PHONE="$a"; break; }
    done
fi
[ -z "$PHONE" ] && { echo "telephone injoignable" >&2; exit 1; }
sh_() { "$ADB" -s "$PHONE" shell "$@"; }

dump() { sh_ 'uiautomator dump /sdcard/pui.xml' >/dev/null 2>&1
         "$ADB" -s "$PHONE" pull /sdcard/pui.xml "$TMP" >/dev/null 2>&1; }

# Renvoie "x y" du centre du 1er noeud dont le texte/desc contient le motif.
# opts : "clickable" pour n'accepter que les cliquables, "right" pour le plus a droite.
trouve() {
    python3 - "$TMP" "$1" "${2:-}" <<'PY'
import sys, xml.etree.ElementTree as ET
chemin, motif, opt = sys.argv[1], sys.argv[2].lower(), sys.argv[3]
try: racine = ET.parse(chemin).getroot()
except Exception: sys.exit(1)
cands = []
for n in racine.iter('node'):
    lab = ((n.get('text') or '') + ' ' + (n.get('content-desc') or '')).strip().lower()
    if motif not in lab: continue
    if 'clickable' in opt and n.get('clickable') != 'true': continue
    try:
        g, d = n.get('bounds', '').split('][')
        x1, y1 = map(int, g.strip('[').split(',')); x2, y2 = map(int, d.strip(']').split(','))
    except ValueError: continue
    cands.append(((x1 + x2) // 2, (y1 + y2) // 2))
if not cands: sys.exit(1)
if 'right' in opt:   cands.sort(key=lambda c: -c[0])   # le plus a droite
elif 'left' in opt:  cands.sort(key=lambda c: c[0])    # le plus a gauche
else:                cands.sort(key=lambda c: c[1])    # le plus haut
print(cands[0][0], cands[0][1])
PY
}

etat_prive() { sh_ 'am get-started-user-state 10' 2>/dev/null | tr -d '\r'; }

deverrouille() {
    case "$(etat_prive)" in
        *RUNNING_UNLOCKED*) echo "espace prive deja deverrouille"; return 0 ;;
    esac

    pin="${PIXEL_PIN:-}"
    [ -z "$pin" ] && [ -r "$HOME/.config/pixel/pin" ] && pin=$(cat "$HOME/.config/pixel/pin")
    [ -z "$pin" ] && { echo "aucun code : PIXEL_PIN ou ~/.config/pixel/pin" >&2; return 1; }

    # garder l'ecran allume pendant toute la sequence
    old_to=$(sh_ 'settings get system screen_off_timeout' 2>/dev/null | tr -d '\r')
    sh_ 'settings put system screen_off_timeout 600000' >/dev/null 2>&1
    sh_ 'svc power stayon true' >/dev/null 2>&1
    restaurer() {
        sh_ 'svc power stayon false' >/dev/null 2>&1
        [ -n "$old_to" ] && sh_ "settings put system screen_off_timeout $old_to" >/dev/null 2>&1
        sh_ 'settings put secure hide_privatespace_entry_point 1' >/dev/null 2>&1  # remasquer
    }
    trap restaurer EXIT

    # ecran principal deverrouille (reutilise l'outil principal)
    "$(dirname "$0")/pixel-ctl.sh" deverrouille >/dev/null 2>&1 || true

    # reveler l'entree de l'espace prive et forcer le launcher a relire le reglage
    sh_ 'settings put secure hide_privatespace_entry_point 0' >/dev/null 2>&1
    sh_ "am force-stop $LANCEUR" >/dev/null 2>&1; sleep 2
    sh_ 'input keyevent 3' >/dev/null 2>&1; sleep 1
    sh_ 'input swipe 504 2000 504 400 300' >/dev/null 2>&1; sleep 1

    # effacer un eventuel texte residuel dans la recherche du tiroir
    dump
    if croix=$(trouve "effacer" clickable 2>/dev/null); then
        sh_ "input tap $croix" >/dev/null 2>&1; sleep 1
    fi

    # defiler jusqu'a voir "Prive, verrouille". Taper le CENTRE de la ligne (le plus
    # a gauche des cliquables), pas le cadenas du bord droit : ce dernier frole la
    # zone de gestes et rate une fois sur deux.
    cadenas=""
    for _ in $(seq 1 14); do
        dump
        if cadenas=$(trouve "verrouill" "clickable left" 2>/dev/null); then break; fi
        sh_ 'input swipe 504 1600 504 600 200' >/dev/null 2>&1; sleep 0.5
    done
    [ -z "$cadenas" ] && { echo "ligne 'Prive' introuvable dans le tiroir" >&2; return 1; }
    sh_ "input tap $cadenas" >/dev/null 2>&1; sleep 3

    # Attendre le pave de code. Deux surprises : l'invite biometrique s'affiche AVANT
    # le pave et met parfois >2 s a venir ; et selon les cas on tombe direct sur le
    # pave, sans passer par "Utiliser le code". On boucle donc jusqu'a voir les touches.
    pave_pret() {   # imprime les coordonnees "digit x y" et "enter x y", vide si absent
        python3 - "$TMP" <<'PY'
import sys, xml.etree.ElementTree as ET
r = ET.parse(sys.argv[1]).getroot()
out = {}
for n in r.iter('node'):
    t = (n.get('text') or '').strip()
    rid = n.get('resource-id', '').split('/')[-1]
    b = n.get('bounds', '').split('][')
    try:
        g, d = b[0].strip('['), b[1].strip(']')
        x = (int(g.split(',')[0]) + int(d.split(',')[0])) // 2
        y = (int(g.split(',')[1]) + int(d.split(',')[1])) // 2
    except (ValueError, IndexError):
        continue
    if t.isdigit() and len(t) == 1:
        out[t] = (x, y)                # les chiffres sont des noeuds texte, sans id
    elif rid.endswith('key_enter'):
        out['enter'] = (x, y)
if all(str(k) in out for k in range(10)) and 'enter' in out:
    print(' '.join(f"{k}:{out[k][0]},{out[k][1]}" for k in list('0123456789') + ['enter']))
PY
    }
    coords=""
    for _ in $(seq 1 10); do
        dump
        # si le bouton "Utiliser le code" est la, le presser pour reveler le pave
        if cb=$(trouve "utiliser le code" clickable 2>/dev/null); then
            sh_ "input tap $cb" >/dev/null 2>&1; sleep 1.5; dump
        fi
        coords=$(pave_pret)
        [ -n "$coords" ] && break
        sleep 1
    done
    [ -z "$coords" ] && { echo "pave de code non atteint" >&2; return 1; }

    # taper le code par les coordonnees relevees, puis ENTREE
    seq=""
    i=0
    while [ "$i" -lt "${#pin}" ]; do
        c=$(printf '%s' "$pin" | cut -c$((i + 1)))
        xy=$(echo "$coords" | tr ' ' '\n' | grep "^$c:" | cut -d: -f2 | tr ',' ' ')
        seq="$seq input tap $xy;"
        i=$((i + 1))
    done
    ent=$(echo "$coords" | tr ' ' '\n' | grep '^enter:' | cut -d: -f2 | tr ',' ' ')
    sh_ "$seq" >/dev/null 2>&1; sleep 0.5
    sh_ "input tap $ent" >/dev/null 2>&1
    sleep 2.5

    case "$(etat_prive)" in
        *RUNNING_UNLOCKED*) echo "espace prive deverrouille"; return 0 ;;
        *) echo "echec : etat = $(etat_prive)" >&2; return 1 ;;
    esac
}

case "${1:-deverrouille}" in
    deverrouille) deverrouille ;;
    etat)         echo "user 10 : $(etat_prive)" ;;
    *)            echo "usage: pixel-prive.sh [deverrouille|etat]" ;;
esac
