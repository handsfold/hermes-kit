#!/usr/bin/env bash
# Contrat de fonctionnement d'Hermes : dit OK ou KO, point par point.
#
# Lecture seule : ne redemarre rien, ne modifie ni la config ni le code.
# Sortie courte, moins de 2 minutes. Code de retour 0 si tout est OK, 1 sinon.
#
#   hermes-verif.sh            tous les points
#   hermes-verif.sh --rapide   sans les tests des retouches (marqueurs seulement)
#   hermes-verif.sh --depot D  controle les retouches dans le depot D (defaut : en service)
#
# Points : gateway, journal, reglages proteges, plugins, commandes Telegram,
# retouches du registre (colonne verif).
set -uo pipefail

DEPOT=$HOME/.hermes/hermes-agent
HOME_H=$HOME/.hermes
PROTEGES="$HOME_H/maj/reglages-proteges.yaml"
REGISTRE=${REGISTRE:-$HOME_H/maj/retouches.md}
VENV_PY="$DEPOT/venv/bin/python"
UNITE=hermes-gateway
RAPIDE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --rapide) RAPIDE=1 ;;
    --depot) shift; DEPOT="$1" ;;
    *) echo "option inconnue : $1" >&2; exit 2 ;;
  esac
  shift
done

NB_KO=0
ok()  { printf 'OK  %s\n' "$*"; }
ko()  { printf 'KO  %s\n' "$*"; NB_KO=$((NB_KO + 1)); }
note() { printf '    %s\n' "$*"; }

# --- 1. Gateway et journal ---------------------------------------------------
if [ "$(systemctl --user is-active "$UNITE" 2>/dev/null)" = "active" ]; then
  ok "gateway actif"
else
  ko "gateway non actif"
fi

DEPUIS=$(systemctl --user show "$UNITE" -p ActiveEnterTimestamp --value 2>/dev/null | sed 's/^[A-Za-z]* //; s/ [A-Z]*$//')
if [ -n "$DEPUIS" ]; then
  JOURNAL=$(journalctl --user -u "$UNITE" --since "$DEPUIS" --no-pager 2>/dev/null)
else
  JOURNAL=""
fi

if [ -z "$JOURNAL" ]; then
  ko "journal vide ou illisible depuis le demarrage"
else
  if grep -q 'Connected to Telegram' <<<"$JOURNAL"; then
    ok "Telegram connecte (depuis le demarrage du ${DEPUIS%%.*})"
  else
    ko "Telegram : aucune ligne 'Connected to Telegram' depuis le demarrage"
  fi
  NB_TB=$(grep -c 'Traceback (most recent call last)' <<<"$JOURNAL" || true)
  if [ "${NB_TB:-0}" -eq 0 ]; then
    ok "aucun Traceback depuis le demarrage"
  else
    ko "$NB_TB Traceback depuis le demarrage"
    # Cause de chaque Traceback : la ligne d'erreur qui le termine.
    grep -A25 'Traceback (most recent call last)' <<<"$JOURNAL" \
      | sed 's/^.*python\[[0-9]*\]: //' \
      | grep -E '^[A-Za-z_.]+(Error|Exception)\b' | sort | uniq -c | sort -rn | head -3 \
      | while read -r ligne; do note "cause : ${ligne:0:140}"; done
    DATE_TB=$(grep -m1 -B0 'Traceback (most recent call last)' <<<"$JOURNAL" | cut -c1-16)
    note "premier le $DATE_TB (journalctl --user -u $UNITE --since \"$DEPUIS\" | grep -A12 Traceback)"
  fi
fi

# --- 2. Reglages proteges ----------------------------------------------------
if [ ! -f "$PROTEGES" ]; then
  ko "fichier des reglages proteges absent : $PROTEGES"
else
  SORTIE=$("$VENV_PY" - "$HOME_H/config.yaml" "$PROTEGES" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
att = yaml.safe_load(open(sys.argv[2])) or {}
def lire(d, chemin):
    for k in chemin.split("."):
        if not isinstance(d, dict) or k not in d:
            return KeyError
        d = d[k]
    return d
def diff(reel, voulu, chemin):
    """Ecarts de `reel` par rapport a `voulu` : seules les cles attendues comptent
    (le fichier protege ne porte aucune cle secrete, la config en a)."""
    if isinstance(voulu, dict):
        if not isinstance(reel, dict):
            return [f"{chemin} : {str(reel)[:50]} (attendu un bloc)"]
        sortie = []
        for k, v in voulu.items():
            if k not in reel:
                sortie.append(f"{chemin}.{k} : absent (attendu {str(v)[:50]})")
            else:
                sortie += diff(reel[k], v, f"{chemin}.{k}")
        return sortie
    if reel != voulu:
        return [f"{chemin} : {str(reel)[:50]} (attendu {str(voulu)[:50]})"]
    return []
ecarts = []
for chemin, voulu in att.items():
    reel = lire(cfg, chemin)
    if reel is KeyError:
        ecarts.append(f"{chemin} : absent (attendu {str(voulu)[:60]})")
    else:
        ecarts += diff(reel, voulu, chemin)
print(len(att))
for e in ecarts:
    print(e)
PY
)
  RC=$?
  if [ $RC -ne 0 ]; then
    ko "reglages proteges : comparaison impossible"
  else
    TOTAL=$(head -1 <<<"$SORTIE")
    ECARTS=$(tail -n +2 <<<"$SORTIE")
    if [ -z "$ECARTS" ]; then
      ok "reglages proteges : $TOTAL cles conformes"
    else
      ko "reglages proteges : $(wc -l <<<"$ECARTS") ecart(s) sur $TOTAL"
      head -6 <<<"$ECARTS" | while read -r l; do note "$l"; done
    fi
  fi
fi

# --- 3. Plugins charges ------------------------------------------------------
# La preuve est dans logs/agent.log (niveau INFO, le journal systemd ne garde que
# les avertissements) : chaque plugin y laisse "capability_check plugin=<nom>" a son
# chargement. Si la DERNIERE ligne d'un plugin est "inactif", c'est un echec (un plugin qui se
# reveille plus tard, comme steer-proxy, n'est plus inactif).
DEBUT_LOG=$(date -d "${DEPUIS%%.*}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "")
LOG_PLUG=""
if [ -n "$DEBUT_LOG" ] && [ -f "$HOME_H/logs/agent.log" ]; then
  LOG_PLUG=$(awk -v d="$DEBUT_LOG" '/^[0-9]{4}-[0-9]{2}-[0-9]{2} / { fait = (substr($0,1,19) >= d) } fait' "$HOME_H/logs/agent.log")
fi
PLUGINS=$("$VENV_PY" -c "
import yaml
c = yaml.safe_load(open('$HOME_H/config.yaml')) or {}
print(' '.join((c.get('plugins') or {}).get('enabled') or []))" 2>/dev/null)
if [ -z "$PLUGINS" ]; then
  ko "plugins : liste enabled illisible"
else
  MANQUE=""
  INACTIF=""
  for p in $PLUGINS; do
    sous=${p//-/_}
    if ! grep -qE "plugin=${p}( |$)|hermes_plugins\.${sous}:|hermes\.plugins\.${sous}:" <<<"$LOG_PLUG"; then
      MANQUE="$MANQUE $p"
    elif grep -E "(hermes_plugins|hermes\.plugins)\.${sous}:" <<<"$LOG_PLUG" | tail -1 | grep -qE "WARNING .*inactif"; then
      INACTIF="$INACTIF $p"
    fi
  done
  if [ -z "$MANQUE" ] && [ -z "$INACTIF" ]; then
    ok "plugins charges : $PLUGINS"
  else
    ko "plugins non charges ou inactifs :$MANQUE$INACTIF"
    [ -z "$LOG_PLUG" ] && note "logs/agent.log sans ligne depuis le demarrage"
  fi
fi

# --- 4. Commandes Telegram (getMyCommands, lecture seule) --------------------
# Le jeton passe par stdin de curl : il n'apparait ni dans les arguments ni a l'ecran.
JETON=$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$HOME_H/.env" 2>/dev/null | cut -d= -f2- | tr -d "'\"")
if [ -z "$JETON" ]; then
  ko "commandes Telegram : jeton introuvable dans l'environnement du gateway"
else
  REP=$(printf 'url = "https://api.telegram.org/bot%s/getMyCommands"\n' "$JETON" | curl -s -m 15 -K - 2>/dev/null)
  unset JETON
  CMDS=$("$VENV_PY" -c "
import json, sys
try:
    r = json.loads(sys.stdin.read())
    print(' '.join(c['command'] for c in r['result']) if r.get('ok') else 'ERREUR')
except Exception:
    print('ERREUR')" <<<"$REP")
  if [ "$CMDS" = "ERREUR" ] || [ -z "$CMDS" ]; then
    ko "commandes Telegram : reponse API illisible"
  else
    ABSENT=""
    for c in menu supp; do
      case " $CMDS " in *" $c "*) ;; *) ABSENT="$ABSENT /$c" ;; esac
    done
    N=$(wc -w <<<"$CMDS")
    if [ -z "$ABSENT" ]; then
      ok "commandes Telegram : /menu /supp visibles ($N commandes)"
    else
      ko "commandes Telegram absentes :$ABSENT ($N commandes visibles)"
    fi
  fi
fi

# --- 5. Retouches du registre ------------------------------------------------
# Colonne verif de chaque ligne R01 a R21 : un marqueur dans le code, un fichier
# de test, ou un sha. Les verifs manuelles (texte libre) sont comptees a part.
if [ ! -f "$REGISTRE" ]; then
  note "pas de registre des retouches ($REGISTRE) : point ignore"
else
  SORTIE=$("$VENV_PY" - "$REGISTRE" "$DEPOT" "$RAPIDE" <<'PY'
import re, subprocess, sys, pathlib
registre, depot, rapide = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3] == "1"
lignes = [l for l in open(registre, encoding="utf-8") if re.match(r"- \*\*R\d+\*\*", l)]
manque, manuel, tests, verifies = [], [], {}, 0
def trouve_test(nom):
    r = list(depot.glob(f"tests/**/{nom}"))
    return r[0] if r else None
for l in lignes:
    num = re.match(r"- \*\*(R\d+)\*\*", l).group(1)
    # Zone verif : ce qui suit "test ", "tests " ou "verif :" jusqu'a la fin de la ligne.
    m = re.search(r"(?:tests?\s|v[ée]rif\s*:)(.*)$", l)
    if not m:
        manuel.append(num)
        continue
    jetons = re.findall(r"`([^`]+)`", m.group(1).split(" · ")[0])
    objectifs = [j for j in jetons if re.fullmatch(r"test_\w+\.py", j) or re.fullmatch(r"[0-9a-f]{10}", j)
                 or re.fullmatch(r"_?[A-Za-z0-9_-]+(\.json)?", j)]
    if not objectifs:
        manuel.append(num)
        continue
    ok = True
    for j in objectifs:
        if re.fullmatch(r"test_\w+\.py", j):
            f = trouve_test(j)
            if f is None:
                ok = False; manque.append(f"{num} {j} absent")
            else:
                tests.setdefault(str(f), []).append(num)
        elif re.fullmatch(r"[0-9a-f]{10}", j):
            if subprocess.run(["git", "-C", str(depot), "cat-file", "-e", j + "^{commit}"],
                              capture_output=True).returncode != 0:
                ok = False; manque.append(f"{num} commit {j} absent")
        else:
            r = subprocess.run(["git", "-C", str(depot), "grep", "-q", "-F", j, "HEAD", "--",
                                "*.py", "*.sh", "*.json"], capture_output=True)
            if r.returncode != 0:
                ok = False; manque.append(f"{num} marqueur {j} absent du code")
    if ok:
        verifies += 1
echec = []
if tests and not rapide:
    py = str(depot / "venv/bin/python")
    if not pathlib.Path(py).exists():
        py = sys.executable
    import os, tempfile
    env = dict(os.environ, HERMES_HOME=tempfile.mkdtemp(), PYTHONPATH=str(depot), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--import-mode=importlib",
                        "-x", "--no-header", *tests], cwd=str(depot), env=env, capture_output=True, text=True, timeout=100)
    if r.returncode != 0:
        dernier = [x for x in r.stdout.splitlines() if x.strip()][-3:]
        echec = ["tests en echec : " + " | ".join(dernier)[:300]]
print(f"{len(lignes)}|{verifies}|{len(tests)}|{int(rapide)}")
print(",".join(manuel))
for x in manque + echec:
    print(x)
PY
)
  RC=$?
  if [ $RC -ne 0 ]; then
    ko "retouches : controle impossible"
  else
    IFS='|' read -r NL NV NT RP <<<"$(sed -n 1p <<<"$SORTIE")"
    MANUELS=$(sed -n 2p <<<"$SORTIE")
    PROBLEMES=$(tail -n +3 <<<"$SORTIE")
    if [ -z "$PROBLEMES" ]; then
      EXTRA="$NT fichiers de test"
      [ "$RP" = "1" ] && EXTRA="tests non lances (--rapide)"
      ok "retouches : $NV sur $NL verifiees par marqueur ou test ($EXTRA)"
    else
      ko "retouches : $(wc -l <<<"$PROBLEMES") probleme(s)"
      head -6 <<<"$PROBLEMES" | while read -r l; do note "$l"; done
    fi
    [ -n "$MANUELS" ] && note "verif manuelle seulement : $MANUELS"
  fi
fi

echo "----"
if [ "$NB_KO" -eq 0 ]; then
  echo "TOUT OK"
  exit 0
fi
echo "$NB_KO point(s) KO"
exit 1
