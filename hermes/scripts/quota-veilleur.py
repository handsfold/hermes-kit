#!/usr/bin/env python3
"""Veilleur du quota Claude (abonnement Max) : previent USER dans le topic QG.

Interroge l'endpoint OAuth d'usage avec le jeton de Claude Code, compare la
fenetre de 5 h aux seuils (50 %, 90 %) et poste UNE fois par seuil et par
fenetre. Quand une nouvelle fenetre s'ouvre apres une alerte a 90 %, le dit
aussi : USER sait qu'il peut repartir. La fenetre de 7 jours est surveillee
a 90 %, et jour par jour depuis le 2026-10-03.

Budget du jour : ce qui reste de la semaine, reparti a parts egales sur les
heures restantes avant la remise a zero, releve de la marge : on garde pour les
jours suivants la moyenne habituelle de USER (7 derniers jours complets), le reste
est permis aujourd'hui. Jamais sous la part egale. Compte sur la journee locale
(minuit a minuit, Bangkok). Un jour econome rend donc le lendemain plus large.
Alerte a 80 % puis 100 % du budget du jour. A 100 %, USER peut mettre en pause
les agents autonomes jusqu'a minuit : `quota-veilleur.py pause`. Reprise
automatique au jour suivant, ou `quota-veilleur.py reprise`.

Commandes : (rien) passage du timer · --test · etat · pause · reprise · alerte (renvoie l alerte avec ses boutons) · sonnet [medium|high] · opus.
Bascule : jamais seule. Le bouton de l alerte de depassement (plugin quota-bouton) lance `sonnet <effort>`; sans choix tout reste sur Opus; a minuit `rythme()` remet Opus et le dit au QG.

Etat : ~/.hermes/quota-veilleur.json. Option --test : poste l'etat courant.
"""
import json, os, subprocess, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from qg_adresse import adresse

HOME = os.path.expanduser("~")
CREDS = f"{HOME}/.claude/.credentials.json"
ETAT = os.environ.get("QUOTA_ETAT") or f"{HOME}/.hermes/quota-veilleur.json"  # QUOTA_ETAT : tests
ENV = f"{HOME}/.hermes/.env"
CHAT, THREAD = adresse()
SEUILS_5H = [50, 90]
SEUIL_7J = 90
SEUILS_JOUR = [80, 100]
# Crons mis en pause par « pause » : les agents autonomes, pas les rappels ni
# les gardes. Liste modifiable dans l'etat (cle « pausables »).
# projet-a-mission (7da31e4d4b05) n'y est plus : depuis le 2026-10-03 il ne part
# qu'a la main (projet-a-lance.sh). La reprise du lendemain le relancerait chaque heure.
PAUSABLES = ["6723555a335a", "0bf1506dee32", "b32f57e2f1a9",
             "090d2e809470"]
TZ = timezone(timedelta(hours=7))

def env(cle):
    for l in open(ENV):
        if l.startswith(cle + "="):
            return l.split("=", 1)[1].strip()
    return ""

# Boutons de l'alerte de depassement (callback_data lu par le plugin quota-bouton).
# Annonce de la nouvelle semaine : USER choisit le modele, puis l'effort, pour TOUS les topics
# Claude (demande de USER, 2026-10-26 : « switcher sur le modèle que je veux avec le niveau
# d'intelligence que je veux, appliqué à tous les topics »). Le plugin quota-bouton porte
# la meme grille (quota:m:<c>, puis quota:t:<c>:<effort>).
MODELES_CHOIX = {"o": ("claude-opus-5-5", "Opus 5.5"), "s": ("claude-sonnet-5-5", "Sonnet 5.5")}
EFFORTS_TOUS = ("low", "medium", "high", "xhigh", "max")
BOUTONS_SEMAINE = [[{"text": n, "callback_data": f"quota:m:{c}"} for c, (_, n) in MODELES_CHOIX.items()],
                   [{"text": "Garder ainsi", "callback_data": "quota:garder"}]]
BOUTONS = [[{"text": "Sonnet 5.5 · medium", "callback_data": "quota:s:medium"},
            {"text": "Sonnet 5.5 · high", "callback_data": "quota:s:high"}],
           [{"text": "Rester sur Opus", "callback_data": "quota:o"}]]

def poster(texte, boutons=None):
    if os.environ.get("QUOTA_SEC"):
        print("[a blanc]", texte, "[boutons]" if boutons else ""); return
    tok = env("TELEGRAM_BOT_TOKEN")
    champs = {"chat_id": CHAT, "message_thread_id": THREAD, "text": texte}
    if boutons:
        champs["reply_markup"] = json.dumps({"inline_keyboard": boutons})
    data = urllib.parse.urlencode(champs).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage",
                           data, timeout=20).read()

def usage():
    tok = json.load(open(CREDS))["claudeAiOauth"]["accessToken"]
    req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": f"Bearer {tok}",
                 "anthropic-beta": "oauth-2025-04-20"})
    return json.load(urllib.request.urlopen(req, timeout=20))

def cle(iso):
    """Cle stable d'une fenetre : l'API recalcule resets_at a chaque appel,
    aux millisecondes pres, et peut franchir une frontiere de minute.
    On arrondit au multiple de 5 minutes le plus proche."""
    if not iso:
        return ""
    d = datetime.fromisoformat(iso).astimezone(timezone.utc)
    t = round(d.timestamp() / 300) * 300
    return datetime.fromtimestamp(t, timezone.utc).isoformat()

def jour_fr(iso):
    d = datetime.fromisoformat(iso).astimezone(TZ)
    j = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"][d.weekday()]
    return f"{j} {d.day} à {d:%H:%M}"

def heure(iso):
    if not iso:
        return "?"
    d = datetime.fromisoformat(iso).astimezone(TZ)
    delta = d - datetime.now(TZ)
    m = max(0, int(delta.total_seconds() // 60))
    return f"{d:%H:%M} (dans {m // 60} h {m % 60:02d})" if m >= 60 else f"{d:%H:%M} (dans {m} min)"

def jour_local(now=None):
    return (now or datetime.now(TZ)).strftime("%Y-%m-%d")

HISTO = f"{HOME}/.hermes/quota-historique.jsonl"

def moy_jour_pct(now=None):
    """Moyenne de % de semaine consommés par jour sur les 7 derniers jours complets (hausses seules du relevé).
    Même base que la moyenne du cockpit. None si l'historique est trop court."""
    now = now or datetime.now(TZ)
    pts = []
    try:
        for l in open(HISTO, encoding="utf-8"):
            try:
                o = json.loads(l)
                pts.append((float(o["t"]), float(o["p7"])))
            except (ValueError, KeyError):
                continue
    except OSError:
        return None
    pts.sort()
    if not pts:
        return None
    d1 = datetime.fromtimestamp(pts[0][0], TZ)
    partiel = d1.strftime("%Y-%m-%d") if d1.hour >= 1 else None
    par_jour = {}
    for (t0, a), (t1, b) in zip(pts, pts[1:]):
        if b > a and t1 - t0 < 3 * 3600:
            j = datetime.fromtimestamp(t1, TZ).strftime("%Y-%m-%d")
            if j != partiel:
                par_jour[j] = par_jour.get(j, 0.0) + (b - a)
    auj = jour_local(now)
    recents = [v for k, v in sorted(par_jour.items()) if k != auj][-7:]
    return sum(recents) / len(recents) if recents else None

def budget_prevu(debut, h_sem, h_jour, moy):
    """Budget du jour en % de semaine. Part égale du reste de la semaine, relevée de la marge :
    ce qui reste moins ce qu'il faut garder pour les jours suivants à la moyenne habituelle de USER.
    Jamais sous la part égale."""
    reste = 100 - debut
    egal = reste * min(h_jour / h_sem, 1)
    if not moy:
        return round(egal, 2)
    gardé = moy * max(h_sem - h_jour, 0) / 24
    return round(max(egal, min(reste - gardé, reste)), 2)

def budget_jour(etat, p7, r7, k7):
    """Met a jour le point de depart du jour et rend (utilise, budget, pct).
    Depart pose au premier passage du jour, ou a l'ouverture d'une semaine."""
    now = datetime.now(TZ)
    j = etat.get("jour") or {}
    if j.get("date") != jour_local(now) or j.get("fenetre") != k7 or p7 < j.get("debut", 0):
        fin = datetime.fromisoformat(r7).astimezone(TZ) if r7 else now + timedelta(days=7)
        minuit = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        h_sem = max((fin - now).total_seconds() / 3600, 1)
        h_jour = max((min(minuit, fin) - now).total_seconds() / 3600, 0.5)
        moy = moy_jour_pct(now)
        j = {"date": jour_local(now), "fenetre": k7, "debut": p7,
             "budget": budget_prevu(p7, h_sem, h_jour, moy), "moy": round(moy, 1) if moy else None,
             "alertes": [], "pose": now.strftime("%H:%M")}
        etat["jour"] = j
    utilise = max(p7 - j["debut"], 0)
    pct = 100 * utilise / j["budget"] if j["budget"] > 0 else 100
    return utilise, j["budget"], pct

def cron(action, jid):
    import subprocess
    r = subprocess.run(["hermes", "cron", action, jid], capture_output=True,
                       text=True, timeout=60)
    return r.returncode == 0

def noms_crons():
    try:
        jobs = json.load(open(f"{HOME}/.hermes/cron/jobs.json"))
        jobs = jobs.get("jobs", jobs) if isinstance(jobs, dict) else jobs
        return {x["id"]: x for x in jobs}
    except Exception:
        return {}

def pause(etat, auto=False):
    crons = noms_crons()
    faits = []
    for jid in etat.get("pausables", PAUSABLES):
        x = crons.get(jid)
        if x and x.get("enabled") and x.get("state") != "paused" and cron("pause", jid):
            faits.append(jid)
    etat["en_pause"] = sorted(set(etat.get("en_pause", []) + faits))
    etat["pause_jour"] = jour_local()
    noms = ", ".join(crons[j]["name"] for j in faits) or "aucun (déjà en pause)"
    return f"Agents autonomes en pause jusqu'à minuit : {noms}."

def reprise(etat):
    crons = noms_crons()
    faits = [j for j in etat.get("en_pause", []) if cron("resume", j)]
    etat["en_pause"], etat["pause_jour"] = [], ""
    noms = ", ".join(crons.get(j, {}).get("name", j) for j in faits) or "aucun"
    return f"Agents autonomes relancés : {noms}."


# --- Rythme et modele (USER, 2026-10-18) -------------------------------------
# Opus et Sonnet puisent dans la meme enveloppe de 7 jours (seven_day_opus est
# vide). Le declencheur est donc l'AVANCE : % utilise moins % de semaine ecoulee.
CONFIG = f"{HOME}/.hermes/config.yaml"
OPUS, SONNET = "claude-opus-5-5", "claude-sonnet-5-5"
# Depuis le 2026-10-25 plus aucune bascule seule : USER choisit au bouton, sans choix tout
# reste sur Opus, et le jour suivant (minuit, Bangkok) tout revient sur Opus.
EFFORTS = ("medium", "high")

def avance(p7, r7):
    """(points d'avance sur le rythme, % de semaine ecoulee)."""
    fin = datetime.fromisoformat(r7).astimezone(TZ) if r7 else None
    if not fin:
        return 0.0, 0.0
    ecoule = 100 * (1 - max((fin - datetime.now(TZ)).total_seconds(), 0) / (7 * 86400))
    return p7 - ecoule, ecoule

def modele_defaut():
    import re
    m = re.search(r"^model:\n  default: (\S+)", open(CONFIG).read(), re.M)
    return m.group(1) if m else ""

def poser_modele(nom):
    import re
    t = open(CONFIG).read()
    n = re.sub(r"(^model:\n  default: )\S+", r"\g<1>" + nom, t, count=1, flags=re.M)
    if n != t and not os.environ.get("QUOTA_SEC"):
        open(CONFIG, "w").write(n)
    return n != t

SURCHARGES = f"{HOME}/.hermes/gateway_model_overrides.json"
SONNET_TOPIC = "claude-sonnet-5-5"

def relire_surcharges():
    """Le gateway ne lit gateway_model_overrides.json qu'au demarrage : redemarrage au calme, detache."""
    if os.environ.get("QUOTA_SEC") or os.environ.get("QUOTA_ETAT"):
        return
    import subprocess
    subprocess.Popen(["setsid", f"{HOME}/.hermes/scripts/redem-sur.sh"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)

CIBLE = SURCHARGES + ".cible"

def ecrire_surcharges(d, changes):
    """Ecrit les surcharges et garde les changements dans CIBLE. Le gateway reecrit
    tout son dict en memoire a chaque /model ou remise a zero de session : pendant
    que redem-sur.sh attend la fin des tours, il ecrasait notre ecriture (retour
    sur Opus de minuit perdu, 2026-10-26). ExecStartPre (appliquer-cible) remet
    donc CIBLE juste avant chaque demarrage."""
    if os.environ.get("QUOTA_SEC") or not changes:
        return
    c = json.load(open(CIBLE)) if os.path.exists(CIBLE) else {}
    c.update(changes)
    open(CIBLE + ".tmp", "w").write(json.dumps(c, indent=1)); os.replace(CIBLE + ".tmp", CIBLE)
    open(SURCHARGES + ".tmp", "w").write(json.dumps(d, indent=1)); os.replace(SURCHARGES + ".tmp", SURCHARGES)
    os.chmod(SURCHARGES, 0o600)
    relire_surcharges()

def appliquer_cible():
    """Lance par ExecStartPre du gateway : gateway arrete, rien ne peut l'ecraser."""
    if not os.path.exists(CIBLE):
        return 0
    c = json.load(open(CIBLE)); d = json.load(open(SURCHARGES)); n = 0
    for k, m in c.items():
        if isinstance(d.get(k), dict) and d[k].get("model") != m:
            d[k]["model"] = m; n += 1
    if n:
        open(SURCHARGES + ".tmp", "w").write(json.dumps(d, indent=1)); os.replace(SURCHARGES + ".tmp", SURCHARGES)
        os.chmod(SURCHARGES, 0o600)
    os.remove(CIBLE)
    return n

def topics_sonnet():
    d = json.load(open(SURCHARGES))
    return [k for k, v in d.items() if isinstance(v, dict) and v.get("model") == SONNET_TOPIC]

def surcharges_vers_sonnet(ry):
    """Les topics fixes sur Opus passent sur Sonnet ; l'original est garde dans ry['orig']."""
    d = json.load(open(SURCHARGES)); n = 0
    for k, v in d.items():
        if isinstance(v, dict) and str(v.get("model", "")).startswith("claude-opus") and k not in ry.setdefault("orig", {}):
            ry["orig"][k] = v["model"]; v["model"] = SONNET_TOPIC; n += 1
    ecrire_surcharges(d, {k: SONNET_TOPIC for k in ry.get("orig", {})})
    return n

def surcharges_restaurer(ry):
    orig = ry.pop("orig", {})
    if not orig:
        return 0
    d = json.load(open(SURCHARGES)); n = 0; ch = {}
    for k, m in orig.items():
        if k in d and isinstance(d[k], dict) and d[k].get("model") == SONNET_TOPIC:
            d[k]["model"] = m; ch[k] = m; n += 1
    ecrire_surcharges(d, ch)
    return n

def opus_tout(ry):
    """Bouton « Tout sur Opus » : retour normal, puis chaque topic encore sur Sonnet 5.5.
    Les topics en Sonnet low, choisis a la main, restent tels quels."""
    n = vers_opus(ry)
    d = json.load(open(SURCHARGES)); ch = {}
    for k in topics_sonnet():
        d[k]["model"] = OPUS; ch[k] = OPUS
    ecrire_surcharges(d, ch)
    return n + len(ch)

def poser_effort(niveau):
    """Effort propre au modele Sonnet (agent.reasoning_overrides), relu a chaque tour
    par le gateway : Opus garde son effort global. niveau None = on retire."""
    import re
    t = open(CONFIG).read()
    n = re.sub(r"^  reasoning_overrides:\n(?:    .*\n)*", "", t, count=1, flags=re.M)
    if niveau:
        n = re.sub(r"(^agent:\n)", r"\1  reasoning_overrides:\n    " + SONNET + ": " + niveau + "\n",
                   n, count=1, flags=re.M)
    if n != t and not os.environ.get("QUOTA_SEC"):
        open(CONFIG + ".tmp", "w").write(n); os.replace(CONFIG + ".tmp", CONFIG)
    return n != t

def vers_sonnet(ry, effort=None):
    poser_modele(SONNET); ry["auto"] = True
    ry["jour_bascule"] = jour_local()
    if effort in EFFORTS:
        poser_effort(effort); ry["effort"] = effort
    return surcharges_vers_sonnet(ry)

def vers_opus(ry):
    poser_modele(OPUS); ry["auto"] = False
    poser_effort(None); ry.pop("effort", None); ry.pop("jour_bascule", None)
    return surcharges_restaurer(ry)

NOMS_COURTS = {m: n for m, n in MODELES_CHOIX.values()}

def nom_court(m):
    return NOMS_COURTS.get(m) or m.replace("claude-", "").replace("-5-5", " 5.5").replace("-", " ").capitalize()

def effort_global(nouveau=None):
    """Lit, ou pose, agent.reasoning_effort : relu par le gateway a chaque tour."""
    lignes = open(CONFIG).read().split("\n"); dans = False
    for i, l in enumerate(lignes):
        if l == "agent:":
            dans = True; continue
        if dans and l and not l.startswith(" "):
            break
        if dans and l.startswith("  reasoning_effort:"):
            val = l.split(":", 1)[1].strip().strip("'\"")
            if nouveau and val != nouveau and not os.environ.get("QUOTA_SEC"):
                import shutil
                lignes[i] = "  reasoning_effort: " + nouveau
                open(CONFIG + ".tmp", "w").write("\n".join(lignes))
                shutil.copymode(CONFIG, CONFIG + ".tmp"); os.replace(CONFIG + ".tmp", CONFIG)
            return val
    return ""

def topics_claude():
    """Topics fixes sur un modele Claude simple (les couples PyRIT restent hors du choix)."""
    d = json.load(open(SURCHARGES))
    return {k: v["model"] for k, v in d.items() if isinstance(v, dict)
            and str(v.get("model", "")).startswith("claude-")
            and "-vs-" not in v["model"] and "pyrit" not in v["model"]}

def resume_topics():
    from collections import Counter
    c = Counter(nom_court(m) for m in topics_claude().values())
    return " · ".join(f"{n} sur {m}" for m, n in c.most_common())

def tout_sur(ry, modele, effort):
    """Choix de USER a l'annonce de la semaine : un modele et un effort pour tous les topics Claude.
    Choix manuel : aucun retour automatique a minuit."""
    poser_modele(modele); poser_effort(None); effort_global(effort)
    for c in ("auto", "orig", "effort", "jour_bascule"):
        ry.pop(c, None)
    ry["choix"] = {"modele": modele, "effort": effort, "jour": jour_local()}
    d = json.load(open(SURCHARGES)); ch = {}
    for k in topics_claude():
        if d[k]["model"] != modele:
            d[k]["model"] = modele; ch[k] = modele
    ecrire_surcharges(d, ch)
    return len(ch)

def rythme(etat, p7, r7, k7):
    """Rend les messages. Etat « rythme » : auto (bascule faite au bouton), jour_bascule, effort.
    Plus de bascule seule ni de recommandation : le bouton de l'alerte du jour decide."""
    ry = etat.setdefault("rythme", {})
    msgs = []
    if ry.get("fenetre") != k7:                      # nouvelle semaine : on repart
        # Annonce toujours, meme sans bascule en cours : le 2026-10-26 la remise
        # a zero n'a rien dit au QG parce que « auto » etait deja retombe a minuit.
        n = vers_opus(ry) if ry.get("auto") else 0
        ry.clear(); ry["fenetre"] = k7
        if etat.get("en_pause"):
            msgs.append("Nouvelle semaine, nouveau budget. " + reprise(etat))
        msgs.append(annonce_semaine(p7, r7, n))
        return msgs
    # Nouveau jour (minuit, Bangkok) : retour sur Opus, dit au QG.
    if ry.get("auto") and ry.get("jour_bascule") and ry["jour_bascule"] != jour_local():
        n = vers_opus(ry)
        msgs.append(f"Nouveau jour : Hermès repasse sur Opus 5.5 ({n} topics remis comme avant), "
                    "effort d'origine rétabli.")
    return msgs

def annonce_semaine(p7, r7, remis=0):
    texte = (f"Quota Claude : nouvelle semaine, compteur à {p7:.0f} %. "
             f"Prochaine remise à zéro {jour_fr(r7)}.")
    if remis:
        texte += f"\nRetour sur Opus 5.5 : {remis} topics remis comme avant."
    try:
        en_cours, eff = resume_topics(), effort_global()
    except Exception:  # noqa: BLE001
        en_cours, eff = "", ""
    if en_cours:
        texte += f"\nEn ce moment : {en_cours}. Effort : {eff or 'par défaut'}."
    # Bilan de la semaine finie (routine choisie par USER le 2026-10-27, rapport 4740).
    try:
        b = subprocess.run([sys.executable, f"{HOME}/.hermes/scripts/quota-bilan.py"],
                           capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:  # noqa: BLE001
        b = ""
    if b:
        texte += "\n\n" + b
    return (texte + "\n\nQuel modèle pour tous les topics ? Tu choisis l'effort juste après.", "semaine")

def ligne_etat(p5, r5, p7, r7, utilise, budget, pct):
    fin = datetime.fromisoformat(r7).astimezone(TZ) if r7 else None
    reste_j = (fin - datetime.now(TZ)).total_seconds() / 86400 if fin else 0
    return (f"Aujourd'hui : {utilise:.0f} % de la semaine consommés sur {budget:.1f} % prévus ({pct:.0f} % du budget du jour).\n"
            f"Semaine : {p7:.0f} %, remise à zéro {jour_fr(r7)} (dans {reste_j:.1f} j).\n"
            f"Fenêtre 5 h : {p5:.0f} %, remise à zéro à {heure(r5)}.")

HISTORIQUE = os.environ.get("QUOTA_HISTORIQUE") or f"{HOME}/.hermes/quota-historique.jsonl"

def historiser(u):
    """Une ligne par mesure : {t, p5, p7, r7}. Nourrit le graphique de l'ecran
    Accueil du Creeper (missions.py). Jamais bloquant : un echec ne doit pas
    empecher l'alerte."""
    try:
        f5, f7 = u.get("five_hour") or {}, u.get("seven_day") or {}
        if not f7:
            return
        ligne = {"t": int(time.time()), "p5": f5.get("utilization"),
                 "p7": f7.get("utilization"), "r7": cle(f7.get("resets_at"))}
        with open(HISTORIQUE, "a") as h:
            h.write(json.dumps(ligne) + "\n")
    except Exception as e:
        print(f"historique non ecrit : {e}", file=sys.stderr)

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ""
    test = "--test" in sys.argv
    etat = {"fenetre_5h": "", "alertes_5h": [], "fenetre_7j": "", "alerte_7j": False}
    if os.path.exists(ETAT):
        etat.update(json.load(open(ETAT)))
    # Pause et reprise ne dependent pas de l'API d'usage : elle rend des 429
    # quand on l'appelle trop (constate le 2026-10-03), et USER doit pouvoir
    # couper ses agents a tout moment.
    if cmd in ("pause", "reprise"):
        m = pause(etat) if cmd == "pause" else reprise(etat)
        json.dump(etat, open(ETAT, "w"), indent=1)
        poster(m)
        print(m)
        return 0
    # Bascule manuelle ou par bouton (plugin quota-bouton) : `sonnet [medium|high]`, `opus`.
    # Sans appel a l'API d'usage, comme pause et reprise.
    if cmd == "appliquer-cible":
        print("topics remis depuis la cible :", appliquer_cible())
        return 0
    if cmd == "semaine":
        # Renvoie l'annonce de la semaine maintenant (essai, ou annonce manquee).
        d = etat.get("derniere_mesure") or {}
        f7 = (d.get("u") or {}).get("seven_day") or {}
        m = annonce_semaine(float(f7.get("utilization") or 0), f7.get("resets_at") or "")
        texte, b = m if isinstance(m, tuple) else (m, None)
        poster(texte, BOUTONS_SEMAINE if b else None)
        print("poste :", texte)
        return 0
    if cmd == "tout":
        # Bouton de l'annonce de la semaine : `tout <o|s> <effort>`.
        c = sys.argv[2] if len(sys.argv) > 2 else ""
        eff = sys.argv[3] if len(sys.argv) > 3 else ""
        if c not in MODELES_CHOIX or eff not in EFFORTS_TOUS:
            print("usage : tout <o|s> <low|medium|high|xhigh|max>"); return 2
        n = tout_sur(etat.setdefault("rythme", {}), MODELES_CHOIX[c][0], eff)
        if not os.environ.get("QUOTA_SEC"):
            json.dump(etat, open(ETAT, "w"), indent=1)
        print("topics changés :", n)
        print("modèle :", modele_defaut(), "· effort :", effort_global())
        return 0
    if cmd == "opus-tout":
        ry = etat.setdefault("rythme", {})
        n = opus_tout(ry)
        if not os.environ.get("QUOTA_SEC"):
            json.dump(etat, open(ETAT, "w"), indent=1)
        print("topics changés :", n)
        return 0
    if cmd in ("sonnet", "opus"):
        ry = etat.setdefault("rythme", {})
        if cmd == "sonnet":
            eff = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in EFFORTS else None
            n = vers_sonnet(ry, eff)
        else:
            n = vers_opus(ry)
        if not os.environ.get("QUOTA_SEC"):
            json.dump(etat, open(ETAT, "w"), indent=1)
        print("topics changés :", n)
        print("modèle par défaut :", modele_defaut(), "· effort Sonnet :", ry.get("effort", "-"))
        return 0
    try:
        u = usage()
        etat["derniere_mesure"] = {"t": time.time(), "u": u}
        historiser(u)
    except Exception as e:
        # « etat » se contente de la derniere mesure de moins de 15 min.
        d = etat.get("derniere_mesure") or {}
        if cmd not in ("etat", "peut-lancer") or time.time() - d.get("t", 0) > 900:
            print(f"usage indisponible : {e}", file=sys.stderr)
            return 1
        u = d["u"]
    f5, f7 = u.get("five_hour") or {}, u.get("seven_day") or {}
    p5, r5 = float(f5.get("utilization") or 0), f5.get("resets_at") or ""
    p7, r7 = float(f7.get("utilization") or 0), f7.get("resets_at") or ""


    k5, k7 = cle(r5), cle(r7)
    msgs = []
    if etat["fenetre_5h"] and etat["fenetre_5h"] != k5:
        # Nouvelle fenetre seulement si le compteur est vraiment retombe.
        if 90 in etat["alertes_5h"] and p5 < SEUILS_5H[0]:
            msgs.append(f"Quota Claude : nouvelle fenêtre 5 h, compteur à {p5:.0f} %. Tu peux repartir.")
            etat["alertes_5h"] = []
        elif p5 < SEUILS_5H[0]:
            etat["alertes_5h"] = []
    etat["fenetre_5h"] = k5
    # Un seul message par passage : le seuil le plus haut franchi.
    franchis = [x for x in SEUILS_5H if p5 >= x and x not in etat["alertes_5h"]]
    if franchis:
        msgs.append(f"Quota Claude : fenêtre 5 h à {p5:.0f} %. Remise à zéro à {heure(r5)}. Semaine : {p7:.0f} %.")
        etat["alertes_5h"] = sorted(set(etat["alertes_5h"] + franchis))
    if etat["fenetre_7j"] != k7:
        etat["fenetre_7j"], etat["alerte_7j"] = k7, False
    if p7 >= SEUIL_7J and not etat["alerte_7j"]:
        msgs.append(f"Quota Claude : fenêtre 7 jours à {p7:.0f} %. Remise à zéro {jour_fr(r7)}.")
        etat["alerte_7j"] = True

    # Budget du jour, et reprise des agents mis en pause un jour precedent.
    if etat.get("en_pause") and etat.get("pause_jour") != jour_local():
        msgs.append("Nouveau jour, nouveau budget. " + reprise(etat))
    # Semaine remise a zero : plus rien a mettre en pause (le 2026-10-26 la pause du jour
    # etait restee apres la remise a zero de 19 h, l'ecran disait « en pause » a 0 %).
    elif etat.get("en_pause") and etat.get("jour", {}).get("fenetre") not in (None, k7):
        msgs.append("Nouvelle semaine, nouveau budget. " + reprise(etat))
    utilise, budget, pct = budget_jour(etat, p7, r7, k7)
    j = etat["jour"]
    franchis = [x for x in SEUILS_JOUR if pct >= x and x not in j["alertes"]]
    if franchis and not cmd:
        haut = max(franchis)
        # A 100 % : pause automatique jusqu'a minuit (demande de USER, 2026-10-03).
        conseil = ("\n" + pause(etat, auto=True) + "\nPour relancer avant minuit : « reprise quota » au QG."
                   if haut >= 100 and not etat.get("en_pause") else "")
        texte = f"Quota du jour à {pct:.0f} %.\n" + ligne_etat(p5, r5, p7, r7, utilise, budget, pct) + conseil
        if haut >= 100 and not etat.get("rythme", {}).get("auto"):
            texte += ("\n\nPasser tous les topics sur Sonnet 5.5 ? Choisis l'effort. "
                      "Sans choix, tout reste sur Opus. Retour sur Opus à minuit.")
            msgs.append((texte, "boutons"))
        else:
            msgs.append(texte)
        j["alertes"] = sorted(set(j["alertes"] + franchis))
    if cmd == "alerte":
        # Renvoie l'alerte avec ses boutons maintenant (essai, ou bouton perdu).
        msgs.append((f"Quota du jour à {pct:.0f} %.\n" + ligne_etat(p5, r5, p7, r7, utilise, budget, pct)
                     + "\n\nPasser tous les topics sur Sonnet 5.5 ? Choisis l'effort. "
                       "Sans choix, tout reste sur Opus. Retour sur Opus à minuit.", "boutons"))
    if not cmd and not test:
        msgs += rythme(etat, p7, r7, k7)
    if cmd == "peut-lancer":
        # Lanceur manuel de ProjetA : code 0 = feu vert, 1 = refus motive.
        if etat.get("en_pause") and etat.get("pause_jour") == jour_local():
            print(f"REFUS : agents en pause quota jusqu'à minuit ({pct:.0f} % du budget du jour).")
            code = 1
        elif pct >= 100:
            print(f"REFUS : budget du jour atteint ({pct:.0f} %, {utilise:.0f} % sur {budget:.1f} % prévus).")
            code = 1
        else:
            print(f"OK : {pct:.0f} % du budget du jour ({utilise:.0f} % sur {budget:.1f} % prévus).")
            code = 0
        json.dump(etat, open(ETAT, "w"), indent=1)
        return code
    if cmd == "etat":
        print(ligne_etat(p5, r5, p7, r7, utilise, budget, pct))
        av, ec = avance(p7, r7)
        print(f"Rythme : semaine {p7:.0f} % pour {ec:.0f} % écoulés, avance {av:+.0f} points. Modèle : {modele_defaut()}")
        print("En pause :", ", ".join(etat.get("en_pause", [])) or "rien")

    if test:
        msgs.append(f"Test du veilleur : 5 h à {p5:.0f} % (remise à zéro à {heure(r5)}), 7 jours à {p7:.0f} %.")
    json.dump(etat, open(ETAT, "w"), indent=1)
    for m in dict.fromkeys(msgs):
        texte, b = m if isinstance(m, tuple) else (m, None)
        poster(texte, BOUTONS_SEMAINE if b == "semaine" else BOUTONS if b else None)
        print("poste :", texte)
    print(f"5h={p5:.0f}% 7j={p7:.0f}% alertes={etat['alertes_5h']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
