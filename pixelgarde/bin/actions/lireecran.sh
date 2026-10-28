#!/usr/bin/env bash
# Bouton « Lire l'ecran » : uiautomator dump (aucun service d'accessibilite,
# les banques les bloquent), extraction des textes visibles, puis lecture par
# le service .Lecteur avec le moteur vocal du telephone.
# Les commandes (pause, precedent, suivant, curseur, arret) sont dans la
# notification media. Un nouvel appui remplace la lecture en cours.
set -uo pipefail
ADDR="${1:?addr}"
ICI="$(cd "$(dirname "$0")/.." && pwd)"
DEBIT="$("$ICI/lecture-debit.sh")"
TEL="/sdcard/Android/data/com.poste.pixelgarde/files"
TMP="$(mktemp -d)"; trap 'rm -rf "${TMP:?}"' EXIT
adb -s "$ADDR" shell uiautomator dump /sdcard/ui-lecture.xml >/dev/null 2>&1
adb -s "$ADDR" pull /sdcard/ui-lecture.xml "$TMP/ui.xml" >/dev/null 2>&1 || { echo "dump ecran impossible"; exit 1; }
python3 - "$TMP/ui.xml" > "$TMP/texte.txt" <<'PY'
import re, sys, xml.etree.ElementTree as ET
racine = ET.parse(sys.argv[1]).getroot()
vus, out = None, []
for n in racine.iter("node"):
    if n.get("package") == "com.poste.pixelgarde":
        continue
    m = re.match(r"\[\d+,\d+\]\[\d+,(\d+)\]", n.get("bounds", ""))
    if m and int(m.group(1)) <= 140:      # barre d'etat
        continue
    t = (n.get("text") or "").strip()
    if not t or t == vus:
        continue
    vus = t
    out.append(t)
print("\n".join(out))
PY
N=$(wc -c < "$TMP/texte.txt")
[ "$N" -gt 1 ] || printf 'Ecran : rien a lire.\n' > "$TMP/texte.txt"
adb -s "$ADDR" push "$TMP/texte.txt" "$TEL/lecture.txt" >/dev/null 2>&1
adb -s "$ADDR" shell am start-foreground-service -n com.poste.pixelgarde/.Lecteur \
  -a com.poste.pixel.LIRE --es fichier lecture.txt --es titre Ecran --ef debit "$DEBIT" >/dev/null 2>&1
echo "Ecran : $N octets envoyes au lecteur (debit $DEBIT)"
