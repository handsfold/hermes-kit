#!/bin/bash
# Test de l'arbitrage « une seule main » sur un faux appareil (10.99.99.99).
# Aucun vrai telephone touche : le vrai adb est remplace par un faux qui note.
D=$(mktemp -d /tmp/telephone-test.XXXX)
ICI=$(dirname "$(readlink -f "$0")")
export ADB_REEL=$D/faux-adb ADB_PRIORITE=$D/prio ADB_HORS_PIXEL=$D/hors.txt
echo "10.99.99.99 FAUX" > "$D/hors.txt"
printf '#!/bin/bash\necho "$(date +%%s) ${ADB_PROPRIO:-lot} $*" >> %s/appels\n' "$D" > "$ADB_REEL"
chmod +x "$ADB_REEL"
G="$ICI/adb-garde -s 10.99.99.99:5555 shell"
ok=0 ko=0
verif() { if eval "$2"; then echo "OK   $1"; ok=$((ok+1)); else echo "ECHEC $1"; ko=$((ko+1)); fi; }

# 1. Un lot detache (double fork, aucun agent parmi ses ancetres) tape en boucle.
setsid bash -c "( sleep 1; for i in \$(seq 1 40); do $G input tap \$i 1 2>>$D/lot.err; sleep 0.5; done; echo fin > $D/lot.fin ) &" </dev/null >/dev/null 2>&1
sleep 3
verif "le lot est reconnu comme lot" "grep -q '^lot' $ADB_PRIORITE/bail-FAUX"

# 2. Un agent A arrive : il passe devant, le lot se met en pause.
ADB_PROPRIO=A $G input tap 500 500 2>$D/a.err
verif "A prend la main sur le lot" "grep -q 'nom:A' $ADB_PRIORITE/bail-FAUX"
verif "A est prevenu de la pause du lot" "grep -q 'pause' $D/a.err"
n1=$(grep -c ' lot ' $D/appels); sleep 3; n2=$(grep -c ' lot ' $D/appels)
verif "le lot ne tape plus pendant que A tient ($n1 -> $n2)" "[ $n1 = $n2 ]"

# 3. Un agent B arrive : il attend sans couper A, puis abandonne en code 75.
ADB_PROPRIO=B ADB_ATTENTE=4 $G input tap 600 600 2>$D/b.err; code=$?
verif "B refuse en 75 sans couper A (code $code)" "[ $code = 75 ] && grep -q 'nom:A' $ADB_PRIORITE/bail-FAUX"
verif "B garde sa place dans la file" "grep -q 'nom:B' $ADB_PRIORITE/file-FAUX/1-*"

# 4. A rend la main : B passe avant le lot, qui reste en pause.
ADB_PROPRIO=A "$ICI/telephone" rendre FAUX >/dev/null
sleep 1.5
verif "le lot attend encore derriere B" "! grep -qs '^lot' $ADB_PRIORITE/bail-FAUX"
ADB_PROPRIO=B $G input tap 600 600 2>/dev/null
verif "B a la main a son tour" "grep -q 'nom:B' $ADB_PRIORITE/bail-FAUX"
n1=$(grep -c ' lot ' $D/appels); sleep 2; n2=$(grep -c ' lot ' $D/appels)
verif "le lot reste en pause pendant B" "[ $n1 = $n2 ]"

# 5. Les lectures passent toujours, meme pendant que B tient.
ADB_PROPRIO=C $G uiautomator dump 2>/dev/null
verif "une lecture de C passe sans attendre" "grep -q ' C ' $D/appels"

# 6. B rend la main : le lot reprend seul.
ADB_PROPRIO=B "$ICI/telephone" rendre FAUX >/dev/null
sleep 3
n3=$(grep -c ' lot ' $D/appels)
verif "le lot reprend seul ($n2 -> $n3)" "[ $n3 -gt $n2 ]"
"$ICI/telephone" etat | sed 's/^/     /'
echo "$ok OK, $ko ECHEC  (journal : $ADB_PRIORITE/journal.log)"
[ "$ko" = 0 ]
