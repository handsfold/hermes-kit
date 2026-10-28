#!/usr/bin/env bash
# Branche humain.mjs dans opencli. Idempotent.
# A relancer apres chaque mise a jour d'opencli (npm -g ecrase dist/).
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
CIBLE="$(npm root -g)/@jackwener/opencli/dist/src/browser/base-page.js"
MARQUE="// opencli-humain"

[ -f "$CIBLE" ] || { echo "introuvable : $CIBLE" >&2; exit 1; }

if [ "${1:-}" = "--retirer" ]; then
    sed -i "/^$MARQUE/,\$d" "$CIBLE"
    sed -i "/^$MARQUE/,\$d" "$(dirname "$CIBLE")/page.js"
    sed -i "/^$MARQUE/,\$d" "$(dirname "$CIBLE")/daemon-client.js"
    echo "retire de $CIBLE"
    exit 0
fi

if grep -q "^$MARQUE" "$CIBLE"; then
    echo "deja branche : $CIBLE"
else
    cat >> "$CIBLE" <<EOF
$MARQUE : gestes humains, voir $ICI/README.md
import { humaniser as __humaniser } from '$ICI/humain.mjs';
__humaniser(BasePage, CDPBasePage);
EOF
    echo "branche : $CIBLE"
fi

# Guet des CAPTCHA : envoyes a USER sur Telegram, l'agent attend sa resolution
PAGE="$(dirname "$CIBLE")/page.js"
if grep -q "^$MARQUE" "$PAGE"; then
    echo "deja branche : $PAGE"
else
    cat >> "$PAGE" <<EOF2
$MARQUE : guet des CAPTCHA, voir $ICI/README.md
import { brancherCaptcha as __brancherCaptcha } from '$ICI/captcha.mjs';
__brancherCaptcha(Page);
EOF2
    echo "branche : $PAGE"
fi

# Garde de focus autour de chaque commande envoyee au daemon (adaptateurs
# compris) : une fenetre Chrome qui passe devant USER est renvoyee derriere.
CLIENT="$(dirname "$CIBLE")/daemon-client.js"
if grep -q "^$MARQUE" "$CLIENT"; then
    echo "deja branche : $CLIENT"
else
    cat >> "$CLIENT" <<EOF3
$MARQUE : garde de focus pendant les commandes, voir $ICI/README.md
import { garderFocusDaemon as __garderFocusDaemon } from '$ICI/focus.mjs';
sendCommandRaw = __garderFocusDaemon(sendCommandRaw);
EOF3
    echo "branche : $CLIENT"
fi

# Fenetres en arriere-plan par defaut : un agent ne vole plus le premier plan
# (--window foreground ou OPENCLI_WINDOW=foreground le redonnent).
CLI="$(dirname "$(dirname "$CIBLE")")/cli.js"
sed -i "s/getBrowserWindowMode(\(undefined\|command\), 'foreground')/getBrowserWindowMode(\1, 'background')/" "$CLI"
grep -q "getBrowserWindowMode(command, 'background')" "$CLI" && echo "verifie : fenetres en arriere-plan par defaut"

# Une fenetre par agent : correctif de l'extension (recharger l'extension apres coup)
python3 "$ICI/fenetre-par-agent.py"

# v3.14 (2026-10-27) : une seule fenetre d'agent partagee, voie native sans focus, menage des onglets natifs
python3 -I "$ICI/fenetre-partagee.py"
grep -q "fenetre-partagee v3.14" "$HOME/.opencli/extension/dist/background.js" \
    && echo "verifie : fenetre d'agent partagee (v3.14)" \
    || { echo "ECHEC : fenetre-partagee v3.14 absente" >&2; exit 1; }

node -e "import('$CIBLE').then(m => {
  const s = String(m.CDPBasePage.prototype.nativeClick);
  if (!s.includes('cliquer') && !s.includes('avecFocusGarde')) { console.error('ECHEC : nativeClick non remplace'); process.exit(1); }
  console.log('verifie : nativeClick humanise');
})"
node -e "import('$PAGE').then(m => {
  if (!String(m.Page.prototype.goto).includes('guetter')) { console.error('ECHEC : guet CAPTCHA absent'); process.exit(1); }
  console.log('verifie : guet CAPTCHA branche');
})"
grep -q "__garderFocusDaemon(sendCommandRaw)" "$CLIENT" && node -e "import('$CLIENT').then(() => console.log('verifie : garde de focus du daemon branchee'))"

# Extension Chrome v3.9 en place, et extension GNOME (le compositeur decide du vol de focus)
grep -q "fenetre-par-agent v3.13" "$HOME/.opencli/extension/dist/background.js" \
    && echo "verifie : extension Chrome v3.13 (balai 15 min, sans orpheline)" \
    || { echo "ECHEC : extension Chrome pas en v3.13" >&2; exit 1; }
GN="$HOME/.local/share/gnome-shell/extensions/opencli-discret@poste/extension.js"
[ -f "$GN" ] && grep -q "captured-event" "$GN" && echo "verifie : extension GNOME v3.9 presente" \
    || { echo "ECHEC : extension GNOME absente ou ancienne" >&2; exit 1; }
if [ "$(curl -s -m 2 127.0.0.1:19826/ping)" = "ok" ]; then
    echo "verifie : extension GNOME chargee (/ping ok)"
else
    echo "ATTENTION : extension GNOME non chargee (reconnexion de session Wayland requise), repli : seule une fenetre nee depuis moins de 4 s est reduite"
fi

# Garde de focus Wayland : etat reel (2026-10-08).
"$(dirname "$0")/verifier-discret.sh" --sec || true
