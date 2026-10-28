#!/usr/bin/env bash
# Bouton « Conversation vocale » : ouvre ou ferme le mode mains libres.
#
# Un seul bouton pour les deux sens : le service lui-meme sait s'il tourne
# (Voix.actif) et coupe au second appui. Afficher deux libelles selon l'etat
# supposerait que hote-1 connaisse cet etat, or il ne l'apprend qu'apres coup,
# par voixdebut / voixfin. Un bouton qui ment est pire qu'un bouton unique.
set -euo pipefail
ADB="${ADB:-adb}"
ADDR="${1:-$("$ADB" devices | awk '/device$/{print $1; exit}')}"
# start-foreground-service et pas start-service : le service passe en premier
# plan des sa premiere seconde. Sans cela, Android le tue en 5 s
# (ForegroundServiceDidNotStartInTimeException), et surtout le micro d'un
# processus d'arriere-plan rend du silence au lieu de lever une erreur.
"$ADB" -s "$ADDR" shell am start-foreground-service \
  -n com.poste.pixelgarde/.Voix -a com.poste.pixel.VOIX >/dev/null 2>&1
