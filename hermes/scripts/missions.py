#!/usr/bin/env python3
"""Les missions automatiques, vues et pilotees depuis le Creeper (2026-10-03).

Demande de USER : savoir toujours ce qui travaille et ou ca en est, parcourir
plan, feuille de route et rapports comme des dossiers, voir le quota, lancer
ou arreter d'un geste. Toute mission d'un autre topic doit y apparaitre.

Registre : ~/.hermes/missions.json. Une mission = un job cron Hermes + des
dossiers (fichiers Markdown, sections, repertoires, rapports du job). Un job
cron dont le nom finit par « mission » et absent du registre apparait quand
meme, avec ses seuls rapports.

  missions.py liste                 JSON : quota, missions, autres taches
  missions.py arbre <id>            JSON : les dossiers de la mission
  missions.py lance <id> [force]    lance un tour (refus si budget du jour atteint)
  missions.py stop <id>             met en pause et coupe le tour en cours
  missions.py etat <id>             1 ligne lisible
  missions.py goals                 JSON : les /goal d'Hermes, tous topics
  missions.py goal <session> pause|reprendre|arreter|supprimer
  missions.py libelle               libelle court pour le menu de la bulle
  missions.py ajoute <id> <job> <topic> <nom> [racine]   inscrit une mission

Lecture : n'importe quel python3. Ecriture (lance, stop) : le venv Hermes,
pour passer par cron.jobs et son verrou, jamais par une ecriture a la main.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HOME = os.path.expanduser("~")
HERMES = os.path.join(HOME, ".hermes")
REGISTRE = os.environ.get("MISSIONS_REGISTRE") or os.path.join(HERMES, "missions.json")
JOBS = os.path.join(HERMES, "cron", "jobs.json")
SORTIES = os.path.join(HERMES, "cron", "output")
QUOTA = os.path.join(HERMES, "quota-veilleur.json")
VEILLEUR = os.path.join(HERMES, "scripts", "quota-veilleur.py")
AGENT = os.path.join(HERMES, "hermes-agent")
VENV = os.path.join(AGENT, "venv", "bin", "python")
ARRETS = os.path.join(HERMES, "missions-arrets")   # <id> : arret demande a cette heure
TZ = timezone(timedelta(hours=7))


# ---------------------------------------------------------------- lecture

def lire_json(p, defaut):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def jobs():
    d = lire_json(JOBS, [])
    return d.get("jobs", []) if isinstance(d, dict) else d


def job(jid):
    return next((j for j in jobs() if j.get("id") == jid), None)


def date_iso(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=TZ)
    except ValueError:
        return None


def hhmm(s):
    d = date_iso(s)
    if not d:
        return ""
    d = d.astimezone(TZ)
    auj = datetime.now(TZ).date()
    h = d.strftime("%H:%M")
    if d.date() == auj:
        return h
    if d.date() == auj - timedelta(days=1):
        return "hier " + h
    if d.date() == auj + timedelta(days=1):
        return "demain " + h
    return d.strftime("%d/%m ") + h


def registre():
    r = lire_json(REGISTRE, {"missions": []})
    ms = r.get("missions", [])
    connus = {m.get("job") for m in ms}
    # Un job « ...mission » cree depuis un autre topic, pas encore inscrit.
    for j in jobs():
        nom = str(j.get("name") or "")
        if j.get("id") not in connus and nom.endswith("mission") and j.get("state") != "completed":
            ms.append({"id": nom[: -len("mission")].strip("-_ ") or j["id"], "nom": nom,
                       "job": j["id"], "auto": True, "dossiers": [{"nom": "Rapports", "rapports": True}]})
    return ms


def mission(mid):
    return next((m for m in registre() if m["id"] == mid), None)


def chemin(m, rel):
    rel = os.path.expanduser(rel)
    return rel if os.path.isabs(rel) else os.path.join(os.path.expanduser(m.get("racine", HOME)), rel)


# ---------------------------------------------------------------- quota

def quota():
    """La derniere mesure du veilleur (minuteur de 5 min). Jamais d'appel a
    l'API ici : elle renvoie des 429 des qu'on l'interroge trop souvent."""
    e = lire_json(QUOTA, {})
    m = e.get("derniere_mesure") or {}
    u = m.get("u") or {}
    f5, f7 = u.get("five_hour") or {}, u.get("seven_day") or {}
    if not f7:
        return None
    p5, p7 = float(f5.get("utilization") or 0), float(f7.get("utilization") or 0)
    j = e.get("jour") or {}
    auj = datetime.now(TZ).strftime("%Y-%m-%d")
    budget = float(j.get("budget") or 0)
    utilise = max(p7 - float(p7 if j.get("debut") is None else j["debut"]), 0) if j.get("date") == auj else 0.0
    pct = 100 * utilise / budget if budget > 0 else 0
    age = int(time.time() - float(m.get("t") or 0))
    return {"jour_pct": round(pct), "jour_utilise": round(utilise, 1), "jour_budget": round(budget, 1),
            "sem_pct": round(p7), "sem_raz": hhmm(f7.get("resets_at")),
            "h5_pct": round(p5), "h5_raz": hhmm(f5.get("resets_at")),
            "age_min": age // 60, "en_pause": bool(e.get("en_pause")),
            "graph": quota_graph(e, p7, date_iso(f7.get("resets_at")), budget, utilise)}


HISTO = os.path.join(HERMES, "quota-historique.jsonl")
ACTIVITE = os.path.join(HERMES, "quota-activite.json")


def quota_graph(e, p7, reset, budget, utilise):
    """Donnees des graphiques de la carte Quota : heatmap des jours, courbe du
    jour avec projection, bilan de la semaine. Sources : quota-historique.jsonl
    (veilleur, % de semaine exact) et quota-activite.json ($ equivalent API
    par jour et par heure, transcripts Claude Code)."""
    try:
        return _quota_graph(e, p7, reset, budget, utilise)
    except Exception as ex:
        return {"erreur": str(ex)[:80]}


def _quota_graph(e, p7, reset, budget, utilise):
    now = datetime.now(TZ)
    auj = now.strftime("%Y-%m-%d")
    act = lire_json(ACTIVITE, {})
    usd_j, usd_h = act.get("jours") or {}, act.get("heures") or {}
    # 1) historique du veilleur : % de semaine consomme par jour (hausses seules)
    pts, pct_j, courbe = [], {}, []
    try:
        for l in open(HISTO):
            try:
                o = json.loads(l)
                pts.append((float(o["t"]), float(o["p7"])))
            except Exception:
                continue
    except OSError:
        pass
    pts.sort()
    partiel = None  # 1er jour de l'historique, incomplet s'il commence apres 1 h du matin
    if pts:
        d1 = datetime.fromtimestamp(pts[0][0], TZ)
        if d1.hour >= 1:
            partiel = d1.strftime("%Y-%m-%d")
    for (t0, a), (t1, b) in zip(pts, pts[1:]):
        if b > a and t1 - t0 < 3 * 3600:
            j = datetime.fromtimestamp(t1, TZ).strftime("%Y-%m-%d")
            if j != partiel:
                pct_j[j] = pct_j.get(j, 0.0) + (b - a)
    # Courbe du jour = hausses cumulees depuis minuit. Une remise a zero de la semaine
    # (p7 qui retombe) ne compte pas : le 2026-10-26 la courbe partait de 100 % a 19 h.
    premier, cumul, prec = None, 0.0, None
    for t, v in pts:
        d = datetime.fromtimestamp(t, TZ)
        if prec is not None and v > prec and d.strftime("%Y-%m-%d") == auj:
            cumul += v - prec
            if premier is None:
                premier = d.hour + d.minute / 60
        if prec is not None and v < prec - 5 and d.strftime("%Y-%m-%d") == auj:
            courbe, cumul, premier = [], 0.0, None   # remise a zero : le jour repart de la
        prec = v
        if d.strftime("%Y-%m-%d") == auj:
            courbe.append([round(d.hour + d.minute / 60, 2), round(cumul, 1)])
    h_now = now.hour + now.minute / 60
    # 2) $ -> % : ratio de la semaine en cours (p7 / $ depuis la remise a zero)
    debut_sem = (reset - timedelta(days=7)) if reset else now - timedelta(days=7)
    usd_sem = 0.0
    for j, hs in usd_h.items():
        for h, v in enumerate(hs):
            d0 = datetime.strptime(j, "%Y-%m-%d").replace(tzinfo=TZ, hour=h)
            if d0 + timedelta(hours=1) > debut_sem:
                usd_sem += v
    ratio = (p7 / usd_sem) if usd_sem > 5 and p7 > 0 else None
    # 3) jours : heatmap (140 jours), % mesure sinon estime par ratio
    jours = []
    d0 = now.date() - timedelta(days=139)
    for i in range(140):
        d = (d0 + timedelta(days=i)).strftime("%Y-%m-%d")
        usd = float(usd_j.get(d) or 0)
        if d in pct_j:
            pct, est = round(pct_j[d], 1), False
        elif ratio and usd:
            pct, est = round(usd * ratio, 1), True
        else:
            pct, est = None, True
        jours.append({"d": d, "usd": round(usd), "pct": pct, "est": est})
    # 4) courbe type : part cumulee de l'activite a la fin de chaque heure (14 jours)
    cum, n = [0.0] * 24, 0
    for k in range(1, 15):
        d = (now.date() - timedelta(days=k)).strftime("%Y-%m-%d")
        hs = usd_h.get(d)
        if not hs or sum(hs) < 20:
            continue
        tot, c = sum(hs), 0.0
        for h in range(24):
            c += hs[h]
            cum[h] += c / tot
        n += 1
    typ = [round(x / n, 3) for x in cum] if n else None
    part = None
    if typ:
        h = int(h_now)
        base = typ[h - 1] if h > 0 else 0.0
        part = base + (typ[h] - base) * (h_now - h)
    # 5) projection de la fin de journee
    moy_jour = None
    recents = [jj["pct"] for jj in jours[-8:-1] if jj["pct"] is not None]
    if recents:
        moy_jour = sum(recents) / len(recents)
    fin = None
    if part is not None and part >= 0.25 and utilise > 0:
        fin = utilise / part
    elif moy_jour is not None:
        fin = max(utilise, moy_jour) if part is None else utilise + moy_jour * (1 - (part or 0))
    verdict = None
    if fin is not None and budget > 0:
        r = fin / budget
        verdict = "depasse" if r > 1.0 else ("serre" if r > 0.8 else "marge")
    # 6) bilan de la semaine
    sem = None
    if reset:
        ecoule = max((now - debut_sem).total_seconds() / 86400, 0.25)
        restant = max((reset - now).total_seconds() / 86400, 0.01)
        rythme = p7 / ecoule
        fin_sem = p7 + rythme * restant
        sem = {"ecoule_j": round(ecoule, 1), "restant_j": round(restant, 1),
               "rythme_jour": round(rythme, 1), "fin_sem": round(fin_sem),
               "reste": round(100 - p7, 1),
               "dispo_jour": round((100 - p7) / restant, 1),
               "plein_le": (lambda d: ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."][d.weekday()] + d.strftime(" %H:%M"))(now + timedelta(days=(100 - p7) / rythme))
               if rythme > 0 and fin_sem > 100 else ""}
    return {"jours": jours, "courbe": courbe, "type": typ, "h_now": round(h_now, 2),
            "debut_h": None if premier is None else round(premier, 2),
            "part": None if part is None else round(part, 2),
            "fin": None if fin is None else round(fin, 1),
            "budget": round(budget, 1), "verdict": verdict,
            "moy_jour": None if moy_jour is None else round(moy_jour, 1),
            "ratio": ratio, "sem": sem, "mesures": len(pct_j)}


# ---------------------------------------------------------------- etat

def arret_demande(mid):
    try:
        return float(open(os.path.join(ARRETS, mid)).read().strip())
    except (OSError, ValueError):
        return 0.0


def etat_job(j, mid=None):
    """en_cours, arret, en_file, programme ou pause. Lu dans jobs.json, donc
    toujours l'etat reel : un bouton qui ment est un bug."""
    if not j:
        return "introuvable"
    if claim_vivant(j):
        if mid and arret_demande(mid) > time.time() - 300:
            return "arret"
        return "en_cours"
    # Claim retire par stop() : le tour vit encore jusqu'au battement suivant.
    if mid and arret_demande(mid) > time.time() - 300 and depuis(j):
        return "arret"
    if j.get("state") == "paused" or not j.get("enabled", True):
        return "pause"
    nxt = date_iso(j.get("next_run_at"))
    if nxt and nxt <= datetime.now(timezone.utc) + timedelta(minutes=2):
        return "en_file"
    return "programme"


def depuis(j):
    """Debut du tour en cours, lu dans executions.db (le « at » du claim est
    rafraichi a chaque battement, il ne dit pas quand le tour a commence)."""
    import sqlite3
    try:
        c = sqlite3.connect("file:%s?mode=ro" % os.path.join(HERMES, "cron", "executions.db"), uri=True, timeout=2)
        r = c.execute("SELECT COALESCE(started_at, claimed_at) FROM executions WHERE job_id=? "
                      "AND status IN ('claimed','running') AND claimed_at > ? ORDER BY claimed_at DESC LIMIT 1",
                      (j["id"], (datetime.now(TZ) - timedelta(hours=3)).isoformat())).fetchone()
        c.close()
        return hhmm(r[0]) if r else ""
    except Exception:
        return ""


def claim_vivant(j):
    """Un claim de plus de 5 min sans battement est celui d'un tour mort."""
    c = j.get("fire_claim")
    d = date_iso(c.get("at")) if isinstance(c, dict) else None
    return bool(d and datetime.now(timezone.utc) - d < timedelta(seconds=300))


def cases(texte):
    fait = len(re.findall(r"^\s*[-*] \[[xX]\]", texte, re.M))
    reste = len(re.findall(r"^\s*[-*] \[ \]", texte, re.M))
    return fait, fait + reste


def avancement(m):
    """Les cases du 1er dossier qui en contient (le plan du jour pour ProjetA)."""
    for d in m.get("dossiers", []):
        if d.get("fichier"):
            t = texte_dossier(m, d)
            f, n = cases(t)
            if n:
                return {"dossier": d["nom"], "fait": f, "total": n}
    return None


def resume(m):
    j = job(m["job"])
    e = etat_job(j, m["id"])
    r = {"id": m["id"], "nom": m.get("nom", m["id"]), "topic": m.get("topic", ""),
         "manuel": bool(m.get("manuel")), "etat": e, "auto": bool(m.get("auto"))}
    if j:
        r["dernier"] = hhmm(j.get("last_run_at"))
        r["statut"] = j.get("last_status") or ""
        r["prochain"] = hhmm(j.get("next_run_at")) if e in ("programme", "en_file") else ""
        r["depuis"] = depuis(j) if e in ("en_cours", "arret") else ""
    r["avancement"] = avancement(m)
    return r


def liste():
    ms = registre()
    pris = {m["job"] for m in ms}
    autres = []
    for j in jobs():
        if j["id"] in pris or j.get("state") == "completed":
            continue
        e = etat_job(j)
        if e == "pause" and not j.get("fire_claim"):
            continue
        autres.append({"nom": j.get("name") or j["id"], "etat": e,
                       "prochain": hhmm(j.get("next_run_at")), "dernier": hhmm(j.get("last_run_at")),
                       "statut": j.get("last_status") or "", "_t": j.get("next_run_at") or "9"})
    autres.sort(key=lambda a: (a["etat"] != "en_cours", a["_t"]))
    for a in autres:
        a.pop("_t")
    return {"quota": quota(), "missions": [resume(m) for m in ms], "taches": autres, **goals(),
            "heure": datetime.now(TZ).strftime("%H:%M:%S")}


# ---------------------------------------------------------------- OpenRouter
# USER, 2026-10-20 : suivre la clé OpenRouter (Pyrit, routeur) comme le quota Claude,
# mais discret, en bas de la page Activité. Chiffres réels de l'API (/key, /credits)
# + détail par jour et par modèle tiré de conso.jsonl (compteurs seuls, aucun texte).
CONSO_ROUTEUR = os.path.join(HOME, "Bureau", "Projets", "perso", "agent", "routeur-llm", "conso.jsonl")
CACHE_OR = os.path.join(HERMES, "cache", "openrouter-activite.json")


def _cle_openrouter():
    try:
        for ligne in open(os.path.join(HERMES, ".env"), encoding="utf-8"):
            if ligne.startswith("OPENROUTER_API_KEY="):
                return ligne.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return os.environ.get("OPENROUTER_API_KEY", "")


def _api_openrouter(chemin, cle):
    import urllib.request
    q = urllib.request.Request("https://openrouter.ai/api/v1" + chemin,
                               headers={"Authorization": "Bearer " + cle})
    return json.load(urllib.request.urlopen(q, timeout=15))["data"]


def openrouter():
    """Résumé de la clé OpenRouter. Mis en cache 2 min (la page rappelle souvent)."""
    try:
        c = json.load(open(CACHE_OR, encoding="utf-8"))
        if time.time() - c["_t"] < 120:
            return c["d"]
    except (OSError, ValueError, KeyError):
        pass
    d = _openrouter_calcul()
    if "erreur" not in d:
        os.makedirs(os.path.dirname(CACHE_OR), exist_ok=True)
        with open(CACHE_OR, "w", encoding="utf-8") as f:
            json.dump({"_t": time.time(), "d": d}, f)
    return d


TARIFS_OR = os.path.join(HERMES, "cache", "openrouter-tarifs.json")


def _tarifs():
    """Tarifs catalogue OpenRouter ($ par token) par modele, cache 24 h."""
    try:
        if time.time() - os.path.getmtime(TARIFS_OR) < 86400:
            return json.load(open(TARIFS_OR, encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        data = _api_openrouter("/models", _cle_openrouter())
        out = {}
        for m in data:
            pr = m.get("pricing") or {}
            out[m["id"]] = {k: float(pr.get(k) or 0) for k in
                            ("prompt", "completion", "input_cache_read", "input_cache_write")}
        os.makedirs(os.path.dirname(TARIFS_OR), exist_ok=True)
        with open(TARIFS_OR, "w", encoding="utf-8") as f:
            json.dump(out, f)
        return out
    except Exception:
        try:
            return json.load(open(TARIFS_OR, encoding="utf-8"))
        except (OSError, ValueError):
            return {}


def _openrouter_calcul():
    from collections import defaultdict
    now = datetime.now(TZ)
    utc0 = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    lundi = utc0 - timedelta(days=utc0.weekday())
    cle = {}
    try:
        k = _api_openrouter("/key", _cle_openrouter())
        cr = _api_openrouter("/credits", _cle_openrouter())
        cle = {"jour": k["usage_daily"], "semaine": k["usage_weekly"], "mois": k["usage_monthly"],
               "total": k["usage"], "credits_reste": round(cr["total_credits"] - cr["total_usage"], 2),
               "maj": now.strftime("%H:%M")}
    except Exception as e:
        return {"erreur": "API OpenRouter : " + str(e)[:80]}
    jours = defaultdict(lambda: {"usd": 0.0, "entree": 0, "lu": 0, "sortie": 0, "appels": 0, "pyrit": 0.0})
    modeles = defaultdict(lambda: {"usd": 0.0, "entree": 0, "lu": 0, "appels": 0})
    j_utc = s_utc = 0.0
    mod_jour = defaultdict(lambda: {"usd": 0.0, "appels": 0, "brut": 0, "lu": 0, "sortie": 0})
    tarifs = _tarifs()
    auj = now.strftime("%Y-%m-%d")
    vide = lambda: {"appels": 0, "brut": 0, "lu": 0, "ecrit": 0, "sortie": 0, "usd": 0.0,
                    "e_brut": 0.0, "e_lu": 0.0, "e_ecrit": 0.0, "e_sortie": 0.0, "duree": 0.0}
    py = {"jour": {"role": defaultdict(vide), "tech": defaultdict(vide)},
          "sept": {"role": defaultdict(vide), "tech": defaultdict(vide)}}
    debut = (now - timedelta(days=13)).strftime("%Y-%m-%d")
    sem7 = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    premier = None
    try:
        for ligne in open(CONSO_ROUTEUR, encoding="utf-8"):
            try:
                r = json.loads(ligne)
                t = datetime.fromisoformat(r["ts"]).replace(tzinfo=TZ)
            except (ValueError, KeyError):
                continue
            premier = premier or r["ts"][:10]
            usd = r.get("cout") or 0
            tu = t.astimezone(timezone.utc)
            if tu >= utc0:
                j_utc += usd
            if tu >= lundi:
                s_utc += usd
            jour = r["ts"][:10]
            if jour >= debut:
                x = jours[jour]
                x["usd"] += usd
                x["entree"] += r.get("entree") or 0
                x["lu"] += r.get("cache_lu") or 0
                x["sortie"] += r.get("sortie") or 0
                x["appels"] += 1
                if r.get("backend") == "pyrit":
                    x["pyrit"] += usd
            if jour == auj:
                mj = mod_jour[(r.get("modele") or "?").split("/")[-1]]
                mj["usd"] += usd
                mj["appels"] += 1
                mj["brut"] += max(0, (r.get("entree") or 0) - (r.get("cache_lu") or 0) - (r.get("cache_ecrit") or 0))
                mj["lu"] += r.get("cache_lu") or 0
                mj["sortie"] += r.get("sortie") or 0
            if jour >= sem7:
                m = modeles[(r.get("modele") or "?").split("/")[-1]]
                m["usd"] += usd
                m["entree"] += r.get("entree") or 0
                m["lu"] += r.get("cache_lu") or 0
                m["appels"] += 1
            if jour >= sem7 and r.get("backend") == "pyrit":
                ent, lu, ec = r.get("entree") or 0, r.get("cache_lu") or 0, r.get("cache_ecrit") or 0
                so = r.get("sortie") or 0
                brut = max(0, ent - lu - ec)
                tf = tarifs.get(r.get("modele") or "") or {}
                role = r.get("role") or "avant"
                tech = r.get("technique") or "avant"
                for per in (("jour", "sept") if jour == auj else ("sept",)):
                    for x in (py[per]["role"][role], py[per]["tech"][tech]):
                        x["appels"] += 1
                        x["brut"] += brut
                        x["lu"] += lu
                        x["ecrit"] += ec
                        x["sortie"] += so
                        x["usd"] += usd
                        x["duree"] += r.get("duree_s") or 0
                        x["e_brut"] += brut * tf.get("prompt", 0)
                        x["e_lu"] += lu * (tf.get("input_cache_read") or tf.get("prompt", 0))
                        x["e_ecrit"] += ec * (tf.get("input_cache_write") or tf.get("prompt", 0))
                        x["e_sortie"] += so * tf.get("completion", 0)
    except OSError as e:
        return {"erreur": "journal du routeur : " + str(e)[:80]}
    pct = lambda lu, e: round(100 * lu / e) if e else None
    # Projection du mois : cumul reel du mois + moyenne des 7 derniers jours complets
    # (journal du routeur, corrige de sa couverture) x jours restants.
    complets = [x["usd"] for j, x in sorted(jours.items()) if j < auj][-7:]
    couv = min(1.0, max(0.5, (s_utc / cle["semaine"]) if cle["semaine"] else 1.0))
    moy = (sum(complets) / len(complets) / couv) if complets else 0.0
    fin_mois = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    restants = fin_mois.day - now.day
    aujourdhui = {"usd": round(sum(m["usd"] for m in mod_jour.values()), 3),
                  "appels": sum(m["appels"] for m in mod_jour.values()),
                  "modeles": sorted([{"nom": n, "usd": round(m["usd"], 3), "appels": m["appels"],
                                      "brut": m["brut"], "lu": m["lu"], "sortie": m["sortie"],
                                      "cache": pct(m["lu"], m["brut"] + m["lu"])}
                                     for n, m in mod_jour.items()], key=lambda m: -m["usd"])}
    return {
        "aujourdhui": aujourdhui,
        "projection": {"mois": round(cle["mois"] + moy * restants, 2), "moy_jour": round(moy, 2),
                       "restants": restants},
        "cle": cle,
        "couverture": {"jour": pct(j_utc, cle["jour"]), "semaine": pct(s_utc, cle["semaine"]),
                       "depuis": premier},
        "jours": [{"date": j, "usd": round(x["usd"], 3), "pyrit": round(x["pyrit"], 3),
                   "appels": x["appels"], "entree": x["entree"], "sortie": x["sortie"],
                   "cache": pct(x["lu"], x["entree"])} for j, x in sorted(jours.items())],
        "modeles": sorted([{"nom": n, "usd": round(m["usd"], 3), "appels": m["appels"],
                            "cache": pct(m["lu"], m["entree"])} for n, m in modeles.items()],
                          key=lambda m: -m["usd"])[:8],
        "pyrit": {per: {"roles": _rang_pyrit(py[per]["role"]),
                        "techniques": _rang_pyrit(py[per]["tech"])} for per in py},
        "heure": now.strftime("%H:%M:%S"),
    }


def _rang_pyrit(groupes):
    """Lignes triees par cout : tokens par type, $ reel, $ estime par type, cache %."""
    lignes = []
    for nom, x in groupes.items():
        entree = x["brut"] + x["lu"] + x["ecrit"]
        lignes.append({
            "nom": nom, "appels": x["appels"], "brut": x["brut"], "lu": x["lu"],
            "ecrit": x["ecrit"], "sortie": x["sortie"], "usd": round(x["usd"], 4),
            "cache": round(100 * x["lu"] / entree) if entree else None,
            "entree_moy": round(entree / x["appels"]) if x["appels"] else 0,
            "sortie_moy": round(x["sortie"] / x["appels"]) if x["appels"] else 0,
            "duree_moy": round(x["duree"] / x["appels"], 1) if x["appels"] else 0,
            "est": {"brut": round(x["e_brut"], 4), "cache": round(x["e_lu"] + x["e_ecrit"], 4),
                    "sortie": round(x["e_sortie"], 4)},
        })
    return sorted(lignes, key=lambda l: -l["usd"])


# ---------------------------------------------------------------- dossiers

def sections(texte, niveau=2):
    """Decoupe un Markdown par titres : [(titre, corps)] ; le corps garde les
    sous-titres, decoupes a leur tour par noeud()."""
    motif = re.compile(r"^#{%d} (.+)$" % niveau, re.M)
    pos = [(mo.start(), mo.end(), mo.group(1).strip()) for mo in motif.finditer(texte)]
    out = []
    for i, (a, b, t) in enumerate(pos):
        fin = pos[i + 1][0] if i + 1 < len(pos) else len(texte)
        out.append((t, texte[b:fin].strip("\n")))
    return out, (texte[: pos[0][0]] if pos else texte).strip("\n")


def noeud(titre, corps, niveau=3):
    enfants, tete = sections(corps, niveau) if niveau <= 4 else ([], corps)
    f, n = cases(corps)
    return {"titre": titre, "md": tete if enfants else corps,
            "fait": f, "total": n,
            "enfants": [noeud(t, c, niveau + 1) for t, c in enfants]}


def texte_dossier(m, d):
    try:
        t = open(chemin(m, d["fichier"]), encoding="utf-8").read()
    except OSError:
        return ""
    if not d.get("section"):
        return t
    for titre, corps in sections(t, 2)[0]:
        if titre.lower().startswith(d["section"].lower()):
            return corps
    return ""


def titre_rapport(nom):
    mo = re.match(r"(\d{4})-(\d\d)-(\d\d)_(\d\d)-(\d\d)", nom)
    if not mo:
        return nom
    d = "-".join(mo.group(1, 2, 3)) + "T" + mo.group(4) + ":" + mo.group(5)
    return "Tour de " + hhmm(d).replace(":", " h ")


def rapports(m, n=12):
    out = []
    for p in sorted(glob.glob(os.path.join(SORTIES, m["job"], "*.md")), reverse=True)[:n]:
        t = open(p, encoding="utf-8", errors="replace").read()
        i = t.rfind("\n## Response")
        corps = t[i + len("\n## Response"):].strip() if i >= 0 else "(rapport sans réponse)"
        if corps.strip() == "[SILENT]":
            corps = "Rien de neuf à signaler sur ce tour."
        out.append({"titre": titre_rapport(os.path.basename(p)), "md": corps,
                     "fait": 0, "total": 0, "enfants": []})
    return out


def repertoire(m, d):
    out = []
    for p in sorted(glob.glob(os.path.join(chemin(m, d["repertoire"]), "*.md"))):
        t = open(p, encoding="utf-8", errors="replace").read()
        out.append({"titre": os.path.basename(p)[:-3].replace("-", " "), "md": t,
                    "fait": 0, "total": 0, "enfants": []})
    return out


COLONNES = [("In Progress", "En cours"), ("To Do", "À faire"), ("Done", "Fait")]
PRIORITES = {"high": (0, "haute"), "medium": (1, "moyenne"), "low": (2, "basse")}
TITRES_BACKLOG = {"Description": "", "Acceptance Criteria": "Critères",
                  "Implementation Plan": "Plan", "Implementation Notes": "Notes",
                  "Final Summary": "Bilan", "Definition of Done": "Fini quand"}


def entete(texte):
    """Frontmatter YAML simple d'une tache Backlog.md (cles, listes « - x »),
    sans dependance a PyYAML, absent du python systeme."""
    mo = re.match(r"---\n(.*?)\n---\n?", texte, re.S)
    if not mo:
        return {}, texte
    d, cle = {}, None
    for ligne in mo.group(1).splitlines():
        m2 = re.match(r"([\w-]+):\s*(.*)$", ligne)
        if m2:
            cle, v = m2.group(1), m2.group(2).strip()
            d[cle] = [] if v in ("", "[]") else v.strip("'\"")
        elif cle and ligne.strip().startswith("- ") and isinstance(d.get(cle), list):
            d[cle].append(ligne.strip()[2:].strip("'\""))
    return d, texte[mo.end():]


def tache(p):
    t = open(p, encoding="utf-8", errors="replace").read()
    h, corps = entete(t)
    corps = re.sub(r"<!--.*?-->\n?", "", corps)
    corps = re.sub(r"^## (.+)$", lambda mo: ("## " + TITRES_BACKLOG[mo.group(1)])
                   if TITRES_BACKLOG.get(mo.group(1)) else
                   ("" if mo.group(1) in TITRES_BACKLOG else mo.group(0)), corps, flags=re.M)
    corps = re.sub(r"^(\s*[-*] \[[ xX]\]) #\d+ ", r"\1 ", corps, flags=re.M)
    infos = []
    rang, prio = PRIORITES.get(h.get("priority", ""), (3, ""))
    if prio:
        infos.append("Priorité " + prio)
    if h.get("due_date"):
        infos.append("échéance " + h["due_date"][8:10] + "/" + h["due_date"][5:7])
    if h.get("dependencies"):
        infos.append("après " + ", ".join(h["dependencies"]))
    md = ("*" + " · ".join(infos) + "*\n\n" if infos else "") + re.sub(r"\n{3,}", "\n\n", corps).strip()
    f, n = cases(corps)
    try:
        ordre = float(h.get("ordinal") or 1e9)
    except ValueError:
        ordre = 1e9
    return {"titre": "%s · %s" % (h.get("id", "?"), h.get("title", os.path.basename(p))),
            "md": md, "fait": f, "total": n, "enfants": [],
            "_statut": h.get("status", "To Do"), "_rang": (rang, ordre)}


def backlog(m, d):
    """Les taches Backlog.md, rangees en colonnes comme le tableau kanban."""
    base = chemin(m, d["backlog"])
    ts = [tache(p) for p in glob.glob(os.path.join(base, "tasks", "*.md"))]
    faites = [tache(p) for p in glob.glob(os.path.join(base, "completed", "*.md"))]
    for t in faites:
        t["_statut"] = "Done"
    ts += faites
    groupes = {s: sorted((t for t in ts if t["_statut"] == s), key=lambda t: t["_rang"])
               for s, _ in COLONNES}
    for t in ts:
        t.pop("_statut"), t.pop("_rang")
    out = []
    for statut, nom in COLONNES:
        enf = groupes[statut]
        out.append({"titre": nom, "md": "" if enf else "Aucune tâche.",
                    "fait": 0, "total": 0, "enfants": enf, "compte": len(enf)})
    return out


def arbre(mid):
    m = mission(mid)
    if not m:
        return {"erreur": "mission inconnue"}
    out = []
    for d in m.get("dossiers", []):
        if d.get("rapports"):
            n = {"titre": d["nom"], "md": "", "fait": 0, "total": 0, "enfants": rapports(m)}
        elif d.get("backlog"):
            cols = backlog(m, d)
            n = {"titre": d["nom"], "md": "La file de l'agent : il prend la 1re tâche « À faire » "
                 "dont les dépendances sont finies.", "fait": 0, "total": 0, "enfants": cols}
            n["compte"] = sum(c["compte"] for c in cols if c["titre"] != "Fait")
            out.append(n)
            continue
        elif d.get("repertoire"):
            enf = repertoire(m, d)
            n = {"titre": d["nom"], "md": "" if enf else "Aucun brouillon en attente.",
                 "fait": 0, "total": 0, "enfants": enf}
        else:
            t = texte_dossier(m, d)
            if d.get("section"):
                n = noeud(d["nom"], t, 3)
            else:
                enf, tete = sections(t, 2)
                f, tot = cases(t)
                n = {"titre": d["nom"], "md": re.sub(r"^# .*\n?", "", tete).strip(),
                     "fait": f, "total": tot, "enfants": [noeud(a, b, 3) for a, b in enf]}
        n["compte"] = len(n["enfants"])
        out.append(n)
    return {"id": m["id"], "nom": m.get("nom", m["id"]), "resume": resume(m), "dossiers": out}


# ---------------------------------------------------------------- actions

def venv(code, *args):
    r = subprocess.run([VENV, "-c", "import sys; sys.path.insert(0, %r)\n" % AGENT + code] + list(args),
                       capture_output=True, text=True, timeout=60)
    return (r.stdout.strip().splitlines() or [r.stderr.strip()[-300:]])[-1]


def lance(mid, force=False):
    m = mission(mid)
    if not m:
        return False, "Mission inconnue."
    j = job(m["job"])
    e = etat_job(j, mid)
    if e in ("en_cours", "arret"):
        return False, "Un tour tourne déjà. Rien de relancé."
    if e == "en_file":
        return False, "Un tour part déjà dans la minute."
    if not force:
        r = subprocess.run(["python3", VEILLEUR, "peut-lancer"], capture_output=True, text=True, timeout=60)
        verdict = (r.stdout + r.stderr).strip()
        if r.returncode != 0:
            return False, "Pas lancé. " + verdict
    else:
        verdict = "Quota ignoré à ta demande."
        # Jeton a usage unique, lu par le script de pre-tour de la mission.
        open(os.path.join(HERMES, mid + "-force"), "w").close()
    try:
        os.remove(os.path.join(ARRETS, mid))
    except OSError:
        pass
    t0 = datetime.now(timezone.utc).isoformat()
    # Pas « hermes cron run » : il fait tourner le tour dans ce processus.
    # trigger_job le pose dans la file du gateway, pris au tick suivant.
    # attach_to_session : le rapport du tour entre aussi dans la memoire de
    # l'agent du topic. USER peut y repondre sans citer le rapport (2026-10-04).
    out = venv("from cron.jobs import trigger_job, _with_job, save_jobs\n"
               "def f(jobs, i, job):\n"
               "    if job.get('attach_to_session') is not True:\n"
               "        job['attach_to_session'] = True; save_jobs(jobs)\n"
               "_with_job(sys.argv[1], f, None)\n"
               "j = trigger_job(sys.argv[1]); print('ok' if j and j.get('enabled') else 'introuvable')",
               m["job"])
    if out != "ok":
        if m.get("manuel"):
            subprocess.run(["hermes", "cron", "pause", m["job"]], capture_output=True, timeout=60)
        return False, "Échec du lancement : " + out
    if m.get("manuel"):
        # Une mission manuelle repasse en pause des que le tour est pris :
        # la pause ne coupe pas un tour, et la fin du tour la respecte.
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "garde", mid, t0],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    return True, "Tour lancé à {}. {}\nDépart sous 1 minute.".format(datetime.now(TZ).strftime("%H:%M"), re.sub(r"(\d)\.(\d)", r"\1,\2", verdict))


def _apres(date_iso, t0):
    try:
        return datetime.fromisoformat(date_iso) > datetime.fromisoformat(t0)
    except (TypeError, ValueError):
        return False


def garde(mid, t0):
    m = mission(mid)
    for _ in range(72):
        time.sleep(5)
        j = job(m["job"]) or {}
        # Comparer des dates, pas des chaines : last_run_at est en heure de
        # Bangkok (+07:00), t0 en UTC. En chaine, « 10:28+07 » passait pour
        # posterieur a « 03:31+00 » : la garde remettait en pause avant le
        # depart (2026-10-04, lancement du Creeper avale).
        if j.get("fire_claim") or _apres(j.get("last_run_at"), t0):
            break
    subprocess.run(["hermes", "cron", "pause", m["job"]], capture_output=True, timeout=60)


def stop(mid):
    """Pause, puis retrait du fire_claim : le battement du tour (60 s) voit
    qu'il a perdu la main, et le planificateur interrompt l'agent."""
    m = mission(mid)
    if not m:
        return False, "Mission inconnue."
    j = job(m["job"])
    tournait = bool(j and j.get("fire_claim"))
    out = venv("from cron.jobs import pause_job, _with_job, save_jobs\n"
               "pause_job(sys.argv[1], reason='arret depuis le Creeper')\n"
               "def f(jobs, i, job):\n"
               "    if not job.get('fire_claim'): return 'libre'\n"
               "    job['fire_claim'] = None; save_jobs(jobs); return 'coupe'\n"
               "print(_with_job(sys.argv[1], f, 'introuvable'))", m["job"])
    if out not in ("libre", "coupe"):
        return False, "Échec de l'arrêt : " + out
    if not tournait:
        return True, "Mission en pause. Aucun tour ne tournait."
    os.makedirs(ARRETS, exist_ok=True)
    with open(os.path.join(ARRETS, mid), "w") as f:
        f.write(str(time.time()))
    return True, "Arrêt demandé. Le tour s'interrompt sous 2 minutes."


def ajoute(mid, jid, topic, nom, racine=None):
    r = lire_json(REGISTRE, {"missions": []})
    r["missions"] = [m for m in r.get("missions", []) if m["id"] != mid]
    m = {"id": mid, "nom": nom, "job": jid, "topic": topic, "manuel": True,
         "dossiers": [{"nom": "Rapports", "rapports": True}]}
    if racine:
        m["racine"] = racine
    r["missions"].append(m)
    tmp = REGISTRE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    os.replace(tmp, REGISTRE)
    return "Mission « {} » inscrite. Ajoute ses dossiers dans {}.".format(nom, REGISTRE)


# ---------------------------------------------------------------- goals
# Les /goal d'Hermes (2026-10-12). Demande de USER : voir dans le Creeper tous
# les goals, de tous les topics, avec etat, tours et dernier verdict, et les
# mettre en pause, les reprendre ou les arreter. Etat : state.db, table
# state_meta, cle goal:<session>. Les topics en « mode objectif » (relais
# d'outils, topics-relais.json) apparaissent aussi, meme sans goal.

STATE = os.path.join(HERMES, "state.db")
NOMS = os.path.join(HERMES, "qg-noms.json")
RELAIS = os.path.join(HERMES, "topics-relais.json")
INJECTER = os.path.join(HERMES, "injecter")
GOAL_MOTS = {"active": "en_cours", "paused": "pause", "done": "fini", "cleared": "arrete"}
# USER, 2026-10-13 : supprimer un goal depuis le Creeper. Hermes garde la ligne
# (statut cleared, sa methode d'archive) ; le Creeper la masque. Les fichiers du
# plugin goal-preuve partent dans goals/_supprimes, rien n'est efface.
MASQUES = os.path.join(HERMES, "goals", "masques.json")


def _ro(chemin):
    import sqlite3
    return sqlite3.connect("file:%s?mode=ro" % chemin, uri=True, timeout=5)


def injecteur_vivant():
    try:
        return time.time() - os.path.getmtime(os.path.join(INJECTER, ".vivant")) < 30
    except OSError:
        return False


def _session(c, sid):
    r = c.execute("select chat_id, thread_id, session_key, ended_at from sessions where id=?", (sid,)).fetchone()
    if not r:
        return {}
    d = {"chat_id": r[0] or "", "thread_id": str(r[1] or ""), "cle": r[2] or "", "close": bool(r[3])}
    if d["cle"]:
        n = c.execute("select id from sessions where session_key=? order by started_at desc limit 1",
                      (d["cle"],)).fetchone()
        d["courante"] = bool(n and n[0] == sid)
    return d


CASE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.+?)\s*$")


def etapes_goal(sid):
    """Les etapes du goal, tirees de ~/.hermes/goals/<sid>/PROGRESS.md
    (plugin goal-preuve, 2026-10-13). Demande de USER : voir ce que l'agent a
    fait et tout ce qui lui reste, une phrase par etape."""
    sur = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)
    try:
        with open(os.path.join(HERMES, "goals", sur, "PROGRESS.md"), encoding="utf-8") as f:
            lignes = f.read().splitlines()
    except OSError:
        return None
    out = []
    for l in lignes:
        m = CASE.match(l)
        if m:
            out.append({"t": m.group(2).replace("`", "")[:200], "fait": m.group(1) != " "})
    return out[:40]


USAGE = os.path.join(HERMES, "proxy-usage.jsonl")
VERDICT_MOTS = {"continue": "Continue", "done": "Atteint", "stalled": "Tourne en rond", "budget": "Plafond",
                "obstacle": "Obstacle", "blocked": "Bloqué", "paused": "Pause", "skipped": "Tour sauté",
                "verifier_ko": "Refusé par le vérificateur"}


def ratio_pct_par_usd():
    """(% de la semaine Claude pour 1 $ equivalent API, debut de la semaine).
    Meme calcul que les graphiques du quota."""
    e = lire_json(QUOTA, {})
    f7 = ((e.get("derniere_mesure") or {}).get("u") or {}).get("seven_day") or {}
    p7 = float(f7.get("utilization") or 0)
    reset = date_iso(f7.get("resets_at"))
    now = datetime.now(TZ)
    debut = (reset - timedelta(days=7)) if reset else now - timedelta(days=7)
    usd = 0.0
    for j, hs in (lire_json(ACTIVITE, {}).get("heures") or {}).items():
        for h, v in enumerate(hs):
            if datetime.strptime(j, "%Y-%m-%d").replace(tzinfo=TZ, hour=h) + timedelta(hours=1) > debut:
                usd += v
    return ((p7 / usd) if usd > 5 and p7 > 0 else None), debut.timestamp()


def depense_topics(depuis_par_topic):
    """$ equivalent API par topic depuis l'heure donnee (proxy-usage.jsonl)."""
    out = {t: 0.0 for t in depuis_par_topic}
    if not out:
        return out
    try:
        with open(USAGE, encoding="utf-8", errors="replace") as f:
            for ligne in f:
                if '"topic":null' in ligne:
                    continue
                try:
                    d = json.loads(ligne)
                except ValueError:
                    continue
                t = str(d.get("topic"))
                if t not in out:
                    continue
                try:
                    ts = datetime.fromisoformat(d["ts"].replace("Z", "+00:00")).timestamp()
                except (KeyError, ValueError):
                    continue
                if ts >= depuis_par_topic[t]:
                    out[t] += float(d.get("cout_usd") or 0)
    except OSError:
        pass
    return out


def tours_goal(sid, ratio):
    """Historique des tours (etat.json du plugin goal-preuve)."""
    sur = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)
    e = lire_json(os.path.join(HERMES, "goals", sur, "etat.json"), {})
    out = []
    for t in e.get("tours") or []:
        c = float(t.get("cout_usd") or 0)
        out.append({"n": t.get("n"), "h": datetime.fromtimestamp(t.get("t") or 0, TZ).strftime("%d/%m %H:%M"),
                    "verdict": VERDICT_MOTS.get(t.get("verdict"), t.get("verdict") or ""),
                    "raison": t.get("raison") or "", "obstacle": t.get("obstacle") or "",
                    "pct": round(c * ratio, 2) if ratio else None, "usd": round(c, 2)})
    return out


def goals():
    noms = lire_json(NOMS, {})
    relais = set(str(x) for x in lire_json(RELAIS, []))
    masques = lire_json(MASQUES, {})
    out, vus = [], set()
    try:
        c = _ro(STATE)
        lignes = c.execute("select key, value from state_meta where key like 'goal:%'").fetchall()
    except Exception as e:  # noqa: BLE001
        return {"goals": [], "erreur": str(e)[:200], "pilotable": injecteur_vivant()}
    for cle, val in lignes:
        try:
            g = json.loads(val)
        except ValueError:
            continue
        sid = cle[5:]
        if masques.get(sid) == g.get("created_at"):
            continue        # supprime depuis le Creeper (un nouveau goal reapparait)
        s = _session(c, sid)
        fil = s.get("thread_id", "")
        if not s:
            continue        # goal de test, sans session reelle
        vus.add(fil)
        t = g.get("last_turn_at") or g.get("created_at") or 0
        out.append({
            "id": sid, "topic": fil, "nom": noms.get(fil) or ("Topic " + fil if fil else "Message privé"),
            "chat": s.get("chat_id", ""), "texte": g.get("goal", ""),
            "etat": GOAL_MOTS.get(g.get("status"), g.get("status") or "?"),
            "tours": g.get("turns_used", 0), "max": g.get("max_turns", 20),
            "verdict": g.get("last_verdict") or "", "raison": g.get("last_reason") or "",
            "pause_raison": g.get("paused_reason") or "",
            "sous": [x.get("text") or x.get("goal") or str(x) for x in (g.get("subgoals") or []) if x][:8],
            "attente": g.get("waiting_reason") or "",
            "etapes": etapes_goal(sid),
            "courante": s.get("courante", True), "relais": fil in relais,
            "depuis": datetime.fromtimestamp(g.get("created_at") or 0, TZ).strftime("%d/%m %H:%M"),
            "dernier": datetime.fromtimestamp(t, TZ).strftime("%d/%m %H:%M") if t else "",
            "_t": t, "_debut": g.get("created_at") or 0})
    for fil in sorted(relais - vus):
        out.append({"id": "", "topic": fil, "nom": noms.get(fil) or "Topic " + fil, "etat": "sans_goal",
                    "relais": True, "texte": "", "_t": 0})
    # USER, 2026-10-13 : la consommation de chaque goal, en % de la semaine.
    ratio, debut_sem = ratio_pct_par_usd()
    debuts = {}
    for g in out:
        if g.get("id") and g.get("topic"):
            debuts[g["topic"]] = min(debuts.get(g["topic"], 9e12), g.get("_debut") or 9e12)
    usd = depense_topics(debuts)
    usd_sem = depense_topics({t: max(d, debut_sem) for t, d in debuts.items()})
    for g in out:
        if not g.get("id"):
            continue
        c = usd.get(g.get("topic"), 0.0)
        g["usd"] = round(c, 2)
        g["pct"] = round(c * ratio, 2) if ratio else None
        cs = usd_sem.get(g.get("topic"), 0.0)
        g["pct_sem"] = round(cs * ratio, 2) if ratio else None
        g["depuis"] = datetime.fromtimestamp(debuts.get(g.get("topic")) or 0, TZ).strftime("%d/%m")
        g["tours_detail"] = tours_goal(g["id"], ratio)
    for g in out:
        g.pop("_debut", None)
    ordre = {"en_cours": 0, "pause": 1, "sans_goal": 2, "fini": 3, "arrete": 4}
    out.sort(key=lambda g: (ordre.get(g["etat"], 5), -g["_t"]))
    for g in out:
        g.pop("_t")
    return {"goals": out, "pilotable": injecteur_vivant()}


def _goal_brut(sid):
    c = _ro(STATE)
    r = c.execute("select value from state_meta where key=?", ("goal:" + sid,)).fetchone()
    return (json.loads(r[0]), _session(c, sid)) if r else (None, {})


def goal_supprimer(sid):
    """Arrete le goal par la voie normale s'il vit encore, puis le masque du
    Creeper et range ses fichiers. La ligne d'Hermes reste (statut cleared)."""
    g, s = _goal_brut(sid)
    if not g:
        return False, "Goal introuvable."
    etat = GOAL_MOTS.get(g.get("status"), "")
    if etat in ("en_cours", "pause"):
        ok, msg = goal_action(sid, "arreter")
        if not ok:
            return False, msg
    elif etat == "fini":
        out = venv("from hermes_cli.goals import GoalManager\n"
                   "GoalManager(session_id=sys.argv[1]).clear()\nprint('ok')", sid)
        if out != "ok":
            return False, "Échec : " + out
    m = lire_json(MASQUES, {})
    m[sid] = g.get("created_at")
    os.makedirs(os.path.dirname(MASQUES), exist_ok=True)
    with open(MASQUES + ".tmp", "w") as f:
        json.dump(m, f, indent=1)
    os.replace(MASQUES + ".tmp", MASQUES)
    sur = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)
    dossier = os.path.join(HERMES, "goals", sur)
    if os.path.isdir(dossier):
        dest = os.path.join(HERMES, "goals", "_supprimes")
        os.makedirs(dest, exist_ok=True)
        os.replace(dossier, os.path.join(dest, "%s-%s" % (sur, time.strftime("%Y%m%d-%H%M%S"))))
    return True, "Goal supprimé."


def goal_action(sid, action):
    """pause | reprendre | arreter. Par le gateway (plugin creeper-goals) quand
    il ecoute : il range aussi le tour deja en file et le dit dans le topic.
    Sinon pause et arret s'ecrivent en base ; la reprise exige le gateway."""
    g, s = _goal_brut(sid)
    if not g:
        return False, "Goal introuvable."
    etat = GOAL_MOTS.get(g.get("status"), "")
    verbe = {"pause": "pause", "reprendre": "resume", "arreter": "clear"}.get(action)
    if not verbe:
        return False, "Action inconnue."
    if action == "pause" and etat != "en_cours":
        return False, "Ce goal ne tourne pas."
    # USER, 2026-10-18 : un goal arrete doit pouvoir repartir. /goal clear garde la
    # ligne (statut cleared) et /goal resume la reactive avec son contrat : le
    # gateway recree un GoalManager a chaque commande, qui relit la base.
    if action == "reprendre" and etat not in ("pause", "fini", "arrete"):
        return False, "Ce goal tourne déjà."
    if action == "arreter" and etat == "arrete":
        return False, "Déjà arrêté."
    if injecteur_vivant() and s.get("chat_id") and s.get("courante", True):
        os.makedirs(INJECTER, exist_ok=True)
        nom = os.path.join(INJECTER, "%d-%s.json" % (time.time() * 1000, action))
        with open(nom + ".tmp", "w") as f:
            json.dump({"chat_id": s["chat_id"], "thread_id": s.get("thread_id", ""),
                       "texte": "/goal " + verbe}, f)
        os.replace(nom + ".tmp", nom)
        for _ in range(20):
            time.sleep(0.5)
            if not os.path.exists(nom):
                break
        else:
            return False, "Hermès n'a pas pris la commande. Réessaie dans 1 minute."
        for _ in range(16):
            time.sleep(0.5)
            n, _s = _goal_brut(sid)
            if n and n.get("status") != g.get("status"):
                break
        mots = {"pause": "Goal en pause.", "reprendre": "Goal relancé. Un tour démarre.",
                "arreter": "Goal arrêté."}
        return True, mots[action]
    if action == "reprendre":
        if s and not s.get("courante", True):
            return False, "Le topic a changé de session. Relance le goal dans le topic."
        return False, "Hermès doit redémarrer pour ce bouton. Ce sera fait sous peu."
    out = venv("from hermes_cli.goals import GoalManager\n"
               "m = GoalManager(session_id=sys.argv[1])\n"
               "(m.pause(reason='pause depuis le Creeper') if sys.argv[2] == 'pause' else m.clear())\n"
               "print('ok')", sid, action)
    if out != "ok":
        return False, "Échec : " + out
    return True, "Goal en pause." if action == "pause" else "Goal arrêté."


def libelle():
    """« Activité · ProjetA tourne » ou « Activité · quota 70 % »."""
    ms = [resume(m) for m in registre()]
    actives = [m["nom"] for m in ms if m["etat"] in ("en_cours", "arret", "en_file")]
    if actives:
        return "Activité · " + (actives[0] + " tourne" if len(actives) == 1 else "%d tournent" % len(actives))
    q = quota()
    return "Activité · quota %d %%" % q["jour_pct"] if q else "Activité"


def main(a):
    if not a:
        print(__doc__)
        return 1
    c = a[0]
    if c == "liste":
        print(json.dumps(liste(), ensure_ascii=False))
    elif c == "arbre" and len(a) > 1:
        print(json.dumps(arbre(a[1]), ensure_ascii=False))
    elif c in ("lance", "stop") and len(a) > 1:
        ok, msg = lance(a[1], "force" in a[2:]) if c == "lance" else stop(a[1])
        if "--json" in a:
            print(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return 0 if ok else 1
    elif c == "garde" and len(a) > 2:
        garde(a[1], a[2])
    elif c == "etat" and len(a) > 1:
        m = mission(a[1])
        if not m:
            print("Mission inconnue.")
            return 1
        r = resume(m)
        mots = {"en_cours": "Un tour tourne depuis " + r.get("depuis", ""), "arret": "Arrêt en cours",
                "en_file": "Un tour part dans la minute", "pause": "À l'arrêt",
                "programme": "Prochain tour " + r.get("prochain", ""), "introuvable": "Job introuvable"}
        der = " Dernier tour {} ({}).".format(r["dernier"], r.get("statut") or "?") if r.get("dernier") else ""
        print("{} : {}.{}".format(r["nom"], mots[r["etat"]], der))
    elif c == "openrouter":
        print(json.dumps(openrouter(), ensure_ascii=False))
    elif c == "goals":
        print(json.dumps(goals(), ensure_ascii=False))
    elif c == "goal" and len(a) > 2:
        ok, msg = goal_supprimer(a[1]) if a[2] == "supprimer" else goal_action(a[1], a[2])
        print(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False) if "--json" in a else msg)
        return 0 if ok else 1
    elif c == "libelle":
        print(libelle())
    elif c == "ajoute" and len(a) > 4:
        print(ajoute(*a[1:6]))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
