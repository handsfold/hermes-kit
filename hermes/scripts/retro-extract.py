#!/usr/bin/env python3
"""Extrait les signaux de friction des sessions Hermes sur une fenetre de N jours.

Sortie : JSON sur stdout, consomme par la skill meta/retro-agent.
Aucun LLM ici : uniquement du comptage deterministe et bon marche.
"""
import json, os, re, sys, argparse
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

SESS = os.path.expanduser("~/.hermes/sessions")
# Retro du 2026-09-28 : depuis le 14/09, Hermes n'ecrit plus de .jsonl, tout
# part dans state.db. Le script lisait un dossier fige et rendait 0 session
# (684 messages de USER ignores). La base est donc la source principale.
DB = os.path.expanduser("~/.hermes/state.db")

# Signaux de reprise en main par l'utilisateur : c'est le coeur du diagnostic.
FRICTION = {
    "repetition":  r"\b(encore|de nouveau|je r[ée]p[èe]te|comme je (t'ai |)ai dit|je t'ai d[ée]j[àa] dit|plusieurs (fois|reprises)|combien de fois)\b",
    "echec":       r"\b(a rat[ée]|marche pas|fonctionne pas|[çc]a marche toujours pas|toujours pas|c'est faux|erreur|rien ne s'est pass[ée]|tu n'as pas)\b",
    "correction":  r"\b(non[,. ]|pas [çc]a|je n'ai pas demand[ée]|c'est pas ce que|au contraire|relis)\b",
    "relance":     r"\b(alors\s*\?|et donc|tu fais quoi|t'en es o[ùu]|toujours en cours|termine|finis)\b",
    "agacement":   r"(putain|merde|s[ée]rieux|n'importe quoi|pff|bordel|\?\?\?|!!!)",
    "verification":r"\b(tu as v[ée]rifi[ée]|prouve|montre.moi|capture|t'es s[ûu]r)\b",
}
ORIGINE = re.compile(r"^Gateway message origin \(JSON data.*?insufficient\.\s*", re.S)
BRUIT_RUNTIME = ("[CONTEXT COMPACTION", "[Continuing toward your standing goal]")
BRUIT_RUNTIME_DANS = ("[Continuing toward your standing goal]",
                      "[ASYNC DELEGATION BATCH COMPLETE")
OOB = re.compile(r"\[/?OUT-OF-BAND USER MESSAGE[^\]]*\]\s*")

# Volontairement strict : le mot "error" seul apparait dans trop de sorties
# legitimes (logs, aide de commandes). On ne compte que les echecs francs.
TOOL_ERR = re.compile(
    r'"success"\s*:\s*false'
    r'|command not found'
    r'|Traceback \(most recent'
    r'|No such file or directory'
    r'|Permission denied'
    r'|HTTP (4|5)\d\d'
    r'|exit(?: code|_status)?[ :=]+[1-9]'
    r'|ModuleNotFoundError|SyntaxError|ConnectionError|TimeoutError'
    r'|fatal:|E: Unable to'
)


def sessions_in_window(days):
    cutoff = datetime.now() - timedelta(days=days)
    out = []
    for name in sorted(os.listdir(SESS)):
        if not name.endswith(".jsonl"):
            continue
        p = os.path.join(SESS, name)
        try:
            if datetime.fromtimestamp(os.path.getmtime(p)) < cutoff:
                continue
        except OSError:
            continue
        out.append(p)
    return out


def sessions_db(days):
    """Rend (etiquette, messages) par session active dans la fenetre, depuis state.db."""
    import sqlite3
    if not os.path.exists(DB):
        return []
    since = (datetime.now() - timedelta(days=days)).timestamp()
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT m.session_id, m.role, m.content, m.tool_calls, m.tool_name, m.timestamp,"
        " COALESCE(s.source,''), COALESCE(s.title,''), COALESCE(s.thread_id,'')"
        " FROM messages m JOIN sessions s ON s.id = m.session_id"
        " WHERE m.timestamp >= ? ORDER BY m.session_id, m.timestamp, m.id", (since,))
    par, meta = defaultdict(list), {}
    for sid, role, content, tcs, tname, ts, src, title, thread in rows:
        try:
            tcs = json.loads(tcs) if tcs else []
        except Exception:
            tcs = []
        par[sid].append({"role": role, "content": content, "tool_calls": tcs,
                         "name": tname,
                         "timestamp": datetime.fromtimestamp(ts).isoformat(timespec="seconds")})
        meta[sid] = f"db:{sid} [{src}{'/' + thread if thread else ''}] {title}".strip()
    con.close()
    return [(meta[k], v) for k, v in par.items()]


def analyse(path, cutoff, msgs_db=None):
    if msgs_db is not None:
        return analyse_msgs(path, msgs_db)
    msgs = []
    for line in open(path, errors="replace"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("role") == "session_meta":
            continue
        ts = d.get("timestamp") or ""
        if ts and ts[:10] < cutoff:
            continue
        msgs.append(d)
    return analyse_msgs(os.path.basename(path), msgs)


def analyse_msgs(label, msgs):
    if not msgs:
        return None

    res = {
        "fichier": label,
        "debut": msgs[0].get("timestamp", "")[:16],
        "fin": msgs[-1].get("timestamp", "")[:16],
        "tours_user": 0, "tours_agent": 0, "appels_outils": 0,
        "frictions": defaultdict(list),
        "outils": Counter(), "outils_en_erreur": Counter(),
        "boucles": [],           # meme outil >=4 fois d'affilee = acharnement
        "sujets": [],            # 1er message user = intitule de la tache
    }
    streak_tool, streak_n = None, 0
    for d in msgs:
        role = d.get("role")
        if role == "user":
            res["tours_user"] += 1
            txt = (d.get("content") or "")
            if isinstance(txt, list):
                txt = " ".join(str(c) for c in txt)
            # Les messages cron portent un gros prompt systeme : on ne compte
            # comme friction que ce que USER tape, pas les consignes injectees.
            if txt.startswith("[IMPORTANT: You are running as a scheduled cron job"):
                continue
            # Bruit du gateway (retro du 2026-09-28) : les fins de processus en
            # fond arrivent en role user et comptaient comme « echec » (exit
            # code). L'en-tete d'origine Telegram precede le vrai message.
            if "[IMPORTANT: Background process" in txt[:60]:
                continue
            # Bruit cron (retro du 2026-10-05) : les rapports planifies (Coach
            # quotidien, Veille IA) reviennent en role user prefixes de
            # « [Cron delivery: ». Ce sont les sorties de l'agent lui-meme, pas
            # des frictions de USER. Leurs mots declenchaient faussement les regex
            # (13 des 31 frictions de la session 635 venaient de la).
            if txt.lstrip().startswith("[Cron delivery"):
                continue
            # Bruit du runtime (retro du 2026-10-19) : les resumes de compaction,
            # les relances automatiques du mode goal et les fins de delegation
            # arrivent en role user. Ils reprennent les mots de toute la session
            # et faisaient 60 % des frictions de la session Amazon 23422.
            debut = txt.lstrip()
            if debut.startswith(BRUIT_RUNTIME) or any(m in txt[:120] for m in BRUIT_RUNTIME_DANS):
                continue
            # Message OUT-OF-BAND : vrai message de USER, on retire l'enveloppe.
            txt = OOB.sub("", txt)
            txt = ORIGINE.sub("", txt.lstrip())
            if len(res["sujets"]) < 3:
                res["sujets"].append(txt[:160])
            low = txt.lower()
            for label, pat in FRICTION.items():
                if re.search(pat, low):
                    res["frictions"][label].append(txt[:220])
        elif role == "assistant":
            res["tours_agent"] += 1
            for tc in d.get("tool_calls") or []:
                name = (tc.get("function") or {}).get("name", "?")
                res["appels_outils"] += 1
                res["outils"][name] += 1
                if name == streak_tool:
                    streak_n += 1
                else:
                    if streak_n >= 4:
                        res["boucles"].append({"outil": streak_tool, "appels": streak_n})
                    streak_tool, streak_n = name, 1
        elif role == "tool":
            body = str(d.get("content") or "")[:2000]
            if TOOL_ERR.search(body):
                res["outils_en_erreur"][d.get("name", "?")] += 1
    if streak_n >= 4:
        res["boucles"].append({"outil": streak_tool, "appels": streak_n})

    res["frictions"] = dict(res["frictions"])
    res["outils"] = dict(res["outils"].most_common(10))
    res["outils_en_erreur"] = dict(res["outils_en_erreur"].most_common(10))
    res["score_friction"] = sum(len(v) for v in res["frictions"].values()) \
        + sum(res["outils_en_erreur"].values()) \
        + sum(b["appels"] // 4 for b in res["boucles"])
    return res


def empreinte(r):
    """Identifie une conversation, pas un fichier.

    Retro du 2026-08-31 : le 30/08, une meme conversation etait persistee dans
    6 fichiers de session distincts, tous horodates a l'instant de la derniere
    ecriture. Trois d'entre eux sont remontes comme « sessions chaudes »
    separees, avec les memes frictions comptees trois fois. Le rapport
    designait alors comme angle mort le sujet le plus recopie, pas le plus
    couteux. On regroupe donc sur l'ouverture de la conversation : deux
    fichiers qui commencent pareil sont le meme fil, reprise comprise.
    """
    return tuple(s[:160] for s in (r.get("sujets") or [])[:3])


def dedupliquer(rapports):
    par_fil = {}
    for r in rapports:
        cle = empreinte(r)
        if not cle:
            par_fil[id(r)] = r
            continue
        garde = par_fil.get(cle)
        if garde is None or r["tours_user"] > garde["tours_user"]:
            r["clones"] = (garde or {}).get("clones", 0) + (1 if garde else 0)
            par_fil[cle] = r
        else:
            garde["clones"] = garde.get("clones", 0) + 1
    return list(par_fil.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jours", type=int, default=7)
    ap.add_argument("--min-score", type=int, default=1)
    ap.add_argument("--sans-dedup", action="store_true",
                    help="garder un rapport par fichier, sans regrouper les copies")
    a = ap.parse_args()

    cutoff = (datetime.now() - timedelta(days=a.jours)).strftime("%Y-%m-%d")
    rapports = []
    for p in sessions_in_window(a.jours):
        r = analyse(p, cutoff)
        if r and r["tours_user"] > 0:
            rapports.append(r)
    for label, msgs in sessions_db(a.jours):
        r = analyse(label, cutoff, msgs_db=msgs)
        if r and r["tours_user"] > 0:
            rapports.append(r)

    avant = len(rapports)
    if not a.sans_dedup:
        rapports = dedupliquer(rapports)
    doublons = avant - len(rapports)

    rapports.sort(key=lambda r: -r["score_friction"])
    chauds = [r for r in rapports if r["score_friction"] >= a.min_score]

    glob_err = Counter()
    glob_fric = Counter()
    for r in rapports:
        for k, v in r["outils_en_erreur"].items():
            glob_err[k] += v
        for k, v in r["frictions"].items():
            glob_fric[k] += len(v)

    print(json.dumps({
        "fenetre_jours": a.jours,
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "sessions_analysees": len(rapports),
        "fichiers_doublons_ecartes": doublons,
        "tours_user_total": sum(r["tours_user"] for r in rapports),
        "appels_outils_total": sum(r["appels_outils"] for r in rapports),
        "frictions_par_type": dict(glob_fric.most_common()),
        "outils_les_plus_en_erreur": dict(glob_err.most_common(8)),
        "sessions_chaudes": chauds[:8],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
