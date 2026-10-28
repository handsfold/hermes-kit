#!/bin/bash
# Auto-update script: launches apt updates on multiple machines every 6h,
# logs results to a SQLite DB for dashboard audit trail.
# Usage: install to /usr/local/bin/auto-update-machines.sh with chmod +x

set -uo pipefail

WOLWEB_DB="/home/exemple/tableau-de-bord/.logs.db"
LOG_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Log action to dashboard SQLite
log_to_db() {
    local type=$1 status=$2 machine=$3 message=$4 log_output=${5:-}
    sqlite3 "$WOLWEB_DB" <<SQL 2>/dev/null || true
INSERT INTO logs (timestamp, type, status, machine, message, log) 
VALUES ($(date +%s.%N), '$type', '$status', '$machine', '$message', '$log_output');
SQL
}

# Update a remote machine over SSH
update_machine() {
    local ssh_target=$1 machine_id=$2 machine_name=$3
    
    echo "$LOG_TIMESTAMP: Starting update on $machine_name ($ssh_target)..." >&2
    
    out=$(ssh -o ConnectTimeout=5 -o BatchMode=yes "$ssh_target" \
        'sudo -n DEBIAN_FRONTEND=noninteractive apt-get update -qq && \
         sudo -n DEBIAN_FRONTEND=noninteractive apt-get -y -o Dpkg::Options::=--force-confold upgrade' 2>&1) || {
        rc=$?
        log_to_db "update" "echec" "$machine_id" "Update failed ($machine_name)" "${out:0:1000}"
        echo "$LOG_TIMESTAMP: FAILED update on $machine_name (rc=$rc)" >&2
        return 1
    }
    
    if echo "$out" | grep -q "Processing triggers\|Setting up"; then
        log_to_db "update" "termine" "$machine_id" "Update succeeded ($machine_name)" "${out:0:1000}"
        echo "$LOG_TIMESTAMP: OK update on $machine_name" >&2
        return 0
    else
        log_to_db "update" "termine" "$machine_id" "No updates available ($machine_name)" ""
        echo "$LOG_TIMESTAMP: Already up-to-date: $machine_name" >&2
        return 0
    fi
}

# Update Pi (local)
if [ -d /home/exemple ]; then
    bash -c 'sudo -n DEBIAN_FRONTEND=noninteractive apt-get update -qq && \
             sudo -n DEBIAN_FRONTEND=noninteractive apt-get -y -o Dpkg::Options::=--force-confold upgrade' 2>&1 | tee /tmp/pi-update.log || {
        rc=$?
        log_to_db "update" "echec" "pi" "Update failed (Raspberry Pi)" "$(tail -500 /tmp/pi-update.log)"
        echo "$LOG_TIMESTAMP: FAILED update on Pi (rc=$rc)" >&2
    } && {
        log_to_db "update" "termine" "pi" "Update succeeded (Raspberry Pi)" ""
        echo "$LOG_TIMESTAMP: OK update on Pi" >&2
    }
fi

# Update remote machines (customize targets and SSH aliases as needed)
update_machine "poste" "poste" "poste (desktop PC)" || true
update_machine "machine-b" "lab" "Lab (portable MSI)" || true

echo "$LOG_TIMESTAMP: Update cycle complete" >&2
