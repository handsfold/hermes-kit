#!/usr/bin/python3
"""Sonde de mesure : quelles routines appellent un modèle, et lesquelles se nomment auprès du proxy.

Une seule source pour le repérage, lue par le cockpit (`donnees/blocs/_timers.py`) et par
`controle-mesure.py`. Tourne en local ou sur une autre machine, sans dépendance :
    ssh <hote> python3 - --crontabs user1,user2 < sonde_mesure.py
Sortie JSON, sans aucune commande ni secret : seulement des drapeaux par routine.
    {"hote": ..., "timers": {"user:x.timer": {...}}, "crontabs": {"pi:3": {...}}}
Drapeaux : modele (appel de modèle repéré), se_nomme (appelant_systemd ou usage-timer),
local (modèle sur le GPU, 0 $), proxy (passe par le proxy), openrouter (clé OpenRouter en direct), actif (timer chargé).
Repérage : la commande, puis les fichiers qu'elle lance, sur 2 niveaux (8 fichiers au plus).
Faux positif vérifié (simple test de joignabilité, URL citée) : écrire `mesure: aucun-modele`
en commentaire dans le script, la sonde le compte alors à 0.
Né le 2026-10-26 : 76 routines sur 159 échappaient à toute mesure (Pi, crontabs, timers coupés).
"""
import json
import os
import re
import shlex
import subprocess
import sys

MARQUEURS = re.compile(
    r"(:8010|openrouter\.ai|api\.anthropic|api\.openai|api\.groq|generativelanguage|"
    r"claude[\"']?\s*,?\s*[\"']?(-p|--print)\b|hermes\s+(chat|-z|cron)|codex\w*[\"']?\s*,?\s*[\"']?exec\b|"
    r"/v1/(messages|chat/completions)|ANTHROPIC_API_KEY|OPENROUTER_API_KEY|GROQ_API_KEY)", re.I)
LOCAL = re.compile(r"ollama|faster.whisper|llama\.cpp|vllm", re.I)  # modèle sur le GPU : 0 $ API
# Annotation posée dans un script pour un faux positif vérifié (test de joignabilité, URL citée) :
AUCUN = re.compile(r"mesure\s*:\s*aucun-modele", re.I)
# 2e niveau : seulement un fichier lancé sur la ligne, jamais un nom cité dans un commentaire
_LANCE = re.compile(r"python3?|bash|\bsh\b|node|subprocess|Popen|\.run\(|exec|source|\./", re.I)
QUOTA = re.compile(r"https?://api\.anthropic\.com/api/oauth/usage")
SE_NOMME = re.compile(r"""appelant_systemd|usage-timer|["']systemd:[\w@.-]+\.service""")
OPENROUTER = re.compile(r"openrouter\.ai|OPENROUTER_API_KEY", re.I)
PROXY = re.compile(r":8010|:8020|/v1/messages|claude_proxy", re.I)
_FICHIER = re.compile(r"""(?<![\w.-])((?:/|~/|\./)?[\w./~-]+\.(?:py|sh|js|mjs|ts))\b""")
ENV = {**os.environ, "LC_ALL": "C.UTF-8", "SYSTEMD_COLORS": "0"}
MAX_FICHIERS = 8


def _sh(args, timeout=30):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=ENV).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _lire(chemin):
    try:
        with open(chemin, errors="ignore") as f:
            return f.read(60000)
    except PermissionError:  # scripts d'un autre compte (un autre compte de la machine)
        return _sh(["sudo", "-n", "head", "-c", "60000", chemin])
    except OSError:
        return ""


def _existe(chemin):
    if os.path.isfile(chemin):
        return True
    return not os.access(os.path.dirname(chemin) or ".", os.R_OK) and \
        subprocess.run(["sudo", "-n", "test", "-f", chemin], env=ENV, capture_output=True).returncode == 0


def texte(commande, cwd=""):
    """Commande + fichiers qu'elle lance, puis ceux que ces fichiers citent (2 niveaux)."""
    vus, txt, a_voir = set(), commande, [(commande, cwd)]
    for _niveau in range(2):
        suivants = []
        for bloc, base in a_voir:
            if _niveau:  # contenu d'un fichier : lignes de code qui lancent quelque chose
                bloc = "\n".join(l for l in bloc.splitlines()
                                  if not l.lstrip().startswith(("#", "//", "*", '"""')) and _LANCE.search(l))
            for m in _FICHIER.findall(bloc):
                c = os.path.expanduser(m)
                if not c.startswith("/"):
                    c = os.path.normpath(os.path.join(base or "/", c))
                if c in vus or len(vus) >= MAX_FICHIERS or not _existe(c):
                    continue
                vus.add(c)
                contenu = _lire(c)
                txt += "\n" + contenu
                suivants.append((contenu, os.path.dirname(c)))
        a_voir = suivants
    return txt


def drapeaux(txt):
    txt = QUOTA.sub("", txt)
    if AUCUN.search(txt):
        return {"modele": False, "local": False, "se_nomme": False, "proxy": False, "openrouter": False,
                "annote": True}
    modele = bool(MARQUEURS.search(txt))
    return {"modele": modele, "local": not modele and bool(LOCAL.search(txt)), "se_nomme": modele and bool(SE_NOMME.search(txt)),
            "proxy": modele and bool(PROXY.search(txt)), "openrouter": modele and bool(OPENROUTER.search(txt))}


def _show(scope, unites, props):
    out, cur = {}, {}
    if not unites:
        return out
    for ligne in _sh(["systemctl", scope, "show", "-p", props, "--", *unites]).splitlines() + [""]:
        if not ligne.strip():
            if cur.get("Id"):
                out[cur["Id"]] = cur
            cur = {}
            continue
        k, _, v = ligne.partition("=")
        cur[k] = (cur.get(k, "") + " " + v) if k in cur else v
    return out


def timers():
    sortie = {}
    for scope, etiq in (("--user", "user"), ("--system", "system")):
        charges = {t["unit"]: t.get("activates") or "" for t in
                   json.loads(_sh(["systemctl", scope, "list-timers", "--all", "--output=json", "--no-pager"]) or "[]")}
        tous = [l.split()[0] for l in _sh(["systemctl", scope, "list-unit-files", "--type=timer", "--no-legend",
                                           "--no-pager"]).splitlines() if l.strip()]
        unites = sorted(set(tous) | set(charges))
        cibles = _show(scope, [u for u in unites if not charges.get(u)], "Id,Unit")
        services = {u: charges.get(u) or (cibles.get(u) or {}).get("Unit", "") for u in unites}
        infos = _show(scope, sorted({s for s in services.values() if s}), "Id,ExecStart,WorkingDirectory")
        for u in unites:
            i = infos.get(services[u]) or {}
            cmd = " ".join(re.findall(r"argv\[\]=([^;]*);", i.get("ExecStart", "")))
            d = drapeaux(texte(cmd, i.get("WorkingDirectory", "")))
            d.update(actif=u in charges, service=services[u])
            sortie[f"{etiq}:{u}"] = d
    return sortie


def crontabs(proprios):
    sortie = {}
    moi = _sh(["id", "-un"]).strip()
    for p in proprios:
        brut = _sh(["crontab", "-l"]) if p == moi else _sh(["sudo", "-n", "crontab", "-u", p, "-l"])
        for n, ligne in enumerate(brut.splitlines(), 1):
            s = ligne.strip()
            if not s or s.startswith("#") or re.match(r"^[A-Za-z_]\w*=", s):
                continue
            mots = s.split()
            cmd = " ".join(mots[1:] if mots[0].startswith("@") else mots[5:])
            m = re.search(r"\bcd\s+(\S+)", cmd)
            base = os.path.expanduser(m.group(1).strip("\"'&;")) if m else os.path.expanduser("~" + p)
            d = drapeaux(texte(cmd, base))
            d["script"] = os.path.basename((_FICHIER.findall(cmd) or [""])[0])  # nom seul, jamais la commande
            sortie[f"{p}:{n}"] = d
    return sortie


def main(argv):
    proprios = []
    if "--crontabs" in argv:
        proprios = [p for p in argv[argv.index("--crontabs") + 1].split(",") if p]
    out = {"hote": os.uname().nodename, "timers": timers(), "crontabs": crontabs(proprios)}
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])


def distante(hote, proprios, timeout=90):
    """Lance cette sonde sur `hote` par ssh (le fichier part sur l'entrée standard)."""
    with open(__file__) as f:
        code = f.read()
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", hote, "python3", "-", "--crontabs",
                        shlex.quote(",".join(proprios))], input=code, capture_output=True, text=True, timeout=timeout)
    return json.loads(r.stdout)
