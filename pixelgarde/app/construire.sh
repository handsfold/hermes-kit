#!/usr/bin/env bash
# Reconstruit et installe l'appli du bouton d'arret, sans gradle.
#
# Pourquoi une appli plutot que `cmd notification post` : le shell adb (uid 2000)
# n'a pas le droit de creer un PendingIntent, donc --content-intent est refuse
# et une notification posee au shell ne peut porter aucun bouton.
set -euo pipefail
cd "$(dirname "$0")"
SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"
BT="$SDK/build-tools/36.1.0"
AJ="$SDK/platforms/android-36/android.jar"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

# Les ressources : le service d'accessibilite exige un @xml de configuration,
# donc aapt2 compile devient obligatoire (avant, le link seul suffisait).
mkdir -p "$T/gen"
"$BT/aapt2" compile --dir res -o "$T/res.zip"
"$BT/aapt2" link --manifest AndroidManifest.xml -I "$AJ" -o "$T/base.apk" \
    -R "$T/res.zip" --auto-add-overlay --java "$T/gen" \
    --min-sdk-version 26 --target-sdk-version 34
# --java : depuis que l'avis de rapport pose une vue sur mesure (res/layout/
# avis.xml), le code doit nommer ses ressources. Sans R.java il faudrait passer
# par getIdentifier, qui echoue en silence a l'execution au lieu d'echouer ici.
javac -nowarn -source 8 -target 8 -bootclasspath "$AJ" -cp "$AJ" \
    -d "$T/classes" src/com/poste/pixelgarde/*.java "$T"/gen/com/poste/pixelgarde/R.java
"$BT/d8" --lib "$AJ" --min-api 26 --output "$T" "$T"/classes/com/poste/pixelgarde/*.class
cp "$T/base.apk" "$T/unsigned.apk"
(cd "$T" && zip -q -j unsigned.apk classes.dex)
"$BT/zipalign" -f -p 4 "$T/unsigned.apk" "$T/aligned.apk"
[ -f debug.keystore ] || keytool -genkeypair -keystore debug.keystore \
    -storepass android -keypass android -alias garde -keyalg RSA -keysize 2048 \
    -validity 10000 -dname "CN=pixelgarde"
"$BT/apksigner" sign --ks debug.keystore --ks-pass pass:android \
    --key-pass pass:android --ks-key-alias garde --out pixelgarde.apk "$T/aligned.apk"

if [ "${1:-}" != "--sans-install" ]; then
    # Le Pixel 9 Pro XL, JAMAIS le premier de la liste : le 23/09/2026 un
    # Samsung s'est glisse en tete d'`adb devices` et a recu l'appli.
    ADDR=$(adb devices -l | awk '/model:Pixel_9_Pro_XL/{print $1; exit}')
    [ -n "$ADDR" ] || { echo "Pixel 9 Pro XL absent d'adb devices" >&2; exit 1; }
    adb -s "$ADDR" install -r -g pixelgarde.apk
    # SYSTEM_ALERT_WINDOW n'est pas une permission « grantable » : elle passe
    # par appops. Sans elle, addView leve BadTokenException et la pastille
    # n'apparait jamais, en silence.
    adb -s "$ADDR" shell appops set com.poste.pixelgarde SYSTEM_ALERT_WINDOW allow || true
    # Plus aucun service d'accessibilite depuis le 2026-08-30 : les
    # applications bancaires bloquent des qu'il y en a un d'actif. On efface
    # activement les deux reglages, car une ancienne installation a pu les
    # laisser derriere elle et Android garde l'entree meme quand le service
    # n'existe plus dans l'APK.
    adb -s "$ADDR" shell settings put secure enabled_accessibility_services '""' || true
    adb -s "$ADDR" shell settings put secure accessibility_button_targets '""' || true
    adb -s "$ADDR" shell settings put secure accessibility_enabled 0 || true
    # Les notifications sont RENDUES depuis le 2026-08-30. Elles etaient
    # coupees en bloc (pm revoke POST_NOTIFICATIONS, puis appops ignore), la
    # pastille etant alors la seule surface voulue. USER a demande ce jour-la un
    # avis cliquable pour ses rapports en attente : voir Avis.java. Sans la
    # permission, nm.notify part sans erreur et n'affiche rien, ce qui se
    # debogue tres mal.
    #
    # Les trois notifications que cela pourrait ramener sont tenues ailleurs :
    #   - « Pilotage agent actif » du Recepteur : plus personne ne diffuse
    #     SHOW, le garde ne pilote plus que la pastille ;
    #   - la notification de premier plan de Voix : passee en IMPORTANCE_MIN,
    #     donc sans icone de barre d'etat ni bruit ;
    #   - l'avertissement systeme de superposition : endormi trente jours par
    #     l'ecouteur Silencieux, qui le reconnait a son etiquette.
    # Si l'une d'elles reapparait, c'est la ligne correspondante qu'il faut
    # reparer, pas cette permission qu'il faut reprendre : la reprendre
    # eteindrait aussi les avis de rapport.
    adb -s "$ADDR" shell pm grant com.poste.pixelgarde android.permission.POST_NOTIFICATIONS || true
    # L'ecouteur qui etouffe l'avertissement systeme de superposition. Une
    # reinstallation revoque l'autorisation : la redonner ici, pas a la main.
    adb -s "$ADDR" shell cmd notification allow_listener com.poste.pixelgarde/.Silencieux || true
    # RECORD_AUDIO est une permission d'execution : `install -g` l'accorde
    # deja, mais une installation manuelle sans -g laisserait le micro muet
    # SANS erreur (AudioRecord rend du silence). On la redonne explicitement
    # plutot que de dependre d'un drapeau qu'on peut oublier.
    adb -s "$ADDR" shell pm grant com.poste.pixelgarde android.permission.RECORD_AUDIO || true
    # Le relais reseau (Relais.java, 2026-10-03). Sans la liste blanche de
    # Doze, l'ecran eteint couperait le reseau de l'appli et la bulle se
    # tairait la nuit. L'URL et le jeton passent une fois par relais.txt,
    # que l'appli range dans ses preferences puis efface.
    adb -s "$ADDR" shell dumpsys deviceidle whitelist +com.poste.pixelgarde >/dev/null || true
    if [ -r "$HOME/.hermes/creeper-relais.token" ]; then
        RT=$(mktemp); chmod 600 "$RT"
        printf 'https://exemple.tld\n%s\n' "$(cat "$HOME/.hermes/creeper-relais.token")" > "$RT"
        PIXEL_SANS_RELAIS=1 adb -s "$ADDR" push "$RT" /sdcard/Android/data/com.poste.pixelgarde/files/relais.txt >/dev/null || true
        rm -f "${RT:?}"
    fi
    # Reposer la pastille par le CLI, pas par un CACHER : `pixel bulle` renvoie
    # le vrai menu de actions/menu.txt ET remet le drapeau « masquee » a faux,
    # sans quoi le receveur de demarrage refuserait de la ramener au reboot.
    "$(dirname "$0")/../../bin/pixel/pixel" bulle >/dev/null || true
    # La grille des applications recentes a ete retiree le 2026-08-30 : on
    # reprend l'acces aux statistiques d'usage, plus personne ne les lit. Le
    # cache d'apercus qu'elle laissait derriere elle est efface par
    # l'application au premier passage, voir Bulle.purgerApercusMorts().
    adb -s "$ADDR" shell appops set com.poste.pixelgarde android:get_usage_stats ignore || true
fi
echo "pixelgarde.apk pret"
