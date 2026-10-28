#!/usr/bin/env bash
# Debit de lecture pour le moteur vocal du telephone : la cle `debit` de
# ~/.hermes/qg-config.json ("+50%") devient un facteur ("1.50").
#
# C'est la MEME cle que le sous-menu Vitesse de la pastille ecrit. Il y avait
# deux cles jusqu'au 2026-09-24 (`debit` pour les rapports, `lecture_debit`
# pour l'ecran et le presse-papier) : USER reglait Vitesse et relisait a la meme
# allure, ce qui ressemblait a une panne. Une seule vitesse, un seul reglage.
#
# Etalonnage du 2026-09-24 : a reglage egal, la voix Google du telephone est
# 15 % plus lente que Henri (edge-tts) qui lit les rapports. Mesure sur 78
# mots : 24,6 s contre 28,0 s a +0 %, 16,4 s contre 19,0 s a +50 %, 12,3 s
# contre 14,0 s a +100 %. Le facteur ci-dessous rattrape l'ecart, pour que
# « Rapide » sonne pareil dans un rapport et dans une lecture d'ecran.
ETALON=1.15
set -uo pipefail
eval "$("$HOME/.hermes/scripts/qg-config.py" env)"
D="${QGC_DEBIT:-+8%}"
LC_NUMERIC=C awk -v d="$D" -v k="$ETALON" 'BEGIN{gsub(/[+%]/,"",d); printf "%.2f\n", (1 + d/100) * k}'
