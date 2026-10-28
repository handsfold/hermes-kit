#!/usr/bin/env bash
# Le telephone a fini (ou coupe) une relecture lancee par rejouer.sh.
# La parole passe en FENETRE : regroupe_s (8 s) pour toucher un bouton rendu,
# puis la lecture auto reprend. Rien ne bouge si un autre etat a pris la main.
QL="$(dirname "$0")/../qg-lecture"
case "$("$QL" lire 2>/dev/null)" in
  *'"LECTURE"'*'"relecture"'*|*'"relecture"'*'"LECTURE"'*) "$QL" poser FENETRE relecture >/dev/null 2>&1 || true ;;
esac
