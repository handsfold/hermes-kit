#!/usr/bin/env python3
"""Pose les fichiers du kit sur la machine, a partir du MANIFESTE lu a l'envers.

Tout arrive par l'environnement (jamais en argument) :
    HK_HOME, HK_CONTEXTE, HK_PROJETS, HERMES_HOME, HERMES_BIN, HK_PLATEFORME,
    HK_PRENOM, HK_TELEGRAM_TOKEN, HK_TELEGRAM_USER, HK_LANG (en par defaut, fr en option),
    HK_QG_CHAT, HK_QG_THREAD, HK_COACH_THREAD, HK_PIXEL_IP (facultatifs).

Le QG est cree par Hermes lui-meme dans le chat prive du bot (platforms.telegram.extra.dm_topics) :
  . phase 1 (avant le premier demarrage) : les sujets n'ont pas encore d'identifiant, on ecrit
    la liste des sujets a creer ;
  . phase 2 (apres) : le coeur a note les identifiants dans config.yaml, on les relit et on
    pose tout ce qui en depend (consignes par sujet, canal d'accueil, scripts).
`poser.py --topics` affiche les identifiants trouves (code 0 si QG et Coach existent).

Regles :
  . un fichier du kit ecrase le fichier de meme nom, jamais un autre fichier de l'utilisateur ;
  . les fichiers texte recoivent les substitutions (trous __X__, chemins, prenom) ;
  . config.yaml, .env et settings.json de Claude sont fusionnes, l'ancien est sauvegarde ;
  . les crons du kit sont ajoutes par nom, ceux de l'utilisateur restent.
Rejouable : relancer ne casse rien.
"""

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

E = os.environ
HOME = Path.home()
HK_HOME = Path(E["HK_HOME"])
HK_CONTEXTE = Path(E.get("HK_CONTEXTE") or HK_HOME / "contexte")
HK_PROJETS = Path(E.get("HK_PROJETS") or HOME / "Projets")
HA = Path(E.get("HERMES_HOME") or HOME / ".hermes")
PRENOM = E.get("HK_PRENOM", "").strip() or "USER"
PIXEL_IP = E.get("HK_PIXEL_IP", "").strip()
LANGUE = "fr" if E.get("HK_LANG", "en").strip().lower().startswith("fr") else "en"
NOMS_SUJETS = {"QG": "QG", "Coach": "COACH", "Ideas": "IDEAS"}


def lire_sujets(chemin: Path) -> dict:
    """Identifiants des sujets que le coeur d'Hermes a notes dans config.yaml (dm_topics)."""
    if not chemin.exists():
        return {}
    texte = chemin.read_text(encoding="utf-8")
    if "dm_topics:" not in texte:
        return {}
    trouves, nom = {}, None
    for ligne in texte.split("dm_topics:", 1)[1].splitlines():
        if ligne and not ligne[0].isspace() and not ligne.startswith("-"):
            break  # fin de la section
        m = re.match(r"^[\s-]*name:\s*['\"]?([^'\"#]+?)['\"]?\s*$", ligne)
        if m:
            nom = m.group(1)
        m = re.match(r"^\s*thread_id:\s*['\"]?(\d+)['\"]?\s*$", ligne)
        if m and nom:
            trouves[nom] = m.group(1)
    return trouves


_SUJETS = lire_sujets(Path(E.get("HERMES_HOME") or Path.home() / ".hermes") / "config.yaml")
QG_CHAT = E.get("HK_QG_CHAT", "").strip() or E["HK_TELEGRAM_USER"]
QG_THREAD = E.get("HK_QG_THREAD", "").strip() or _SUJETS.get("QG", "")
COACH_THREAD = E.get("HK_COACH_THREAD", "").strip() or _SUJETS.get("Coach", "")
TS = time.strftime("%Y%m%d-%H%M%S")
# Tout fichier existant que le placer remplace y est garde, au chemin relatif a HOME.
SAUVEGARDE = HOME / ".config" / "hermes-kit" / "sauvegardes" / TS
# Co-author line added by Claude Code to commits made through the kit.
# On by default; `hk coauteur off` (or HK_COAUTEUR=0) writes the marker and removes it.
COAUTEUR = "Co-Authored-By: HandsFold <hello@handsfold.com>"
SANS_COAUTEUR = HOME / ".config" / "hermes-kit" / "sans-coauteur"
BILAN = {"ecrits": 0, "identiques": 0, "gardes": 0}
MANIFESTE = HK_HOME / "MANIFESTE.txt"
BINAIRE = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".apk",
    ".jar",
    ".zip",
    ".gz",
    ".tar",
    ".pdf",
    ".ttf",
    ".woff",
    ".woff2",
    ".mp3",
    ".wav",
    ".ogg",
    ".so",
    ".pyc",
    ".db",
}


def rel_home(p: Path) -> str:
    try:
        return str(p.relative_to(HOME))
    except ValueError:
        return str(p)


# Ordre important : les formes longues avant les courtes
SUBSTITUTIONS = [
    ("~/Bureau/Projets/contexte", str(HK_CONTEXTE).replace(str(HOME), "~", 1)),
    ("$HOME/Bureau/Projets/contexte", str(HK_CONTEXTE).replace(str(HOME), "$HOME", 1)),
    ("Bureau/Projets/contexte", rel_home(HK_CONTEXTE)),
    ("~/Bureau/Projets", str(HK_PROJETS).replace(str(HOME), "~", 1)),
    ("$HOME/Bureau/Projets", str(HK_PROJETS).replace(str(HOME), "$HOME", 1)),
    ("Bureau/Projets", rel_home(HK_PROJETS)),
    ("__QG_CHAT__", QG_CHAT),
    ("__QG_THREAD__", QG_THREAD),
    ("__COACH_THREAD__", COACH_THREAD),
    ("__PIXEL_IP__", PIXEL_IP or "127.0.0.1"),
    ("__LAN_IP__", PIXEL_IP or "127.0.0.1"),
    ("__HOST_IP__", "127.0.0.1"),
    ("__TS_IP__", "127.0.0.1"),
]
# USER (le prenom) : jamais $USER, ${USER}, USER_X, X_USER
RE_USER = re.compile(r"(?<![$_A-Za-z0-9{])USER(?![_A-Za-z0-9}])")


def substituer(texte: str) -> str:
    for a, b in SUBSTITUTIONS:
        texte = texte.replace(a, b)
    return RE_USER.sub(PRENOM, texte)


def cible_de(src: str) -> Path:
    """Chemin d'origine du manifeste -> chemin sur cette machine."""
    pref = "~/Bureau/Projets/contexte/"
    if src.startswith(pref):
        return HK_CONTEXTE / src[len(pref) :]
    if src.startswith("~/.hermes/plugins-essai/"):
        # le manifeste nomme la source chez l'auteur ; Hermes ne charge que plugins/
        return HA / "plugins" / src[len("~/.hermes/plugins-essai/") :]
    if src.startswith("~/.hermes/"):
        return HA / src[len("~/.hermes/") :]
    if src.startswith("~/"):
        return HOME / src[2:]
    return Path(src)


def garder(dst: Path):
    """Copie dst dans le dossier de sauvegarde avant qu'il soit remplace."""
    if not dst.is_file():
        return
    try:
        rel = dst.relative_to(HOME)
    except ValueError:
        rel = Path("hors-home") / str(dst).lstrip("/")
    copie = SAUVEGARDE / rel
    copie.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dst, copie, follow_symlinks=True)
    BILAN["gardes"] += 1


def ecrire_si_change(dst: Path, contenu: bytes, mode: int | None = None):
    """Ecrit dst seulement si le contenu change, en gardant l'ancienne version."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file() and not dst.is_symlink() and dst.read_bytes() == contenu:
        BILAN["identiques"] += 1
    else:
        garder(dst)
        if dst.is_symlink():
            dst.unlink()
        dst.write_bytes(contenu)
        BILAN["ecrits"] += 1
    if mode is not None:
        dst.chmod(mode)


def copier_fichier(src: Path, dst: Path):
    brut = src.read_bytes()
    if src.suffix.lower() not in BINAIRE:
        try:
            texte = brut.decode("utf-8")
        except UnicodeDecodeError:
            texte = None  # fichier non texte : copie telle quelle
        if texte is not None:
            brut = substituer(texte).encode("utf-8")
    ecrire_si_change(dst, brut, src.stat().st_mode & 0o7777)


def copier(src: Path, dst: Path) -> int:
    if src.is_file():
        copier_fichier(src, dst)
        return 1
    n = 0
    for f in sorted(src.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts:
            copier_fichier(f, dst / f.relative_to(src))
            n += 1
    return n


def lire_manifeste():
    for ligne in MANIFESTE.read_text().splitlines():
        ligne = ligne.split("#", 1)[0].strip()
        if "->" not in ligne:
            continue
        a, b = (x.strip() for x in ligne.split("->", 1))
        yield a, b


def charger_yaml_simple(texte: str):
    try:
        import yaml

        return yaml.safe_load(texte)
    except ImportError:
        return None


def poser_arbre():
    total = 0
    for origine, kit in lire_manifeste():
        src = HK_HOME / kit
        if not src.exists():
            continue
        if kit.startswith("pixelgarde/app"):
            continue  # l'APK se construit a part (pixelgarde/README.md)
        if kit.startswith("pixelgarde/") and not PIXEL_IP:
            continue  # pas de telephone declare
        if kit in ("claude/settings.json", "claude/CLAUDE.md"):
            continue  # fusionnes plus bas
        if (
            kit.startswith("hermes/config")
            or kit.startswith("hermes/gateway_model_overrides")
            or kit.startswith("hermes/cron")
        ):
            continue  # generes plus bas
        total += copier(src, cible_de(origine))
    print(f"  {total} fichiers poses")


def retirer_bloc_coach(texte: str, marque: str = "__COACH_THREAD__") -> str:
    """Retire le bloc channel_prompts d'un sujet (Coach double du QG, ou pas encore cree)."""
    lignes = texte.splitlines(keepends=True)
    out, i = [], 0
    while i < len(lignes):
        ligne = lignes[i]
        if re.match(rf"^\s+'?{marque}'?\s*:", ligne):
            ind = len(ligne) - len(ligne.lstrip())
            i += 1
            while i < len(lignes) and (
                not lignes[i].strip() or len(lignes[i]) - len(lignes[i].lstrip()) > ind
            ):
                i += 1
            continue
        out.append(ligne)
        i += 1
    return "".join(out)


def noter_sujets(texte: str) -> str:
    """Phase 2 : remet dans dm_topics les identifiants crees (sinon le coeur recree les sujets)."""
    connus = dict(_SUJETS)
    if QG_THREAD:
        connus.setdefault("QG", QG_THREAD)
    if COACH_THREAD:
        connus.setdefault("Coach", COACH_THREAD)
    for nom, ident in connus.items():
        texte = re.sub(
            rf"^(\s*)- name: {nom}\n(?!\s*thread_id)",
            lambda m, ident=ident: f"{m.group(0)}{m.group(1)}  thread_id: {ident}\n",
            texte,
            flags=re.M,
        )
    return texte


def poser_langue():
    """Reglage unique de la langue des menus : ~/.hermes/telegram-menus.json, cle \"langue\"."""
    f = HA / "telegram-menus.json"
    try:
        etat = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError:
        etat = {}
    etat["langue"] = LANGUE
    f.write_text(json.dumps(etat, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  langue des menus : {LANGUE}")


def poser_config():
    src = HK_HOME / "hermes/config.exemple.yaml"
    dst = HA / "config.yaml"
    texte = src.read_text(encoding="utf-8")
    if not QG_THREAD:
        texte = retirer_bloc_coach(texte, "__QG_THREAD__")
    if not COACH_THREAD or COACH_THREAD == QG_THREAD:
        texte = retirer_bloc_coach(texte)
    texte = noter_sujets(texte)
    # Hermes ne developpe pas $HOME dans command: et cwd: (crawl4ai introuvable).
    texte = substituer(texte).replace("$HOME/", f"{HOME}/")
    HA.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.read_text(encoding="utf-8") != texte:
        shutil.copy2(dst, dst.with_name(f"config.yaml.avant-hermes-kit-{TS}"))
    dst.write_text(texte, encoding="utf-8")
    d = charger_yaml_simple(texte)
    # Dossier de travail du terminal : Hermes le reclame a chaque tour s'il manque.
    cwd = ((d or {}).get("terminal") or {}).get("cwd") or str(HA / "workspace")
    Path(os.path.expanduser(str(cwd))).mkdir(parents=True, exist_ok=True)
    if d is None:
        print("  config.yaml ecrit (pyyaml absent : syntaxe non verifiee)")
    else:
        print("  config.yaml ecrit")
    ov = HA / "gateway_model_overrides.json"
    if not ov.exists():
        ov.write_text(
            substituer((HK_HOME / "hermes/gateway_model_overrides.exemple.json").read_text())
        )
        print("  gateway_model_overrides.json ecrit")
    (HA / "qg-adresse.json").write_text(
        json.dumps({"chat": str(QG_CHAT), "thread": str(QG_THREAD)}) + "\n"
    )


def poser_env():
    dst = HA / ".env"
    actuel = {}
    lignes = []
    if dst.exists():
        shutil.copy2(dst, dst.with_name(f".env.avant-hermes-kit-{TS}"))
        os.chmod(dst.with_name(f".env.avant-hermes-kit-{TS}"), 0o600)
        lignes = dst.read_text(encoding="utf-8").splitlines()
        for ligne in lignes:
            m = re.match(r"^([A-Z0-9_]+)=(.*)$", ligne)
            if m:
                actuel[m.group(1)] = m.group(2)
    voulu = {
        "TELEGRAM_BOT_TOKEN": E["HK_TELEGRAM_TOKEN"],
        "TELEGRAM_ALLOWED_USERS": E["HK_TELEGRAM_USER"],
        "TELEGRAM_HOME_CHANNEL": QG_CHAT,
        "TELEGRAM_HOME_CHANNEL_NAME": "QG",
    }
    if QG_THREAD:
        voulu["TELEGRAM_HOME_CHANNEL_THREAD_ID"] = QG_THREAD
    if "HERMES_GATEWAY_TOKEN" not in actuel:
        voulu["HERMES_GATEWAY_TOKEN"] = secrets.token_hex(24)
    if "ANTHROPIC_API_KEY" not in actuel:
        voulu["ANTHROPIC_API_KEY"] = "local"
    for k, v in voulu.items():
        for i, ligne in enumerate(lignes):
            if ligne.startswith(k + "="):
                lignes[i] = f"{k}={v}"
                break
        else:
            lignes.append(f"{k}={v}")
    dst.write_text("\n".join(lignes).rstrip("\n") + "\n", encoding="utf-8")
    os.chmod(dst, 0o600)
    print("  .env fusionne")


def prochain_passage(schedule):
    """Demande a Hermes lui-meme la prochaine execution ; None si impossible."""
    ha = HA / "hermes-agent"
    py = ha / "venv" / "bin" / "python"
    if not py.exists():
        return None
    code = (
        f"import sys, json; sys.path.insert(0, {str(ha)!r}); "
        "from cron.jobs import compute_next_run; "
        "print(json.dumps(compute_next_run(json.loads(sys.stdin.read()))))"
    )
    try:
        # python du venv Hermes, code fixe : rien ne vient de l'exterieur
        r = subprocess.run(  # noqa: S603
            [str(py), "-c", code],
            input=json.dumps(schedule),
            capture_output=True,
            text=True,
            cwd=str(ha),
            timeout=30,
        )
        return json.loads(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        return None


def poser_crons():
    src = HK_HOME / "hermes/cron/exemples.json"
    if not src.exists():
        return
    exemples = json.loads(substituer(src.read_text(encoding="utf-8")))["jobs"]
    # Crons propres au kit (hors export de la machine d'origine)
    kit_src = HK_HOME / "install" / "crons-kit.json"
    if kit_src.exists():
        exemples += json.loads(kit_src.read_text(encoding="utf-8"))["jobs"]
    cron_dir = HA / "cron"
    cron_dir.mkdir(parents=True, exist_ok=True)
    dst = cron_dir / "jobs.json"
    etat = {"jobs": [], "updated_at": None}
    if dst.exists():
        try:
            etat = json.loads(dst.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            shutil.copy2(dst, dst.with_name(f"jobs.json.illisible-{TS}"))
    noms = {j.get("name") for j in etat["jobs"]}
    ajoutes = 0
    sans_date = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    for j in exemples:
        if j.get("name") in noms:
            continue
        j = dict(j)
        j.setdefault("id", secrets.token_hex(6))
        j.setdefault("created_at", now)
        j.setdefault("enabled", True)
        # Un exemple livre desactive s'affiche "paused" dans `hermes cron list`.
        j["state"] = "scheduled" if j["enabled"] else "paused"
        if j.get("script"):
            j["script"] = (
                str(cible_de(j["script"]).expanduser())
                if j["script"].startswith("~")
                else j["script"]
            )
        if not j.get("next_run_at"):
            j["next_run_at"] = prochain_passage(j.get("schedule") or {})
            if j["next_run_at"] is None:
                sans_date += 1
        etat["jobs"].append(j)
        ajoutes += 1
    etat["updated_at"] = now
    dst.write_text(json.dumps(etat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    actifs = sum(1 for j in etat["jobs"] if j.get("enabled", True))
    msg = f"  crons : {ajoutes} ajoutes, {len(etat['jobs'])} au total, {actifs} actifs"
    if sans_date:
        msg += f" ({sans_date} sans date calculee : Hermes la posera au premier tour)"
    print(msg)


def seed_contexte():
    HK_CONTEXTE.mkdir(parents=True, exist_ok=True)
    (HK_CONTEXTE / "methodes").mkdir(exist_ok=True)
    graines = {
        "focus.md": f"# Cap de {PRENOM}\n\n## Cap\n\n"
        "(a ecrire : le but des 3 prochains mois, en 1 phrase)\n\n"
        "## 3 actifs\n\n1. \n2. \n3. \n",
        "taches.md": "# A faire\n\n- [ ] premiere tache\n",
        "journal.md": "# Journal du coach\n\n",
        "methodes/appris.md": "# Lecons apprises\n\n",
    }
    n = 0
    for nom, contenu in graines.items():
        p = HK_CONTEXTE / nom
        if not p.exists():
            p.write_text(contenu, encoding="utf-8")
            n += 1
    if n:
        print(f"  contexte : {n} fichiers de depart dans {HK_CONTEXTE}")


def fusion_settings_claude():
    src = HK_HOME / "claude/settings.json"
    if not src.exists():
        return
    kit = json.loads(substituer(src.read_text(encoding="utf-8")))
    dst = HOME / ".claude" / "settings.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    mien = {}
    if dst.exists():
        try:
            mien = json.loads(dst.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            mien = {}
        shutil.copy2(dst, dst.with_name(f"settings.json.avant-hermes-kit-{TS}"))
    fusion = dict(mien)
    for k in ("hooks", "env", "statusLine", "cleanupPeriodDays"):
        if k in kit:
            fusion[k] = kit[k]
    fusion["permissions"] = fusion_permissions(mien.get("permissions") or {})
    for k in ("model", "outputStyle", "language", "effortLevel"):
        if k in mien:
            fusion[k] = mien[k]
    if "outputStyle" in kit and "outputStyle" not in mien:
        fusion["outputStyle"] = kit["outputStyle"]  # le style du kit, sauf choix de l'utilisateur
    for k in ("enabledPlugins", "extraKnownMarketplaces"):
        a, b = mien.get(k) or {}, kit.get(k) or {}
        if a or b:
            fusion[k] = {**b, **a}
    regler_coauteur(fusion, mien)
    dst.write_text(json.dumps(fusion, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("  ~/.claude/settings.json fusionne")


def coauteur_actif() -> bool:
    if E.get("HK_COAUTEUR", "1").strip() == "0":
        SANS_COAUTEUR.parent.mkdir(parents=True, exist_ok=True)
        SANS_COAUTEUR.touch()
    return not SANS_COAUTEUR.exists()


def regler_coauteur(fusion: dict, mien: dict) -> None:
    """HandsFold co-author line in Claude Code commits, without overriding the user.

    An attribution the user wrote himself is kept as is. Ours is set when active,
    removed when switched off.
    """
    attr = dict(mien.get("attribution") or {})
    commit = attr.get("commit")
    if commit not in (None, COAUTEUR):
        return  # the user's own choice
    if coauteur_actif():
        attr["commit"] = COAUTEUR
    else:
        attr.pop("commit", None)
    if attr:
        fusion["attribution"] = attr
    else:
        fusion.pop("attribution", None)


def fusion_permissions(miennes: dict) -> dict:
    """Permissions reglees du kit (install/claude-permissions.json) + celles de l'utilisateur.

    Jamais le mode bypassPermissions de la machine d'origine : les actions courantes
    sont autorisees, les destructrices demandees. Les listes s'additionnent ; le
    mode par defaut choisi par l'utilisateur est garde, sauf bypassPermissions.
    """
    src = HK_HOME / "install" / "claude-permissions.json"
    kit = json.loads(src.read_text(encoding="utf-8"))["permissions"] if src.exists() else {}
    out = dict(miennes)
    for k in ("allow", "ask", "deny"):
        vus = list(miennes.get(k) or [])
        out[k] = vus + [r for r in kit.get(k) or [] if r not in vus]
    mode = miennes.get("defaultMode")
    out["defaultMode"] = (
        mode if mode and mode != "bypassPermissions" else kit.get("defaultMode", "default")
    )
    return out


def poser_telemetrie():
    """Les scripts lus par Hermes vont dans HERMES_HOME/scripts : les statistiques (inertes sans
    consentement ni jeton) et l'aiguilleur de skills, que charge le plugin aiguilleur."""
    for nom in ("hk-telemetrie.py", "hk-aiguilleur.py"):
        src = HK_HOME / "install" / nom
        if not src.exists():
            continue
        dst = HA / "scripts" / nom
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        dst.chmod(0o755)


MARQUE_DEBUT = "<!-- HERMES-KIT:DEBUT -->"
MARQUE_FIN = "<!-- HERMES-KIT:FIN -->"


def fusionner_claude_md(existant: str, kit: str) -> str:
    """Le contenu du kit entre deux marqueurs : remplace le bloc s'il existe, sinon l'ajoute."""
    bloc = f"{MARQUE_DEBUT}\n{kit.strip()}\n{MARQUE_FIN}\n"
    d, f = existant.find(MARQUE_DEBUT), existant.find(MARQUE_FIN)
    if d != -1 and f > d:
        return existant[:d] + bloc + existant[f + len(MARQUE_FIN) :].lstrip("\n")
    if not existant.strip():
        return bloc
    return existant.rstrip("\n") + "\n\n" + bloc


def poser_claude_md():
    src = HK_HOME / "claude/CLAUDE.md"
    if not src.exists():
        return
    kit = substituer(src.read_text(encoding="utf-8"))
    dst = HOME / ".claude" / "CLAUDE.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        # copie dans les marqueurs : un second passage remplace au lieu de dupliquer
        dst.write_text(fusionner_claude_md("", kit), encoding="utf-8")
        print("  ~/.claude/CLAUDE.md pose")
        return
    avant = dst.read_text(encoding="utf-8")
    apres = fusionner_claude_md(avant, kit)
    if apres != avant:
        shutil.copy2(dst, dst.with_name(f"CLAUDE.md.avant-hermes-kit-{TS}"))
        dst.write_text(apres, encoding="utf-8")
    print("  ~/.claude/CLAUDE.md : bloc du kit entre marqueurs")


def liens():
    bin_dir = HOME / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for nom, cible in (
        ("focus", HA / "scripts" / "focus.py"),
        ("pieces", HA / "scripts" / "pieces.py"),
    ):
        if not cible.exists():
            continue
        lien = bin_dir / nom
        if lien.is_symlink() and lien.resolve() == cible.resolve():
            continue
        if lien.is_symlink() or lien.exists():
            garder(lien)
            lien.unlink()
        lien.symlink_to(cible)
        cible.chmod(cible.stat().st_mode | 0o111)
    outils = (("hk", "hk"), ("hk-boite.py", "hk-boite"))
    for fichier, nom in outils:
        src = HK_HOME / "install" / fichier
        if src.exists():
            ecrire_si_change(bin_dir / nom, src.read_bytes(), 0o755)


def poser_skills_kit():
    """Skills propres au kit (pas d'origine sur une machine) : install/skills/<nom>."""
    racine = HK_HOME / "install" / "skills"
    if not racine.is_dir():
        return
    # auto-jailbreak : seulement si le membre a dit oui (HK_AUTOJB=oui).
    # Non : rien n'est pose, et install.sh ne telecharge pas son moteur.
    optionnels = {"auto-jailbreak": E.get("HK_AUTOJB") == "oui"}
    for skill in sorted(p for p in racine.iterdir() if (p / "SKILL.md").exists()):
        if not optionnels.get(skill.name, True):
            continue
        copier(skill, HA / "skills" / "productivity" / skill.name)


def en_conteneur() -> bool:
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


def home_reel() -> Path:
    """Le HOME du compte (passwd), que HOME=... ne peut pas deguiser."""
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError):
        return HOME


def garde_home():
    """Refuse d'ecrire dans un vrai HOME quand le lancement ressemble a un essai.

    Ne le 2026-10-12 : un essai lance avec HERMES_HOME temporaire mais SANS HOME=
    a reecrit ~/.claude (hooks, outils, skills) avec le prenom « Test ».
    HERMES_HOME isole seul ne protege rien : HOME reste le vrai.
    Passer outre en connaissance de cause : HK_FORCER_HOME=1.
    """
    if E.get("HK_FORCER_HOME") == "1":
        return
    raisons = []
    try:
        HA.resolve().relative_to(HOME.resolve())
    except ValueError:
        raisons.append(f"HERMES_HOME ({HA}) est hors de HOME ({HOME})")
    jetable = (
        E.get("HK_CI") == "1"
        or E.get("CI") == "true"
        or en_conteneur()
        or HOME.resolve() != home_reel().resolve()
    )
    if PRENOM.lower() in ("test", "alice", "demo", "user") and not jetable:
        raisons.append(f"prenom d'essai « {PRENOM} » dans le HOME du compte, hors conteneur")
    if raisons:
        sys.exit(
            "Refus : ce lancement ecrirait dans le vrai HOME "
            f"({HOME}).\n  - " + "\n  - ".join(raisons) + "\n"
            "Pour un essai, isoler HOME aussi : HOME=$(mktemp -d) ou Docker.\n"
            "Pour passer outre volontairement : HK_FORCER_HOME=1."
        )


def main():
    if "--topics" in sys.argv:
        print(" ".join(f"{k}={v}" for k, v in _SUJETS.items()))
        sys.exit(0 if "QG" in _SUJETS and "Coach" in _SUJETS else 1)
    if not MANIFESTE.exists():
        sys.exit(f"MANIFESTE absent : {MANIFESTE}")
    garde_home()
    poser_arbre()
    poser_skills_kit()
    poser_config()
    poser_env()
    poser_langue()
    poser_telemetrie()
    poser_crons()
    seed_contexte()
    fusion_settings_claude()
    poser_claude_md()
    liens()
    print(
        f"  fichiers : {BILAN['ecrits']} ecrits, {BILAN['identiques']} deja a jour"
        + (f", {BILAN['gardes']} anciennes versions dans {SAUVEGARDE}" if BILAN["gardes"] else "")
    )


if __name__ == "__main__":
    main()
