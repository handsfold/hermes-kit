#!/usr/bin/env bash
# Reecouter la derniere voix jouee sur le Pixel (rapport, reponse, bilan).
# USER, 2026-10-02 : « pouvoir reecouter un rapport meme apres l'avoir ecoute ».
# L'appli range chaque voix jouee dans files/voix/lus (10 gardees) et choisit
# elle-meme la plus recente : rien a pousser d'ici.
# start-foreground-service et non un startService depuis la bulle : seul le
# shell adb peut lancer le service au premier plan depuis l'arriere-plan.
adb -s "$1" shell am start-foreground-service \
  -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIXREJOUER >/dev/null 2>&1
# La relecture tient la parole : sans ca, la lecture auto partait 6 s apres
# la fin et recouvrait les boutons rendus (USER, 2026-10-10). Seulement si
# personne d'autre ne l'a : un tour du standard ou un rapport en cours gagne.
# L'appli envoie relufini a la fin (ou a la coupure) : 8 s de fenetre ensuite.
# Sans relufini, l'etat LECTURE expire seul au bout de 4 min.
QL="$(dirname "$0")/../qg-lecture"
case "$("$QL" lire 2>/dev/null)" in
  *'"LIBRE"'*|*'"FENETRE"'*) "$QL" poser LECTURE relecture >/dev/null 2>&1 || true ;;
esac
