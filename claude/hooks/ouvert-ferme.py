#!/usr/bin/env python3
"""Ce qui s'ouvre pour un essai se ferme tout seul (demande de USER, 2026-10-17).

Deux usages, un seul fichier :
  ouvert-ferme.py note   (PreToolUse Bash, avant la commande) : repere une commande qui ouvre
                          quelque chose de temporaire et la note pour la session.
  ouvert-ferme.py ferme  (Stop)             : ferme ce que CETTE session a ouvert.

Sont temporaires : un serveur `http.server`, un tunnel `ssh -L/-N`, un navigateur
sans ecran (--headless, playwright), un script lance par setsid ou nohup depuis
/tmp. Les emulateurs Android sont fermes par `emulateur-fin.py`.

Garde-fous : on ne ferme que des processus nes APRES la commande notee, par la
session qui l'a lancee, jamais un ancetre de ce hook, jamais un service systemd.
Un `# garder` dans la commande l'exclut. Silencieux, sort toujours en 0.
"""
import json, os, re, signal, subprocess, sys, time

DOSSIER = os.path.expanduser("~/.claude/ouvert")

# (nom, motif dans la COMMANDE lancee, motif dans les ARGS du processus a fermer)
MOTIFS = [
    ("serveur http", r"http\.server", r"-m http\.server"),
    ("tunnel ssh", r"\bssh\b[^|;&]*\s-[A-Za-z]*[LNRD]\b", r"\bssh\b[^|;&]*\s-[A-Za-z]*[LNRD]\b"),
    ("navigateur sans ecran", r"--headless|playwright", r"chrom[^ ]*[^|]*--headless|playwright.*(node|driver)"),
]
TMP_LANCE = re.compile(r"(?:setsid|nohup)\s+(?:python3?\s+(?:-\w+\s+)*|bash\s+|sh\s+|node\s+)?(/(?:tmp|var/tmp)/[^\s;&|)]+)")


def lire_entree():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def note(e):
    cmd = (e.get("tool_input") or {}).get("command", "") or ""
    sid = e.get("session_id", "")
    if not cmd or not sid or "# garder" in cmd or "ouvert-ferme" in cmd:
        return
    trouves = [(nom, motif_proc) for nom, motif_cmd, motif_proc in MOTIFS if re.search(motif_cmd, cmd)]
    m = TMP_LANCE.search(cmd)
    if m:
        trouves.append(("script /tmp", re.escape(m.group(1))))
    if not trouves:
        return
    os.makedirs(DOSSIER, exist_ok=True)
    with open(os.path.join(DOSSIER, sid + ".jsonl"), "a") as f:
        for nom, motif in trouves:
            f.write(json.dumps({"t": time.time(), "nom": nom, "proc": motif}) + "\n")


def ancetres():
    res, pid = set(), os.getpid()
    while pid > 1:
        res.add(pid)
        try:
            pid = int(open("/proc/%d/stat" % pid).read().rsplit(")", 1)[1].split()[1])
        except Exception:
            break
    return res


def ferme(e):
    sid = e.get("session_id", "")
    chemin = os.path.join(DOSSIER, sid + ".jsonl")
    if not sid or not os.path.exists(chemin):
        return
    notes = [json.loads(l) for l in open(chemin) if l.strip()]
    os.remove(chemin)
    garde = ancetres()
    ps = subprocess.run(["ps", "-eo", "pid=,etimes=,args="], capture_output=True, text=True).stdout
    maintenant = time.time()
    for ligne in ps.splitlines():
        p = ligne.split(None, 2)
        if len(p) < 3 or not p[0].isdigit():
            continue
        pid, age, args = int(p[0]), int(p[1]), p[2]
        if pid in garde or "ouvert-ferme" in args or "systemd" in args[:40]:
            continue
        nes = maintenant - age
        for n in notes:
            if nes >= n["t"] - 1 and re.search(n["proc"], args):
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
                break


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        {"note": note, "ferme": ferme}.get(mode, lambda e: None)(lire_entree())
    except Exception:
        pass
    sys.exit(0)
