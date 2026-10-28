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
import subprocess
import sqlite3
import sys
import time

DB = os.path.expanduser("~/.hermes/qg.db")
STATE = os.path.expanduser("~/.hermes/state.db")
ANNUAIRE = os.path.expanduser("~/.hermes/channel_directory.json")
NOMS = os.path.expanduser("~/.hermes/qg-noms.json")
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
            txt = llm(GABARIT.format(msg=(r["dernier_message"] or "(inconnue)")[:500],
                                     rep=(r["derniere_reponse"] or "(aucune)")[:500])).strip()
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
