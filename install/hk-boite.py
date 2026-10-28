#!/usr/bin/env python3
"""hk-boite : lit la boite mail du membre EN LECTURE SEULE et en fait une base locale.

Principe :
- passe par le Chrome du membre, deja connecte, via `opencli browser` ;
- ne clique, n'ouvre, n'envoie, ne supprime, n'archive rien : il lit la liste
  et, pour les fils DEJA lus seulement, la vue impression (qui ne change aucun etat) ;
- tout reste sur la machine : SQLite + recherche plein texte (FTS5),
  fichier ~/.local/share/hermes-kit/boite.db en mode 600.

Commandes :
  hk-boite indexer [--jours 90] [--max 1000] [--u 0] [--corps 40] [--fond]
  hk-boite cherche "question" [--n 5]
  hk-boite bilan [--sec] [--langue en|fr]
  hk-boite stats
"""

from __future__ import annotations

import argparse
import contextlib
import html
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

DONNEES = Path(os.environ.get("HK_BOITE_DIR", Path.home() / ".local/share/hermes-kit"))
BASE = DONNEES / "boite.db"
SESSION = "hk-boite"
HERMES = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))

FACTURE = re.compile(
    r"\b(invoice|facture|receipt|re[cç]u|payment|paiement|order|commande|bill|billing|"
    r"rechnung|factura|fattura|subscription|abonnement|renewal|statement)\b|ใบแจ้งหนี้|ใบเสร็จ|ใบกำกับ",
    re.I,
)
AUTO_SUJET = re.compile(
    r"(verify your|confirm your|automatic reply|auto-?reply|automatische antwort|out of office|"
    r"r[ée]ponse automatique|absence|abwesen|welcome to|password|login link|sign-?in|"
    r"security alert|"
    r"verification code|code de v[ée]rification|unsubscribe)",
    re.I,
)
AUTOMATE = re.compile(
    r"(no-?reply|do-?not-?reply|notification|newsletter|mailer|bounce|news@|info@|"
    r"marketing|digest|alerts?@|updates?@|hello@|team@|support@|accounts?@|security@|"
    r"calendar|billing|invoices?@|receipts?@|orders?@|payments?@|google\.com$|facebookmail|linkedin\.com$)",
    re.I,
)


# ---------------------------------------------------------------- navigateur
def opencli(*args: str, timeout: int = 60) -> str:
    """Appelle opencli browser et rend la sortie standard (les avis vont sur stderr)."""
    # binaire fixe, arguments en liste : pas de shell
    r = subprocess.run(  # noqa: S603
        ["opencli", "browser", SESSION, *args],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(f"opencli {args[0]} : {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


def evaluer(js: str, timeout: int = 60):
    sortie = opencli("eval", js, timeout=timeout)
    try:
        v = json.loads(sortie)
    except json.JSONDecodeError:
        return sortie
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v
    return v


JS_PAGE = r"""(async()=>{
const cible=%(hash)s; if(location.hash!==cible){location.hash=cible;}
const prem=()=>{const r=document.querySelector('tr.zA [data-legacy-thread-id]');
 return r?r.getAttribute('data-legacy-thread-id'):''};
const avant=%(avant)s; let t0=Date.now();
while(Date.now()-t0<12000){await new Promise(r=>setTimeout(r,400));
 const vide=document.querySelector('td.TC');
 if(location.hash===cible && prem() && prem()!==avant) break;
 if(location.hash===cible && vide && vide.offsetParent && !prem()) break;}
await new Promise(r=>setTimeout(r,500));
const moi=(document.title.match(/[\w.+-]+@[\w-]+(\.[\w-]+)+/)||[''])[0];
const lignes=[...document.querySelectorAll('div[role=main] tr.zA')]
 .filter(r=>r.offsetParent).map(r=>{
 const s=r.querySelector('[data-legacy-thread-id]');
 return {thread:s?s.getAttribute('data-legacy-thread-id'):'',
  dernier:s?s.getAttribute('data-legacy-last-message-id'):'',
  sujet:s?s.textContent.trim():'',
  extrait:((r.querySelector('.y2')||{}).textContent||'').replace(/^\s*[- ]\s*/,'').trim(),
  non_lu:r.classList.contains('zE'),
  nb:((r.querySelector('.bx0')||{}).textContent||'').trim(),
  libelles:[...r.querySelectorAll('div.at[title]')].map(x=>x.getAttribute('title')),
  gens:[...r.querySelectorAll('.yW span[email]')].map(x=>({email:x.getAttribute('email'),
   nom:x.getAttribute('name')||x.textContent.trim()}))};
});
return JSON.stringify({moi:moi,titre:document.title,lignes:lignes});})()"""

JS_CORPS = r"""(async()=>{
const ik=(window.GLOBALS||[])[9]; const ids=%(ids)s; const out={};
for(const t of ids){try{
 const u=location.pathname+'?ik='+ik+'&view=pt&search=all&th='+t;
 const r=await fetch(u,{credentials:'include'});
 let h=await r.text();
 h=h.replace(/<(script|style)[\s\S]*?<\/\1>/gi,' ')
  .replace(/<br\s*\/?>|<\/(p|div|tr|li|h\d)>/gi,'\n').replace(/<[^>]+>/g,' ');
 out[t]=h.replace(/[ \t ]+/g,' ').replace(/\n\s*\n+/g,'\n').slice(0,6000);
}catch(e){out[t]='';}}
return JSON.stringify(out);})()"""


def date_gmail(hexid: str) -> str:
    try:
        ms = int(hexid, 16) >> 20
        return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat(timespec="seconds")
    except (ValueError, OverflowError, OSError):
        return ""


def ligne_vers_mail(x: dict, moi: str, u: int, boite: int) -> dict | None:
    if not x.get("thread"):
        return None
    gens = [g for g in x.get("gens", []) if g.get("email")]
    autres = [g for g in gens if g["email"].lower() != moi.lower()]
    de = autres[0] if autres else (gens[0] if gens else {"email": "", "nom": ""})
    dernier = gens[-1]["email"].lower() if gens else ""
    hexid = x.get("dernier") or x["thread"]
    return {
        "id": f"gmail:{x['thread']}",
        "compte": moi,
        "fournisseur": "gmail",
        "thread": x["thread"],
        "date": date_gmail(hexid),
        "de_email": de["email"].lower(),
        "de_nom": de.get("nom") or de["email"],
        "participants": ", ".join(sorted({g["email"].lower() for g in gens})),
        "dernier_moi": 1 if (moi and dernier == moi.lower()) else 0,
        "sujet": x.get("sujet", ""),
        "extrait": x.get("extrait", ""),
        "corps": "",
        "non_lu": 1 if x.get("non_lu") else 0,
        "boite": boite,
        "libelles": ", ".join(x.get("libelles", [])),
        "lien": f"https://mail.google.com/mail/u/{u}/#all/{x['thread']}",
    }


def lister_gmail(requete: str, u: int, maxi: int, boite: int) -> tuple[str, list[dict]]:
    q = urllib.parse.quote(requete, safe="")
    opencli(
        "open",
        f"https://mail.google.com/mail/u/{u}/#search/{q}",
        "--window",
        "background",
        timeout=90,
    )
    moi, mails, avant, page = "", [], "''", 1
    while len(mails) < maxi:
        h = f"#search/{q}" + (f"/p{page}" if page > 1 else "")
        res = evaluer(JS_PAGE % {"hash": json.dumps(h), "avant": avant}, timeout=60)
        if not isinstance(res, dict):
            raise RuntimeError(f"page Gmail illisible : {str(res)[:200]}")
        moi = moi or res.get("moi", "")
        lignes = res.get("lignes", [])
        if not lignes:
            break
        nouveaux = [ligne_vers_mail(x, moi, u, boite) for x in lignes]
        nouveaux = [m for m in nouveaux if m]
        connus = {m["id"] for m in mails}
        nouveaux = [m for m in nouveaux if m["id"] not in connus]
        if not nouveaux:
            break
        mails += nouveaux
        avant = json.dumps(lignes[0]["thread"])
        if len(lignes) < 50:
            break
        page += 1
    if not moi:
        raise RuntimeError("compte Gmail introuvable : Chrome est-il connecte a Gmail ?")
    return moi, mails[:maxi]


def nettoyer_corps(texte: str) -> str:
    """Retire l'en-tete de la vue impression (titre, compte, nombre de messages)."""
    return re.sub(r"^.*?\b\d+ messages?\b\s*", "", texte, count=1, flags=re.S).strip()


def corps_gmail(threads: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(threads), 10):
        res = evaluer(JS_CORPS % {"ids": json.dumps(threads[i : i + 10])}, timeout=120)
        if isinstance(res, dict):
            out.update({k: nettoyer_corps(html.unescape(v)) for k, v in res.items()})
    return out


JS_OUTLOOK = r"""(async()=>{await new Promise(r=>setTimeout(r,4000));
const lignes=[...document.querySelectorAll('div[role=option][data-convid]')].map(r=>({
 thread:r.getAttribute('data-convid'),
 texte:(r.getAttribute('aria-label')||r.innerText||'').replace(/\s+/g,' ').trim(),
 non_lu:/unread|non lu/i.test(r.getAttribute('aria-label')||'')}));
return JSON.stringify({titre:document.title,lignes:lignes});})()"""


def lister_outlook(maxi: int) -> tuple[str, list[dict]]:
    """Best-effort : premiere page de la boite Outlook web (liste seulement, sans corps)."""
    opencli("open", "https://outlook.live.com/mail/0/", "--window", "background", timeout=90)
    res = evaluer(JS_OUTLOOK, timeout=60)
    mails = []
    for x in (res or {}).get("lignes", [])[:maxi]:
        mails.append(
            {
                "id": f"outlook:{x['thread']}",
                "compte": "outlook",
                "fournisseur": "outlook",
                "thread": x["thread"],
                "date": "",
                "de_email": "",
                "de_nom": x["texte"][:40],
                "participants": "",
                "dernier_moi": 0,
                "sujet": x["texte"][:200],
                "extrait": x["texte"],
                "corps": "",
                "non_lu": 1 if x.get("non_lu") else 0,
                "boite": 1,
                "libelles": "",
                "lien": "https://outlook.live.com/mail/0/",
            }
        )
    return "outlook", mails


# ---------------------------------------------------------------- base
COLONNES = [
    "id",
    "compte",
    "fournisseur",
    "thread",
    "date",
    "de_email",
    "de_nom",
    "participants",
    "dernier_moi",
    "sujet",
    "extrait",
    "corps",
    "non_lu",
    "boite",
    "libelles",
    "lien",
]


def ouvrir(chemin: Path = BASE) -> sqlite3.Connection:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    neuf = not chemin.exists()
    c = sqlite3.connect(chemin)
    if neuf:
        os.chmod(chemin, 0o600)
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE IF NOT EXISTS mails ("
        + ", ".join(c_ + (" PRIMARY KEY" if c_ == "id" else "") for c_ in COLONNES)
        + ")"
    )
    c.execute("CREATE TABLE IF NOT EXISTS meta (cle PRIMARY KEY, valeur)")
    try:
        c.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS mails_fts USING fts5(id UNINDEXED, de_nom,"
            " de_email, sujet, extrait, corps, tokenize='unicode61 remove_diacritics 2')"
        )
        c.execute("INSERT OR REPLACE INTO meta VALUES ('fts', '1')")
    except sqlite3.OperationalError:
        c.execute("INSERT OR REPLACE INTO meta VALUES ('fts', '0')")
    return c


def a_fts(c: sqlite3.Connection) -> bool:
    r = c.execute("SELECT valeur FROM meta WHERE cle='fts'").fetchone()
    return bool(r and r[0] == "1")


def enregistrer(c: sqlite3.Connection, mails: list[dict]) -> None:
    for m in mails:
        ancien = c.execute("SELECT corps FROM mails WHERE id=?", (m["id"],)).fetchone()
        if ancien and ancien["corps"] and not m.get("corps"):
            m["corps"] = ancien["corps"]
        c.execute(
            # noms de colonnes fixes (COLONNES), valeurs en parametres
            f"INSERT OR REPLACE INTO mails ({','.join(COLONNES)}) "  # noqa: S608
            f"VALUES ({','.join('?' * len(COLONNES))})",
            [m.get(k, "") for k in COLONNES],
        )
        if a_fts(c):
            c.execute("DELETE FROM mails_fts WHERE id=?", (m["id"],))
            c.execute(
                "INSERT INTO mails_fts (id, de_nom, de_email, sujet, extrait, corps)"
                " VALUES (?,?,?,?,?,?)",
                (m["id"], m["de_nom"], m["de_email"], m["sujet"], m["extrait"], m.get("corps", "")),
            )
    c.commit()


def cherche(c: sqlite3.Connection, question: str, n: int = 5) -> list[sqlite3.Row]:
    mots = [
        w
        for w in re.findall(r"[\w@.-]{3,}", question.lower())
        if w
        not in {
            "what",
            "who",
            "when",
            "the",
            "from",
            "did",
            "does",
            "about",
            "with",
            "for",
            "that",
            "quoi",
            "qui",
            "quand",
            "les",
            "des",
            "est",
            "pour",
            "avec",
            "dans",
            "une",
            "mon",
            "mes",
            "latest",
            "last",
            "send",
            "sent",
            "expect",
        }
    ]
    if not mots:
        return []
    if a_fts(c):
        req = " OR ".join('"' + w.replace('"', "") + '"' for w in mots)
        try:
            return c.execute(
                "SELECT m.* FROM mails_fts f JOIN mails m ON m.id=f.id WHERE mails_fts MATCH ? "
                "ORDER BY bm25(mails_fts, 0, 5, 5, 3, 1, 1), m.date DESC LIMIT ?",
                (req, n),
            ).fetchall()
        except sqlite3.OperationalError:
            pass
    cond = " OR ".join(
        "(sujet || ' ' || extrait || ' ' || corps || ' ' || de_nom || ' ' || de_email) LIKE ?"
        for _ in mots
    )
    return c.execute(
        # cond ne contient que des "... LIKE ?" fixes ; les mots passent en parametres
        f"SELECT * FROM mails WHERE {cond} ORDER BY date DESC LIMIT ?",  # noqa: S608
        [f"%{w}%" for w in mots] + [n],
    ).fetchall()


# ---------------------------------------------------------------- analyse
def humain(email: str) -> bool:
    return bool(email) and not AUTOMATE.search(email)


def jours_depuis(iso: str, maintenant: datetime | None = None) -> float:
    if not iso:
        return 9999
    maintenant = maintenant or datetime.now(UTC)
    return (maintenant - datetime.fromisoformat(iso)).total_seconds() / 86400


def analyser(mails: list[dict], moi: str = "", maintenant: datetime | None = None) -> dict:
    moi = moi.lower()
    dates = sorted(m["date"] for m in mails if m.get("date"))
    expediteurs = Counter()
    noms = {}
    for m in mails:
        if m["de_email"] and m["de_email"] != moi:
            expediteurs[m["de_email"]] += 1
            noms.setdefault(m["de_email"], m["de_nom"])
    attente = [
        m
        for m in mails
        if m.get("boite")
        and humain(m["de_email"])
        and m["de_email"] != moi
        and not m.get("dernier_moi")
        and not AUTO_SUJET.search(m["sujet"])
        and jours_depuis(m["date"], maintenant) <= 21
    ]
    attente.sort(key=lambda m: m["date"], reverse=True)
    factures = [m for m in mails if FACTURE.search(f"{m['sujet']} {m['extrait']}")]
    factures.sort(key=lambda m: m["date"], reverse=True)
    fournisseurs = Counter(m["de_nom"] or m["de_email"] for m in factures)
    return {
        "total": len(mails),
        "debut": dates[0][:10] if dates else "",
        "fin": dates[-1][:10] if dates else "",
        "non_lus": sum(1 for m in mails if m.get("non_lu")),
        "top": [(noms[e], e, k) for e, k in expediteurs.most_common(5)],
        "attente": attente,
        "factures": factures,
        "fournisseurs": fournisseurs.most_common(5),
    }


def questions(a: dict, langue: str = "en") -> list[tuple[str, dict]]:
    fr = langue == "fr"
    qs: list[tuple[str, dict]] = []
    vus = set()

    def ajoute(q, m):
        if m and m["id"] not in vus and len(qs) < 3:
            vus.add(m["id"])
            qs.append((q, m))

    if a["factures"]:
        m = a["factures"][0]
        ajoute(
            (f"Que m'a facture {m['de_nom']} ?" if fr else f"What did {m['de_nom']} bill me for?"),
            m,
        )
    if a["attente"]:
        m = a["attente"][0]
        ajoute(
            (
                f"Qu'attend {m['de_nom']} de moi ?"
                if fr
                else f"What does {m['de_nom']} expect from me?"
            ),
            m,
        )
    for nom, email, _ in a["top"]:
        tous = [m for m in a.get("_mails", []) if m["de_email"] == email]
        if tous:
            m = max(tous, key=lambda x: x["date"])
            ajoute((f"Quoi de neuf chez {nom} ?" if fr else f"What's the latest from {nom}?"), m)
    for m in a["attente"][1:] + a["factures"][1:]:
        ajoute((f"Resume-moi « {m['sujet'][:50]} »" if fr else f'Sum up "{m["sujet"][:50]}"'), m)
    return qs


def esc(t: str) -> str:
    t = (t or "").replace("\u2014", "-").replace("\u2013", "-")
    return html.escape(t, quote=False)


def lien(m: dict) -> str:
    return f'<a href="{m["lien"]}">{esc(m["sujet"][:60] or "(no subject)")}</a>'


def court(iso: str) -> str:
    return iso[:10] if iso else "?"


def rediger(a: dict, langue: str = "en", prenom: str = "") -> str:
    fr = langue == "fr"
    lignes_msg = []
    salut = (f"Bonjour {prenom}, " if fr else f"Hi {prenom}, ") if prenom else ""
    lignes_msg.append(
        f"<b>{esc(salut)}"
        + ("voici ta boite mail en 1 minute" if fr else "here is your mailbox in 1 minute")
        + "</b>"
    )
    lignes_msg.append(
        (
            f"{a['total']} mails lus du {a['debut']} au {a['fin']}, {a['non_lus']} non lus. "
            "Lecture seule, tout reste sur ta machine."
        )
        if fr
        else (
            f"{a['total']} mails read from {a['debut']} to {a['fin']}, {a['non_lus']} unread. "
            "Read-only, everything stays on your machine."
        )
    )
    if a["top"]:
        lignes_msg.append(
            "\n<b>" + ("Qui t'ecrit le plus" if fr else "Who writes to you most") + "</b>"
        )
        lignes_msg += [f"· {esc(n)} ({k})" for n, _, k in a["top"]]
    lignes_msg.append(
        "\n<b>"
        + ("Attend sans doute ta reponse" if fr else "Probably waiting for your reply")
        + f" ({len(a['attente'])})</b>"
    )
    if a["attente"]:
        lignes_msg += [
            f"· {lien(m)} · {esc(m['de_nom'])} · {court(m['date'])}" for m in a["attente"][:5]
        ]
    else:
        lignes_msg.append("· " + ("rien d'urgent" if fr else "nothing urgent"))
    lignes_msg.append(
        "\n<b>"
        + ("Factures et fournisseurs" if fr else "Invoices and suppliers")
        + f" ({len(a['factures'])})</b>"
    )
    if a["fournisseurs"]:
        lignes_msg += [f"· {esc(n)} ({k})" for n, k in a["fournisseurs"]]
    else:
        lignes_msg.append("· " + ("aucune trouvee" if fr else "none found"))
    qs = questions(a, langue)
    if qs:
        lignes_msg.append(
            "\n<b>"
            + ("3 questions a me poser maintenant" if fr else "3 questions you can ask me now")
            + "</b>"
        )
        for i, (q, m) in enumerate(qs, 1):
            lignes_msg.append(
                f"{i}. {esc(q)}\n   "
                + ("source" if fr else "source")
                + f" : {lien(m)} ({court(m['date'])})"
            )
    lignes_msg.append(
        "\n"
        + (
            "Ecris une de ces questions ici, je reponds avec le mail source."
            if fr
            else "Type one of these questions here. I answer with the source mail."
        )
    )
    texte = "\n".join(lignes_msg)
    return texte[:4000]


# ---------------------------------------------------------------- telegram
def envoyer_telegram(texte: str) -> bool:
    jeton = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    env = HERMES / ".env"
    if not jeton and env.exists():
        for ligne in env.read_text().splitlines():
            if ligne.startswith("TELEGRAM_BOT_TOKEN="):
                jeton = ligne.split("=", 1)[1].strip().strip("'\"")
    adr = HERMES / "qg-adresse.json"
    if os.environ.get("HK_QG_CHAT"):
        qg = {"chat": os.environ["HK_QG_CHAT"], "thread": os.environ.get("HK_QG_THREAD", "")}
    elif adr.exists():
        qg = json.loads(adr.read_text())
    else:
        qg = {}
    if not jeton or not qg.get("chat"):
        print("telegram non configure : message non envoye", file=sys.stderr)
        return False
    donnees = {
        "chat_id": qg["chat"],
        "text": texte,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if qg.get("thread"):
        donnees["message_thread_id"] = qg["thread"]
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{jeton}/sendMessage",
        data=urllib.parse.urlencode(donnees).encode(),
    )
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310  URL https fixe
        return json.load(r).get("ok", False)


# ---------------------------------------------------------------- commandes
def lire_tous(c: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT * FROM mails")]


def cmd_indexer(args) -> int:
    if args.fond:
        log = DONNEES / "boite-fond.log"
        DONNEES.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            os.path.abspath(__file__),
            "indexer",
            "--jours",
            str(args.jours),
            "--max",
            str(args.max),
            "--u",
            str(args.u),
            "--corps",
            str(args.corps),
            "--fournisseur",
            args.fournisseur,
        ]
        with open(log, "a") as f:
            subprocess.Popen(cmd, stdout=f, stderr=f, start_new_session=True)  # noqa: S603
        print(f"indexation de fond lancee, journal : {log}")
        return 0
    t0 = time.time()
    c = ouvrir()
    try:
        if args.fournisseur == "outlook":
            moi, mails = lister_outlook(args.max)
        else:
            moi, boite = lister_gmail(f"in:inbox newer_than:{args.jours}d", args.u, args.max, 1)
            reste = max(0, args.max - len(boite))
            _, autres = (
                lister_gmail(
                    f"newer_than:{args.jours}d -in:inbox -in:sent -in:spam -in:trash",
                    args.u,
                    reste,
                    0,
                )
                if reste
                else ("", [])
            )
            ids = {m["id"] for m in boite}
            mails = boite + [m for m in autres if m["id"] not in ids]
            # corps : seulement les fils deja lus (la vue impression ne change aucun etat)
            a = analyser(mails, moi)
            utiles = [m for m in a["attente"] + a["factures"] if not m["non_lu"]]
            utiles += sorted(
                (m for m in mails if not m["non_lu"]), key=lambda m: m["date"], reverse=True
            )
            fils = list(dict.fromkeys(m["thread"] for m in utiles))[: args.corps]
            corps = corps_gmail(fils) if fils else {}
            for m in mails:
                m["corps"] = corps.get(m["thread"], "")
    finally:
        # la session se ferme meme apres une erreur ; un echec ici ne change rien
        with contextlib.suppress(Exception):
            opencli("close", timeout=20)
    enregistrer(c, mails)
    c.execute("INSERT OR REPLACE INTO meta VALUES ('moi', ?)", (moi,))
    c.execute(
        "INSERT OR REPLACE INTO meta VALUES ('maj', ?)",
        (datetime.now(UTC).isoformat(timespec="seconds"),),
    )
    c.commit()
    print(
        f"HK_BOITE mails={len(mails)} corps={sum(1 for m in mails if m['corps'])}"
        f" compte={moi} duree={time.time() - t0:.0f}s"
    )
    return 0


def cmd_bilan(args) -> int:
    c = ouvrir()
    mails = lire_tous(c)
    if not mails:
        print("base vide : lancer d'abord hk-boite indexer", file=sys.stderr)
        return 2
    moi = (c.execute("SELECT valeur FROM meta WHERE cle='moi'").fetchone() or [""])[0]
    a = analyser(mails, moi)
    a["_mails"] = mails
    texte = rediger(a, args.langue, os.environ.get("HK_PRENOM", ""))
    if args.sec:
        print(texte)
        return 0
    ok = envoyer_telegram(texte)
    print(texte if not ok else "bilan envoye sur Telegram")
    return 0 if ok else 3


def cmd_cherche(args) -> int:
    c = ouvrir()
    res = cherche(c, args.question, args.n)
    if args.json:
        print(json.dumps([dict(r) for r in res], ensure_ascii=False, indent=1))
        return 0
    if not res:
        print("rien trouve dans la base locale")
        return 1
    for r in res:
        texte = (r["corps"] or r["extrait"] or "").strip().replace("\n", " ")
        print(
            f"- {court(r['date'])} · {r['de_nom']} <{r['de_email']}> · {r['sujet']}\n"
            f"  {texte[:400]}\n  source : {r['lien']}"
        )
    return 0


def cmd_stats(args) -> int:
    c = ouvrir()
    n = c.execute("SELECT COUNT(*), SUM(corps<>''), MIN(date), MAX(date) FROM mails").fetchone()
    meta = dict(c.execute("SELECT cle, valeur FROM meta").fetchall())
    print(
        json.dumps(
            {
                "mails": n[0],
                "corps": n[1] or 0,
                "debut": n[2],
                "fin": n[3],
                **meta,
                "base": str(BASE),
            },
            ensure_ascii=False,
        )
    )
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="hk-boite", description="Boite mail en lecture seule, base locale."
    )
    s = p.add_subparsers(dest="cmd", required=True)
    i = s.add_parser("indexer")
    i.add_argument("--jours", type=int, default=90)
    i.add_argument("--max", type=int, default=1000)
    i.add_argument(
        "--u",
        type=int,
        default=int(os.environ.get("HK_BOITE_U", "0")),
        help="index du compte Gmail dans Chrome (/mail/u/N)",
    )
    i.add_argument(
        "--corps", type=int, default=40, help="nombre de fils deja lus dont on garde le texte"
    )
    i.add_argument("--fournisseur", choices=["gmail", "outlook"], default="gmail")
    i.add_argument("--fond", action="store_true")
    b = s.add_parser("bilan")
    b.add_argument("--sec", action="store_true", help="affiche sans envoyer")
    b.add_argument("--langue", choices=["en", "fr"], default=os.environ.get("HK_LANGUE", "en"))
    q = s.add_parser("cherche")
    q.add_argument("question")
    q.add_argument("--n", type=int, default=5)
    q.add_argument("--json", action="store_true")
    s.add_parser("stats")
    args = p.parse_args(argv)
    return {"indexer": cmd_indexer, "bilan": cmd_bilan, "cherche": cmd_cherche, "stats": cmd_stats}[
        args.cmd
    ](args)


if __name__ == "__main__":
    sys.exit(main())
