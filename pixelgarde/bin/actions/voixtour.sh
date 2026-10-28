#!/usr/bin/env bash
# Un tour de conversation vocale : le telephone a parle, on lui repond.
#
# Le circuit complet, declenche par la commande `voixtour` que Voix.java depose
# des qu'il detecte la fin d'une phrase :
#
#   1. on ramene le WAV du telephone            (adb pull)
#   2. on le transcrit                          (Groq whisper turbo, ~0,5 s ;
#                                                whisper local en secours)
#   2b. on accuse reception a voix haute        (Gemini Flash + edge-tts, en
#                                                parallele du QG)
#   3. le standard comprend et propose         (qg-standard.py : un appel au
#                                                routeur 8010, sans outil, ~4 s)
#   4. on laisse la trace ecrite sur Telegram   (USER relit, ou reprend au clavier)
#   5. on synthetise et on repousse             (edge-tts, adb push, VOIXREP)
#
# Depuis le 2026-10-01, la voix ne passe plus par la session Hermes du 2923.
# Elle y coutait 51 s de mediane par tour : Opus avec tous ses outils, pour un
# travail qui n'est que de la comprehension. Le standard lit le contexte
# d'avance, propose, et envoie lui-meme au topic quand USER dit oui. Le prix :
# un tour vocal n'entre plus dans la memoire de la session ecrite du QG. La
# trace Telegram reste, c'est elle que USER relit.
set -uo pipefail

ADB="${ADB:-adb}"
ADDR="${1:-$("$ADB" devices | awk '/device$/{print $1; exit}')}"
ADDR="${ADDR:-${PIXEL_ADDR:-__PIXEL_IP__:5555}}"   # sans ADB : l'adresse fixe
VOIX_TEL="/sdcard/Android/data/com.poste.pixelgarde/files/voix"
PIXEL_TMP="${PIXEL_TMP:-/tmp}"
MARQUEUR="$PIXEL_TMP/pixel-voix"
QG_BIN="${QG_BIN:-$HOME/Bureau/Projets/contexte/bin/qg}"
LECTURE="$(dirname "$0")/../qg-lecture"
# L'id de la bulle de ce tour : le telephone le renvoie avec chaque bouton
# (voixb1:t1759...), qg-standard.py range les libelles sous ce nom. Un id par
# bulle : le tour suivant n'ecrase plus les boutons de la precedente.
POUR="t$(date +%s)"
export VOIX_POUR="$POUR"
# Arret d'urgence (pixel-stop, pose par le garde) : plus rien ne part vers le
# telephone, meme d'un tour deja lance. Revue du 2026-10-06 : un tour en vol
# rejouait sa reponse apres l'arret.
arrete() { [ -e "$PIXEL_TMP/pixel-stop" ]; }
HA="$HOME/.hermes/hermes-agent"
PY="$HA/venv/bin/python"
ENV="$HOME/.hermes/.env"
CHAT="__QG_CHAT__"
THREAD="2923"
VOIX_TTS="fr-FR-RemyMultilingualNeural"
DEBIT="+8%"
# Au-dela, la synthese dure plus longtemps que l'attention de qui ecoute. Le
# texte complet part sur Telegram : la voix n'est pas la seule copie.
LIMITE_TTS=1400

TMP="$(mktemp -d)"
# Les envois Telegram et l'accuse tournent en arriere-plan : on les attend
# avant d'effacer le dossier qu'ils utilisent. `fini` dit a l'accuse que ce
# n'est plus la peine de parler.
trap 'touch "$TMP/fini" 2>/dev/null; wait; rm -rf "${TMP:?}"' EXIT

# Chaque ligne porte le temps ecoule depuis le debut du tour : c'est ce qui
# permet de mesurer ou part la latence sans rien instrumenter de plus.
T0="$(date +%s%3N)"
JOURNAL="$HOME/.hermes/logs/voixtour.log"
journal() {
  local l="voixtour +$(( $(date +%s%3N) - T0 ))ms : $*"
  echo "$l" >&2
  echo "$(date '+%F %T') $l" >> "$JOURNAL" 2>/dev/null || true
}

# La conversation a-t-elle ete coupee entre le depot du tour et maintenant ?
# Sans ce controle, une reponse arriverait apres un raccroche, et le service la
# jouerait au prochain reveil, hors contexte.
[ -e "$MARQUEUR" ] || { journal "conversation fermee, tour abandonne"; exit 0; }
arrete && { journal "arret d'urgence, tour abandonne"; exit 0; }

# La parole est a ce tour : la lecture auto des rapports attend sa fin
# (voixpret, envoiconfirme, voixfin). Un bouton l'a deja posee pour sa bulle.
[ "$("$LECTURE" etat 2>/dev/null)" = "TOUR" ] || "$LECTURE" poser TOUR "$POUR" >/dev/null 2>&1

# Traitement en cours : la pastille passe sur ce sous-etat des ici, avant
# meme le pull du WAV, pour que USER voie tout de suite que son tour est parti.
echo "travaille" > "$PIXEL_TMP/pixel-voix-etat"

# Rend la parole a USER sans rien dire : le service reprend l'ecoute. Le
# sous-etat repasse a "ecoute" ici, sur CHAQUE chemin d'echec : sans quoi la
# pastille resterait bloquee sur "travaille" alors que le micro est deja
# rouvert.
rendre_micro() {
  echo "ecoute" > "$PIXEL_TMP/pixel-voix-etat"
  arrete && return 0
  "$ADB" -s "$ADDR" shell am start-foreground-service \
    -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIXREP >/dev/null 2>&1
}

# Bouton « Oui » ou « Detail » touche au-dessus de la bulle (voixoui.sh,
# voixdetail.sh) : le mot arrive deja ecrit. Ni son a ramener, ni
# transcription, ni accuse : le tour part droit au standard.
if [ -n "${VOIX_TEXTE:-}" ]; then
  DIT="$VOIX_TEXTE"
  # Bouton d'un rapport : le garde passe son id (VOIX_RAPPORT), lu sur le
  # bouton lui-meme. Le standard vise ce rapport, et aucun autre.
  [ -n "${VOIX_RAPPORT:-}" ] && export VOIX_RAPPORT
  journal "bouton : $DIT${VOIX_RAPPORT:+ (rapport $VOIX_RAPPORT)}"
else
# ----------------------------------------------------------------- 1. le son

# Le relais reseau d'abord : l'appli y poste chaque tour par HTTPS. C'est la
# seule voie quand ADB est coupe (Tailscale ou debogage sans fil eteints, 4G).
# Le nom porte l'heure de fin du tour (ms, horloge du telephone) : on ne
# prend qu'un tour fini moins de 15 s avant cet appui. Le 2026-10-03 a 14h43,
# un tour de 9 s arrivait 1 instant apres l'appui (logcat plus rapide que
# l'envoi) et le script avait pris le tour d'avant, presque vide.
RECUS="$HOME/.hermes/creeper-relais/recus"
recu_frais() {
  local f n
  for f in $(find "$RECUS" -maxdepth 1 -name 'tour-*.wav' 2>/dev/null | sort -r); do
    n="${f##*/tour-}"; n="${n%.wav}"
    grep -qx "${f##*/}" "$RECUS/.pris" 2>/dev/null && continue   # deja ramene par ADB
    [ "$n" -ge $(( T0 - 15000 )) ] 2>/dev/null && { echo "$f"; return; }
  done
}
RECU=""
ADB_OK=0
timeout 4 "$ADB" -s "$ADDR" shell true >/dev/null 2>&1 && ADB_OK=1
# ADB vivant : 2 s pour le relais, puis adb pull. ADB mort : 20 s, le temps
# qu'un long tour monte en 4G.
ATTENTE=$(( ADB_OK ? 10 : 100 ))
for _ in $(seq 1 $ATTENTE); do
  RECU="$(recu_frais)"
  [ -n "$RECU" ] && break
  sleep 0.2
done
if [ -n "$RECU" ]; then
  mv -f "$RECU" "$TMP/tour.wav"
  journal "son recu par le relais ($(basename "$RECU"))"
  # Les tours plus vieux ne serviront plus. Le meme tour reste sur le
  # telephone : on l'efface si ADB passe.
  find "$RECUS" -maxdepth 1 -name 'tour-*.wav' ! -newer "$TMP/tour.wav" -delete 2>/dev/null
  [ "$ADB_OK" = 1 ] && timeout 3 "$ADB" -s "$ADDR" shell rm -f "$VOIX_TEL/$(basename "$RECU")" >/dev/null 2>&1
elif [ "$ADB_OK" = 0 ]; then
  journal "aucun tour recu par le relais"; rendre_micro; exit 0
else
TOUR="$("$ADB" -s "$ADDR" shell "ls -1 $VOIX_TEL/tour-*.wav 2>/dev/null | tail -1" | tr -d '\r')"
[ -n "$TOUR" ] || { journal "aucun tour a ramener"; rendre_micro; exit 0; }
"$ADB" -s "$ADDR" pull "$TOUR" "$TMP/tour.wav" >/dev/null 2>&1 \
  || { journal "pull impossible"; rendre_micro; exit 1; }
# Le telephone n'efface que ses vieux tours au depot suivant. Effacer ici evite
# qu'un lien coupe laisse un tour deja traite se faire rejouer.
"$ADB" -s "$ADDR" shell rm -f "$TOUR" >/dev/null 2>&1
# Sa copie par le relais arrivera peut-etre apres : elle ne doit pas servir
# au tour suivant.
echo "${TOUR##*/}" >> "$RECUS/.pris"; tail -20 "$RECUS/.pris" > "$RECUS/.pris.n" && mv -f "$RECUS/.pris.n" "$RECUS/.pris"
fi

# ------------------------------------------------------------ 2. la parole

journal "son ramene"

# Groq d'abord : 0,3 a 0,6 s, et il ecrit « EntrepriseA » la ou whisper base
# local entendait « Marouel » (mesure du 2026-10-01 : local 3,3 s). Le modele
# turbo, pas large-v3 : le grand modele, lui, entend encore « Marouel ».
GROQ="$(grep -m1 '^GROQ_API_KEY=' "$ENV" | cut -d= -f2-)"
DIT=""
# Mains libres (2026-10-12) : en voiture, la radio ou une chanson anglaise
# entre dans le micro. Forcer le francais ne protege pas (whisper ecrit alors
# du francais sous la chanson) : une 2e transcription, SANS langue imposee,
# part en meme temps et dit quelle langue whisper reconnait. voix-langue.py
# juge plus bas. En parallele : aucune seconde de plus.
MAINS_ML="$(jq -r '.mains_libres // false' "$HOME/.hermes/qg-config.json" 2>/dev/null)"
P_AUTO=""
if [ -n "$GROQ" ] && [ "$MAINS_ML" = true ] && [ -z "${VOIX_TEXTE:-}" ]; then
  curl -sS --max-time 8 https://api.groq.com/openai/v1/audio/transcriptions \
      -H "Authorization: Bearer $GROQ" -F file=@"$TMP/tour.wav" \
      -F model=whisper-large-v3-turbo -F response_format=verbose_json \
      -o "$TMP/auto.json" 2>/dev/null &
  P_AUTO=$!
fi
if [ -n "$GROQ" ]; then
  DIT="$(curl -sS --max-time 8 https://api.groq.com/openai/v1/audio/transcriptions \
      -H "Authorization: Bearer $GROQ" -F file=@"$TMP/tour.wav" \
      -F model=whisper-large-v3-turbo -F language=fr -F response_format=text \
      2>/dev/null | head -c 4000)"
  # Une erreur d'API rend du JSON, pas une phrase : on ne la lit pas comme
  # une transcription.
  case "$DIT" in *'"error"'*) journal "groq refuse : $(printf '%s' "$DIT" | head -c 120)"; DIT="" ;; esac
fi
# Secours : whisper local, plus lent mais sans reseau.
[ -n "${DIT// }" ] || DIT="$("$PY" - "$TMP/tour.wav" <<'PYEOF' 2>/dev/null
import sys, os
sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))
os.environ.setdefault("HERMES_HOME", os.path.expanduser("~/.hermes"))
from tools.transcription_tools import transcribe_audio
r = transcribe_audio(sys.argv[1])
print((r.get("transcript") or "").strip() if r.get("success") else "")
PYEOF
)"
DIT="$(printf '%s' "$DIT" | tr '\n' ' ' | sed 's/^ *//;s/ *$//')"

# Une transcription "vide" ne l'est pas toujours : sur du silence ou du bruit,
# whisper rend une suite de points ou de virgules. Le 2026-08-28, USER a recu un
# « Vin a dit : ... » suivi de dix lignes de points, pour un tour ou personne
# n'avait parle. On juge donc sur le contenu ALPHANUMERIQUE, pas sur la
# longueur : moins de deux caracteres utiles, il ne s'est rien dit.
UTILE="$(printf '%s' "$DIT" | tr -cd '[:alnum:]' | wc -c)"
if [ -z "${DIT// }" ] || [ "$UTILE" -lt 2 ]; then
  journal "rien de compris (utile=$UTILE), on reecoute"
  rendre_micro
  exit 0
fi
# Mains libres : seul le francais de USER passe. Une chanson, la radio, de
# l'anglais en fond : rien ne part, ni au QG ni sur Telegram, le micro attend.
if [ -n "$P_AUTO" ]; then
  wait "$P_AUTO" 2>/dev/null || true
  LIB_ML=""
  ID_ML="$(cut -f1 "$HOME/.hermes/qg-dernier-ecoute" 2>/dev/null || true)"
  [ -n "$ID_ML" ] && [ -s "$HOME/.hermes/qg-voix/$ID_ML.libelles" ] && LIB_ML="$HOME/.hermes/qg-voix/$ID_ML.libelles"
  VERDICT="$(python3 "$(dirname "$0")/../voix-langue.py" "$DIT" "$TMP/auto.json" $LIB_ML 2>/dev/null || echo ok)"
  if [ "$VERDICT" != ok ]; then
    journal "ignore ($VERDICT) : $DIT"
    # Micro EN ATTENTE, pas rouvert : sous une radio qui ne s'arrete pas, le
    # rouvrir referait un tour rejete toutes les 10 s, sans fin. USER le rouvre
    # d'un appui (bulle, volant), comme apres « pause ».
    echo "ecoute" > "$PIXEL_TMP/pixel-voix-etat"
    arrete || "$ADB" -s "$ADDR" shell am start-foreground-service -n com.poste.pixelgarde/.Voix \
      -a com.poste.pixel.VOIXREP --ez attendre true >/dev/null 2>&1
    exit 0
  fi
fi
journal "entendu : $DIT"
# Mains libres (2026-10-12) : 3 ordres courts pilotent la voix sans passer
# par le standard. 4 mots au plus : « stop » au milieu d'une vraie phrase
# reste une phrase. Oui, non, detail passent au standard, comme les boutons.
if [ "$(jq -r '.mains_libres // false' "$HOME/.hermes/qg-config.json" 2>/dev/null)" = true ]; then
  ORDRE="$(printf '%s' "$DIT" | tr '[:upper:]' '[:lower:]' | sed 's/[[:punct:]]//g; s/  */ /g; s/^ //; s/ $//')"
  if [ "$(printf '%s' "$ORDRE" | wc -w)" -le 4 ]; then
    case "$ORDRE" in
      fin|stop|termine|terminé|raccroche|"au revoir"|"cest fini"|"fin de la conversation")
        journal "ordre vocal : fin"
        "$(dirname "$0")/voixraccrocher.sh" "$ADDR"
        exit 0 ;;
      pause|attends|"attends un peu"|"mets en pause"|silence)
        journal "ordre vocal : pause, micro en attente"
        echo "ecoute" > "$PIXEL_TMP/pixel-voix-etat"
        "$ADB" -s "$ADDR" shell am start-foreground-service -n com.poste.pixelgarde/.Voix \
          -a com.poste.pixel.VOIXREP --ez attendre true >/dev/null 2>&1
        exit 0 ;;
      relis|répète|repete|redis|"relis le"|"répète sil te plaît"|"tu peux répéter")
        journal "ordre vocal : relis"
        "$ADB" -s "$ADDR" shell am start-foreground-service -n com.poste.pixelgarde/.Voix \
          -a com.poste.pixel.VOIXREJOUER >/dev/null 2>&1
        exit 0 ;;
    esac
  fi
fi
fi

# La transcription part MAINTENANT, avant que le QG travaille. C'est le seul
# signal qui dit a USER que sa phrase est passee : sans lui, il a 30 a 60 s de
# silence total et il croit que le bouton n'a rien fait.
# En arriere-plan : l'envoi prend 0,3 a 1 s, le QG n'a pas a l'attendre.
TOKEN="$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$ENV" | cut -d= -f2-)"
# Ecrire (VOIX_MODE pose par ecrire.sh) : rien sur Telegram, USER ne veut pas ses conversations au QG.
if [ -n "$TOKEN" ] && [ -z "${VOIX_MODE:-}" ]; then
  curl -sS --max-time 20 -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
    -d chat_id="$CHAT" -d message_thread_id="$THREAD" \
    --data-urlencode text="$( [ -n "${VOIX_TEXTE:-}" ] && echo "👆 Vin a touché" || echo "🎙 Vin a dit" ) : $DIT" >/dev/null 2>&1 &
fi

# ------------------------------------------------------ 2b. l'accuse vocal
#
# Le QG met 15 a 60 s (mediane 51 s sur 19 tours, mesure du 2026-10-01). Sans
# rien entendre pendant ce temps, USER croit que rien ne s'est passe. Un modele
# rapide dit donc tout de suite qu'il a compris le sujet, en une phrase, sans
# repondre au fond. Il tourne EN PARALLELE du QG : il ne lui retire rien.
# Il se tait si la vraie reponse est deja la (`fini`) ou si USER a raccroche.
accuser() {
  local cle phrase corps
  cle="$(grep -m1 '^OPENROUTER_API_KEY=' "$ENV" | cut -d= -f2-)"
  [ -n "$cle" ] || return 0
  corps="$(python3 -c 'import json,sys
print(json.dumps({"model": "google/gemini-2.5-flash", "max_tokens": 60,
  "temperature": 0.3, "reasoning": {"enabled": False},
  "messages": [{"role": "system", "content":
    "Tu es le standardiste vocal de USER. Il vient de parler. Un autre agent "
    "lui repondra sur le fond dans une minute. Toi, tu accuses reception en "
    "UNE phrase parlee de 10 mots au plus, en francais, qui montre que tu as "
    "compris le sujet. Jamais de reponse au fond, jamais de question, jamais "
    "de chiffre, jamais de promesse de resultat. Ne dis jamais que tu lances "
    "ou que tu fais une tache : rien ne part sans le oui de USER. Ton seul "
    "verbe d action permis est regarder. Jamais lancer, demander, envoyer, "
    "corriger, transmettre. Exemples : "
    "Compris, je regarde ou en est EntrepriseA. / "
    "D accord, l export Watsons de septembre, je regarde ca."},
   {"role": "user", "content": sys.argv[1]}]}))' "$DIT")"
  phrase="$(printf '%s' "$corps" | curl -sS --max-time 6 \
      https://openrouter.ai/api/v1/chat/completions \
      -H "Authorization: Bearer $cle" -H "Content-Type: application/json" \
      --data-binary @- 2>/dev/null \
    | python3 -c 'import json,sys
try: print((json.load(sys.stdin)["choices"][0]["message"]["content"] or "").strip())
except Exception: print("")' | head -c 200)"
  [ -n "${phrase// }" ] || { journal "accuse : rien rendu"; return 0; }
  [ -e "$TMP/fini" ] && return 0
  edge-tts --voice "$VOIX_TTS" --rate="$DEBIT" --text "$phrase" \
      --write-media "$TMP/acc.mp3" >/dev/null 2>&1 && [ -s "$TMP/acc.mp3" ] || return 0
  # Le standard repond en 4 s environ, et VOIXREP coupe net un accuse en cours
  # de lecture. L'accuse attend donc 4,5 s apres le debut du tour : il ne parle
  # que si la vraie reponse traine. Sinon il se tait, et USER n'entend qu'une voix.
  while [ $(( $(date +%s%3N) - T0 )) -lt 4500 ] && [ ! -e "$TMP/fini" ]; do sleep 0.1; done
  if [ -e "$TMP/fini" ] || [ ! -e "$MARQUEUR" ] || arrete; then return 0; fi
  local nom="acc-$(date +%s%3N).mp3"
  "$ADB" -s "$ADDR" push "$TMP/acc.mp3" "$VOIX_TEL/$nom" >/dev/null 2>&1 || return 0
  "$ADB" -s "$ADDR" shell am start-foreground-service \
    -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIXATTENTE \
    --es fichier "$nom" >/dev/null 2>&1
  journal "accuse joue : $phrase"
}
# Seance du Conseil en cours (bouton « Conseil », actions/conseil.sh) : la
# reponse vient du Conseil, pas du standard. Pas d'accuse « je regarde » : le
# Conseil repond en quelques secondes, et l'accuse parlerait de travail lance.
# Un marqueur de plus de 30 min est une seance abandonnee (bulle fermee sans
# raccrocher) : on la clot et la phrase repart au standard.
# Le marqueur de seance se deplace pour les essais (tests/creeper-file.sh) :
# une seance ouverte sur hote-1 ne doit pas aspirer un tour de test.
CONSEIL_MARQUE="${QG_CONSEIL_MARQUE:-/tmp/pixel-conseil}"
CONSEIL=""
if [ -e "$CONSEIL_MARQUE" ]; then
  if [ $(( $(date +%s) - $(stat -c %Y "$CONSEIL_MARQUE") )) -lt 1800 ]; then
    CONSEIL=1
  else
    python3 "$HOME/Bureau/Projets/contexte/bin/qg/qg-conseil.py" clore 2>>"$HOME/.hermes/logs/qg-conseil.log"
  fi
fi
[ -n "$CONSEIL" ] || [ -n "${VOIX_TEXTE:-}" ] || accuser &

# -------------------------------------------------------- 3. le standard

# Tout le standard vit dans qg-standard.py : contexte, appel, proposition en
# attente, envoi au topic sur le oui. Ici on ne fait que lui passer la phrase.
STANDARD="$QG_BIN/qg-standard.py"
if [ -n "$CONSEIL" ]; then
  REP="$(python3 "$HOME/Bureau/Projets/contexte/bin/qg/qg-conseil.py" tour "$DIT" 2>>"$HOME/.hermes/logs/qg-conseil.log")"
  journal "conseil : $( [ -e "$CONSEIL_MARQUE" ] && echo en cours || echo seance finie )"
else
REP="$(python3 "$STANDARD" tour "$DIT" 2>>"$HOME/.hermes/logs/qg-standard.log")"
fi
# Premiere ligne « @compte@ » : le standard a propose un envoi, le telephone
# affichera le compte a rebours. Le drapeau voyage avec la reponse : le
# fichier /tmp d'avant se perdait (3 propositions sur 11, le 2026-10-01).
COMPTE=()
case "$REP" in
  "@compte@"*) COMPTE=(--ei compte 1); REP="${REP#@compte@}"; REP="${REP#$'\n'}" ;;
esac
# Premiere ligne « @choix@oui:Oui|b1:Et EntrepriseA ? » : apres la lecture, le
# telephone montre ces reponses quelques secondes au-dessus de la bulle.
# adb shell repasse la ligne a un shell distant : sans les apostrophes, la
# barre ferait un tube et l'espace couperait l'argument. Le standard retire
# les apostrophes des libelles.
CHOIX=()
case "$REP" in
  "@choix@"*) MOTS="${REP#@choix@}"; MOTS="${MOTS%%$'\n'*}"
              CHOIX=(--es choix "'$MOTS'"); REP="${REP#*$'\n'}" ;;
esac

if [ -z "${REP// }" ]; then
  journal "le standard n a rien rendu"
  if [ -n "${VOIX_ECRAN:-}" ]; then
    printf 'Le standard ne répond pas. Réessaie.\n' > "$TMP/ecrire-rep.txt"
    "$ADB" -s "$ADDR" push "$TMP/ecrire-rep.txt" \
      "/sdcard/Android/data/com.poste.pixelgarde/files/ecrire-rep.txt" >/dev/null 2>&1
  fi
  rendre_micro
  exit 1
fi
touch "$TMP/fini"
# Question tapee dans Creeper (2.45) : la reponse s'affiche aussi dans le champ.
if [ -n "${VOIX_ECRAN:-}" ]; then
  # Memoire des personnes (2.49) : messages vus, verdict du brouillon
  # precedent, identite donnee par le modele. Faite AVANT la reponse (2.53) :
  # la carte de la personne doit etre sur le telephone quand le panneau
  # recoit le texte.
  rm -f "${TMP:?}/personne-carte.json"
  if [ "${VOIX_MODE:-}" = repondre ]; then
    printf '%s\n' "$REP" > "$TMP/brouillon.txt"
    PERSONNE_CARTE="$TMP/personne-carte.json" \
      python3 "$(dirname "$0")/../personnes.py" maj "$VOIX_ECRAN" "$TMP/brouillon.txt" \
      "${VOIX_PERSONNE_OUT:-/nonexistent}" "${VOIX_QUESTION:-}" >&2 2>>"$HOME/.hermes/logs/voixtour.log" || true
    if [ -s "$TMP/personne-carte.json" ]; then
      "$ADB" -s "$ADDR" push "$TMP/personne-carte.json" \
        "/sdcard/Android/data/com.poste.pixelgarde/files/ecrire-personne.json" >/dev/null 2>&1
    fi
  fi
  printf '%s\n' "$REP" > "$TMP/ecrire-rep.txt"
  "$ADB" -s "$ADDR" push "$TMP/ecrire-rep.txt" \
    "/sdcard/Android/data/com.poste.pixelgarde/files/ecrire-rep.txt" >/dev/null 2>&1
  # Memoire de CETTE conversation (2.48) : les tours precedents reviennent
  # dans la consigne du tour suivant.
  if [ -n "${VOIX_CONV:-}" ]; then
    mkdir -p "$HOME/.hermes/pixel-ecrire"
    Q_="${VOIX_QUESTION:-$DIT}" R_="$REP" python3 -c '
import json, os
print(json.dumps({"q": os.environ["Q_"], "r": os.environ["R_"]}, ensure_ascii=False))
' >> "$HOME/.hermes/pixel-ecrire/$VOIX_CONV.jsonl"
  fi
fi
journal "repondu : $(printf '%s' "$REP" | head -c 120)"

# ------------------------------------------------- 4. la trace sur Telegram

# La phrase de USER est deja partie plus haut. Ici, seule la reponse.
# Ce que le bot poste n'entre PAS dans la session Hermes du 2923 : c'est la
# seule trace du tour, pour l'oeil.
# En arriere-plan, pendant que la voix se synthetise.
if [ -n "${TOKEN:-}" ] && [ -z "${VOIX_MODE:-}" ]; then
  curl -sS --max-time 20 -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
    -d chat_id="$CHAT" -d message_thread_id="$THREAD" \
    --data-urlencode text="$REP" >/dev/null 2>&1 &
fi

# --------------------------------------------------------- 5. la voix rendue

[ -e "$MARQUEUR" ] || { journal "raccroche pendant le tour, pas de reponse jouee"; exit 0; }
arrete && { journal "arret d'urgence pendant le tour, pas de reponse jouee"; exit 0; }
# Proposition d'envoi : la parole reste a ce tour jusqu'a la fin du compte a
# rebours. Aucun rapport ne le recouvre (envoiconfirme ou envoiannuler la rendent).
if [ ${#COMPTE[@]} -gt 0 ]; then
  ID_TOUR="$("$LECTURE" id 2>/dev/null)"
  "$LECTURE" poser TOUR "${ID_TOUR:-$POUR}" compte >/dev/null 2>&1
fi

A_DIRE="$(printf '%s' "$REP" | head -c "$LIMITE_TTS")"
# Mains libres : les boutons ne se voient pas en conduisant, on les dit.
if [ ${#CHOIX[@]} -gt 0 ] && [ "$(jq -r '.mains_libres // false' "$HOME/.hermes/qg-config.json" 2>/dev/null)" = true ]; then
  LIBS="$(printf '%s' "$MOTS" | tr '|' '\n' | cut -d: -f2- | paste -sd'|' | sed 's/|/, ou /g; s/[ ?.!]*$//')"
  [ -n "$LIBS" ] && A_DIRE="$A_DIRE Tu peux dire : $LIBS."
fi
# Le standard a propose un envoi : le telephone affichera un compte a rebours
# sur la bulle pendant et apres la lecture, puis enverra seul. Toucher la bulle
# annule. Le drapeau ne vaut que pour ce tour.
NOM="rep-$(date +%s%3N).mp3"
# Envoi propose apres un BOUTON touche (Oui, ou une reponse devinee) : USER sait
# deja ce qu'il a choisi. Pas de « d'accord, j'envoie » a voix haute (USER,
# 2026-10-03) : un silence de 0,2 s, et le compte part des la fin. Le texte
# reste visible dans le topic.
SILENCE=""
[ -n "${VOIX_TEXTE:-}" ] && [ ${#COMPTE[@]} -gt 0 ] && SILENCE=1
# Mode « repondre » du panneau Ecrire (2.48) : un brouillon ne se lit pas.
[ -n "${VOIX_MUET:-}" ] && SILENCE=1
if { if [ -n "$SILENCE" ]; then
       ffmpeg -loglevel error -f lavfi -i anullsrc=r=24000:cl=mono -t 0.2 \
         -q:a 9 "$TMP/$NOM" </dev/null
     else
       # Phrases synthetisees en parallele : 2,3 s au lieu de 4,1 s pour
       # 4 phrases (mesure du 2026-10-03). Repli en serie si une phrase manque.
       # Lecture anticipee (2.18) : la 1re phrase part au telephone des
       # qu'elle est prete (0,8 s contre 5,7 s pour la complete, 6 phrases,
       # mesure du 2026-10-03). Le telephone la joue, puis reprend la
       # complete a la meme position.
       DEB="deb-$NOM"
       TTS_PREMIERE="$TMP/$DEB" "$(dirname "$0")/../tts-rapide.sh" \
         "$A_DIRE" "$TMP/$NOM" "$VOIX_TTS" "$DEBIT" &
       PTTS=$!
       while kill -0 "$PTTS" 2>/dev/null && [ ! -s "$TMP/$DEB" ]; do sleep 0.05; done
       # Drapeau pose par l'installation de la 2.18 : une 2.17 jouerait la
       # 1re phrase comme une reponse entiere, puis tout depuis le debut.
       if [ -e "$HOME/.hermes/pixel-anticipe" ] && ! arrete \
          && [ -s "$TMP/$DEB" ] && kill -0 "$PTTS" 2>/dev/null \
          && "$ADB" -s "$ADDR" push "$TMP/$DEB" "$VOIX_TEL/$DEB" >/dev/null 2>&1; then
         "$ADB" -s "$ADDR" shell am start-foreground-service \
           -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIXREP \
           --es fichier "$DEB" --ez debut true --es suite "$NOM" \
           --es pour "$POUR" >/dev/null 2>&1
         journal "1re phrase poussee ($DEB)"
       fi
       wait "$PTTS" \
         || edge-tts --voice "$VOIX_TTS" --rate="$DEBIT" \
              --text "$A_DIRE" --write-media "$TMP/$NOM" >/dev/null 2>&1
     fi; } \
   && [ -s "$TMP/$NOM" ] && ! arrete \
   && "$ADB" -s "$ADDR" push "$TMP/$NOM" "$VOIX_TEL/$NOM" >/dev/null 2>&1 \
   && ! arrete; then
  "$ADB" -s "$ADDR" shell am start-foreground-service \
    -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIXREP \
    --es fichier "$NOM" --es pour "$POUR" "${COMPTE[@]}" "${CHOIX[@]}" >/dev/null 2>&1
  journal "reponse jouee ($NOM)${COMPTE:+ avec compte a rebours}${SILENCE:+, sans voix}"
elif arrete; then
  journal "arret d'urgence pendant la synthese, pas de reponse jouee"
else
  # La synthese ou le transfert ont lache : on rend quand meme la parole,
  # sinon la conversation reste muette et USER croit le telephone plante.
  journal "synthese ou transfert impossible, micro rendu sans reponse"
  rendre_micro
fi
