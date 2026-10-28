#!/usr/bin/env python3
"""Check Open WebUI update log on Pi and output notification if new update found."""
import subprocess, os

STATE_FILE = os.path.expanduser("~/.hermes/scripts/openwebui-update-state.txt")

def get_last_version():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return f.read().strip()
    return ""

def save_version(version):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        f.write(version)

# SSH into Pi, grab last "MAJ:" line from update.log
result = subprocess.run(
    ["ssh", "exemple@__TS_IP__", "grep 'MAJ:' /home/exemple/.open-webui/update.log | tail -1"],
    capture_output=True, text=True, timeout=15
)

last_line = result.stdout.strip()
old_version = get_last_version()

# Extract new version from line like "Tue 30 Jun 03:01:17 +07 2026 MAJ: open-webui v0.9.6 -> open-webui v0.10.1"
if "MAJ:" in last_line:
    # Get the version after "->"
    new_version = last_line.split("->")[-1].strip() if "->" in last_line else last_line
    if new_version != old_version:
        save_version(new_version)
        print(f"🔄 Open WebUI mis à jour ! {last_line.split('MAJ:')[1].strip()}")
    else:
        print("NO_UPDATE")
else:
    # Check current version in case timer hasn't run yet
    result2 = subprocess.run(
        ["ssh", "exemple@__TS_IP__", "sudo -u exemple env HOME=/home/exemple PATH=/home/exemple/.local/bin:/usr/bin:/bin uv tool list | grep 'open-webui v'"],
        capture_output=True, text=True, timeout=15
    )
    current = result2.stdout.strip()
    if current and current != old_version:
        save_version(current)
        print(f"ℹ️ Open WebUI version actuelle : {current} (pas de MAJ ce cycle)")
    else:
        print("NO_UPDATE")
