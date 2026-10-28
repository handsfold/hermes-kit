#!/usr/bin/env bash
# Retouches d'apres import : ce que le manifeste et le sed ne savent pas faire.
# Rejouable : chaque etape est sans effet si elle a deja ete faite.
# Aucun nom d'origine en clair ici : ce fichier passe lui aussi par l'audit.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# 1. settings.json : la marketplace locale n'existe que sur la machine d'origine
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path("claude/settings.json")
if p.exists():
    d = json.loads(p.read_text())
    m = d.get("extraKnownMarketplaces", {})
    m.pop("local-marketing", None)
    if not m:
        d.pop("extraKnownMarketplaces", None)
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
EOF
rm -f claude/commands/switch-model.sh
# le plugin de bascule du routeur local n'a pas de sens sans ce routeur (hors kit)
# plugins : on garde mode-objectif, aiguilleur (choix de la skill avant le modele) et celui des menus Telegram (versions bilingues, source plugins-essai ;
# renomme telegram-menus, son nom d'origine contient une identite donc on le prend par motif).
# Tout autre dossier est propre a l'auteur et jete.
for d in hermes/plugins/*/; do
  n=$(basename "$d")
  case "$n" in
    mode-objectif|telegram-menus|aiguilleur) ;;
    telegram-*) rm -rf hermes/plugins/telegram-menus; mv "$d" hermes/plugins/telegram-menus ;;
    *) rm -rf "$d" ;;
  esac
done
# /mwbot pilote un bot mail d'entreprise : retire du plugin des menus Telegram (voir le script)
python3 outils/retirer-mwbot.py
# hermes-verif.sh : pas de /mwbot attendu, registre des retouches optionnel
python3 outils/adapter-scripts.py

# 2. PixelGarde : paquet Java renomme en com.hermeskit, artefacts de build et cle dehors,
#    scripts du second telephone (a07-*) exclus : ils sont lies a un usage prive
APP=pixelgarde/app
if [ -d "$APP/src/com" ]; then
  for d in "$APP"/src/com/*/pixelgarde; do
    [ -d "$d" ] || continue
    case "$d" in */com/hermeskit/pixelgarde) continue;; esac
    mkdir -p "$APP/src/com/hermeskit"
    rm -rf "$APP/src/com/hermeskit/pixelgarde"
    mv "$d" "$APP/src/com/hermeskit/pixelgarde"
    rmdir "$(dirname "$d")"
  done
fi
for f in "$APP"/skin-*.png; do
  [ -f "$f" ] && mv -f "$f" "$APP/skin.png"
done
rm -f "$APP"/*.apk "$APP"/*.idsig "$APP"/*.keystore
rm -rf pixelgarde/bin/a07-*
# relais SMS de l'ancien telephone : parle au bot d'entreprise, usage prive
rm -f pixelgarde/bin/sms-ancien-tel

# 3. Fichiers generes depuis l'installation vivante (le sed de desidentification passe apres)
python3 outils/exporter-config.py
python3 outils/exporter-crons.py
python3 outils/exporter-reglages.py
bash outils/exporter-patches.sh

# 4. Tirets longs des fichiers importes (les .patch ne sont pas touches : ils reproduisent le code amont)
python3 scripts/no_long_dashes.py >/dev/null
