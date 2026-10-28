---
name: systemd-service-operations
description: "Service systemd, timer, unité : écrire, dépanner, auditer. Écrit, débogue et audite les unités et timers systemd."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [systemd, timers, linux, unattended-updates, service-discovery, watchdog]
    related_skills: [webhook-subscriptions]
---

# systemd Service Operations

Sommaire :
- When to use
- 1. Never leave logic inline in ExecStart
- 2. Restart on real change, not on version change
- 3. Validate BOTH branches before declaring victory
- 4. Give slow services time to come up
- 5. Finding the unit behind an unknown service
- 6. Inspecting timers
- 7. WorkingDirectory gotcha for Python imports
- Reporting to the user

Covers the whole lifecycle of systemd units on a managed host: authoring service/timer
pairs, making unattended maintenance actually correct, validating both branches of the
logic before trusting it, and finding which unit is behind a service you didn't know about.

## When to use

- Writing or fixing a `.service` / `.timer` pair (auto-update, watchdog, backup, health check)
- A scheduled job "runs fine" but the effect never lands
- You need to identify which unit serves a port or a web UI on a host
- Auditing what a Pi / VPS / lab box is actually running

## 1. Never leave logic inline in ExecStart

The single most common mess: a whole bash pipeline crammed into one `ExecStart=` line with
escaped quotes. It is unreadable, unlintable, and untestable.

**Always** move the logic to a script and keep the unit trivial:

```ini
[Service]
Type=oneshot
ExecStart=/usr/local/bin/my-job.sh
TimeoutStartSec=1800
```

Install the script explicitly with ownership and mode:

```bash
sudo install -o root -g root -m 755 /tmp/staged.sh /usr/local/bin/my-job.sh
bash -n /usr/local/bin/my-job.sh          # syntax check BEFORE enabling
```

Always back up the unit you are replacing:
`sudo cp /etc/systemd/system/X.service /etc/systemd/system/X.service.bak`

After replacing: `sudo systemctl daemon-reload && systemd-analyze verify /etc/systemd/system/X.service`

> `systemd-analyze verify` may print `Permission denied` lines for *other* units it pulls in
> as dependencies. Those are noise: only the verdict on your own unit matters.

## 2. Restart on real change, not on version change

**Pitfall that motivated this skill.** An auto-update job that only restarts the service when
the *headline version string* changes will silently rot. Package managers update **transitive
dependencies** on almost every run. The files on disk move; the running process keeps the old
code in memory. Observed drift: a full week between the installed venv and the live process.

Detect *any* dependency change and restart on that:

```bash
# uv prints "- pkg==old" / "+ pkg==new" for real changes,
# and "~ pkg==ver" for no-ops. Count only -/+ lines.
CHANGES=$(echo "$OUT" | grep -cE '^[[:space:]]*[-+] [a-zA-Z0-9._-]+==')
[ "$CHANGES" -gt 0 ] && systemctl restart the.service
```

Same principle applies to pip, npm, and container image digests: compare what actually
changed on disk, not the advertised version.

See `references/uv-tool-auto-update.md` for a single-service auto-update and
`references/fleet-auto-update-timer.md` for a multi-machine pattern with dashboard logging.
Use `templates/uv-tool-update.sh` or `templates/auto-update-machines.sh` as starter scripts.

## 3. Validate BOTH branches before declaring victory

A oneshot that exits 0 proves nothing: the "nothing to do" path also exits 0. Force the
change path and confirm the side effect.

```bash
systemctl show my.service -p MainPID --value   # capture PID before
# ... induce a real change, run the job ...
systemctl show my.service -p MainPID -p ActiveEnterTimestamp   # PID must differ
```

A changed `MainPID` is the proof. `ActiveState=active` alone is not: the unit may never
have restarted.

**Pitfall:** don't validate the detection regex only against a hand-written sample. Capture
the tool's *real* output from an actual run and grep that. Test the negative case too
(a no-op run must yield 0 matches).

## 4. Give slow services time to come up

On low-power hosts (Raspberry Pi), a heavy Python service takes tens of seconds to bind its
port after restart. An immediate `curl` returns `000` and looks like a failure.

Poll instead of assuming:

```bash
for i in $(seq 1 20); do
  C=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:PORT/health)
  [ "$C" = "200" ] && { echo "up after ~$((i*10))s"; break; }
  sleep 10
done
```

## 5. Finding the unit behind an unknown service

When the user references a dashboard/app on a host and you don't know what serves it:

```bash
# 1. What is listening, and which process owns it
sudo ss -tlnp | grep LISTEN

# 2. What is running, minus the OS noise
systemctl list-units --type=service --state=running --no-legend \
  | grep -viE "systemd|dbus|ssh|cron|rsyslog|polkit|udev|getty|user@|avahi|wpa|dhcp"

# 3. Resolve an ambiguous PID to its real command
tr "\0" " " < /proc/<PID>/cmdline

# 4. Grep for a UI string you can literally see in a screenshot
grep -rilE "Some Visible Label|Another Button Text" /var/www/ /home/*/ \
  --include="*.html" --include="*.py" --include="*.js" 2>/dev/null
```

**Pitfall:** a plausibly-named unit is not proof. A service called `pi-reboot-server` sounded
like the multi-machine dashboard but was 67 lines: far too small. Check `wc -l` and the
actual content before concluding; the real app was elsewhere entirely. Step 4 (grepping a
string visible in the UI) is the fastest reliable identifier.

## 6. Inspecting timers

```bash
systemctl list-timers --all                      # NEXT / LEFT / LAST / PASSED for everything
systemctl list-timers my.timer --no-pager        # one timer
systemctl cat my.service --no-pager              # unit source, including drop-ins
systemctl status my-oneshot.service --no-pager   # last run of a oneshot (inactive is normal)
```

A oneshot showing `Active: inactive (dead) ... status=0/SUCCESS` is healthy: that is what a
completed oneshot looks like. Don't report it as a failure.

## 7. WorkingDirectory gotcha for Python imports

When moving a Python script from its home directory to `/usr/local/bin/`, relative imports and
`BASE = os.path.dirname(__file__)` break because BASE now points to `/usr/local/bin/`. Config files
referenced with `open(os.path.join(BASE, "config.json"))` will look in the wrong place.

**Fix:** Use `WorkingDirectory=` in the service unit to keep the script's context:

```ini
[Service]
Type=simple
WorkingDirectory=/home/myapp
ExecStart=/usr/bin/python3 /home/myapp/server.py
```

Alternatively, pin the config path explicitly:
```python
CONFIG_PATH = \"/home/myapp/config.json\"
CONF = json.load(open(CONFIG_PATH))
```

## Reporting to the user

State what you verified with real output (PIDs, timestamps, exit codes), and flag separately
anything you could NOT confirm. Never present an untested branch as working.
