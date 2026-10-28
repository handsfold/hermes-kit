#!/usr/bin/env bash
# Verifie qu'un poste de travail peut piloter le Pixel 9 Pro XL.
# A lancer sur n'importe quelle machine :
#   ~/Bureau/Projets/contexte/bin/pixel/verifier-poste.sh
#
# Sortie : une ligne par prerequis, puis un verdict.

PIXEL_TS=__PIXEL_IP__:5555
PIXEL_LAN=__LAN_IP__:5555
ADB="$HOME/.local/platform-tools/adb"
ok=0
ko=0

dire() { # dire <etat> <libelle> [detail]
    case "$1" in
        oui) printf '  OK    %-28s %s\n' "$2" "${3:-}"; ok=$((ok + 1)) ;;
        non) printf '  ECHEC %-28s %s\n' "$2" "${3:-}"; ko=$((ko + 1)) ;;
        *)   printf '  --    %-28s %s\n' "$2" "${3:-}" ;;
    esac
}

echo "Poste : $(hostname) - utilisateur $(whoami)"
echo

# 1. la documentation est-elle arrivee par Syncthing ?
FICHE="$HOME/Bureau/Projets/contexte/projets/pixel.md"
[ -r "$FICHE" ] && dire oui "fiche pixel.md" "$(wc -l <"$FICHE") lignes" \
                || dire non "fiche pixel.md" "absente - Syncthing n'a pas replique"

# 2. platform-tools de Google (ceux de Debian sont trop vieux pour un Pixel 9)
if [ -x "$ADB" ]; then
    dire oui "adb" "$("$ADB" version 2>/dev/null | head -1)"
else
    dire non "adb" "absent de ~/.local/platform-tools - voir projets/pixel.md"
fi

# 3. Tailscale, qui rend le telephone joignable hors du reseau local
if command -v tailscale >/dev/null 2>&1 && tailscale status >/dev/null 2>&1; then
    dire oui "tailscale" "$(tailscale status 2>/dev/null | grep -ci pixel) pixel visible"
else
    dire non "tailscale" "absent ou arrete - repli sur le LAN uniquement"
fi

# 4. le telephone repond-il, et par quelle route ?
JOINT=""
if [ -x "$ADB" ]; then
    for A in "$PIXEL_TS" "$PIXEL_LAN"; do
        "$ADB" connect "$A" >/dev/null 2>&1
        if [ "$("$ADB" -s "$A" shell getprop ro.product.device 2>/dev/null | tr -d '\r')" = "komodo" ]; then
            JOINT="$A"
            break
        fi
    done
fi
if [ -n "$JOINT" ]; then
    voie=$([ "$JOINT" = "$PIXEL_TS" ] && echo "par Tailscale" || echo "par le LAN seulement")
    dire oui "telephone joignable" "$JOINT $voie"
else
    dire non "telephone joignable" "ni Tailscale ni LAN - telephone eteint ?"
fi

# 5. le pilotage lui-meme
CTL="$HOME/Bureau/Projets/contexte/bin/pixel/pixel-ctl.sh"
if [ -n "$JOINT" ] && [ -x "$CTL" ]; then
    if "$CTL" etat 2>/dev/null | grep -q 'Physical size'; then
        dire oui "pilotage pixel-ctl.sh" "$("$CTL" etat 2>/dev/null | grep -m1 'Physical size')"
    else
        dire non "pilotage pixel-ctl.sh" "le script ne repond pas"
    fi
else
    dire non "pilotage pixel-ctl.sh" "script absent ou telephone injoignable"
fi

echo
if [ "$ko" -eq 0 ]; then
    echo "VERDICT : ce poste peut piloter le Pixel. ($ok/$((ok + ko)))"
else
    echo "VERDICT : $ko prerequis manquant(s) sur $((ok + ko)). Voir projets/pixel.md."
    exit 1
fi
