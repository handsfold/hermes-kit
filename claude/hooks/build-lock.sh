#!/usr/bin/env bash
# Build/Push/Commit mutex lock for Claude Code agents
# Prevents concurrent git and build operations across multiple agent instances
#
# Usage: build-lock.sh acquire|release
# - acquire: checks lock, BLOCKS with clear JSON message if another agent is active
# - release: releases the lock
#
# Strategy: instead of silently waiting (which the agent can't see),
# we BLOCK with a clear message telling the agent to retry after a delay.
# The agent sees the block reason and knows to wait and retry.

LOCKDIR="/tmp/claude-code-build.lock"
LOCKINFO="$LOCKDIR/info"
STALE_TIMEOUT=600  # 10 minutes = definitely stale

ACTION="${1:-acquire}"

is_lock_stale() {
  if [ ! -f "$LOCKINFO" ]; then
    return 0
  fi
  local lock_pid lock_time
  lock_pid=$(sed -n '1p' "$LOCKINFO" 2>/dev/null)
  lock_time=$(sed -n '3p' "$LOCKINFO" 2>/dev/null)

  # No PID or PID is dead = stale
  if [ -z "$lock_pid" ] || ! kill -0 "$lock_pid" 2>/dev/null; then
    return 0
  fi

  # Lock older than 10 minutes = stale
  if [ -n "$lock_time" ]; then
    local now elapsed
    now=$(date +%s)
    elapsed=$((now - lock_time))
    if [ "$elapsed" -gt "$STALE_TIMEOUT" ]; then
      return 0
    fi
  fi

  return 1  # Lock is valid
}

case "$ACTION" in
  acquire)
    # If lock exists, check if stale first
    if [ -d "$LOCKDIR" ]; then
      if is_lock_stale; then
        rm -rf "$LOCKDIR"
      else
        # Lock is held by another active agent - BLOCK with clear message
        lock_cmd=$(sed -n '2p' "$LOCKINFO" 2>/dev/null | head -c 200)
        lock_pid=$(sed -n '1p' "$LOCKINFO" 2>/dev/null)
        lock_time=$(sed -n '3p' "$LOCKINFO" 2>/dev/null)
        now=$(date +%s)
        elapsed=$((now - ${lock_time:-now}))

        cat <<ENDJSON
{"decision": "block", "reason": "🔒 MUTEX: Un autre agent Claude Code est en train d'exécuter une opération git/build (PID $lock_pid, depuis ${elapsed}s). Commande en cours: $lock_cmd. NE PAS contourner ce blocage - attends 30 secondes puis réessaye ta commande. Ne supprime aucun fichier lock, ne force rien, attends simplement."}
ENDJSON
        exit 0
      fi
    fi

    # No lock or stale lock cleared - acquire
    if mkdir "$LOCKDIR" 2>/dev/null; then
      echo "$PPID" > "$LOCKINFO"
      echo "${TOOL_INPUT:-unknown}" >> "$LOCKINFO"
      echo "$(date +%s)" >> "$LOCKINFO"
    else
      # Race condition: another process grabbed it between our check and mkdir
      cat <<ENDJSON
{"decision": "block", "reason": "🔒 MUTEX: Un autre agent vient d'acquérir le verrou. Attends 30 secondes puis réessaye."}
ENDJSON
      exit 0
    fi
    ;;

  release)
    rm -rf "$LOCKDIR"
    ;;
esac
