#!/usr/bin/env python3
"""Stop : sous le proxy Hermes, refuse de finir le tour si une commande Bash tourne encore en fond.

Cause, mesuree le 2026-10-04 (topic Sparring) : claude-proxy lance UN process
`claude -p` par tour Telegram. Il sort des que la reponse part, et tue toute
commande lancee avec `run_in_background`. Le test SSR s'est arrete a 72
reponses sur 1 000, sans aucune alerte : le tour avait fini normalement, donc
tours-veilleur n'avait rien a signaler. agent-fond-guard.py ne couvre que l'outil Agent.

Detection : les commandes de l'outil Bash tournent sous un `bash -c` qui
source `~/.claude/shell-snapshots/`. On cherche ces process parmi les
descendants du process `claude` du tour. Une commande detachee par
`setsid nohup ... &` est reparentee a systemd : elle n'est pas comptee.

Exit 2 + stderr = le tour continue, Claude lit le remede. Une seule fois par
tour (stop_hook_active), pour ne jamais boucler.
"""
import json
import os
import sys

sous_proxy = bool(os.environ.get("HERMES_TOPIC_DIR") or os.environ.get("CLAUDE_TIMEOUT_MS"))
if not sous_proxy:
    sys.exit(0)

try:
    donnees = json.load(sys.stdin)
except Exception:
    donnees = {}
if donnees.get("stop_hook_active"):
    sys.exit(0)


def lire(pid, quoi):
    try:
        with open(f"/proc/{pid}/{quoi}", "rb") as f:
            return f.read()
    except OSError:
        return b""


def parent(pid):
    stat = lire(pid, "stat").decode(errors="replace")
    try:
        return int(stat.rsplit(")", 1)[1].split()[1])
    except (IndexError, ValueError):
        return 0


# Remonter jusqu'au process `claude` du tour
ancetres, pid, claude = set(), os.getpid(), 0
while pid > 1:
    ancetres.add(pid)
    if lire(pid, "comm").strip() == b"claude":
        claude = pid
        break
    pid = parent(pid)
if not claude:
    sys.exit(0)

# Enfants de chaque process, en une passe sur /proc
enfants = {}
for nom in os.listdir("/proc"):
    if nom.isdigit():
        enfants.setdefault(parent(int(nom)), []).append(int(nom))

pile, orphelins = list(enfants.get(claude, [])), []
while pile:
    p = pile.pop()
    pile += enfants.get(p, [])
    if p in ancetres:
        continue
    cmd = lire(p, "cmdline").replace(b"\0", b" ").decode(errors="replace")
    if "shell-snapshots" in cmd and " eval " in cmd:
        orphelins.append((p, cmd))

if not orphelins:
    sys.exit(0)

lignes = []
for p, cmd in orphelins[:5]:
    coeur = cmd.split("eval ", 1)[-1].strip(" '")[:140]
    lignes.append(f"  pid {p} : {coeur}")
sys.stderr.write(
    f"{len(orphelins)} commande(s) Bash encore en fond. Ce tour sous claude-proxy "
    "va finir et les tuer sans trace (test SSR coupe a 72/1000 le 2026-10-04) :\n"
    + "\n".join(lignes) + "\n"
    "Remede, au choix :\n"
    "  1. Attendre la fin dans ce tour (Monitor ou `until ...; do sleep 10; done`), puis repondre.\n"
    "  2. La relancer detachee : `setsid nohup bash -c '...' >log 2>&1 </dev/null &`, "
    "et dire a USER ou lire le resultat.\n"
    "  3. Si elle est inutile : la tuer, et le dire.\n"
)
sys.exit(2)
