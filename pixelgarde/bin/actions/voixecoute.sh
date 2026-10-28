#!/usr/bin/env bash
# Le telephone annonce qu'il reprend l'ecoute apres une reponse jouee.
#
# Meme conversation, meme marqueur /tmp/pixel-voix (jamais touche ici) : seul
# le sous-etat change, de "pret" a "ecoute". C'est ce que USER vient de
# declencher par un appui volontaire sur le bouton, puisque le micro ne se
# rouvre plus tout seul (voir Voix.java, onCompletion).
set -euo pipefail
# Le telephone ecoute : la conversation est donc ouverte, quoi qu'en pense
# hote-1. Le 2026-10-01, USER a repris la parole 18 min apres la derniere reponse.
# Le garde avait retire le marqueur au bout de 10 min, le service du telephone
# vivait encore : sa phrase est arrivee, et voixtour l'a jetee comme un tour
# d'une conversation fermee. Le telephone fait foi, on rouvre le marqueur.
PIXEL_TMP="${PIXEL_TMP:-/tmp}"
touch "$PIXEL_TMP/pixel-voix"
echo "ecoute" > "$PIXEL_TMP/pixel-voix-etat"
echo "voix : ecoute reprise" >&2
