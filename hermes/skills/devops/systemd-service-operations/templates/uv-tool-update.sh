#!/bin/bash
# Template: uv tool auto-update with restart-on-any-dependency-change.
#
# Adapt: SERVICE, TOOL, RUN_AS, LOG.
# Install with:  sudo install -o root -g root -m 755 this.sh /usr/local/bin/<name>.sh
# Pair with a trivial unit:
#   [Service]
#   Type=oneshot
#   ExecStart=/usr/local/bin/<name>.sh
#   TimeoutStartSec=1800
#
# Why not compare version strings: `uv tool upgrade` bumps transitive deps on almost
# every run while the headline version stays put. Comparing versions alone leaves the
# running process on stale in-memory code indefinitely. See references/uv-tool-auto-update.md

set -uo pipefail

TOOL=open-webui
SERVICE=open-webui.service
LOG=/home/exemple/.open-webui/update.log
RUN_AS="sudo -u exemple env HOME=/home/exemple PATH=/home/exemple/.local/bin:/usr/bin:/bin"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$LOG"; }

OLD_VER=$($RUN_AS uv tool list 2>/dev/null | grep -oP "$TOOL v\S+" || echo "inconnue")

OUT=$($RUN_AS uv tool upgrade "$TOOL" 2>&1)
RC=$?

NEW_VER=$($RUN_AS uv tool list 2>/dev/null | grep -oP "$TOOL v\S+" || echo "inconnue")

if [ $RC -ne 0 ]; then
    log "ECHEC uv tool upgrade (rc=$RC) - version toujours $NEW_VER"
    echo "$OUT" >>"$LOG"
    exit $RC
fi

# Real changes are "- pkg==x" / "+ pkg==x".
# "~ pkg==x" lines appear even on no-op runs -- excluding them avoids false positives.
CHANGES=$(echo "$OUT" | grep -cE '^[[:space:]]*[-+] [a-zA-Z0-9._-]+==')

if [ "$OLD_VER" != "$NEW_VER" ]; then
    log "MAJ $TOOL: $OLD_VER -> $NEW_VER ($CHANGES paquets modifies) - restart"
    echo "$OUT" | grep -E '^[[:space:]]*[-+] ' >>"$LOG"
    systemctl restart "$SERVICE" && log "restart OK" || log "restart ECHOUE"
elif [ "$CHANGES" -gt 0 ]; then
    log "$NEW_VER inchangee mais $CHANGES paquets modifies - restart"
    echo "$OUT" | grep -E '^[[:space:]]*[-+] ' >>"$LOG"
    systemctl restart "$SERVICE" && log "restart OK" || log "restart ECHOUE"
else
    log "$NEW_VER - rien a faire"
fi
