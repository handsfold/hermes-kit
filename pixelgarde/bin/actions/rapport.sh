#!/usr/bin/env bash
# Bouton « Lire » : le rapport en tete de la file du QG, en voix, sur Telegram.
#
# Le pari de ce script : USER ne lit pas un rapport sur un ecran de telephone
# tenu a bout de bras. Il l'ecoute. Le texte part quand meme, pour relire une
# ligne precise, mais c'est la voix qui porte.
#
# Il ne fabrique l'audio QU'AU MOMENT de l'appui : un rapport jamais lu ne
# coute donc rien. C'est ce qui permet d'en laisser s'accumuler sans remords.
set -euo pipefail

# Journal durable. La trace du garde (/tmp/pixel-traces/rapport.log) est ecrasee
# a chaque appui : le 2026-10-01, 4 rapports en 8 minutes ont efface la preuve
# qu'un texte etait bien parti au QG. Ici chaque lecture s'ajoute, horodatee,
# avec l'id du rapport et le message_id rendu par Telegram.
JOURNAL="$HOME/.hermes/logs/rapport.log"
if [ -f "$JOURNAL" ] && [ "$(stat -c %s "$JOURNAL")" -gt 500000 ]; then
  tail -c 200000 "$JOURNAL" > "$JOURNAL.tmp" && mv "$JOURNAL.tmp" "$JOURNAL"
fi
exec 2> >(while IFS= read -r l; do printf '%s %s\n' "$(date '+%F %T')" "$l"; done | tee -a "$JOURNAL" >&2)
echo "debut rapport id=${QG_ID:-file} conv=${QG_DANS_CONVERSATION:-0}" >&2

# Tout ce qui touche au systeme en service se deplace par l'environnement :
# les essais tournent sur une base, un dossier temporaire et un faux adb.
PIXEL_TMP="${PIXEL_TMP:-/tmp}"
ADB="${ADB:-adb}"
ICI="$(dirname "$(readlink -f "$0")")"
ADDR="${1:-$("$ADB" devices | awk '/device$/{print $1; exit}')}"
FILE="${QG_ATTENTE_PY:-$HOME/.hermes/scripts/qg-attente.py}"
LECTURE="$ICI/../qg-lecture"
STANDARD="${QG_BIN:-$ICI/../../qg}/qg-standard.py"
ENV="$HOME/.hermes/.env"
# Le dossier que le service .Voix relit : direSeul() y cherche le fichier.
TEL_VOIX="/sdcard/Android/data/com.poste.pixelgarde/files/voix"
# Tous les reglages du QG en un seul appel : voix, debit, modele, salon, delais.
# Ils se changent dans ~/.hermes/qg-config.json, jamais ici. `qg-config.py` sans
# argument les affiche tous avec leur origine.
eval "$("$HOME/.hermes/scripts/qg-config.py" env)"
VOIX="$QGC_VOIX"
DEBIT="$QGC_DEBIT"
VOIX_TG="$ICI/../../voix-telegram.sh"

# Le topic QG : le siege de l'orchestrateur, pas un salon devine au vol.
CHAT="$QGC_TELEGRAM_CHAT"
THREAD="$QGC_TELEGRAM_THREAD"

# Par l'appli (2.19), donc par le relais reseau quand ADB est coupe.
vibre() { "$ADB" -s "$ADDR" shell am broadcast -n com.poste.pixelgarde/.Recepteur -a com.poste.pixel.VIBRE --es ms "${1:-120}" >/dev/null 2>&1 || true; }

# Ecran, verrou et silence ne se testent plus ici : la lecture auto du garde
# ne part qu'avec un telephone pret a ecouter, et un appui sur « Lire » est
# une demande expresse. Revue du 2026-10-06 : le differe a une seule place
# que ce script posait perdait les rapports suivants, marques lus quand meme.

# L'avis de rapport, en mode silencieux. Demande par USER le 2026-08-30 :
# puisque le rapport ne parle pas tout seul, il faut qu'il se signale et
# qu'un appui suffise a le lire.
# Voir applis/pixelgarde/src/com/poste/pixelgarde/Avis.java.
#
# Le nettoyage n'est pas de la coquetterie. `adb shell` recolle les arguments
# avec des espaces et les redonne a un shell distant : une apostrophe, un
# retour a la ligne ou un $ dans le resume casserait la commande, ou pire, y
# ferait passer autre chose. Le texte devient donc une ligne unique, sans
# metacaractere, bornee a 180 caracteres, entouree de guillemets simples.
sans_danger() {
  printf '%s' "$1" | tr '\n\r\t' '   ' \
    | sed "s/'/\xe2\x80\x99/g; s/\"/\xe2\x80\x9d/g; s/[\\\`\$&;|<>()]//g" \
    | cut -c1-180
}

avis() {
  local f t x
  f="$1"; t="$(sans_danger "${2:-}")"; x="$(sans_danger "${3:-}")"
  [ -n "$t" ] || t="Rapport en attente"
  "$ADB" -s "$ADDR" shell "am broadcast -n com.poste.pixelgarde/.Recepteur \
    -a com.poste.pixel.AVIS --es fichier '$f' --es titre '$t' --es texte '$x'" \
    >/dev/null 2>&1 || true
}

TOKEN="$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$ENV" | cut -d= -f2-)"
[ -n "$TOKEN" ] || { echo "pas de TELEGRAM_BOT_TOKEN dans $ENV" >&2; exit 1; }

# Un seul lecteur a la fois. Le digest passe par un LLM et prend une dizaine
# de secondes : sans ce verrou, la lecture auto du garde et un appui de USER
# lisaient le meme lot en parallele, et USER recevait tout en double.
exec 9>"$PIXEL_TMP/qg-rapport.lock"
flock -n 9 || { echo "lecture deja en cours, appui ignore" >&2; exit 0; }

# QG_ID cible UN rapport precis : c'est le cas normal depuis le 2026-08-29, ou
# chaque rapport a son propre bouton dans le menu de la pastille. Sans lui, on
# retombe sur l'ancien comportement, qui prend toute la file.
CIBLE_ID="${QG_ID:-}"
IDS="$("$FILE" ids 2>/dev/null || true)"
if [ -n "$CIBLE_ID" ]; then
  # Le rapport a pu etre lu entretemps, par la lecture auto ou par un autre
  # appui : le menu de la pastille date d'au plus une minute.
  # Les ids sortent un par ligne : sans cette mise a plat, le motif « espace id
  # espace » ne matchait jamais et tout appui repartait en « deja lu ».
  # Rejeu depuis l'historique du menu (2026-10-21) : le rapport est deja lu,
  # il n'est plus dans la file, et on le rejoue tel quel.
  if [ "${QG_REJEU:-0}" = "1" ]; then
    IDS="$CIBLE_ID"
  else
  case " $(printf '%s' "$IDS" | tr '\n' ' ') " in
    *" $CIBLE_ID "*) IDS="$CIBLE_ID" ;;
    *) vibre 60
       # Le garde a pose LECTURE en lancant ce script : rien ne sera lu.
       "$LECTURE" poser LIBRE >/dev/null 2>&1 || true
       echo "rapport $CIBLE_ID deja lu ou disparu" >&2
       exit 0 ;;
  esac
  fi
fi
if [ -z "$IDS" ]; then
  vibre 60
  curl -sS -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
    -d chat_id="$CHAT" -d message_thread_id="$THREAD" \
    --data-urlencode text="Rien en attente." >/dev/null
  exit 0
fi

vibre 120
if [ -n "$CIBLE_ID" ]; then
  # Le rapport RESUME, pas son texte brut. USER a tranche deux fois le
  # 2026-08-29 : d'abord un rapport par sujet et non plus un digest de trois
  # chantiers (le detail et le ton de chaque sujet y disparaissaient), puis
  # trois phrases et non le brut (« ca me fait des grands rapports comme ca, ca
  # va pas du tout »). Un rapport = un sujet, trois phrases, a lire comme a
  # entendre. Le texte entier reste en base pour qui veut le detail.
  TXT="$("$FILE" voix "$CIBLE_ID")"
  [ -n "$TXT" ] || TXT="$("$FILE" texte "$CIBLE_ID")"
  N=1
  SUJETS="$("$FILE" menu 2>/dev/null | awk -F'\t' -v i="$CIBLE_ID" '$1==i{print $2}')"
else
  # Sans id : toute la file en une synthese. Ne reste que pour un appel manuel.
  TXT="$("$FILE" digest)"
  # Les ids sont RELUS ici, apres le digest, et pas avant. Le digest interroge
  # la file au moment ou il tourne : un rapport depose pendant ses quinze
  # secondes y figure donc deja. Le marquer lu avec les autres est le seul moyen
  # qu'il ne reparte pas au tour suivant (doublons du 2026-08-27).
  IDS="$("$FILE" ids 2>/dev/null || true)"
  N="$(printf '%s\n' "$IDS" | wc -l | tr -d ' ')"
  SUJETS="$("$FILE" sujets 2>/dev/null || true)"
fi
TITRE="$(printf '%s' "$TXT" | head -1)"
# Ecrit et dit sont desormais le MEME texte : le resume passe par un cache, donc
# le demander deux fois ne coute rien. Seul le digest sans id garde son brut.
TXT_VOIX="$TXT"
CACHE="$HOME/.hermes/qg-voix"
# Le nom du topic ouvre la voix (USER, 2026-10-03 : « je ne sais pas de quel
# rapport il parle »). Relu maintenant, pas a l'arrivee du rapport : si USER a
# renomme le topic depuis, la voix fabriquee d'avance porte l'ancien nom, on
# la jette et on la refait.
if [ -n "$CIBLE_ID" ]; then
  SUJET_NOM="$("$FILE" sujet "$CIBLE_ID" 2>/dev/null || true)"
  [ -n "$SUJET_NOM" ] && TXT_VOIX="Rapport $SUJET_NOM. $TXT"
  if [ -s "$CACHE/$CIBLE_ID.mp3" ] \
     && [ "$(cat "$CACHE/$CIBLE_ID.nom" 2>/dev/null)" != "$SUJET_NOM" ]; then
    rm -f "${CACHE:?}/$CIBLE_ID.mp3" "${CACHE:?}/$CIBLE_ID.ogg" "${CACHE:?}/$CIBLE_ID.pousse"
  fi
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Les boutons devines a la prefabrication (qg-prevoix.sh) : leur ligne part
# avec la lecture. Leurs libelles restent dans $CACHE/<id>.libelles, ou le
# garde les cherche avec l'id que le bouton porte. Bug du 2026-10-06 : ils
# etaient recopies dans /tmp/pixel-voix-choix, que le rapport suivant
# ecrasait avant que USER ait touche le bouton du premier.
CHOIX_RAP=()
if [ -n "$CIBLE_ID" ] && [ -s "$CACHE/$CIBLE_ID.choix" ]; then
  MOTS_RAP="$(head -1 "$CACHE/$CIBLE_ID.choix" | tr -d "'\n")"
  CHOIX_RAP=(--es choix "'$MOTS_RAP'")
elif printf '%s' "$TXT" | grep -qi "rien à décider"; then
  # Boutons non calcules : le telephone montrerait Oui Non Detail. Rien a
  # valider ici, Oui n'a pas de sens (2026-10-03, 10:41).
  CHOIX_RAP=(--es choix "'detail:Détail'")
fi
echo "$(date '+%F %T') boutons ${CIBLE_ID:-?} : ${CHOIX_RAP[*]:-aucun, Detail seul}" >> "$HOME/.hermes/logs/rapport.log"

# La voix : la paire du cache si elle est faite d'avance, sinon on fabrique,
# comme avant : le mp3 du telephone ici, la bulle Telegram par
# bin/voix-telegram.sh.
if [ -n "$CIBLE_ID" ] && [ -s "$CACHE/$CIBLE_ID.ogg" ] && [ -s "$CACHE/$CIBLE_ID.mp3" ]; then
  cp "$CACHE/$CIBLE_ID.mp3" "$TMP/r.mp3"; cp "$CACHE/$CIBLE_ID.ogg" "$TMP/r.ogg"
fi
VOIX_OK=0
if { [ -s "$TMP/r.ogg" ] && [ -s "$TMP/r.mp3" ]; } \
   || { edge-tts --voice "$VOIX" --rate="$DEBIT" \
        --text "$TXT_VOIX" --write-media "$TMP/r.mp3" >/dev/null 2>&1 \
      && [ -s "$TMP/r.mp3" ] \
      && printf '%s' "$TXT_VOIX" | "$VOIX_TG" "$TMP/r.ogg" \
      && [ -s "$TMP/r.ogg" ]; }; then
  VOIX_OK=1
fi

# Le telephone le DIT a voix haute, avant tout appel a Telegram : l'appui de
# USER n'attend ni le reseau ni le texte. VOIXDIRE joue le fichier sans ouvrir
# de conversation ; dans une conversation vocale, VOIXREP le dit puis rend la
# parole a USER (etat pret), et le standard apprend ce qui a ete dit : le
# « oui » qui suit vise ce topic.
#
# `rapport` fait revenir le telephone : rapportfini a la fin du son, ou
# rapportcoupe s'il est interrompu. C'est la fin du son qui marque le rapport
# lu, plus ce script. `auto` dit au telephone que personne n'a rien demande :
# s'il parle deja, il refuse (rapportrefuse) au lieu de couper.
LECTURE_LANCEE=0
DANS_CONV=0
if [ -n "$CIBLE_ID" ] && [ "${QG_SANS_VOIX:-0}" != "1" ]; then
  POUSSE=0
  if [ "$VOIX_OK" = "1" ] && [ ! -e "$PIXEL_TMP/pixel-stop" ]; then
    POUSSE=1
    # Rejeu : le telephone a pu effacer son fichier, on repousse (100 Ko).
    # Sauf s'il y est deja : le push coute ~2 s, l'attente que USER a signalee.
    SUR_TEL=0
    if [ "${QG_REJEU:-0}" = "1" ] && [ -e "$CACHE/$CIBLE_ID.pousse" ] \
       && "$ADB" -s "$ADDR" shell "test -s $TEL_VOIX/qg-pre-$CIBLE_ID.mp3" >/dev/null 2>&1; then
      SUR_TEL=1
    fi
    if [ "$SUR_TEL" = "0" ] && { [ ! -e "$CACHE/$CIBLE_ID.pousse" ] || [ "${QG_REJEU:-0}" = "1" ]; }; then
      "$ADB" -s "$ADDR" push "$TMP/r.mp3" "$TEL_VOIX/qg-pre-$CIBLE_ID.mp3" >/dev/null 2>&1 || POUSSE=0
    fi
  fi
  # Mains libres : la phrase « Tu peux dire : ... » que le telephone joue
  # apres le rapport, avant d'ouvrir le micro (qg-dire-choix.sh). En fond : le
  # rapport dure plus longtemps qu'elle ne met a se fabriquer et se pousser.
  if [ "$POUSSE" = "1" ] && [ "$(jq -r '.mains_libres // false' "$HOME/.hermes/qg-config.json" 2>/dev/null)" = true ]; then
    ADB="$ADB" "$ICI/../qg-dire-choix.sh" "$CIBLE_ID" "$ADDR" </dev/null >/dev/null 2>&1 &
  fi
  ACTION=VOIXDIRE
  [ "${QG_DANS_CONVERSATION:-0}" = "1" ] && ACTION=VOIXREP
  AUTO=()
  [ "${QG_AUTO:-0}" = "1" ] && AUTO=(--ez auto true)
  if [ "$POUSSE" = "1" ] && [ ! -e "$PIXEL_TMP/pixel-stop" ]; then
    [ "$ACTION" = "VOIXREP" ] && echo "travaille" > "$PIXEL_TMP/pixel-voix-etat"
    if "$ADB" -s "$ADDR" shell am start-foreground-service \
         -n com.poste.pixelgarde/.Voix -a "com.poste.pixel.$ACTION" \
         --es fichier "qg-pre-$CIBLE_ID.mp3" --es rapport "$CIBLE_ID" \
         "${AUTO[@]}" "${CHOIX_RAP[@]}" >/dev/null 2>&1; then
      LECTURE_LANCEE=1
      echo "rapport $CIBLE_ID envoye au telephone ($ACTION)" >&2
      if [ "$ACTION" = "VOIXREP" ]; then
        DANS_CONV=1
        "$STANDARD" entendu "${SUJETS:-un topic}" "$TXT_VOIX" >/dev/null 2>&1 || true
      fi
    else
      [ "$ACTION" = "VOIXREP" ] && echo "pret" > "$PIXEL_TMP/pixel-voix-etat"
    fi
  fi
  if [ "$LECTURE_LANCEE" = "0" ]; then
    # Rien ne joue : la parole est rendue, et le rapport reste nouveau. Le
    # garde le representera au tour suivant.
    "$LECTURE" poser LIBRE >/dev/null 2>&1 || true
    echo "lecture impossible : le rapport $CIBLE_ID reste en file" >&2
  fi
fi

# Rejeu depuis l'historique (USER, 2026-10-22) : la lecture est lancee, on s'arrete
# la. Le texte et la voix sont deja au QG, les reposter ajoutait des secondes
# et des doublons dans le salon.
if [ "${QG_REJEU:-0}" = "1" ] && [ "$LECTURE_LANCEE" = "1" ]; then
  echo "rejeu du rapport $CIBLE_ID lance, rien reposte au QG" >&2
  exit 0
fi

# Les reponses de l'API partaient a /dev/null : un refus 400 laissait croire a
# une livraison reussie, et les rapports etaient marques lus sans que USER ait
# rien recu. Chaque appel dit maintenant s'il a abouti.
dire() {
  local rep; rep="$(cat)"
  case "$rep" in
    *'"ok":true'*)
      echo "Telegram ok ($1) message_id=$(printf '%s' "$rep" | grep -o '"message_id":[0-9]*' | head -1 | cut -d: -f2)" >&2
      return 0 ;;
    *) echo "Telegram a refuse ($1) : $(printf '%s' "$rep" | head -c 300)" >&2; return 1 ;;
  esac
}

# Le texte d'abord : si la synthese echoue, USER a quand meme son rapport.
# L'ordre inverse laissait un audio orphelin quand l'API repondait 400.
TEXTE_OK=1
# Le texte d'un rapport part de hote-1 (qg-facteur, toutes les 30 s), meme sans
# telephone. Deja poste : on ne le redouble pas, la bulle ne fait que la voix.
QG_DB="${QG_DB:-$HOME/.hermes/qg.db}"
DEJA_POSTE=0
if [ -n "$CIBLE_ID" ] && [ -n "$(sqlite3 "$QG_DB" "select notifie from attente where id=$CIBLE_ID and notifie is not null" 2>/dev/null)" ]; then
  DEJA_POSTE=1
  echo "texte deja poste par le facteur, voix seule" >&2
fi
[ "$DEJA_POSTE" = 1 ] || { curl -sS -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
  -d chat_id="$CHAT" -d message_thread_id="$THREAD" \
  --data-urlencode text="$(
    if [ "$N" -gt 1 ]; then
      printf 'Rapports groupes (%s)%s' "$N" "${SUJETS:+ : $SUJETS}"
    else
      printf 'Rapport%s' "${SUJETS:+ $SUJETS}"
    fi )
$TXT" | dire sendMessage || TEXTE_OK=0; }
if [ "$DEJA_POSTE" = 0 ] && [ "$TEXTE_OK" = 1 ]; then
  for ID in $IDS; do
    sqlite3 "$QG_DB" "update attente set notifie=cast(strftime('%s','now') as real) where id=$ID and notifie is null" 2>/dev/null || true
  done
fi

# QG_SANS_VOIX=1 est pose par le garde quand la lecture auto part en mode
# silencieux, ou pendant une conversation vocale. Il coupe UNIQUEMENT la lecture
# a haute voix sur le telephone. La bulle vocale, elle, part dans le QG dans
# tous les cas : USER veut retrouver l'audio dans le salon et l'ecouter quand il
# le decide, sans que le telephone se mette a parler tout seul.
# Deux regressions du meme genre sont deja passees par la : le 2026-08-28 le
# mode silencieux coupait le texte, et USER n'a plus rien recu de la journee ; le
# 2026-08-30 il coupait la bulle vocale. La regle tient en une phrase : ce mode
# ne retire jamais un contenu du QG, il empeche seulement le telephone de parler.
# Un appui sur le bouton Lire ne pose jamais ce drapeau : demander le rapport,
# c'est demander a l'entendre, meme en silencieux.
if [ "$VOIX_OK" = "1" ]; then
  curl -sS -X POST "https://api.telegram.org/bot$TOKEN/sendVoice" \
    -F chat_id="$CHAT" -F message_thread_id="$THREAD" \
    -F voice="@$TMP/r.ogg" | dire sendVoice || true
  echo "voix envoyee ($(stat -c%s "$TMP/r.ogg") octets)" >&2

  if [ "${QG_SANS_VOIX:-0}" = "1" ]; then
    # Le telephone se tait, mais il previent. USER a rapproche les deux lui-meme
    # le 2026-08-30 : « comme si j'avais desactive lire a haute voix, ca met
    # une notification ». Le mp3 part quand meme sur l'appareil, sinon l'appui
    # sur l'avis n'aurait rien a jouer.
    NOM="qg-$(date +%s%3N).mp3"
    if "$ADB" -s "$ADDR" push "$TMP/r.mp3" "$TEL_VOIX/$NOM" >/dev/null 2>&1; then
      "$ADB" -s "$ADDR" shell "ls -1t $TEL_VOIX/qg-*.mp3 2>/dev/null | tail -n +11 | xargs -r rm -f" >/dev/null 2>&1 || true
      avis "$NOM" "$SUJETS" "$TXT_VOIX"
    fi
    echo "sans lecture : la bulle vocale est dans le QG, le telephone se tait" >&2
  fi
else
  echo "synthese vocale indisponible, texte seul" >&2
fi

# Rien n'est marque lu si le texte n'est jamais parti : un rapport perdu doit
# rester en file et se representer au tour suivant, pas disparaitre en silence.
if [ "$TEXTE_OK" = "0" ]; then
  echo "rien marque lu : la livraison a echoue" >&2
  exit 1
fi
if [ -n "$CIBLE_ID" ] && [ "${QG_SANS_VOIX:-0}" != "1" ]; then
  # Mode voix : le rapport reste nouveau tant que le telephone n'a pas dit
  # rapportfini. Le garde le marquera entendu a ce moment-la. Les fichiers du
  # cache restent : un rapport coupe se relit sans refaire la synthese.
  vibre 200
  echo "rapport $CIBLE_ID transmis, en attente de la fin de lecture"
  exit 0
fi
if [ -n "$CIBLE_ID" ]; then
  # Mode silencieux : le texte et la bulle sont au QG, c'est la que USER le
  # lit. Lu et ecoute maintenant, puis la courte fenetre avant le suivant.
  "$FILE" entendu "$CIBLE_ID" >/dev/null 2>&1 || true
  "$LECTURE" poser FENETRE "$CIBLE_ID" >/dev/null 2>&1 || true
  # Les libelles et le choix restent : les boutons du rapport servent encore.
  rm -f "${CACHE:?}/$CIBLE_ID.mp3" "${CACHE:?}/$CIBLE_ID.ogg" "${CACHE:?}/$CIBLE_ID.pousse" "${CACHE:?}/$CIBLE_ID.txt" "${CACHE:?}/$CIBLE_ID.nom"
  "$ADB" -s "$ADDR" shell "rm -f $TEL_VOIX/qg-pre-$CIBLE_ID.mp3" >/dev/null 2>&1 || true
else
  # Le digest sans id, appel manuel : tout le lot est lu d'un coup.
  for ID in $IDS; do "$FILE" lu "$ID" >/dev/null; done
fi
vibre 200
echo "$N rapport(s) lus : $TITRE"
