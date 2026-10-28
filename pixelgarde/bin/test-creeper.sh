#!/usr/bin/env bash
# Batterie de tests de bout en bout pour la bulle Creeper (Pixel 9 Pro XL).
#
# Rejoue sur le VRAI telephone les scenarios decrits dans
# projets/creeper.md. Chaque test est independant : un echec n'empeche pas
# les suivants de tourner (pas de `set -e`). Chaque action laissee sur le
# telephone ou dans les fichiers du garde est retiree par le trap de sortie,
# meme si le script est interrompu au milieu.
#
# Budget d'envois reels sur Telegram : trois au maximum (tests 5, 6, 7),
# chacun prefixe [TEST]. Les autres tests verifient la logique sans jamais
# laisser un rapport partir (inject puis rejeter avant le delai de
# regroupement de 8 s).
#
# Usage : bin/pixel/test-creeper.sh
set -uo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTIONS="$ICI/actions"
GARDE_UNIT="pixel-garde"
QG_ATTENTE="$HOME/.hermes/scripts/qg-attente.py"
QG_DB="$HOME/.hermes/qg.db"
QG_MODE_F="$HOME/.hermes/qg-voix-mode"
CMD_TEL="/sdcard/Android/data/com.poste.pixelgarde/files/cmd.txt"
TRACES="/tmp/pixel-traces"
CAPTURES="$HOME/Images/Pixel"

ADB_BIN="${ADB:-$(command -v adb || echo "$HOME/.local/platform-tools/adb")}"

TOTAL=0
PASSES=0
SAUTES=0
ECHECS_LISTE=()

ok() { PASSES=$((PASSES + 1)); TOTAL=$((TOTAL + 1)); echo "OK    $1"; }
echec() { TOTAL=$((TOTAL + 1)); ECHECS_LISTE+=("$1 : $2"); echo "ECHEC $1 : $2"; }
saute() { SAUTES=$((SAUTES + 1)); echo "SAUTE $1 : $2"; }

# Le nettoyage est une pile : on defait dans l'ordre inverse de la pose, et
# CHAQUE commande tourne meme si une precedente a echoue (`|| true` implicite
# via le sous-shell). Un test qui plante en cours de route ne doit jamais
# laisser un arret d'urgence arme ou un faux rapport dans la file.
ROLLBACK=()
ajouter_rollback() { ROLLBACK+=("$1"); }
nettoyer() {
  echo
  echo "-- nettoyage --"
  local i
  for ((i = ${#ROLLBACK[@]} - 1; i >= 0; i--)); do
    bash -c "${ROLLBACK[$i]}" 2>/dev/null
  done
}
trap nettoyer EXIT

# Attend qu'un motif apparaisse dans le journal du garde depuis un instant
# donne. journalctl --since fait le tri : pas besoin de suivre un flux.
attendre_log() {
  local depuis="$1" motif="$2" delai="${3:-15}"
  local fin=$(($(date +%s) + delai))
  while [ "$(date +%s)" -lt "$fin" ]; do
    if journalctl --user -u "$GARDE_UNIT" --no-pager --since "$depuis" 2>/dev/null \
       | grep -qF "$motif"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# Rejoue exactement etat_courant() du garde, sans attendre son tour de
# peinture (0,3 s en moyenne, mais pas garanti). Importer le module pese
# ~0,2 s : largement moins cher qu'un aller-retour adb, et ca teste le VRAI
# code, pas une resupposition de sa logique.
garde_etat_courant() {
  python3 - "$ICI" <<'PY'
import sys, os, importlib.util
sys.path.insert(0, sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "garde_test", os.path.join(sys.argv[1], "pixel-garde"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(m.etat_courant())
PY
}

# Idem pour le menu assemble : c'est CE texte, et pas menu.txt tout seul,
# qui part vers la pastille.
garde_menu_live() {
  python3 - "$ICI" <<'PY'
import sys, os, importlib.util
sys.path.insert(0, sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "garde_test", os.path.join(sys.argv[1], "pixel-garde"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(m.menu_bulle())
PY
}

echo "=== test-creeper : verification de la bulle Creeper ==="
echo

# Un arret d'urgence deja arme au demarrage veut dire que USER a le telephone
# en main pour de bon : on ne touche a rien.
if [ -e /tmp/pixel-stop ]; then
  echo "ARRET D'URGENCE deja arme (/tmp/pixel-stop) : la campagne ne demarre pas."
  exit 1
fi

# Une conversation vocale reelle en cours : les tests qui manipulent le
# marqueur /tmp/pixel-voix ou qui dependent de son absence sont sautes,
# jamais rejoues par-dessus une vraie conversation de USER.
VOIX_REELLE=0
if [ -e /tmp/pixel-voix ]; then
  VOIX_REELLE=1
  echo "conversation vocale reelle detectee (/tmp/pixel-voix) : tests 7 et 9 sautes."
fi

MODE_ORIGINE="$(cat "$QG_MODE_F" 2>/dev/null || echo silencieux)"
ETAT_ORIGINE="$(cat /tmp/pixel-etat 2>/dev/null || echo veille)"
ajouter_rollback "printf '%s' '$MODE_ORIGINE' > '$QG_MODE_F'"
ajouter_rollback "printf '%s' '$ETAT_ORIGINE' > /tmp/pixel-etat"

ADDR="$(python3 "$ICI/pixel" etat 2>/dev/null | awk -F': *' '/^adresse/{print $2; exit}')"
echo "adresse : ${ADDR:-(aucune)}"
echo

# ---------------------------------------------------------------- 1 -----
echo "-- 1. le service tourne, l'adresse adb est valide --"
if systemctl --user is-active --quiet "$GARDE_UNIT" \
   && [[ "$ADDR" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+$ ]] \
   && timeout 10 "$ADB_BIN" -s "$ADDR" shell true >/dev/null 2>&1; then
  ok "1" "pixel-garde actif, $ADDR joignable"
else
  echec "1" "service inactif ou $ADDR injoignable"
fi

# ---------------------------------------------------------------- 2 -----
echo "-- 2. la pastille repond a un broadcast d'etat --"
DEPUIS2="$(date '+%Y-%m-%d %H:%M:%S')"
"$ADB_BIN" -s "$ADDR" logcat -c 2>/dev/null
echo pilote > /tmp/pixel-etat
sleep 1.5
if "$ADB_BIN" -s "$ADDR" logcat -d -s pixelgarde:I 2>/dev/null | grep -q "recu com.poste.pixel.BULLE"; then
  ok "2" "l'appli recoit le broadcast BULLE apres changement d'etat (pilote, vert)"
else
  echec "2" "aucun broadcast BULLE recu par l'appli apres changement d'etat"
fi
echo "$ETAT_ORIGINE" > /tmp/pixel-etat

# ---------------------------------------------------------------- 3 -----
echo "-- 3. menu.txt sur disque, puces attendues, sans Raccrocher --"
MENU="$ACTIONS/menu.txt"
MANQUE=""
# Deux niveaux depuis le 2026-10-01 : le quotidien dans menu.txt, le reste
# dans reglages.txt, ouvert par la puce « reglages ».
for id in voix bilan lirepresse voixmode masquer reglages; do
  grep -qE "^${id}:" "$MENU" || MANQUE="$MANQUE $id"
done
for id in lireecran rec; do
  grep -qE "^${id}:" "$ACTIONS/reglages.txt" || MANQUE="$MANQUE reglages/$id"
done
MENU_LIVE="$(garde_menu_live)"
if [ -z "$MANQUE" ] \
   && ! grep -qiE "^raccrocher:" "$MENU" \
   && [[ "$MENU_LIVE" != *voixraccrocher* ]] \
   && [[ "$MENU_LIVE" != *"Raccrocher"* ]]; then
  ok "3" "menu.txt et le menu assemble contiennent les puces attendues, sans Raccrocher"
else
  echec "3" "puces manquantes:[$MANQUE] ou Raccrocher present (menu vecu : $MENU_LIVE)"
fi

# ---------------------------------------------------------------- 4 -----
echo "-- 4. un rapport injecte allume l'ambre (etat_courant = attente) --"
ID4="$("$QG_ATTENTE" add "[TEST] verif ambre" \
       --resume "ligne de test, jetee avant le delai de regroupement." \
       --source test-creeper)"
ajouter_rollback "$QG_ATTENTE rejeter $ID4 >/dev/null 2>&1"
ETAT4="$(garde_etat_courant)"
if [ "$ETAT4" = "attente" ]; then
  ok "4" "etat_courant() rend 'attente' des qu'un rapport nouveau existe (#$ID4)"
else
  echec "4" "etat_courant() a rendu '$ETAT4' au lieu de 'attente'"
fi
"$QG_ATTENTE" rejeter "$ID4" >/dev/null 2>&1

# ---------------------------------------------------------------- 5 -----
echo "-- 5. deux rapports a 3 s d'intervalle partent en UN seul digest --"
echo silencieux > "$QG_MODE_F"
DEPUIS5="$(date '+%Y-%m-%d %H:%M:%S')"
ID5A="$("$QG_ATTENTE" add "[TEST] regroupement A" \
        --resume "premier rapport du test de regroupement." --source test-creeper)"
sleep 3
ID5B="$("$QG_ATTENTE" add "[TEST] regroupement B" \
        --resume "second rapport, trois secondes plus tard." --source test-creeper)"
ajouter_rollback "$QG_ATTENTE rejeter $ID5A >/dev/null 2>&1"
ajouter_rollback "$QG_ATTENTE rejeter $ID5B >/dev/null 2>&1"
# QG_REGROUPE_S = 8 s apres le DERNIER depot ; la boucle de veille tourne
# toutes les 5 s, donc le delai reel vu par USER est de 8 a 13 s (creeper.md).
if attendre_log "$DEPUIS5" "lecture auto de 2 rapport(s)" 20; then
  ok "5" "deux rapports proches partent en un seul lot (#$ID5A, #$ID5B)"
else
  echec "5" "pas de lecture groupee de 2 rapports vue dans le journal sous 20 s"
fi

# ---------------------------------------------------------------- 6 -----
echo "-- 6. mode ecrits seulement : le texte part, la voix se tait --"
echo silencieux > "$QG_MODE_F"
DEPUIS6="$(date '+%Y-%m-%d %H:%M:%S')"
ID6="$("$QG_ATTENTE" add "[TEST] silencieux" \
       --resume "verifie que le texte part et que la voix se tait." --source test-creeper)"
ajouter_rollback "$QG_ATTENTE rejeter $ID6 >/dev/null 2>&1"
if attendre_log "$DEPUIS6" "lecture auto de 1 rapport(s) (texte seul)" 20; then
  sleep 3   # laisser rapport.sh finir d'ecrire sa trace apres le sendMessage
  if grep -q "mode texte seul" "$TRACES/rapport.log" 2>/dev/null \
     && ! grep -q "lu a voix haute" "$TRACES/rapport.log" 2>/dev/null; then
    ok "6" "mode ecrits seulement : texte envoye, voix coupee (correctif du 28/08)"
  else
    echec "6" "trace rapport.log ne confirme pas texte seul : $(tail -3 "$TRACES/rapport.log" 2>/dev/null)"
  fi
else
  echec "6" "pas de lecture auto 'texte seul' vue dans le journal sous 20 s"
fi

# ---------------------------------------------------------------- 7 -----
echo "-- 7. mode lus a voix haute : texte ET voix --"
if [ "$VOIX_REELLE" = "1" ]; then
  saute "7" "conversation vocale reelle en cours, le son partirait dedans"
else
  echo continu > "$QG_MODE_F"
  DEPUIS7="$(date '+%Y-%m-%d %H:%M:%S')"
  ID7="$("$QG_ATTENTE" add "[TEST] voix haute" \
         --resume "dernier envoi reel de la campagne : texte et voix attendus." \
         --source test-creeper)"
  ajouter_rollback "$QG_ATTENTE rejeter $ID7 >/dev/null 2>&1"
  if attendre_log "$DEPUIS7" "lecture auto de 1 rapport(s)" 20; then
    sleep 4   # edge-tts + push + VOIXDIRE prennent quelques secondes de plus
    if grep -q "voix envoyee" "$TRACES/rapport.log" 2>/dev/null \
       && grep -q "lu a voix haute sur le telephone" "$TRACES/rapport.log" 2>/dev/null; then
      ok "7" "mode lus a voix haute : texte et voix partent tous les deux"
    else
      echec "7" "trace rapport.log ne confirme pas la voix : $(tail -5 "$TRACES/rapport.log" 2>/dev/null)"
    fi
  else
    echec "7" "pas de lecture auto vue dans le journal sous 20 s"
  fi
  echo silencieux > "$QG_MODE_F"   # retour immediat au defaut de USER
fi

# ---------------------------------------------------------------- 8 -----
echo "-- 8. arret d'urgence arme : rien ne part, et le garde l'ecrit --"
"$ICI/pixel" pause >/dev/null 2>&1
ajouter_rollback "$ICI/pixel go >/dev/null 2>&1"
DEPUIS8="$(date '+%Y-%m-%d %H:%M:%S')"
ID8="$("$QG_ATTENTE" add "[TEST] arret d'urgence" \
       --resume "ne doit jamais partir tant que le stop est arme." --source test-creeper)"
ajouter_rollback "$QG_ATTENTE rejeter $ID8 >/dev/null 2>&1"
if attendre_log "$DEPUIS8" "NON lus : ARRET D'URGENCE arme" 15; then
  STATUT8="$(sqlite3 "$QG_DB" "SELECT statut FROM attente WHERE id=$ID8;" 2>/dev/null)"
  if [ "$STATUT8" = "nouveau" ]; then
    ok "8" "arret d'urgence : rien ne part (statut toujours 'nouveau'), et le journal le dit"
  else
    echec "8" "le rapport #$ID8 est passe a '$STATUT8' malgre l'arret d'urgence"
  fi
else
  echec "8" "le journal ne dit pas 'NON lus : ARRET D'URGENCE arme'"
fi
"$ICI/pixel" go >/dev/null 2>&1
"$QG_ATTENTE" rejeter "$ID8" >/dev/null 2>&1

# ---------------------------------------------------------------- 9 -----
echo "-- 9. un marqueur de conversation vieux de plus de 10 min est retire --"
if [ "$VOIX_REELLE" = "1" ]; then
  saute "9" "conversation vocale reelle en cours, on ne simule pas par-dessus"
else
  # VOIX_PEREMPTION_S = 600 dans pixel-garde. On antidate directement plutot
  # que d'attendre 10 min pour de vrai.
  touch -d '-11 minutes' /tmp/pixel-voix /tmp/pixel-voix-etat
  ajouter_rollback "rm -f /tmp/pixel-voix /tmp/pixel-voix-etat"
  DEPUIS9="$(date '+%Y-%m-%d %H:%M:%S')"
  if attendre_log "$DEPUIS9" "marqueur de conversation perime" 20; then
    if [ ! -e /tmp/pixel-voix ] && [ ! -e /tmp/pixel-voix-etat ]; then
      ok "9" "un marqueur vieux de 11 min est retire tout seul par le garde"
    else
      echec "9" "le journal annonce la peremption mais les fichiers sont encore la"
    fi
  else
    echec "9" "aucune peremption vue dans le journal sous 20 s"
  fi
fi

# --------------------------------------------------------------- 10 -----
echo "-- 10. une transcription vide ou en points seuls est jetee --"
# On rejoue LE MEME pipeline que voixtour.sh, pas une reimplementation : si la
# ligne source change, l'assertion sur sa presence echoue en premier, avant
# que le test ne se mette a juger un code qu'il ne teste plus vraiment.
if grep -qF "tr -cd '[:alnum:]'" "$ACTIONS/voixtour.sh"; then
  UTILE_VIDE=$(printf '%s' "......." | tr -cd '[:alnum:]' | wc -c)
  UTILE_BRUIT=$(printf '%s' ", . , ... ,," | tr -cd '[:alnum:]' | wc -c)
  UTILE_VRAI=$(printf '%s' "ok, cinq minutes" | tr -cd '[:alnum:]' | wc -c)
  if [ "$UTILE_VIDE" -lt 2 ] && [ "$UTILE_BRUIT" -lt 2 ] && [ "$UTILE_VRAI" -ge 2 ]; then
    ok "10" "le seuil UTILE (moins de 2 caracteres alphanumeriques) trie silence et vraie phrase"
  else
    echec "10" "seuil UTILE incoherent : vide=$UTILE_VIDE bruit=$UTILE_BRUIT vrai=$UTILE_VRAI"
  fi
else
  echec "10" "la ligne 'tr -cd [:alnum:] | wc -c' n'est plus dans voixtour.sh"
fi

# --------------------------------------------------------------- 11 -----
echo "-- 11. un appui rattrape depuis cmd.txt ne part pas deux fois --"
MARQ_CAPTURES="$(mktemp)"
DEPUIS11="$(date '+%Y-%m-%d %H:%M:%S')"
TS11="$(date +%s%3N)"
# "shot" est le bouton le plus inoffensif du menu : une capture, un flash,
# une vibration. Pas d'etat a annuler derriere lui, hormis le fichier produit.
"$ADB_BIN" -s "$ADDR" shell "echo '$TS11 shot' > $CMD_TEL" >/dev/null 2>&1
ajouter_rollback "$ADB_BIN -s $ADDR shell rm -f $CMD_TEL"
if attendre_log "$DEPUIS11" "appui rattrape (fichier) : shot" 12; then
  sleep 7   # laisser passer un second tour de veille (5 s) sans reexecution
  N_ACTION="$(journalctl --user -u "$GARDE_UNIT" --no-pager --since "$DEPUIS11" 2>/dev/null \
              | grep -c "action shot")"
  if [ "$N_ACTION" = "1" ]; then
    ok "11" "un appui rattrape via cmd.txt n'est rejoue qu'une seule fois"
  else
    echec "11" "action shot vue $N_ACTION fois (attendu 1) : cmd.txt a ete rejoue"
  fi
else
  echec "11" "l'appui depose dans cmd.txt n'a jamais ete rattrape"
fi
"$ADB_BIN" -s "$ADDR" shell "rm -f $CMD_TEL" >/dev/null 2>&1
find "$CAPTURES" -newer "$MARQ_CAPTURES" -name 'pixel-*.png' -delete 2>/dev/null
rm -f "$MARQ_CAPTURES"

# --------------------------------------------------------------- 12 -----
echo "-- 12. une action inconnue est refusee et le dit dans le journal --"
DEPUIS12="$(date '+%Y-%m-%d %H:%M:%S')"
TS12="$(date +%s%3N)"
"$ADB_BIN" -s "$ADDR" shell "echo '$TS12 testcreeperinconnue' > $CMD_TEL" >/dev/null 2>&1
ajouter_rollback "$ADB_BIN -s $ADDR shell rm -f $CMD_TEL"
if attendre_log "$DEPUIS12" "action inconnue : testcreeperinconnue" 12; then
  if [ ! -e "$TRACES/testcreeperinconnue.log" ]; then
    ok "12" "action inconnue refusee proprement, sans trace fantome, ecrite au journal"
  else
    echec "12" "une trace a ete creee pour une action pourtant inconnue"
  fi
else
  echec "12" "aucune ligne 'action inconnue' vue dans le journal sous 12 s"
fi
"$ADB_BIN" -s "$ADDR" shell "rm -f $CMD_TEL" >/dev/null 2>&1

# --------------------------------------------------------------------------
echo
echo "=== resultat : $PASSES/$TOTAL tests passes, $SAUTES saute(s) ==="
if [ "$PASSES" -eq "$TOTAL" ]; then
  echo "tout est vert."
  exit 0
fi
echo "echecs :"
printf '  - %s\n' "${ECHECS_LISTE[@]}"
exit 1
