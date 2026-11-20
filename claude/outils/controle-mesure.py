#!/usr/bin/python3
"""Controle de la mesure : toute routine qui appelle un modele doit se nommer aupres du proxy.

N'ecrit au QG que si l'ecart a change depuis le dernier passage.
  1. Routines actives (timers, crontabs) qui appellent un modele payant sans se nommer,
     en local et sur les hotes de ~/.config/controle-mesure.conf (une ligne : `alias proprio1,proprio2`).
  2. Timers coupes dans le meme cas : non mesures le jour ou on les relance.
  3. Journal du proxy (~/.hermes/proxy-usage.jsonl), 7 jours : cout sans appelant ni topic
     (source `auxiliaire` surtout). Ecart au-dessus de SEUIL_ANONYME.
  4. Meme journal, 24 h : cout d'un tour incoherent avec ses tokens (plus cher que le plafond
     au tarif Opus le plus haut). Signe d'un cumul de session compte comme un tour.
     Ne le 2026-10-27 : 94 tours faux en 7 j, 5 357 $ affiches pour ~30 $ (server.js, deltaSession).
Reparer : skill `atelier` (guide mesure-partout). Repérage : `sonde_mesure.py` (meme dossier).

Usage : controle-mesure.py [--sec]   (--sec : affiche sans deposer au QG)
Sortie 1 s'il reste un ecart. Timer : controle-mesure.timer (systemd utilisateur), 8 h 30.
Ne le 2026-10-26 : 76 routines sur 159 hors de toute mesure sur la page Routines.
"""
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sonde_mesure  # noqa: E402

CONF = Path.home() / ".config/controle-mesure.conf"
JOURNAL = Path.home() / ".hermes/proxy-usage.jsonl"
ETAT = Path.home() / ".local/state/controle-mesure/dernier.json"
SEUIL_ANONYME = 0.05  # part du cout de la semaine sans appelant
# Plafond par tour : tarif Opus le plus cher ($/Mtok entree, sortie, cache lu, cache ecrit).
# Aucun tour honnete ne peut le depasser ; x3 + 0,5 $ absorbe les arrondis et le contexte 1M.
PLAFOND_TARIF = (15.0, 75.0, 1.5, 18.75)


def hotes():
    if not CONF.exists():
        return []
    out = []
    for l in CONF.read_text().splitlines():
        mots = l.split("#")[0].split()
        if mots:
            # 3e colonne facultative : journal du proxy de l'hote (ses routines nommees y sont mesurees)
            out.append((mots[0], (mots[1] if len(mots) > 1 else "").split(","), mots[2] if len(mots) > 2 else ""))
    return out


def a_corriger(releve, machine, distante, journal=False):
    """(actives, coupees) : routines qui appellent un modele payant sans etre mesurees."""
    actives, coupees = [], []
    for cle, d in (releve.get("timers") or {}).items():
        if not d.get("modele") or d.get("local"):
            continue
        if d.get("se_nomme") and (not distante or journal):  # hote distant : mesure seulement s'il a son journal
            continue
        nom = f"{machine} · {cle.split(':', 1)[1]}"
        (actives if d.get("actif") else coupees).append(nom)
    for cle, d in (releve.get("crontabs") or {}).items():
        if d.get("modele") and not d.get("local") and ((distante and not journal) or not d.get("se_nomme")):
            actives.append(f"{machine} · crontab {cle} ({d.get('script') or '?'})")
    return actives, coupees


def journal_anonyme(jours=7):
    if not JOURNAL.exists():
        return 0.0, 0.0, {}
    lim = (datetime.now(timezone.utc) - timedelta(days=jours)).strftime("%Y-%m-%dT%H:%M:%S")
    total, anonyme, par_source = 0.0, 0.0, {}
    with JOURNAL.open(errors="ignore") as f:
        for l in f:
            try:
                d = json.loads(l)
            except ValueError:
                continue
            if str(d.get("ts", ""))[:19] < lim:
                continue
            c = d.get("cout_usd") or 0
            total += c
            # cron : rattache par state.db (cout_routines) ; prime : session de USER, nommee par son cwd
            if not d.get("appelant") and not d.get("topic") and d.get("source") not in ("cron", "prime"):
                anonyme += c
                par_source[d.get("source")] = par_source.get(d.get("source"), 0) + c
    return total, anonyme, par_source


def journal_incoherent(jours=7):
    """Tours dont cout_usd depasse ce que leurs tokens peuvent couter : (nb, cout affiche, plafond)."""
    if not JOURNAL.exists():
        return 0, 0.0, 0.0
    lim = (datetime.now(timezone.utc) - timedelta(days=jours)).strftime("%Y-%m-%dT%H:%M:%S")
    nb, affiche, plafond = 0, 0.0, 0.0
    e, so, lu, ec = PLAFOND_TARIF
    with JOURNAL.open(errors="ignore") as f:
        for l in f:
            try:
                d = json.loads(l)
            except ValueError:
                continue
            if str(d.get("ts", ""))[:19] < lim:
                continue
            c = d.get("cout_usd") or 0
            maxi = ((d.get("entree") or 0) * e + (d.get("sortie") or 0) * so
                    + (d.get("cache_lu") or 0) * lu + (d.get("cache_ecrit") or 0) * ec) / 1e6
            if c > 3 * maxi + 0.5:
                nb += 1
                affiche += c
                plafond += maxi
    return nb, affiche, plafond


def main():
    sec = "--sec" in sys.argv
    actives, coupees = a_corriger(json.loads(subprocess.run(
        [sys.executable, sonde_mesure.__file__, "--crontabs", subprocess.run(
            ["id", "-un"], capture_output=True, text=True).stdout.strip()],
        capture_output=True, text=True, timeout=300).stdout or "{}"), "local", False)
    injoignables = []
    for hote, proprios, journal in hotes():
        try:
            a, c = a_corriger(sonde_mesure.distante(hote, [p for p in proprios if p]), hote, True, bool(journal))
            actives += a
            coupees += c
        except Exception as e:  # noqa: BLE001 : hote eteint, ssh refuse
            injoignables.append(f"{hote} ({type(e).__name__})")
    total, anonyme, par_source = journal_anonyme()

    ecarts = []
    if actives:
        ecarts.append(f"**Routines actives non mesurees** : {len(actives)}\n" + "\n".join(f"- `{n}`" for n in actives))
    if total and anonyme / total > SEUIL_ANONYME:
        detail = ", ".join(f"{s} {v:.0f} $" for s, v in sorted(par_source.items(), key=lambda x: -x[1]))
        ecarts.append(f"**Journal du proxy** : {anonyme:.0f} $ sur {total:.0f} $ en 7 jours "
                      f"({anonyme / total:.0%}) sans appelant ni topic ({detail})")
    nb_inc, affiche, plafond = journal_incoherent(1)  # 24 h : n'alerte que sur du neuf
    if nb_inc:
        ecarts.append(f"**Cout du proxy faux** : {nb_inc} tours en 24 h affichent {affiche:.0f} $, "
                      f"leurs tokens en valent {plafond:.0f} $ au plus. Cumul de session compte "
                      f"comme un tour : voir `deltaSession` dans claude-proxy/server.js")
    infos = []
    if coupees:
        infos.append(f"Timers coupes qui ne seraient pas mesures : {len(coupees)} ("
                     + ", ".join(n.split(' · ')[1] for n in coupees) + ")")
    if injoignables:
        infos.append("Hotes injoignables : " + ", ".join(injoignables))

    if not ecarts:
        print("Aucun ecart." + ("\n" + "\n".join(infos) if infos else ""))
        return 0
    texte = "\n\n".join(ecarts + infos) + "\n\nReparer : skill `atelier` (guide mesure-partout)."
    print(texte)
    signature = hashlib.sha1("\n".join(ecarts).split(" sur ")[0].encode()).hexdigest()
    ancien = json.loads(ETAT.read_text()).get("signature") if ETAT.exists() else None
    if not sec and signature != ancien and shutil.which("qg-attente"):
        subprocess.run(["qg-attente", "add", f"Controle de la mesure : {len(ecarts)} point(s)",
                        "--resume", texte, "--source", "controle-mesure"], check=False)
    if not sec:
        ETAT.parent.mkdir(parents=True, exist_ok=True)
        ETAT.write_text(json.dumps({"signature": signature, "a": datetime.now().isoformat(timespec="seconds")}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
