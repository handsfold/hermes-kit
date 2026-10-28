#!/usr/bin/env bash
# Deploiement unique du site. Copier dans scripts/, remplir DOMAINE et ZONE. Jamais `wrangler deploy` a la main.
# Ordre : filet, version tamponnee, envoi, purge de la zone, preuve en ligne,
# retour a la version precedente si la preuve echoue.
# Lecon MARQUE-E (2026-09-30) : seule la preuve en ligne fait foi, pas le code
# de retour de wrangler.
set -euo pipefail
ICI="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ICI"
DOMAINE=__DOMAINE__   # ex. realvoxai.com
ZONE=__ZONE_ID__       # curl .../zones?name=$DOMAINE
COMPTE=37dd3d14df51f1d62cfce6d461e62b02

bash scripts/check.sh --fast >/dev/null || { echo "Filet rouge : rien n'est envoye (scripts/check.sh --fast)."; exit 1; }

VERSION="$(TZ=Asia/Bangkok date '+%Y-%m-%d %H:%M')"
ATTENDU="$VERSION"; [ "${VP_ECHEC:-}" = 1 ] && ATTENDU="echec-simule"   # test du retour arriere
sed -i -E "s|<!--VERSION-->[^<]*<!--/VERSION-->|<!--VERSION-->${VERSION}<!--/VERSION-->|" public/index.html

cd ~/Bureau/Projets/business/sites/projet-a
infisical run --env=prod --path=/cloudflare --silent -- bash -c '
  set -euo pipefail
  cd "'"$ICI"'"
  export CLOUDFLARE_API_TOKEN="$API_TOKEN_SUPER" CLOUDFLARE_ACCOUNT_ID='"$COMPTE"'
  W=./node_modules/.bin/wrangler
  purger() { curl -s -X POST -H "Authorization: Bearer $API_TOKEN_SUPER" -H "Content-Type: application/json" \
    "https://api.cloudflare.com/client/v4/zones/'"$ZONE"'/purge_cache" -d "{\"purge_everything\":true}" >/dev/null; }
  AVANT=$($W deployments list --json 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[-1][\"versions\"][0][\"version_id\"] if d else \"\")" || true)
  $W deploy 2>&1 | grep -E "Version ID|Deployed"
  purger
  for i in 1 2 3 4 5 6; do  # 30 s au plus
    sleep 5
    if curl -s "https://'"$DOMAINE"'/?neuf=$RANDOM" | grep -q "<!--VERSION-->'"$ATTENDU"'"; then
      echo "En ligne : version '"$VERSION"'"; exit 0
    fi
  done
  echo "La version '"$VERSION"' ne s affiche pas en ligne."
  if [ -n "$AVANT" ]; then
    $W rollback "$AVANT" -y -m "deploiement non prouve" >/dev/null 2>&1 && echo "Retour a $AVANT."
    purger   # sans purge, l edge sert encore la page ratee (vu au test du 2026-10-28)
  fi
  exit 1'
