# Fleet Auto-Update via Systemd Timer + Logging

**Use case:** Automatically update multiple machines (Pi, local PC, remote host, etc.) on a schedule, with results tracked in a persistent log DB and exposed via a dashboard.

**Key decisions:**
- Timer runs a oneshot service that loops over machine targets
- Each machine update logs to SQLite with timestamp, status (en_cours/termine/echec), and output excerpt
- Dashboard reads logs via API, filters by type/status/machine, shows history
- Restarts only when real changes detected (dependency updates, not just version bumps)

## Service + Timer Files

**auto-update-machines.timer:**
```ini
[Unit]
Description=Auto-update machines: pi, poste, lab
After=network-online.target
Requires=network-online.target

[Timer]
OnBootSec=5min
OnCalendar=daily
OnCalendar=04:00
Persistent=true

[Install]
WantedBy=timers.target
```

Note: `OnCalendar=daily` alone repeats every 24h from the first trigger. Add a second `OnCalendar=04:00` line to specify an absolute wall-clock time (daily at 04:00). Do NOT use `OnUnitActiveSec=6h`: that syntax does not exist in systemd (common typo).

**auto-update-machines.service:**
```ini
[Unit]
Description=Auto-update machines: pi, poste, lab
Requires=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/auto-update-machines.sh
StandardOutput=journal
StandardError=journal
```

## Script Pattern

**Key insight:** The script must:
1. Run updates via SSH on remote machines, local for the Pi itself
2. Detect actual changes (grep output, not version string)
3. Log results to the dashboard's SQLite DB with structured fields
4. Handle errors gracefully: one machine failure does not block others

**Gotcha:** When copying server.py to a different directory (e.g., `/usr/local/bin/`), the line `BASE = os.path.dirname(__file__)` evaluates to the new location, breaking relative config loading. Solutions:
- Move the logic to a subdirectory and use WorkingDirectory in the unit, OR
- Keep the script in its original directory and adjust only the systemd unit to reference it there

See `templates/auto-update-machines.sh` for a ready-to-adapt implementation.

## Dashboard Integration

The server.py should implement:
- `/api/logs` endpoint returning recent log records
- `log_action(type_, status, machine, message, log_output)` function called after each action
- SQLite table with columns: `timestamp, type, status, machine, message, log`

Example logging after a successful update:
```python
log_action("update", "termine", "poste", "Mise à jour réussie", excerpt_of_apt_output)
```

The front-end filters and displays these logs, providing audit trail and status visibility without manual button clicks.

## Validation Pattern

After deploying, force a change and verify the log records:

```bash
# Induce a downgrade to force apt to install something
ssh target 'sudo apt-get install package=old-version'

# Run the timer manually
sudo systemctl start auto-update-machines.service

# Check results in dashboard logs or query DB directly
sqlite3 /path/to/.logs.db "SELECT timestamp, status, machine, message FROM logs ORDER BY timestamp DESC LIMIT 5;"
```

Expected: logs show one entry per machine, all with status="termine" (or "echec" if a machine was unreachable).
