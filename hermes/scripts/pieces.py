#!/usr/bin/env python3
"""pieces : archive et index de toutes les pieces jointes que USER envoie a Hermes.

Pourquoi : le gateway efface `~/.hermes/cache/{images,documents,...}` apres 24 h
(`_housekeeping_cache_cleanup`, gateway/run.py). Mesure du 2026-10-03 : sur 137
pieces citees par USER en 30 jours, 13 existaient encore. Au-dela d'un jour,
l'agent ne pouvait plus rouvrir un passeport, un contrat, une capture.

  pieces collecter            copie les pieces encore en cache, OCR, indexe
  pieces cherche "passeport"  recherche plein texte (legende, description, OCR)
  pieces recents [--n 10]     les dernieres pieces archivees
  pieces stats                volume archive

Archive : ~/.hermes/pieces/AAAA-MM/ (mode 700, hors Syncthing : il y a des
pieces d'identite). Index : ~/.hermes/pieces/index.db (SQLite FTS5).
Collecte lancee par pieces-collecte.timer (utilisateur, toutes les 20 min).
"""
import argparse, hashlib, os, re, shutil, sqlite3, subprocess, sys, time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
STATE = HOME / ".hermes/state.db"
ARCH = HOME / ".hermes/pieces"
DB = ARCH / "index.db"
CACHE = str(HOME / ".hermes/cache")

RX = [
    re.compile(r"Image attached at: ([^\]\n]+)\]"),
    re.compile(r"saved at: (" + re.escape(CACHE) + r"/.+?)\. Its text"),
    re.compile(r"(" + re.escape(CACHE) + r"/(?:images|documents|videos|audio)/[^\s\]\)]+)"),
]
BRUIT = re.compile(r"Gateway message origin \(JSON data.*", re.S)
IMG = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def base():
    ARCH.mkdir(mode=0o700, exist_ok=True)
    os.chmod(ARCH, 0o700)
    con = sqlite3.connect(DB)
    con.executescript("""
    create table if not exists pieces(
      sha text primary key, nom text, archive text, source text, sujet text,
      session_id text, msg_id integer, recu_le real, taille integer);
    create virtual table if not exists pieces_fts using fts5(
      sha unindexed, nom, contexte, ocr, tokenize='trigram remove_diacritics 1');
    create table if not exists vus(chemin text primary key);
    """)
    return con


def ocr(p: Path) -> str:
    ext = p.suffix.lower()
    try:
        if ext in IMG:
            r = subprocess.run(["tesseract", str(p), "-", "-l", "tha+fra+eng"],
                               capture_output=True, text=True, timeout=90)
            return r.stdout.strip()
        if ext == ".pdf":
            r = subprocess.run(["pdftotext", "-layout", "-l", "20", str(p), "-"],
                               capture_output=True, text=True, timeout=90)
            return r.stdout.strip()
        if ext in {".txt", ".md", ".csv", ".json"}:
            return p.read_text(errors="replace")[:200_000]
    except Exception as e:  # une piece illisible ne bloque pas la collecte
        return f"(OCR impossible : {e.__class__.__name__})"
    return ""


def collecter(args):
    con = base()
    st = sqlite3.connect(f"file:{STATE}?mode=ro", uri=True)
    sujets = {r[0]: f"{r[1]}/{r[2] or '-'} {r[3] or ''}".strip()
              for r in st.execute("select id, source, thread_id, title from sessions")}
    depuis = time.time() - args.jours * 86400
    rows = st.execute(
        "select id, session_id, content, timestamp from messages where role='user' "
        "and timestamp > ? and content like ? order by id", (depuis, f"%{CACHE}%"))
    neuf = perdu = 0
    for mid, sid, contenu, ts in rows:
        chemins = []
        for rx in RX:
            for c in rx.findall(contenu or ""):
                c = c.strip()
                if c not in chemins and not any(c in x for x in chemins):
                    chemins.append(c)
        for c in chemins:
            if con.execute("select 1 from vus where chemin=?", (c,)).fetchone():
                continue
            p = Path(c)
            if not p.is_file():
                perdu += 1
                continue
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            con.execute("insert or ignore into vus values(?)", (c,))
            if con.execute("select 1 from pieces where sha=?", (sha,)).fetchone():
                continue
            d = datetime.fromtimestamp(ts)
            dest = ARCH / d.strftime("%Y-%m") / f"{d:%Y%m%d-%H%M}_{p.name}"
            dest.parent.mkdir(mode=0o700, exist_ok=True)
            shutil.copy2(p, dest)
            texte = BRUIT.sub("", contenu or "").strip()[:8000]
            con.execute("insert into pieces values(?,?,?,?,?,?,?,?,?)",
                        (sha, p.name, str(dest), sujets.get(sid, "?").split(" ")[0],
                         sujets.get(sid, "?"), sid, mid, ts, dest.stat().st_size))
            con.execute("insert into pieces_fts values(?,?,?,?)",
                        (sha, p.name, texte, ocr(dest)))
            con.commit()
            neuf += 1
    con.commit()
    if not args.silencieux or neuf:
        print(f"{neuf} piece(s) archivee(s) · {perdu} deja effacee(s) par le gateway")


def afficher(rows):
    for nom, archive, sujet, ts, extrait in rows:
        print(f"{datetime.fromtimestamp(ts):%Y-%m-%d %H:%M}  [{sujet[:60]}]")
        print(f"   {archive}")
        if extrait:
            print("   " + re.sub(r"\s+", " ", extrait)[:220])


def cherche(args):
    con = base()
    mots = [m.replace('"', '') for m in args.question.split() if len(m) >= 3]
    if not mots:
        sys.exit("Mot trop court : 3 caracteres minimum (index par trigrammes).")
    q = " ".join(f'"{m}"' for m in mots)
    try:
        rows = con.execute(
            "select p.nom, p.archive, p.sujet, p.recu_le, "
            "snippet(pieces_fts, -1, '[', ']', ' ... ', 40) from pieces_fts f "
            "join pieces p on p.sha=f.sha where pieces_fts match ? "
            "order by bm25(pieces_fts) limit ?", (q, args.n)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if not rows:  # repli : un seul mot suffit
        q = " OR ".join(f'"{m}"' for m in mots)
        rows = con.execute(
            "select p.nom, p.archive, p.sujet, p.recu_le, "
            "snippet(pieces_fts, -1, '[', ']', ' ... ', 40) from pieces_fts f "
            "join pieces p on p.sha=f.sha where pieces_fts match ? "
            "order by bm25(pieces_fts) limit ?", (q, args.n)).fetchall()
    if not rows:
        print("Aucune piece ne correspond.")
    afficher(rows)


def recents(args):
    con = base()
    afficher(con.execute(
        "select p.nom, p.archive, p.sujet, p.recu_le, substr(f.contexte,1,200) "
        "from pieces p join pieces_fts f on f.sha=p.sha order by p.recu_le desc limit ?",
        (args.n,)).fetchall())


def stats(args):
    con = base()
    n, t = con.execute("select count(*), coalesce(sum(taille),0) from pieces").fetchone()
    print(f"{n} pieces archivees, {t/1e6:.1f} Mo, dans {ARCH}")
    for s, k in con.execute("select source, count(*) from pieces group by 1 order by 2 desc"):
        print(f"   {s}: {k}")


def main():
    ap = argparse.ArgumentParser(prog="pieces", description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("collecter"); a.add_argument("--jours", type=float, default=3)
    a.add_argument("--silencieux", action="store_true"); a.set_defaults(f=collecter)
    a = sp.add_parser("cherche"); a.add_argument("question"); a.add_argument("--n", type=int, default=8)
    a.set_defaults(f=cherche)
    a = sp.add_parser("recents"); a.add_argument("--n", type=int, default=10); a.set_defaults(f=recents)
    sp.add_parser("stats").set_defaults(f=stats)
    args = ap.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
