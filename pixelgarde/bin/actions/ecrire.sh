#!/usr/bin/env bash
# Une question tapee dans le champ « Ecrire » de Creeper (2.45).
#
# Le garde passe le texte dans ECRIRE_TEXTE (ECRIRE_QG=1 pour le bouton QG).
# On lit l'ecran du telephone par uiautomator dump : aucun service
# d'accessibilite, et l'arbre des vues reste lisible meme quand l'appli
# interdit la capture (FLAG_SECURE, mesure du 2026-10-21). Le standard recoit
# la question avec cet ecran (VOIX_ECRAN) ; sa reponse revient dans le champ
# par ecrire-rep.txt (ecrit par voixtour.sh) et par la voix.
set -uo pipefail
ADDR="${1:?addr}"
ICI="$(cd "$(dirname "$0")" && pwd)"
PIXEL_TMP="${PIXEL_TMP:-/tmp}"
TEL="/sdcard/Android/data/com.poste.pixelgarde/files"
Q="${ECRIRE_TEXTE:-}"
# Mode (2.48) : question | repondre | resumer. Un mode sans consigne de USER est
# permis (« Repondre » d'un toucher) ; seul « question » exige un texte.
MODE="${ECRIRE_MODE:-question}"
case "$MODE" in question|repondre|resumer|traduire|seduire) ;; *) MODE=question ;; esac
CONV="${ECRIRE_CONV:-}"
[ -n "$Q" ] || [ "$MODE" != question ] || exit 1
TMP="$(mktemp -d)"; trap 'rm -rf "${TMP:?}"' EXIT

rendre() {   # texte -> champ du telephone
  printf '%s\n' "$1" > "$TMP/rep.txt"
  adb -s "$ADDR" push "$TMP/rep.txt" "$TEL/ecrire-rep.txt" >/dev/null 2>&1
}

# Etape en cours : le panneau l'affiche avec les secondes ecoulees. Sans ca
# il restait muet pendant 10 s (retour de USER, 2026-10-21).
etape() {
  printf '%s\n' "$1" > "$TMP/etape.txt"
  adb -s "$ADDR" push "$TMP/etape.txt" "$TEL/ecrire-etat.txt" >/dev/null 2>&1
}
# Traduire (2.51) : le texte a traduire est dans Q, aucun besoin de lire l'ecran.
if [ "$MODE" = traduire ]; then
  etape "Je traduis"
  : > "$PIXEL_TMP/pixel-ecran-ctx.txt"
  grep -v '^muet:' "$ICI/../../qg/modes/traduire.md" > "$PIXEL_TMP/pixel-ecrire-consigne.txt"
  [ -e "$PIXEL_TMP/pixel-voix" ] || bash "$ICI/voixdebut.sh"
  VOIX_MODE=traduire VOIX_ECRAN="$PIXEL_TMP/pixel-ecran-ctx.txt" \
    VOIX_CONSIGNE="$PIXEL_TMP/pixel-ecrire-consigne.txt" VOIX_MUET=1 VOIX_CONV="$CONV" \
    VOIX_QUESTION="Traduire ce message" VOIX_TEXTE="Traduis ce texte : $Q" \
    exec bash "$ICI/voixtour.sh" "$ADDR"
fi
etape "Je lis ton écran"

# ------------------------------------------------------------- l'ecran
# --windows : toutes les fenetres, pas seulement la fenetre active.
# Auto-soin (2026-10-23) : apres une coupure Tailscale ou un redemarrage du PC,
# le transport ADB reste « device » mais ses commandes pendent. Un dump borne a
# 15 s ; sans fichier, on coupe puis rouvre la liaison et on retente une fois.
ADB_REEL=/usr/lib/android-sdk/platform-tools/adb
lire_ecran() {
  rm -f "${TMP:?}/ui.xml"
  timeout 15 adb -s "$ADDR" shell uiautomator dump --windows /sdcard/ui-ecrire.xml >/dev/null 2>&1 \
    || timeout 15 adb -s "$ADDR" shell uiautomator dump /sdcard/ui-ecrire.xml >/dev/null 2>&1
  timeout 10 adb -s "$ADDR" pull /sdcard/ui-ecrire.xml "$TMP/ui.xml" >/dev/null 2>&1
  [ -s "$TMP/ui.xml" ]
}
# Sans ADB (2.61) : l'appli a deja poste l'arbre des vues au relais (Ecran.java).
# Frais de moins de 2 min, sinon on retombe sur le releve ADB ci-dessous.
RECUS_ECRAN="$HOME/.hermes/creeper-relais/recus"
EXML="$(find "$RECUS_ECRAN" -maxdepth 1 -name 'ecran-*.xml' -mmin -2 2>/dev/null | sort | tail -1)"
if [ -n "$EXML" ] && [ -s "$EXML" ]; then
  cp "$EXML" "$TMP/ui.xml"
  find "$RECUS_ECRAN" -maxdepth 1 -name 'ecran-*.xml' -delete 2>/dev/null
  echo "$(date '+%F %T') ecrire : ecran lu par l'appli (sans ADB)" >> "$HOME/.hermes/logs/voixtour.log"
elif ! lire_ecran; then
  etape "Je rétablis la liaison"
  timeout 8 "$ADB_REEL" disconnect "$ADDR" >/dev/null 2>&1
  timeout 15 "$ADB_REEL" connect "$ADDR" >/dev/null 2>&1
  # Le garde memorise « injoignable » 20 s : sans l'effacer, le 2e essai est refuse d'office.
  rm -f /tmp/adb-pixel-injoignable
  lire_ecran || : > "$TMP/ui.xml"
  echo "$(date '+%F %T') ecrire : liaison ADB rétablie avant relevé" >> "$HOME/.hermes/logs/voixtour.log"
fi
python3 - "$TMP/ui.xml" "$MODE" > "$TMP/ecran.txt" <<'PY'
import re, sys, xml.etree.ElementTree as ET
try:
    racine = ET.parse(sys.argv[1]).getroot()
except Exception:
    print("(ecran illisible)")
    sys.exit(0)
out, vus, pkgs = [], set(), []
# Modes « repondre » et « resumer » : chaque ligne porte le cote de sa bulle.
# C'est ce qui dit qui parle (a droite = USER, a gauche = l'autre).
cote = len(sys.argv) > 2 and sys.argv[2] in ("repondre", "resumer", "seduire")


def bornes(n):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds") or "")
    return tuple(int(x) for x in m.groups()) if m else None


larg = 1
for n in racine.iter("node"):
    b = bornes(n)
    if b and b[2] > larg and (n.get("package") or "") != "com.poste.pixelgarde":
        larg = b[2]
for n in racine.iter("node"):
    pk = n.get("package") or ""
    # Notre propre champ et le clavier ne sont pas l'ecran de USER.
    if pk == "com.poste.pixelgarde" or "inputmethod" in pk or pk == "com.android.systemui":
        continue
    t = (n.get("text") or "").strip()
    d = (n.get("content-desc") or "").strip()
    brut = t or d
    if not brut:
        continue
    b = bornes(n)
    if cote and b:
        # Deux messages identiques (« ok ») restent deux messages : on ne
        # dedoublonne que sur le texte ET la place.
        cle = (brut, b)
    else:
        cle = brut
    if cle in vus:
        continue
    vus.add(cle)
    if pk and pk not in pkgs:
        pkgs.append(pk)
    if cote and b and b[2] > b[0]:
        g, dr = round(100 * b[0] / larg), round(100 - 100 * b[2] / larg)
        if g >= 20 and dr >= 20 and abs(g - dr) <= 8:
            c = "C"
        elif g < dr - 8:
            c = "G"
        elif dr < g - 8:
            c = "D"
        else:
            c = "?"
        brut = "[{}] {{{}-{}}} {}".format(c, g, 100 - dr, brut.replace("\n", " / "))
    out.append(brut)
print("Appli au premier plan : " + (", ".join(pkgs) or "inconnue"))
if cote and sum(len(x) + 1 for x in out) > 5600:
    # Une conversation se lit par la fin : on garde l'en-tete (nom de
    # l'interlocuteur) et les derniers messages.
    tete, reste, taille = out[:6], out[6:], 0
    fin = []
    for x in reversed(reste):
        taille += len(x) + 1
        if taille > 5000:
            break
        fin.append(x)
    out = tete + ["(...messages plus anciens omis...)"] + list(reversed(fin))
print("\n".join(out) if out else "(aucun texte lisible : image, jeu ou champ masque)")
PY
head -c 6000 "$TMP/ecran.txt" > "$TMP/ecran.cut"
echo "ecrire : $(wc -c < "$TMP/ecran.cut") octets d'ecran" >&2

# Carte d'identite precoce (2.57) : qui est la personne a l'ecran, lu en 1 s,
# avant le modele. Le panneau bascule dans SA conversation pendant l'attente.
CIBLE=""
if [ "$MODE" = repondre ] || [ "$MODE" = resumer ] || [ "$MODE" = seduire ]; then
  python3 "$ICI/../personnes.py" carte "$TMP/ecran.cut" "$CONV" > "$TMP/carte.json" 2>/dev/null
  if [ -s "$TMP/carte.json" ]; then
    adb -s "$ADDR" push "$TMP/carte.json" "$TEL/ecrire-carte.json" >/dev/null 2>&1
    CIBLE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("cible",""))' "$TMP/carte.json" 2>/dev/null)"
    echo "ecrire : carte $(head -c 200 "$TMP/carte.json")" >&2
  fi
fi

# ------------------------------------------------------------- le QG
if [ -n "${ECRIRE_QG:-}" ]; then
  etape "J'envoie au QG"
  DEM="$(printf 'USER ecrit depuis Creeper : %s\n\nSon ecran a cet instant (arbre des vues, lu par ADB) :\n%s\n\nRepond-lui ici, il te lit sur son telephone.' "$Q" "$(cat "$TMP/ecran.cut")")"
  lanceur=(setsid nohup)
  command -v systemd-run >/dev/null 2>&1 && lanceur=(systemd-run --user --collect --quiet \
    "--setenv=PATH=$PATH" "--setenv=HOME=$HOME")
  "${lanceur[@]}" "$HOME/Bureau/Projets/contexte/bin/qg/qg-envoyer.sh" 2923 "$DEM" \
    </dev/null >/dev/null 2>&1
  rendre "Envoyé au QG avec ton écran. La réponse arrive dans tes rapports, compte environ 1 minute."
  exit 0
fi

# ------------------------------------------------------------- le standard
cp "$TMP/ecran.cut" "$PIXEL_TMP/pixel-ecran-ctx.txt"

# La consigne du mode (bin/qg/modes/<mode>.md) et les derniers tours de CETTE
# conversation. La ligne « muet: oui » coupe la voix : un brouillon de reponse
# ne se lit pas a haute voix.
FICHE="$ICI/../../qg/modes/$MODE.md"
[ -f "$FICHE" ] || FICHE="$ICI/../../qg/modes/question.md"
# Modele du mode (ligne « modele: » du fichier, 2.62) : le panneau Ecrire n'a pas
# a suivre le modele vocal standard. Un mode sans ligne garde le standard.
MODELE_FICHE="$(sed -n 's/^modele:[[:space:]]*//p' "$FICHE" | head -1)"
[ -n "$MODELE_FICHE" ] && export QG_STANDARD_MODELE="$MODELE_FICHE"
HIST="$HOME/.hermes/pixel-ecrire/$CONV.jsonl"
[ -n "$CIBLE" ] && [ -s "$HOME/.hermes/pixel-ecrire/$CIBLE.jsonl" ] && HIST="$HOME/.hermes/pixel-ecrire/$CIBLE.jsonl"
{
  grep -v -e '^muet:' -e '^modele:' "$FICHE"
  printf '\nMoment present (heure de Thailande) : %s. Tiens-en compte : un « bonne soiree » a 1 h du matin sonne faux.\n' "$(TZ=Asia/Bangkok date '+%A %d/%m %H:%M')"
  if [ "$MODE" = repondre ] || [ "$MODE" = seduire ]; then
    # Memoire des personnes (2.49) : dossier de la personne, tous reseaux.
    python3 "$ICI/../personnes.py" contexte "$TMP/ecran.cut" 2>/dev/null
  fi
  if [ -n "$CONV" ] && [ -s "$HIST" ]; then
    printf '\nTours precedents de CETTE conversation (du plus ancien au plus recent) :\n'
    tail -n 6 "$HIST" | python3 -c '
import json, sys
for l in sys.stdin:
    try:
        d = json.loads(l)
    except ValueError:
        continue
    print("USER : " + d.get("q", "")[:300])
    print("Toi : " + d.get("r", "")[:500])
'
  fi
} > "$PIXEL_TMP/pixel-ecrire-consigne.txt"
MUET=""
grep -q '^muet: oui' "$FICHE" && MUET=1

case "$MODE" in
  repondre) DIT="Écris ma réponse au message affiché${Q:+ : $Q}" ;;
  seduire)  DIT="Écris le message qui la fait basculer${Q:+ (consigne : $Q)}" ;;
  resumer)  DIT="Résume l'écran${Q:+ (consigne : $Q)}" ;;
  *)        DIT="$Q" ;;
esac
etape "Je réfléchis"
[ -e "$PIXEL_TMP/pixel-voix" ] || bash "$ICI/voixdebut.sh"
rm -f "$PIXEL_TMP/pixel-ecrire-personne.json"
VOIX_MODE="$MODE" VOIX_PERSONNE_OUT="$PIXEL_TMP/pixel-ecrire-personne.json" \
  VOIX_ECRAN="$PIXEL_TMP/pixel-ecran-ctx.txt" VOIX_CONSIGNE="$PIXEL_TMP/pixel-ecrire-consigne.txt" \
  VOIX_MUET="$MUET" VOIX_CONV="$CONV" VOIX_QUESTION="$Q" VOIX_TEXTE="$DIT" \
  exec bash "$ICI/voixtour.sh" "$ADDR"
