#!/usr/bin/env bash
# Remonte le verdict du dernier déploiement automatique dans la conversation.
# Lancé par le hook UserPromptSubmit : ce que ce script écrit sur stdout entre
# dans le contexte de Claude.
#
# Pourquoi ce second hook existe : auto_deploy.sh lance deploy_pi.sh en
# arrière-plan (le build Docker sur le serveur dure plusieurs minutes, un hook Stop
# synchrone bloquerait la fin de chaque réponse). Sans ce rapport, un
# déploiement raté ne se verrait nulle part - exactement le défaut qui a coûté
# trente-et-un déploiements silencieux à DJ entre juin et août 2026.
#
# Ne parle qu'une fois par verdict : le marqueur .deploy_reported garde
# l'horodatage déjà annoncé, sinon chaque message répéterait le même bilan.

set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
STATUS_FILE="${PROJECT_DIR}/.claude/deploy_status.json"
SEEN_FILE="${PROJECT_DIR}/.claude/.deploy_reported"

[ -f "$STATUS_FILE" ] || exit 0

STATUS=$(cat "$STATUS_FILE" 2>/dev/null) || exit 0
AT=$(printf '%s' "$STATUS"    | grep -oP '"at":"\K[^"]*'     || true)
STATE=$(printf '%s' "$STATUS" | grep -oP '"state":"\K[^"]*'  || true)
REASON=$(printf '%s' "$STATUS"| grep -oP '"reason":"\K[^"]*' || true)

# Un déploiement en cours se signale à chaque message tant qu'il tourne : c'est
# une information vivante, pas un verdict, donc elle échappe à la déduplication.
if [ "$STATE" = "running" ]; then
    echo "[déploiement auto] En cours depuis $AT. La prod sert encore l'ancien code."
    exit 0
fi

[ -n "$AT" ] || exit 0
[ "$(cat "$SEEN_FILE" 2>/dev/null)" = "$AT" ] && exit 0
printf '%s' "$AT" > "$SEEN_FILE"

case "$STATE" in
  done)
    echo "[déploiement auto] Réussi à $AT. La prod sert le code courant, santé vérifiée."
    ;;
  failed|aborted)
    echo "[déploiement auto] ÉCHEC à $AT - la prod n'a PAS été mise à jour."
    [ -n "$REASON" ] && echo "[déploiement auto] Raison : $REASON"
    echo "[déploiement auto] Le dire à l'utilisateur au lieu de conclure que c'est en ligne. Journal : .claude/deploy.log"
    ;;
esac

exit 0
