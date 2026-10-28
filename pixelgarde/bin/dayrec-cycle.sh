#!/usr/bin/env bash
# Sans root : les images arrivent en continu par dayrec-remote.service.
# Ce cycle ne fait plus que l'OCR/regroupement puis l'allegement.
set -uo pipefail
exec 9>/tmp/dayrec-cycle.lock; flock -n 9 || exit 0
{ echo "--- $(date '+%F %T') ---"
  "$HOME/bin/dayrec.py" indexer
  "$HOME/bin/dayrec.py" alleger
} >>"$HOME/DayRec/cycle.log" 2>&1
