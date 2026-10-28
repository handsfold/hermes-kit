#!/usr/bin/env bash
# Bouton « Lire le presse-papier » : l'activite transparente .Presse lit le
# presse-papier (seule une app au premier plan y a acces depuis Android 10)
# et lance elle-meme le service .Lecteur, moteur vocal du telephone.
# Rien ne revient sur hote-1 : la voix part en moins d'une seconde.
# Les commandes (pause, precedent, suivant, curseur, arret) sont dans la
# notification media. Un nouvel appui remplace la lecture en cours.
set -uo pipefail
ADDR="${1:?addr}"
ICI="$(cd "$(dirname "$0")/.." && pwd)"
DEBIT="$("$ICI/lecture-debit.sh")"
# Le volet des notifications, s'il est ouvert, garde le focus : l'activite ne
# lirait rien. On le replie d'abord.
adb -s "$ADDR" shell "cmd statusbar collapse; am start -n com.poste.pixelgarde/.Presse --ez lire true --ef debit $DEBIT" >/dev/null 2>&1
echo "Presse-papier : lecture lancee sur le telephone (debit $DEBIT)"
