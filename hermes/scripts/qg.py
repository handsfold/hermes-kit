#!/usr/bin/env python3
"""QG : l'etat de tous les topics, en une commande.

Le pari de ce fichier : l'orchestrateur ne relit jamais un transcript. Il lit
une ligne d'etat par sujet. Relire coute de plus en plus cher a mesure que les
conversations grossissent ; lire une ligne coute pareil au bout d'un an.

  qg              etat de tous les topics, du plus recent au plus vieux
  qg resumer      met a jour les resumes des topics qui ont bouge (1 LLM par topic)
  qg topic <id>   detail d'un topic
  qg nom <id> <nom>  nomme un topic a la main
"""
import json
import os
import re
import subprocess
import sqlite3
import sys
import time
import urllib.error
import urllib.request

DB = os.path.expanduser("~/.hermes/qg.db")
STATE = os.path.expanduser("~/.hermes/state.db")
ANNUAIRE = os.path.expanduser("~/.hermes/channel_directory.json")
NOMS = os.path.expanduser("~/.hermes/qg-noms.json")
OVERRIDES = os.path.expanduser("~/.hermes/gateway_model_overrides.json")
CONFIG = os.path.expanduser("~/.hermes/config.yaml")
AUTH = os.path.expanduser("~/.hermes/auth.json")
NEUTRE = "/tmp/hermes-qg-run"


PLATEFORMES = ("telegram", "discord", "slack", "signal", "matrix", "whatsapp", "feishu", "yuanbao")


def plateforme_depuis_cle(key):
    """'agent:main:telegram:group:-100...:2' -> 'telegram'."""
    for part in (key or "").split(":"):
        if part in PLATEFORMES:
            return part
    return ""


def cx_qg():
    c = sqlite3.connect(DB, timeout=5.0)
    c.row_factory = sqlite3.Row
    try:
        c.execute("ALTER TABLE topics ADD COLUMN nom_infere TEXT")
        c.commit()
    except sqlite3.OperationalError:
        pass  # deja la
    return c


def titres():
    """session_id -> titre, depuis state.db (seul endroit ou il vit)."""
    out = {}
    try:
        c = sqlite3.connect(f"file:{STATE}?mode=ro", uri=True, timeout=5.0)
        for sid, t in c.execute("SELECT id, title FROM sessions WHERE title IS NOT NULL"):
            out[sid] = t
        c.close()
    except Exception:
        pass
    return out


def noms_topics():
    """cle 'chat:thread' -> nom lisible.

    L'annuaire du gateway ne connait que 'Hermes QG / topic 2923' : l'API Bot de
    Telegram ne sait pas lister les sujets d'un forum. Les vrais noms viennent
    donc des messages de service (creation, renommage), captes par le gateway
    dans qg-noms.json, ou de `qg nom`. Ce fichier prime sur l'annuaire.
    """
    out = {}
    try:
        d = json.load(open(ANNUAIRE))
        out = {c["id"]: c.get("name", "") for c in d["platforms"].get("telegram", [])}
    except Exception:
        pass
    for cle, nom in charger_noms().items():
        if nom:
            out[cle] = nom
    return out


def charger_noms():
    try:
        return json.load(open(NOMS)) or {}
    except Exception:
        return {}


def cmd_nom(ident, nom):
    """Nomme un topic a la main, quand aucun message de service ne l'a fait."""
    c = cx_qg()
    r = c.execute("SELECT chat_id, thread_id FROM topics WHERE thread_id=? OR session_id=? "
                  "ORDER BY derniere_activite DESC LIMIT 1", (ident, ident)).fetchone()
    c.close()
    if not r or not r["chat_id"]:
        print(f"topic {ident} inconnu : il faut au moins un tour dedans")
        return 1
    cle = f'{r["chat_id"]}:{r["thread_id"]}'
    d = charger_noms()
    d[cle] = nom
    tmp = NOMS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, NOMS)
    print(f"{cle} = {nom}")
    return 0


def age(ts):
    if not ts:
        return "?"
    d = time.time() - ts
    if d < 3600:
        return f"{int(d // 60)} min"
    if d < 86400:
        return f"{int(d // 3600)} h"
    return f"{int(d // 86400)} j"


def lignes():
    c = cx_qg()
    rows = c.execute(
        "SELECT * FROM topics ORDER BY derniere_activite DESC").fetchall()
    c.close()
    # Topics supprimes de Telegram puis fusionnes (arbre.json, _fusion) : ils ne sont plus des sujets actifs.
    try:
        mortes = set(json.load(open(os.path.expanduser("~/.hermes/fil/arbre.json"))).get("_fusion", {}))
    except Exception:
        mortes = set()
    if mortes and not os.environ.get("QG_TOUT"):
        rows = [r for r in rows if str(r["thread_id"] or "") not in mortes]
    return rows


def cmd_etat():
    tt, nn = titres(), noms_topics()
    rows = lignes()
    if not rows:
        print("Aucun topic enregistre. Le hook qg alimente la base a la premiere "
              "reponse du gateway apres son redemarrage.")
        return 0
    print(f"{len(rows)} sessions suivies\n")
    for r in rows:
        cle = f'{r["chat_id"]}:{r["thread_id"]}' if r["chat_id"] else ""
        brut = nn.get(cle) or ""
        auto = (r["nom_infere"] or "") if "nom_infere" in r.keys() else ""
        if brut and not brut.endswith(f'topic {r["thread_id"]}'):
            nom = brut
        elif auto:
            nom = f'{auto} (deduit) · topic {r["thread_id"]}'
        else:
            nom = f'topic {r["thread_id"]}' if r["thread_id"] else (r["platform"] or "?")
        titre = tt.get(r["session_id"], "")
        etat = r["etat"] or titre or (r["dernier_message"] or "")[:100]
        frais = "" if r["tours"] == r["etat_tours"] else f' (+{r["tours"] - r["etat_tours"]} tours non resumes)'
        plat = r["platform"] or plateforme_depuis_cle(r["session_key"])
        # Sans plateforme, la cible est ':-100...:2' et send_message la refuse.
        # Mieux vaut ne rien afficher qu'afficher une cible qui echouera.
        cible = f' · cible {plat}:{cle}' if (cle and plat) else ""
        print(f'- {nom} · il y a {age(r["derniere_activite"])} · {r["tours"]} tours{frais}{cible}')
        print(f'  {etat}')
    return 0


def llm(prompt, modele="haiku", timeout=180):
    os.makedirs(NEUTRE, exist_ok=True)
    r = subprocess.run(
        ["claude", "-p", "--output-format", "json", "--model", modele,
         "--max-turns", "1", "--setting-sources", "", "--strict-mcp-config",
         "--no-session-persistence"],
        input=prompt, capture_output=True, text=True, timeout=timeout, cwd=NEUTRE)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:200] or "echec claude -p")
    try:
        return json.loads(r.stdout).get("result", "")
    except Exception:
        return r.stdout


def _cle_env(nom):
    """Valeur d'une variable de ~/.hermes/.env (jamais affichee)."""
    try:
        for l in open(os.path.expanduser("~/.hermes/.env")):
            if l.startswith(nom + "="):
                return l.split("=", 1)[1].strip().strip("'\"")
    except Exception:
        pass
    return os.environ.get(nom, "")


def cles_du_pool(prov, cle_figee=""):
    """Cles du pool d'identifiants pour ce provider, dans l'ordre du gateway
    (priorite puis ordre de declaration), en sautant celles marquees epuisees
    ou invalides. La cle figee dans l'override passe en dernier recours : c'est
    elle qui vieillit quand USER recharge une autre cle du pool (2026-11-06).
    """
    cles = []
    try:
        pool = json.load(open(AUTH)).get("credential_pool") or {}
        entrees = pool.get(f"custom:{prov}") or pool.get(prov) or []
        gardees = []
        for i, e in enumerate(entrees):
            c = e.get("access_token") or ""
            if c and e.get("last_status") not in ("exhausted", "invalid"):
                gardees.append((e.get("priority") or 0, i, c))
        cles = [c for _, _, c in sorted(gardees)]
    except Exception:
        pass
    if cle_figee and cle_figee not in cles:
        cles.append(cle_figee)
    return cles


def route_du_topic(session_key, thread_id=None):
    """La route LLM effective d'un topic, dans l'ordre du gateway :
    1) override de session (gateway_model_overrides.json, commande /model),
    2) platforms.telegram.channel_overrides de config.yaml (cle = thread_id),
    3) defaut global (bloc `model:`).
    Un duel PyRIT (`a-vs-b`) est ramene a sa cible (apres le dernier `-vs-`).
    """
    import yaml
    try:
        cfg = yaml.safe_load(open(CONFIG)) or {}
    except Exception:
        cfg = {}
    provs = cfg.get("providers") or {}

    def route(modele, prov, base="", mode="", cle=""):
        if "-vs-" in (modele or ""):
            modele = modele.rsplit("-vs-", 1)[1]
        p = provs.get(prov) or {}
        if not cle and p.get("key_env"):
            cle = _cle_env(p["key_env"])
        cle = cle or p.get("api_key", "")
        cles = cles_du_pool(prov, cle)
        return {"model": modele, "provider": prov,
                "base_url": base or p.get("base_url", ""),
                "api_mode": mode or p.get("api_mode", ""),
                "api_key": cles[0] if cles else cle, "cles": cles}

    try:
        ov = json.load(open(OVERRIDES)).get(session_key or "") or None
    except Exception:
        ov = None
    if ov and ov.get("model") and ov.get("base_url"):
        return route(ov["model"], ov.get("provider", ""), ov["base_url"],
                     ov.get("api_mode", ""), ov.get("api_key", ""))
    co = (((cfg.get("platforms") or {}).get("telegram") or {})
          .get("channel_overrides") or {})
    ch = co.get(str(thread_id)) if thread_id else None
    if ch and ch.get("model") and ch.get("provider"):
        return route(ch["model"], ch["provider"])
    m = cfg.get("model") or {}
    if not m.get("default"):
        return None
    return route(m["default"], m.get("provider", ""), m.get("base_url", ""),
                 m.get("api_mode", ""))


def _http_json(url, entetes, corps, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(corps).encode("utf-8"),
        headers={"content-type": "application/json", **entetes})
    with urllib.request.urlopen(req, timeout=timeout) as rep:
        return json.loads(rep.read().decode("utf-8"))


def llm_topic(prompt, route, timeout=180):
    """Un appel LLM direct sur la route du topic, sans passer par le CLI Claude
    (qui ne connait que les modeles Anthropic)."""
    base = (route.get("base_url") or "").rstrip("/")
    if route.get("api_mode") == "anthropic_messages":
        data = _http_json(base + "/v1/messages",
                          {"x-api-key": route.get("api_key", ""),
                           "anthropic-version": "2023-06-01"},
                          {"model": route["model"], "max_tokens": 700,
                           "messages": [{"role": "user", "content": prompt}]},
                          timeout)
        txt = "".join(b.get("text", "") for b in (data.get("content") or [])
                      if isinstance(b, dict) and b.get("type") == "text")
    else:
        corps = {"model": route["model"], "max_tokens": 700,
                 "messages": [{"role": "user", "content": prompt}]}
        # Refuseless refuse `medium` (HTTP 400) : effort explicite bas.
        if route.get("provider") == "refuseless":
            corps["reasoning_effort"] = "low"
        # Une cle en 402 ne tue pas le resume : on passe a la suivante du pool.
        cles = route.get("cles") or ([route["api_key"]] if route.get("api_key") else [])
        txt, dernier = "", None
        for c in cles:
            try:
                data = _http_json(base + "/chat/completions",
                                  {"Authorization": "Bearer " + c}, corps, timeout)
                txt = (((data.get("choices") or [{}])[0].get("message") or {})
                       .get("content") or "")
                if txt.strip():
                    break
                dernier = RuntimeError("reponse vide")
            except urllib.error.HTTPError as e:
                dernier = e
                if e.code in (401, 402, 403, 429):
                    continue
                raise
            except Exception as e:
                dernier = e
                continue
        else:
            raise RuntimeError(f"toutes les cles en echec ({dernier})")
    txt = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", txt, flags=re.S).strip()
    if not txt:
        raise RuntimeError(f"reponse vide de {route.get('model')}")
    return txt


GABARIT = """Voici le dernier echange d'une conversation de travail entre USER et son agent.

Derniere demande de USER :
{msg}

Derniere reponse de l'agent (tronquee) :
{rep}

Ecris l'etat de ce sujet en deux phrases maximum, en francais, a la troisieme personne.
Premiere phrase : ou en est le travail. Deuxieme phrase, seulement s'il y a lieu :
ce qui attend une decision de USER ou ce qui bloque.
Pas de preambule, pas de tiret cadratin, pas d'emoji. Si l'echange ne permet pas de
conclure, ecris exactement : indetermine.

Puis, sur une derniere ligne seule, prefixee de "SUJET: ", donne un nom de deux ou
trois mots pour ce sujet, comme un titre de dossier (ex: "SUJET: gateway Hermes").
Si tu ne peux pas conclure, ecris "SUJET: ?"."""


def cmd_resumer(force=False):
    c = cx_qg()
    rows = c.execute(
        "SELECT * FROM topics WHERE tours > etat_tours OR ? ORDER BY derniere_activite DESC",
        (1 if force else 0,)).fetchall()
    faits = 0
    for r in rows:
        if not (r["dernier_message"] or r["derniere_reponse"]):
            continue
        try:
            prompt = GABARIT.format(msg=(r["dernier_message"] or "(inconnue)")[:500],
                                    rep=(r["derniere_reponse"] or "(aucune)")[:500])
            route = route_du_topic(r["session_key"], r["thread_id"])
            try:
                if not route:
                    raise RuntimeError("pas de route")
                txt = llm_topic(prompt, route).strip()
            except Exception as e:
                print(f'  route {route and route.get("model")} en echec ({e}) : repli haiku',
                      file=sys.stderr)
                txt = llm(prompt).strip()
        except Exception as e:
            print(f'  echec sur {r["session_id"]}: {e}', file=sys.stderr)
            continue
        txt = txt.replace(":", " : ").replace("-", "-")
        # Le modele rend l'etat puis, en derniere ligne, un nom de dossier. Les
        # sujets de forum Telegram n'ont pas de nom lisible via l'API : ce nom
        # deduit est la seule chose qui rende la carte lisible d'un coup d'oeil.
        sujet = ""
        lignes_txt = [l for l in txt.splitlines() if l.strip()]
        if lignes_txt and lignes_txt[-1].strip().upper().startswith("SUJET:"):
            sujet = lignes_txt.pop().split(":", 1)[1].strip()
            if sujet in ("?", ""):
                sujet = ""
            txt = "\n".join(lignes_txt).strip()
        txt = txt[:400]
        c.execute("UPDATE topics SET etat=?, etat_maj=?, etat_tours=?, "
                  "nom_infere=CASE WHEN ?!='' THEN ? ELSE nom_infere END WHERE session_id=?",
                  (txt, time.time(), r["tours"], sujet, sujet, r["session_id"]))
        c.commit()
        faits += 1
    c.close()
    print(f"{faits} resume(s) mis a jour")
    return 0


def cmd_topic(ident):
    c = cx_qg()
    rows = c.execute(
        "SELECT * FROM topics WHERE thread_id=? OR session_id=? "
        "ORDER BY derniere_activite DESC", (ident, ident)).fetchall()
    c.close()
    if not rows:
        print("inconnu")
        return 1
    tt = titres()
    for r in rows:
        print(f'session {r["session_id"]} · {r["tours"]} tours · il y a {age(r["derniere_activite"])}')
        print(f'  titre  : {tt.get(r["session_id"], "(sans titre)")}')
        print(f'  etat   : {r["etat"] or "(pas encore resume)"}')
        print(f'  dernier: {(r["dernier_message"] or "")[:200]}')
    return 0


def main():
    a = sys.argv[1:]
    if not a:
        return cmd_etat()
    if a[0] == "resumer":
        return cmd_resumer(force="--force" in a)
    if a[0] == "topic" and len(a) > 1:
        return cmd_topic(a[1])
    if a[0] == "nom" and len(a) > 2:
        return cmd_nom(a[1], " ".join(a[2:]))
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
