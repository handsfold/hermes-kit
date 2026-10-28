#!/system/bin/sh
# Lance l'enregistrement de la journee au demarrage, et purge les vieux jours.
# Pose par Magisk dans /data/adb/service.d/ : execute en root apres le boot.
#
# Copie de reference ; l'original tourne en /data/adb/service.d/dayrec.sh

BASE=/sdcard/DayRec
RETENTION_JOURS=14

# attendre que le stockage /sdcard soit monte
i=0
while [ ! -d /sdcard ] && [ $i -lt 60 ]; do
    sleep 2
    i=$((i + 1))
done

# purge des journees trop anciennes
if [ -d "$BASE" ]; then
    find "$BASE" -maxdepth 1 -type d -name '20*' -mtime +"$RETENTION_JOURS" -exec rm -rf {} \; 2>/dev/null
fi

# une seule instance a la fois.
# setsid detache la boucle de la session appelante : sans lui, un lancement
# manuel depuis `adb shell` meurt des que la connexion se ferme.
#
# Deux enregistreurs qui se completent : rec-journee voit ce qui est affiche,
# rec-actions voit ou le doigt appuie. L'un sans l'autre ne se rejoue pas.
for R in rec-journee rec-actions; do
    if ! pgrep -f "$R.sh" >/dev/null 2>&1; then
        setsid sh "/data/adb/$R.sh" </dev/null >/dev/null 2>&1 &
    fi
done
