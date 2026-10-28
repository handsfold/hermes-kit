#!/usr/bin/env python3
"""Relais reseau du Creeper : hote-1 parle a l'appli sans ADB ni Tailscale.

POURQUOI (2026-10-03)
Toute la voix du Creeper passait par ADB : hote-1 poussait les mp3 et lancait
les intents. Debogage sans fil coupe, Tailscale coupe, telephone redemarre :
plus rien. USER veut que la bulle marche a la maison comme en 4G. L'appli
interroge donc elle-meme ce serveur, en HTTPS, par le tunnel Cloudflare
`exemple.tld`, avec un jeton secret.

L'AUTRE SENS (etape 2)
L'appli poste aussi ses appuis (POST /appui, la meme ligne que cmd.txt) et
les tours de voix de USER (POST /depot?nom=tour-<ms>.wav). Le garde lit
appuis.txt, voixtour.sh prend le WAV dans recus/ : plus besoin d'ADB pour
entendre USER.

DEUX MODES
  creeper-relais.py serveur
      Le service `creeper-relais` (port 8725). Long-poll de 25 s au plus,
      sous la limite de 100 s de Cloudflare.
  creeper-relais.py deposer <arguments adb...>
      Appele par adb-garde. Si la commande vise l'appli et que le relais est
      vivant, la met en file et attend l'accuse de l'appli. Code 0 : livre
      par le reseau. Code 1 : a faire par ADB, comme avant. Un echec du relais
      retombe donc toujours sur ADB, jamais sur un silence.

Le jeton vit dans ~/.hermes/creeper-relais.token (600), jamais ici.
"""
import hmac
import json
import os
import re
import shlex
import shutil
import subprocess
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

APPLI = "com.poste.pixelgarde"
PORT = int(os.environ.get("CREEPER_RELAIS_PORT", "8725"))
MISSIONS = os.path.expanduser("~/.hermes/scripts/missions.py")
MISSIONS_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "missions", "index.html")
RACINE = os.environ.get("CREEPER_RELAIS_RACINE") or os.path.expanduser("~/.hermes/creeper-relais")
SPOOL = os.path.join(RACINE, "spool")
BASE = os.path.join(RACINE, "file.db")
ETAT = os.path.join(RACINE, "etat")     # ecran et verrou, dits par l'appli
VU = os.path.join(RACINE, "vu")          # touche a chaque appel de l'appli
APPUIS = os.path.join(RACINE, "appuis.txt")   # les appuis de USER, une ligne chacun
RECUS = os.path.join(RACINE, "recus")         # les tours de voix de USER
NOM_RECU = re.compile(r"^tour-[0-9]{10,16}\.wav$")
DEPOT_MAX = 25 * 1024 * 1024
JETON = os.environ.get("CREEPER_RELAIS_JETON") or os.path.expanduser("~/.hermes/creeper-relais.token")
PREFIXES = ("/sdcard/Android/data/{}/files/".format(APPLI),
            "/storage/emulated/0/Android/data/{}/files/".format(APPLI))
SOUS_AM = ("start-foreground-service", "startforegroundservice",
           "startservice", "start-service", "broadcast", "start",
           "start-activity")
VIVANT_S = 40       # l'appli a appele il y a moins de 40 s
PERIME_S = 600      # un ordre de plus de 10 min ne se joue plus
ATTENTE_ACK = {"push": 20.0, "am": 8.0}


def base():
    os.makedirs(SPOOL, exist_ok=True)
    c = sqlite3.connect(BASE, timeout=10, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS ev (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, cree REAL, type TEXT,
        corps TEXT, statut TEXT DEFAULT 'attente', note TEXT)""")
    return c


# ------------------------------------------------------------------ deposer

def relais_vivant():
    try:
        return time.time() - os.path.getmtime(VU) < VIVANT_S
    except OSError:
        return False


def traduire(args):
    """Arguments adb -> liste d'evenements, ou None si ADB doit s'en charger."""
    a = list(args)
    while a and a[0].startswith("-"):
        opt = a.pop(0)
        if opt in ("-s", "-t", "-H", "-P", "-L") and a:
            a.pop(0)
    if not a:
        return None
    verbe, reste = a[0], a[1:]
    if verbe == "push":
        fich = [x for x in reste if not x.startswith("-")]
        if len(fich) != 2 or not os.path.isfile(fich[0]):
            return None
        src, dst = fich
        rel = None
        for p in PREFIXES:
            if dst.startswith(p):
                rel = dst[len(p):]
        if rel is None:
            return None
        if rel == "" or rel.endswith("/"):
            rel += os.path.basename(src)
        if ".." in rel.split("/") or rel.startswith("/"):
            return None
        return [{"type": "push", "rel": rel, "src": src}]
    if verbe != "shell" or not reste:
        return None
    ligne = " ".join(reste)
    try:
        lx = shlex.shlex(ligne, posix=True, punctuation_chars=";&|<>()")
        lx.whitespace_split = True
        jetons = list(lx)
    except ValueError:
        return None
    cmds, cour = [], []
    for j in jetons:
        if j in (";", "&&"):
            if cour:
                cmds.append(cour)
            cour = []
        elif j and set(j) <= set(";&|<>()"):
            return None              # tube, redirection : pas pour nous
        else:
            cour.append(j)
    if cour:
        cmds.append(cour)
    evs = []
    for c in cmds:
        if len(c) < 4 or c[0] != "am" or c[1] not in SOUS_AM:
            return None
        if "-n" not in c or not c[c.index("-n") + 1].startswith(APPLI + "/"):
            return None
        evs.append({"type": "am", "args": c})
    return evs or None


def deposer(args):
    if not relais_vivant():
        return 1
    evs = traduire(args)
    if not evs:
        return 1
    c = base()
    for ev in evs:
        corps = {k: v for k, v in ev.items() if k != "src"}
        cur = c.execute("INSERT INTO ev (cree, type, corps) VALUES (?,?,?)",
                        (time.time(), ev["type"], json.dumps(corps)))
        seq = cur.lastrowid
        if ev["type"] == "push":
            tmp = os.path.join(SPOOL, ".{}".format(seq))
            shutil.copyfile(ev["src"], tmp)
            os.replace(tmp, os.path.join(SPOOL, str(seq)))
            c.execute("UPDATE ev SET statut='pret' WHERE seq=?", (seq,))
        else:
            c.execute("UPDATE ev SET statut='pret' WHERE seq=?", (seq,))
        # Chaque ordre attend son accuse avant le suivant : un VOIXDIRE ne
        # doit jamais partir avant que son mp3 soit pose.
        fin = time.time() + ATTENTE_ACK[ev["type"]]
        while time.time() < fin:
            st, note = c.execute("SELECT statut, note FROM ev WHERE seq=?",
                                 (seq,)).fetchone()
            if st == "ok":
                break
            if st == "echec":
                journal("echec {} {} : {}".format(seq, ev["type"], note))
                return 1
            time.sleep(0.05)
        else:
            # Trop tard : on l'annule pour que l'appli ne le joue pas en
            # double apres le repli ADB.
            c.execute("UPDATE ev SET statut='annule' WHERE seq=? AND statut!='ok'",
                      (seq,))
            if c.execute("SELECT statut FROM ev WHERE seq=?", (seq,)).fetchone()[0] != "ok":
                journal("delai {} {}, repli adb".format(seq, ev["type"]))
                return 1
    return 0


def journal(m):
    try:
        with open(os.path.join(RACINE, "relais.log"), "a") as f:
            f.write("{} {}\n".format(time.strftime("%F %T"), m))
    except OSError:
        pass


# ------------------------------------------------------------------ serveur

def noter_etat(q):
    """ecran, verrou et casque (0|1), ecrits pour la garde et ecran-indispo.sh (sans ADB)."""
    e, v = q.get("ecran", [""])[0], q.get("verrou", [""])[0]
    if e not in ("0", "1") or v not in ("0", "1"):
        return
    ligne = "ecran={} verrou={}".format(e, v)
    # Ecouteurs (appli 2.35) : une appli plus ancienne ne l'envoie pas.
    c = q.get("casque", [""])[0]
    if c in ("0", "1"):
        ligne += " casque=" + c
    ligne += "\n"
    # Chaque bascule est journalisee (2026-10-10) : un rapport retenu pour
    # « ecran verrouille » doit pouvoir se confronter a ce que l'appli a dit.
    try:
        avant = open(ETAT).read()
    except OSError:
        avant = ""
    if avant != ligne:
        journal("etat " + ligne.strip())
    tmp = ETAT + ".tmp"
    with open(tmp, "w") as f:
        f.write(ligne)
    os.replace(tmp, ETAT)


ETAT_LANGUE = os.path.expanduser("~/.hermes/telegram-menus.json")


def langue():
    """La langue unique du systeme : cle « langue » du fichier d'etat d'Hermes.
    « en » par defaut, « fr » seulement si demande. L'appli l'applique."""
    try:
        with open(ETAT_LANGUE, encoding="utf-8") as f:
            v = str(json.load(f).get("langue", "en")).strip().lower()
    except (OSError, ValueError, AttributeError):
        v = "en"
    return v if v in ("en", "fr") else "en"


def jeton():
    with open(JETON) as f:
        return f.read().strip()


class Gestion(BaseHTTPRequestHandler):
    server_version = "creeper-relais"

    def log_message(self, fmt, *a):
        pass

    def autorise(self):
        h = self.headers.get("Authorization", "")
        return h.startswith("Bearer ") and hmac.compare_digest(
            h[7:].strip().encode(), self.server.jeton.encode())

    def repondre(self, code, corps=b"", typ="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if corps:
            self.wfile.write(corps)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/sante":
            return self.repondre(200, b'{"ok":true}')
        if u.path.startswith("/missions"):
            return self.missions(u, None)
        if not self.autorise():
            return self.repondre(401, b'{"erreur":"jeton"}')
        if u.path == "/evenements":
            # Seul l'appel de l'appli rend le relais « vivant ».
            open(VU, "a").close()
            os.utime(VU, None)
            noter_etat(parse_qs(u.query))
            return self.evenements(parse_qs(u.query))
        if u.path.startswith("/fichier/"):
            seq = u.path.rsplit("/", 1)[1]
            p = os.path.join(SPOOL, seq)
            if not seq.isdigit() or not os.path.isfile(p):
                return self.repondre(404)
            with open(p, "rb") as f:
                return self.repondre(200, f.read(), "application/octet-stream")
        self.repondre(404)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path.startswith("/missions"):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return self.missions(u, json.loads(self.rfile.read(n) or b"{}"))
            except ValueError:
                return self.repondre(400)
        if not self.autorise():
            return self.repondre(401, b'{"erreur":"jeton"}')
        if u.path == "/depot":
            return self.depot(parse_qs(u.query))
        if u.path == "/etat":
            noter_etat(parse_qs(u.query))
            return self.repondre(200, b'{"ok":true}')
        n = int(self.headers.get("Content-Length") or 0)
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.repondre(400)
        if u.path == "/appui":
            ligne = " ".join(str(d.get("ligne", "")).split())[:200]
            # Meme format que cmd.txt : "<millisecondes> <id>".
            if not re.match(r"^[0-9]{10,16} \S", ligne):
                return self.repondre(400)
            with open(APPUIS, "a") as f:
                f.write(ligne + "\n")
            return self.repondre(200, b'{"ok":true}')
        if u.path == "/accuse":
            c = base()
            try:
                c.execute("UPDATE ev SET statut=?, note=? WHERE seq=? AND statut='livre'",
                          ("ok" if d.get("ok") else "echec", str(d.get("note", ""))[:300],
                           int(d.get("seq", 0))))
            finally:
                c.close()
            return self.repondre(200, b'{"ok":true}')
        self.repondre(404)

    # ------------------------------------------------------------ Missions
    # Ecran Missions (2026-10-03) : une page web dans l'appli (WebView).
    # La 1re requete porte le Bearer ; le relais pose alors un cookie
    # HttpOnly limite a /missions, que les appels suivants de la page
    # renvoient seuls. Les donnees viennent de ~/.hermes/scripts/missions.py.
    def cookie_ok(self):
        for morceau in self.headers.get("Cookie", "").split(";"):
            k, _, v = morceau.strip().partition("=")
            if k == "creeper" and hmac.compare_digest(
                    v.encode(), self.server.jeton.encode()):
                return True
        return False

    def missions(self, u, corps):
        bearer = self.autorise()
        if not (bearer or self.cookie_ok()):
            return self.repondre(401, b'{"erreur":"jeton"}')
        chemin = u.path.rstrip("/") or "/missions"
        if corps is None and chemin in ("/missions", "/missions/index.html"):
            if not u.path.endswith("/"):
                self.send_response(302)
                self.send_header("Location", "/missions/")
                self.end_headers()
                return
            with open(MISSIONS_PAGE, "rb") as f:
                page = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            if bearer:
                self.send_header("Set-Cookie", "creeper={}; Path=/missions; HttpOnly; "
                                 "Secure; SameSite=Strict; Max-Age=31536000".format(self.server.jeton))
            self.end_headers()
            return self.wfile.write(page)
        q = parse_qs(u.query)
        ident = (corps or {}).get("id") or q.get("id", [""])[0]
        if ident and not re.match(r"^[a-z0-9_-]{1,40}$", ident):
            return self.repondre(400)
        if corps is None and chemin == "/missions/api/liste":
            args = ["liste", "--json"]
        elif corps is None and chemin == "/missions/api/arbre" and ident:
            args = ["arbre", ident, "--json"]
        elif corps is not None and chemin == "/missions/api/lance" and ident:
            args = ["lance", ident] + (["force"] if corps.get("force") else []) + ["--json"]
        elif corps is not None and chemin == "/missions/api/stop" and ident:
            args = ["stop", ident, "--json"]
        else:
            return self.repondre(404)
        try:
            r = subprocess.run([sys.executable, MISSIONS] + args, capture_output=True,
                               timeout=45, text=True)
            sortie = r.stdout.strip()
            json.loads(sortie)
        except (subprocess.TimeoutExpired, ValueError) as e:
            journal("missions {} : {}".format(args[0], e))
            sortie = json.dumps({"ok": False, "message": "Le moteur des missions n'a pas répondu."},
                                ensure_ascii=False)
        self.repondre(200, sortie.encode())

    def depot(self, q):
        nom = q.get("nom", [""])[0]
        n = int(self.headers.get("Content-Length") or 0)
        if not NOM_RECU.match(nom) or n <= 0 or n > DEPOT_MAX:
            return self.repondre(400)
        os.makedirs(RECUS, exist_ok=True)
        tmp = os.path.join(RECUS, "." + nom)
        reste = n
        with open(tmp, "wb") as f:
            while reste > 0:
                b = self.rfile.read(min(65536, reste))
                if not b:
                    break
                f.write(b)
                reste -= len(b)
        if reste:
            os.remove(tmp)
            return self.repondre(400)
        os.replace(tmp, os.path.join(RECUS, nom))
        journal("tour recu {} ({} o)".format(nom, n))
        return self.repondre(200, b'{"ok":true}')

    def evenements(self, q):
        try:
            apres = int(q.get("apres", ["0"])[0])
            attente = min(25.0, float(q.get("attente", ["25"])[0]))
        except ValueError:
            return self.repondre(400)
        c = base()
        dernier = c.execute("SELECT COALESCE(MAX(seq),0) FROM ev").fetchone()[0]
        if apres > dernier:          # base remise a zero : on repart
            apres = 0
        fin = time.time() + attente
        while True:
            lignes = c.execute(
                "SELECT seq, type, corps FROM ev WHERE seq>? AND statut='pret'"
                " AND cree>? ORDER BY seq LIMIT 20",
                (apres, time.time() - PERIME_S)).fetchall()
            if lignes or time.time() >= fin:
                break
            time.sleep(0.1)
        evs = []
        for seq, typ, corps in lignes:
            e = json.loads(corps)
            e["seq"] = seq
            evs.append(e)
            c.execute("UPDATE ev SET statut='livre' WHERE seq=? AND statut='pret'", (seq,))
        dernier = c.execute("SELECT COALESCE(MAX(seq),0) FROM ev").fetchone()[0]
        os.utime(VU, None)
        try:
            self.repondre(200, json.dumps({"dernier": dernier, "langue": langue(), "evenements": evs}).encode())
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            # L'appli a coupe pendant l'envoi (appui long, bascule reseau) :
            # rien n'est arrive. On remet en file, sinon l'ordre est perdu
            # et le script qui l'attend retombe sur ADB (2026-10-03, rapport 962).
            for e in evs:
                c.execute("UPDATE ev SET statut='pret' WHERE seq=? AND statut='livre'",
                          (e["seq"],))
        c.close()  # sans lui, 1 descripteur fuit par appel : « Too many open files » le 2026-10-08


def menage():
    """Les fichiers de plus d'une heure et les ordres de plus d'un jour."""
    c = base()
    c.execute("DELETE FROM ev WHERE cree<?", (time.time() - 86400,))
    c.close()
    for dos in (SPOOL, RECUS):
        if not os.path.isdir(dos):
            continue
        for n in os.listdir(dos):
            p = os.path.join(dos, n)
            if time.time() - os.path.getmtime(p) > 3600:
                os.remove(p)
    # appuis.txt ne garde que les 200 dernieres lignes : le garde ne relit
    # que la fin, mais le fichier ne doit pas grossir sans fin.
    try:
        with open(APPUIS) as f:
            lignes = f.readlines()
        if len(lignes) > 400:
            with open(APPUIS + ".tmp", "w") as f:
                f.writelines(lignes[-200:])
            os.replace(APPUIS + ".tmp", APPUIS)
    except OSError:
        pass


def serveur():
    base().close()
    menage()
    s = ThreadingHTTPServer(("127.0.0.1", PORT), Gestion)
    s.daemon_threads = True
    s.jeton = jeton()
    print("creeper-relais sur 127.0.0.1:{}".format(PORT), flush=True)
    s.serve_forever()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "serveur":
        serveur()
    elif len(sys.argv) >= 2 and sys.argv[1] == "deposer":
        try:
            sys.exit(deposer(sys.argv[2:]))
        except Exception as e:       # noqa: BLE001  le repli ADB prime
            journal("deposer : {}".format(e))
            sys.exit(1)
    elif len(sys.argv) >= 2 and sys.argv[1] == "traduire":
        print(json.dumps(traduire(sys.argv[2:]), ensure_ascii=False))
    else:
        print(__doc__)
        sys.exit(2)
