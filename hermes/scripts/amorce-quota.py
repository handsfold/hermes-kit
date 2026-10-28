#!/usr/bin/env python3
"""Amorce la fenetre de quota de 5 h des qu'elle expire.

Pourquoi
    Chez Anthropic comme chez OpenAI, la fenetre de 5 h ne demarre pas a heure
    fixe : elle s'ouvre au PREMIER appel et court 5 h. Si USER ne travaille pas
    entre 20 h et 1 h, sa fenetre reste fermee. Quand il s'y met a 1 h et la
    vide en 30 min, il doit attendre 4 h 30.

    Ce demon envoie un message minuscule des que la fenetre precedente expire.
    La suivante demarre donc immediatement, sans lui. Consequence : une fenetre
    est toujours en cours, et le pire temps d'attente tombe a quelques minutes.

Cout
    1 ping par fenetre et par fournisseur. Claude ~33 k tokens, Codex ~17 k.
    Soit moins de 1 % d'une fenetre de 5 M. Le ping tourne dans un dossier vide
    pour ne pas charger les CLAUDE.md et AGENTS.md de projet.

Sources de verite
    Codex   `resets_at` (epoch) est ecrit tel quel dans les rollouts JSONL.
    Claude  l'API `/api/oauth/usage`, celle que sert la commande `/usage` du
            terminal, donne `five_hour.resets_at` et le pourcentage utilise.
            En repli, les fenetres sont reconstituees depuis les horodatages
            des transcripts : le premier appel ouvre [t, t+5h].

Usage
    amorce-quota.py [--forcer] [--sec]   (--sec : diagnostic, sans ping)
"""
import json, os, subprocess, sys, time, glob, datetime
from qg_adresse import adresse

FENETRE = 5 * 3600
MARGE = 30          # secondes apres l'expiration, pour ne pas tomber trop tot
GARDE = 4.5 * 3600  # jamais 2 pings d'affilee dans cet intervalle
ETAT = os.path.expanduser("~/.hermes/amorce-quota.json")
JOURNAL = os.path.expanduser("~/.hermes/amorce-quota.log")
BAC = "/tmp/amorce-quota"
CODEX = "/usr/lib/chatgpt/resources/codex"
ENV = os.path.expanduser("~/.hermes/.env")
CHAT, THREAD = adresse()


def note(msg):
    ligne = f"{datetime.datetime.now():%F %T} {msg}"
    print(ligne)
    with open(JOURNAL, "a") as f:
        f.write(ligne + "\n")


def etat_lu():
    try:
        return json.load(open(ETAT))
    except Exception:
        return {}


def etat_ecrit(d):
    json.dump(d, open(ETAT, "w"), indent=1)


def prevenir(texte):
    """Une ligne dans le QG, au plus une par fenetre et par fournisseur."""
    jeton = ""
    try:
        for l in open(ENV):
            if l.startswith("TELEGRAM_BOT_TOKEN="):
                jeton = l.split("=", 1)[1].strip().strip("\"'")
    except Exception:
        return
    if not jeton:
        return
    subprocess.run(["curl", "-s", "-m", "20",
                    f"https://api.telegram.org/bot{jeton}/sendMessage",
                    "--data-urlencode", f"chat_id={CHAT}",
                    "--data-urlencode", f"message_thread_id={THREAD}",
                    "--data-urlencode", f"text={texte}"],
                   capture_output=True)


# ---------------------------------------------------------------- Codex

def fin_fenetre_codex():
    """Le resets_at le plus recent trouve dans les rollouts. None si inconnu."""
    fichiers = sorted(glob.glob(os.path.expanduser(
        "~/.codex/sessions/*/*/*/rollout-*.jsonl")), key=os.path.getmtime)[-12:]
    fin = None
    for f in fichiers:
        try:
            for ligne in open(f, errors="ignore"):
                if "resets_at" not in ligne:
                    continue
                d = json.loads(ligne)
                rl = (d.get("payload", {}).get("rate_limits") or {})
                p = rl.get("primary") or {}
                # On ne retient que la fenetre de 5 h, pas l'hebdomadaire.
                if p.get("window_minutes") == 300 and p.get("resets_at"):
                    fin = max(fin or 0, int(p["resets_at"]))
        except Exception:
            continue
    return fin


def ping_codex():
    return subprocess.run(
        [CODEX, "exec", "--skip-git-repo-check",
         "-c", 'model_reasoning_effort="low"', "ok"],
        cwd=BAC, capture_output=True, timeout=240).returncode


# --------------------------------------------------------------- Claude

def usage_claude():
    """Interroge l'API officielle. Rend (fin_epoch, pourcentage) ou None.

    Endpoint trouve dans le binaire Claude Code 2.1.270, c'est celui que sert
    la commande `/usage` du terminal. Le jeton OAuth n'est jamais journalise.
    """
    import urllib.request
    c = json.load(open(os.path.expanduser("~/.claude/.credentials.json")))
    jeton = (c.get("claudeAiOauth") or {}).get("accessToken")
    if not jeton:
        return None
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": f"Bearer {jeton}",
                 "anthropic-beta": "oauth-2025-04-20"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    b = d.get("five_hour") or {}
    if not b.get("resets_at"):
        return None
    fin = datetime.datetime.fromisoformat(b["resets_at"]).timestamp()
    return fin, b.get("utilization")


def fin_fenetre_claude():
    """L'API d'abord. Si elle tombe, on reconstitue depuis les transcripts.

    Le repli reste utile : jeton expire, reseau coupe, format modifie. Il a
    ete verifie exact a la seconde pres contre l'API le 2026-09-13.
    """
    try:
        r = usage_claude()
        if r:
            fin, pct = r
            note(f"claude: {pct:.0f} % utilise (source API)")
            return fin
    except Exception as e:
        note(f"claude: API usage indisponible ({e}), repli sur les transcripts")

    depuis = time.time() - 30 * 3600
    ts = []
    for f in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        try:
            if os.path.getmtime(f) < depuis:
                continue
            for ligne in open(f, errors="ignore"):
                i = ligne.find('"timestamp":"')
                if i < 0:
                    continue
                try:
                    t = datetime.datetime.fromisoformat(
                        ligne[i + 13:i + 37].replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
                if t >= depuis:
                    ts.append(t)
        except Exception:
            continue
    if not ts:
        return None
    ts.sort()
    debut = ts[0]
    for t in ts:
        if t > debut + FENETRE:
            debut = t
    return debut + FENETRE


def ping_claude():
    # --output-format json : usage-timer.py note la consommation du ping dans
    # proxy-usage.jsonl, attribuee au timer (cockpit, 2026-10-22).
    r = subprocess.run(
        ["claude", "-p", "ok", "--model", "claude-haiku-5-5", "--output-format", "json"],
        cwd=BAC, capture_output=True, text=True, timeout=240)
    try:
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage-timer.py")],
                       input=r.stdout, capture_output=True, text=True, timeout=30)
    except Exception:
        pass
    return r.returncode


# ----------------------------------------------------------------- boucle

FOURNISSEURS = [
    ("codex", fin_fenetre_codex, ping_codex),
    ("claude", fin_fenetre_claude, ping_claude),
]


def main():
    forcer = "--forcer" in sys.argv
    sec = "--sec" in sys.argv
    # --seul <nom> : n'agir que sur un fournisseur, pour tester sans
    # entamer le quota de l'autre.
    seul = sys.argv[sys.argv.index("--seul") + 1] if "--seul" in sys.argv else None
    os.makedirs(BAC, exist_ok=True)
    for nom in ("CLAUDE.md", "AGENTS.md"):
        chemin = os.path.join(BAC, nom)
        if os.path.exists(chemin):
            os.remove(chemin)

    etat = etat_lu()
    maintenant = time.time()

    for nom, lire_fin, ping in FOURNISSEURS:
        if seul and nom != seul:
            continue
        try:
            fin = lire_fin()
        except Exception as e:
            note(f"{nom}: lecture impossible ({e})")
            continue
        if fin is None:
            note(f"{nom}: aucune fenetre connue, rien a amorcer")
            continue

        reste = int(fin - maintenant)
        if sec:
            note(f"{nom}: fenetre finit a {datetime.datetime.fromtimestamp(fin):%F %T}"
                 f" (dans {reste // 60} min)")
            continue

        dernier = etat.get(nom, {}).get("dernier_ping", 0)
        if maintenant - dernier < GARDE and not forcer:
            continue
        if reste > MARGE and not forcer:
            continue

        note(f"{nom}: fenetre expiree, amorcage")
        code = ping()
        etat.setdefault(nom, {})["dernier_ping"] = maintenant
        etat[nom]["dernier_code"] = code
        etat_ecrit(etat)
        if code == 0:
            note(f"{nom}: nouvelle fenetre ouverte")
            prevenir(f"Quota {nom} : nouvelle fenetre de 5 h amorcee. "
                     f"Elle court jusqu'a "
                     f"{datetime.datetime.fromtimestamp(time.time() + FENETRE):%Hh%M}.")
        else:
            note(f"{nom}: le ping a echoue (code {code})")


if __name__ == "__main__":
    main()
