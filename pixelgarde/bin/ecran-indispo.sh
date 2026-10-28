#!/usr/bin/env bash
# Le telephone est-il indisponible pour une lecture a voix haute ?
#
# Code 0 : indisponible (ecran eteint, en veille, ou allume mais verrouille).
# Code 1 : disponible, USER a l'appareil en main et deverrouille.
# Code 2 : injoignable, donc on ne sait pas.
#
# POURQUOI : un rapport lu tout haut alors que le telephone dort dans une poche
# ou sur une table n'est pas un service. USER ne le demande pas, ne le regarde
# pas, et la voix part dans le vide ou reveille la piece. USER l'a signale le
# 2026-08-30 : « quand mon ecran est eteint ca ne devrait pas lancer la lecture
# automatique ». Puis, le meme jour : « meme l'ecran doit etre deverrouille ».
# Un ecran allume sur l'ecran de verrouillage, c'est une notification qu'on
# regarde en passant, pas quelqu'un qui ecoute. La lecture est donc mise de
# cote, et reprise quand USER reprend son telephone.
#
# Deux sources, et il faut les deux.
#
# `dumpsys power`, champ mWakefulness. Trois valeurs comptent :
#   Awake   : l'ecran est allume.
#   Dozing  : affichage permanent, ecran quasi eteint. Pour USER c'est eteint.
#   Asleep  : eteint.
# mScreenState de `dumpsys display` ne suffit pas : il annonce ON pendant
# l'affichage permanent, ou l'ecran est noir et le telephone pose.
#
# `dumpsys trust`, champ deviceLocked, sur la ligne marquee (current). Cette
# precision compte : le profil « Private space » a sa propre ligne, avec son
# propre verrou, et la confondre avec la session de USER ferait attendre un
# rapport pour rien. deviceLocked=1 veut dire « ecran de verrouillage devant »,
# meme quand l'ecran est allume et lumineux.
set -uo pipefail

# L'appli le dit elle-meme par le relais reseau (2026-10-03) : a chaque
# appel, au plus 25 s, et a chaque allumage ou deverrouillage. Frais de moins
# de 40 s, il fait foi et ADB n'est pas appele. Sinon, repli sur dumpsys.
ETAT_RELAIS="$HOME/.hermes/creeper-relais/etat"
if [ -r "$ETAT_RELAIS" ] && [ $(( $(date +%s) - $(stat -c %Y "$ETAT_RELAIS") )) -lt 40 ]; then
  case "$(cat "$ETAT_RELAIS")" in
    *"ecran=1 verrou=0"*) exit 1 ;;
    *ecran=*) exit 0 ;;
  esac
fi

ADDR="${1:-$(adb devices | awk '/device$/{print $1; exit}')}"
[ -n "$ADDR" ] || exit 2

# Une seule traversee du reseau pour les deux questions : le canal ADB passe
# par Tailscale, chaque aller-retour coute une seconde et le garde repasse
# toutes les cinq. Le 2>/dev/null etouffe le « Broken pipe » que dumpsys crie
# quand grep -m1 lui ferme le tuyau au nez ; ce n'est pas une erreur.
ETAT="$(timeout 12 adb -s "$ADDR" shell \
  "dumpsys power 2>/dev/null | grep -m1 'mWakefulness='; \
   dumpsys trust 2>/dev/null | grep -m1 '(current)'" 2>/dev/null)" || exit 2
[ -n "$ETAT" ] || exit 2

# L'ecran d'abord. Endormi, la question du verrou ne se pose meme pas.
case "$ETAT" in
  *Awake*) ;;
  *) exit 0 ;;
esac

# Puis le verrou. Une ligne (current) absente n'autorise rien : on prefere un
# rapport qui attend a un rapport qui parle a un ecran de verrouillage.
case "$ETAT" in
  *"(current)"*deviceLocked=0*) exit 1 ;;
  *) exit 0 ;;
esac
