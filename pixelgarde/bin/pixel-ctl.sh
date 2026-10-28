#!/usr/bin/env bash
# Pilotage du Pixel 9 Pro XL depuis cette machine.
# Cible les elements par leur texte affiche plutot que par coordonnees.

set -uo pipefail

ADB="${ADB:-$(command -v adb 2>/dev/null || echo "$HOME/.local/platform-tools/adb")}"
TMP_XML="/tmp/pixel-ctl-ui.xml"
CACHE_ADDR="/tmp/pixel-ctl-adresse"

# Trouve le telephone sans qu'on ait a connaitre son reseau.
# Tailscale d'abord : marche depuis n'importe quel poste et n'importe ou.
# Repli sur le LAN de la maison, dont l'IP peut bouger au gre du DHCP.
# PIXEL_ADDR force la valeur si besoin.
resoudre_adresse() {
    [ -n "${PIXEL_ADDR:-}" ] && { echo "$PIXEL_ADDR"; return; }
    if [ -s "$CACHE_ADDR" ]; then
        a=$(cat "$CACHE_ADDR")
        timeout 8 "$ADB" -s "$a" shell true >/dev/null 2>&1 && { echo "$a"; return; }
    fi
    # timeout sur chaque essai : quand le telephone est hors ligne sur Tailscale,
    # `adb connect` attend la fin du timeout TCP et la commande semble figee.
    for a in __PIXEL_IP__:5555 __LAN_IP__:5555; do
        timeout 8 "$ADB" connect "$a" >/dev/null 2>&1
        if timeout 8 "$ADB" -s "$a" shell true >/dev/null 2>&1; then
            echo "$a" >"$CACHE_ADDR"
            echo "$a"
            return
        fi
    done
    echo "telephone injoignable : ni Tailscale (__PIXEL_IP__) ni LAN (__LAN_IP__)" >&2
    exit 1
}
PHONE=$(resoudre_adresse)

sh_() { "$ADB" -s "$PHONE" shell "$@"; }

dump_ui() {
    if [ -z "${ECRAN_L:-}" ]; then
        taille=$(sh_ 'wm size' 2>/dev/null | tr -d '\r' | grep -oE '[0-9]+x[0-9]+' | head -1)
        export ECRAN_L="${taille%x*}" ECRAN_H="${taille#*x}"
    fi
    sh_ 'uiautomator dump /sdcard/ui.xml' >/dev/null 2>&1
    "$ADB" -s "$PHONE" pull /sdcard/ui.xml "$TMP_XML" >/dev/null 2>&1
}

# Attend que l'ecran cesse de bouger : cliquer pendant une animation rate la cible,
# car l'element a deja quitte la position lue dans l'arbre.
stabiliser() {
    precedent=""
    for _ in 1 2 3 4 5 6; do
        dump_ui
        courant=$(md5sum "$TMP_XML" 2>/dev/null | cut -d' ' -f1)
        [ -n "$courant" ] && [ "$courant" = "$precedent" ] && return 0
        precedent="$courant"
        sleep 1
    done
    return 0
}

# Cherche un noeud dont le texte ou la description correspond au motif.
# Affiche "X Y texte", correspondances exactes d'abord, puis de haut en bas.
# Ignore ce qui deborde de l'ecran : un element hors zone visible n'est pas cliquable.
chercher() {
    python3 - "$TMP_XML" "$1" "${2:-non}" "${ECRAN_L:-1080}" "${ECRAN_H:-2400}" <<'PY'
import sys, xml.etree.ElementTree as ET
chemin, motif, cliquables_seuls = sys.argv[1], sys.argv[2].lower(), sys.argv[3] == "oui"
larg, haut = int(sys.argv[4]), int(sys.argv[5])
try:
    racine = ET.parse(chemin).getroot()
except Exception:
    sys.exit(2)

trouves = []
for n in racine.iter('node'):
    txt, desc = n.get('text', '').strip(), n.get('content-desc', '').strip()
    label = txt or desc
    combine = (txt + ' ' + desc).strip().lower()
    if motif and motif not in combine:
        continue
    if cliquables_seuls and n.get('clickable') != 'true':
        continue
    if n.get('enabled') == 'false':
        continue
    try:
        g, d = n.get('bounds', '').split('][')
        x1, y1 = map(int, g.strip('[').split(','))
        x2, y2 = map(int, d.strip(']').split(','))
    except ValueError:
        continue
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    # hors ecran, surface nulle, ou colle au bord bas (barre systeme) : inutilisable
    if not (0 <= cx < larg and 0 <= cy < haut - 40):
        continue
    if x2 <= x1 or y2 <= y1:
        continue
    if motif:
        exact = combine == motif
        debut = combine.startswith(motif)
        rang = 0 if exact else (1 if debut else 2)
    else:
        rang = 0
    trouves.append((rang, cy, cx, label[:50]))

for rang, cy, cx, label in sorted(trouves):
    print(cx, cy, label)
PY
}

usage() {
    cat <<'EOF'
pixel-ctl.sh - pilotage du Pixel depuis le PC

  etat                    app au premier plan et resolution
  apps                    applications installees par l'utilisateur
  open <paquet>           lancer une application
  ui                      elements visibles a l'ecran
  click <texte>           cliquer sur l'element portant ce texte
  find <texte>            coordonnees sans cliquer
  attendre <texte> [sec]  attendre qu'un texte apparaisse (defaut 15 s)
  tap <x> <y>             taper a des coordonnees
  swipe <x1> <y1> <x2> <y2> [ms]
  saisir <texte>          taper du texte au clavier
  touche <nom>            back, home, entree, recents, power, volup, voldown
  shot [fichier.png]      capture d'ecran vers le PC
  deverrouille            reveille et saisit le code PIN (voir PIXEL_PIN)
EOF
}

case "${1:-}" in
    etat)
        sh_ 'dumpsys window' 2>/dev/null | tr -d '\r' | grep -m1 mCurrentFocus
        sh_ 'wm size; wm density' 2>/dev/null | tr -d '\r'
        ;;
    apps)
        sh_ 'pm list packages -3' | tr -d '\r' | sed 's/^package://' | sort
        ;;
    open)
        [ $# -ge 2 ] || { echo "usage: open <paquet>"; exit 1; }
        sh_ "monkey -p $2 -c android.intent.category.LAUNCHER 1" >/dev/null 2>&1
        echo "lance: $2"
        ;;
    ui)
        dump_ui
        chercher "" non | grep -vE '^[0-9]+ +[0-9]+ *$' \
            | sed 's/^\([0-9]*\) \([0-9]*\) /[\1,\2] /'
        ;;
    find|click)
        [ $# -ge 2 ] || { echo "usage: $1 <texte>"; exit 1; }
        shift_cmd="$1"; shift
        motif="$*"
        if [ "$shift_cmd" = "click" ]; then stabiliser; else dump_ui; fi
        res=$(chercher "$motif" oui)
        [ -z "$res" ] && res=$(chercher "$motif" non)

        # pas a l'ecran : faire defiler pour aller le chercher
        if [ -z "$res" ] && [ "$shift_cmd" = "click" ]; then
            cx=$((ECRAN_L / 2)); yh=$((ECRAN_H * 7 / 10)); yb=$((ECRAN_H * 3 / 10))
            for essai in 1 2 3 4 5; do
                sh_ "input swipe $cx $yh $cx $yb 250" >/dev/null 2>&1
                sleep 1
                dump_ui
                res=$(chercher "$motif" oui)
                [ -z "$res" ] && res=$(chercher "$motif" non)
                if [ -n "$res" ]; then
                    echo "trouve apres $essai defilement(s)"
                    break
                fi
            done
        fi

        if [ -z "$res" ]; then
            echo "introuvable: $motif" >&2
            exit 1
        fi
        read -r x y label <<<"$(echo "$res" | head -1)"
        if [ "$shift_cmd" = "click" ]; then
            avant=$(md5sum "$TMP_XML" 2>/dev/null | cut -d' ' -f1)
            sh_ "input tap $x $y" >/dev/null 2>&1
            sleep 1

            # Un tap pres du bord bas tombe parfois dans la zone de gestes Android
            # et n'atteint pas l'application : on retente une fois.
            # Attention : un arbre inchange ne prouve PAS l'echec (ouvrir le clavier
            # ou donner le focus ne modifie pas le dump). D'ou un simple avertissement.
            dump_ui
            apres=$(md5sum "$TMP_XML" 2>/dev/null | cut -d' ' -f1)
            if [ "$avant" = "$apres" ]; then
                sh_ "input tap $x $y" >/dev/null 2>&1
                sleep 1
                dump_ui
                apres=$(md5sum "$TMP_XML" 2>/dev/null | cut -d' ' -f1)
                [ "$avant" = "$apres" ] \
                    && echo "clic sur \"$label\" en [$x,$y] (ecran inchange, a verifier)" \
                    || echo "clic sur \"$label\" en [$x,$y] (2e essai)"
            else
                echo "clic sur \"$label\" en [$x,$y]"
            fi
        else
            echo "$res" | sed 's/^\([0-9]*\) \([0-9]*\) /[\1,\2] /'
        fi
        ;;
    attendre)
        [ $# -ge 2 ] || { echo "usage: attendre <texte> [sec]"; exit 1; }
        motif="$2"; limite="${3:-15}"; i=0
        while [ "$i" -lt "$limite" ]; do
            dump_ui
            if [ -n "$(chercher "$motif" non)" ]; then
                echo "apparu apres ${i}s: $motif"
                exit 0
            fi
            sleep 1
            i=$((i + 1))
        done
        echo "absent apres ${limite}s: $motif" >&2
        exit 1
        ;;
    tap)     sh_ "input tap $2 $3" >/dev/null 2>&1; echo "tap [$2,$3]" ;;
    swipe)   sh_ "input swipe $2 $3 $4 $5 ${6:-300}" >/dev/null 2>&1; echo "swipe [$2,$3] -> [$4,$5]" ;;
    saisir)
        shift
        sh_ "input text '$(printf '%s' "$*" | sed "s/ /%s/g")'" >/dev/null 2>&1
        echo "saisi: $*"
        ;;
    touche)
        case "${2:-}" in
            back)    k=4 ;;   home)    k=3 ;;   entree) k=66 ;;
            recents) k=187 ;; power)   k=26 ;;  volup)  k=24 ;;
            voldown) k=25 ;;  *)       k="${2:-}" ;;
        esac
        sh_ "input keyevent $k" >/dev/null 2>&1; echo "touche: ${2:-} ($k)"
        ;;
    shot)
        # Telephone non roote : screencap tourne en shell, sans su. Les ecrans
        # FLAG_SECURE ressortent noirs (le contournement Xposed est parti avec le root).
        dest="${2:-capture-$(date +%H%M%S).png}"
        sh_ 'screencap -p /sdcard/s.png' >/dev/null 2>&1
        "$ADB" -s "$PHONE" pull /sdcard/s.png "$dest" >/dev/null 2>&1
        sh_ 'rm -f /sdcard/s.png' >/dev/null 2>&1
        echo "capture: $dest"
        ;;
    deverrouille)
        # Reveille l'ecran et saisit le code PIN sur le pave de verrouillage.
        # Le code vient de $PIXEL_PIN ou du fichier local ~/.config/pixel/pin, jamais
        # du dossier synchronise : un code en clair repliquerait sur toutes les machines.
        #
        # Deux pieges appris a la dure :
        #  - le pave (bouncer) se REFERME apres ~2 s d'inactivite : reveler puis taper
        #    doit se faire d'un seul trait, sans aller-retour vers le PC entre les deux.
        #  - `input text` ne cible pas le champ du pave : il faut taper les TOUCHES.
        #
        # NE MARCHE PAS apres un redemarrage : tant que l'ecran n'a pas ete deverrouille
        # une fois a la main, /data est chiffre et ADB n'est meme pas autorise.
        pin="${PIXEL_PIN:-}"
        [ -z "$pin" ] && [ -r "$HOME/.config/pixel/pin" ] && pin=$(cat "$HOME/.config/pixel/pin")
        if [ -z "$pin" ]; then
            echo "aucun code : definir PIXEL_PIN ou ecrire ~/.config/pixel/pin" >&2
            exit 1
        fi
        etat_kg() { sh_ 'dumpsys window' 2>/dev/null | tr -d '\r' | grep -m1 isKeyguardShowing; }
        sh_ 'input keyevent 224' >/dev/null 2>&1; sleep 1
        case "$(etat_kg)" in
            *true*) ;;
            *) echo "deja deverrouille"; exit 0 ;;
        esac
        # Coordonnees du pave PIN Pixel 9 Pro XL (ecran 1008x2244). key0..key9,
        # puis la fleche de validation en bas a droite.
        px() { case "$1" in
            0) echo "503 1820";; 1) echo "269 1172";; 2) echo "503 1172";;
            3) echo "737 1172";; 4) echo "269 1388";; 5) echo "503 1388";;
            6) echo "737 1388";; 7) echo "269 1604";; 8) echo "503 1604";;
            9) echo "737 1604";; esac; }
        seq="input keyevent 224; sleep 0.5; input swipe 504 1500 504 500 200; sleep 0.8"
        i=0
        while [ "$i" -lt "${#pin}" ]; do
            c=$(printf '%s' "$pin" | cut -c$((i + 1)))
            seq="$seq; input tap $(px "$c")"
            i=$((i + 1))
        done
        seq="$seq; sleep 0.4; input tap 737 1820"      # fleche de validation
        sh_ "$seq" >/dev/null 2>&1; sleep 2
        case "$(etat_kg)" in
            *true*) echo "echec : code refuse ou pave absent" >&2; exit 1 ;;
            *) echo "deverrouille" ;;
        esac
        ;;
    *) usage ;;
esac
