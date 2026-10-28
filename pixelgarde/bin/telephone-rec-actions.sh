#!/system/bin/sh
# Enregistre les gestes : ce que rec-journee.sh ne voit pas.
#
# Une capture d'ecran dit ce qui etait affiche. Elle ne dit pas ou le doigt a
# appuye. Sans cette ligne, une journee ne se rejoue pas : on voit l'ecran
# d'arrivee sans savoir quel bouton y menait. C'est la piece qui manquait pour
# transformer une journee enregistree en macro.
#
# Deux fichiers par jour, a cote des captures :
#
#   actions.tsv      HHMMSS.cc <TAB> type <TAB> x <TAB> y <TAB> x2 <TAB> y2 <TAB> ms <TAB> doigts
#   ui/HHMMSS.tsv    les elements de l'ecran une fois stabilise, avec leurs bornes
#
# Les coordonnees sont deja en pixels d'ecran : elles se rejouent telles quelles
# avec `input tap X Y`. Les arbres, eux, donnent le texte a viser - c'est par le
# texte qu'une macro reste valable quand la mise en page bouge.
#
# L'arbre est photographie APRES le geste, une fois l'ecran calme. Ce n'est pas
# un defaut : l'ecran d'arrivee du geste N est l'ecran de depart du geste N+1.
#
# Les taps injectes par `input tap` ne passent pas par le pilote tactile : ils
# n'apparaissent pas ici. Seuls les vrais gestes sont enregistres, jamais ceux
# des scripts d'automatisation.
#
# Copie de reference ; l'original tourne en /data/adb/rec-actions.sh

BASE="${BASE:-/sdcard/DayRec}"
TMP_UI=/data/local/tmp/_recui.xml
# Un geste, puis UI_CALME secondes de silence : l'ecran a fini de bouger.
UI_CALME="${UI_CALME:-2}"
# Jamais deux arbres a moins de UI_MINI secondes : un defilement en produirait cent.
UI_MINI="${UI_MINI:-5}"
# Un doigt qui parcourt moins de SEUIL pixels a tape, il n'a pas glisse.
SEUIL="${SEUIL:-24}"

# --- reperer le materiel ------------------------------------------------------
# Jamais /dev/input/eventN en dur : la numerotation depend de l'ordre de sondage
# des pilotes au demarrage.

TOUCH=$(getevent -pl 2>/dev/null | awk '
    /^add device/       { dev = $NF }
    /ABS_MT_POSITION_X/ { print dev; exit }
')
KEYS=$(getevent -pl 2>/dev/null | awk '
    /^add device/  { dev = $NF }
    /KEY_VOLUMEUP/ { print dev; exit }
')
[ -n "$TOUCH" ] || exit 1

# Le digitizer compte plus fin que l'ecran : 13440 pas pour 1008 pixels.
maxi() {
    getevent -pl "$TOUCH" 2>/dev/null | awk -v a="$1" '
        $1 == a { gsub(/,/, ""); for (i = 1; i <= NF; i++) if ($i == "max") { print $(i+1) + 1; exit } }
    '
}
BRUT_X=$(maxi ABS_MT_POSITION_X)
BRUT_Y=$(maxi ABS_MT_POSITION_Y)

# La derniere ligne l'emporte : `wm size` annonce l'override apres la taille physique.
TAILLE=$(wm size 2>/dev/null | grep -oE '[0-9]+x[0-9]+' | tail -1)
ECRAN_L="${TAILLE%x*}"
ECRAN_H="${TAILLE#*x}"
[ -n "$ECRAN_L" ] && [ -n "$ECRAN_H" ] && [ -n "$BRUT_X" ] && [ -n "$BRUT_Y" ] || exit 1

FX=$(awk "BEGIN { print $BRUT_X / $ECRAN_L }")
FY=$(awk "BEGIN { print $BRUT_Y / $ECRAN_H }")

# --- les gestes ---------------------------------------------------------------

lire_tactile() {
    getevent -lt "$TOUCH" 2>/dev/null | awk -v base="$BASE" -v fx="$FX" -v fy="$FY" -v seuil="$SEUIL" '
        function h2d(s,   i, c, v, n) {
            n = 0
            for (i = 1; i <= length(s); i++) {
                c = substr(s, i, 1)
                v = index("0123456789abcdef", c)
                if (v > 0) n = n * 16 + (v - 1)
            }
            return n
        }
        # Un seul fork par geste, au moment ou le doigt se pose : cest cet instant
        # qui se recoupe avec la capture decran, pas celui du relachement.
        function maintenant(   cmd, l) {
            cmd = "date \"+%Y-%m-%d %H%M%S.%2N\""
            cmd | getline l
            close(cmd)
            return l
        }
        function ecrire(quand, type, ax, ay, bx, by, ms, n,   jour, heure, f) {
            jour = substr(quand, 1, 10)
            heure = substr(quand, 12)
            if (jour != ouvert) {
                system("mkdir -p " base "/" jour " 2>/dev/null")
                ouvert = jour
            }
            f = base "/" jour "/actions.tsv"
            printf "%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\n", heure, type, ax, ay, bx, by, ms, n >> f
            fflush(f)
        }
        {
            ts = $2; sub(/\]$/, "", ts); ts = ts + 0
            code = $4
            val = $5
        }
        code == "ABS_MT_SLOT" { slot = h2d(val); next }
        code == "ABS_MT_POSITION_X" && slot == 0 { x = int(h2d(val) / fx); vux = 1; next }
        code == "ABS_MT_POSITION_Y" && slot == 0 { y = int(h2d(val) / fy); vuy = 1; next }
        code == "ABS_MT_TRACKING_ID" {
            if (val == "ffffffff") {
                if (ndoigts > 0) ndoigts--
                if (slot == 0 && actif) {
                    actif = 0
                    if (neuf) { x0 = x; y0 = y; neuf = 0 }
                    # Tant que les deux axes nont pas ete lus au moins une fois,
                    # leur valeur en vigueur reste inconnue : on jette le geste
                    # plutot que decrire un zero qui passerait pour le bord.
                    # Pas dapostrophes ici : le bloc awk est entre quotes simples.
                    if (vux && vuy) {
                        ms = int((ts - t0) * 1000)
                        d = sqrt((x - x0) * (x - x0) + (y - y0) * (y - y0))
                        if (d > seuil)   type = "swipe"
                        else if (ms >= 600) type = "long"
                        else             type = "tap"
                        ecrire(debut, type, x0, y0, x, y, ms, nmax)
                    }
                }
                next
            }
            ndoigts++
            if (ndoigts > nmax) nmax = ndoigts
            if (slot == 0 && !actif) {
                actif = 1; t0 = ts; nmax = ndoigts; neuf = 1
                debut = maintenant()
            }
            next
        }
        # Le point de depart se lit a la fin du paquet, pas a son ouverture : les
        # coordonnees suivent l ID de contact. Et le noyau ne repete pas une
        # coordonnee inchangee - un doigt qui se pose exactement ou le precedent
        # n emet aucun ABS_MT_POSITION. La position en vigueur est alors la
        # derniere lue, jamais une valeur neuve.
        code == "SYN_REPORT" && neuf { x0 = x; y0 = y; neuf = 0; next }
    '
}

# Boutons physiques : ils bornent la journee (ecran allume, ecran eteint) et
# expliquent les sauts qu'aucun tap ne justifie.
lire_touches() {
    [ -n "$KEYS" ] || return
    getevent -lt "$KEYS" 2>/dev/null | awk -v base="$BASE" '
        function maintenant(   cmd, l) {
            cmd = "date \"+%Y-%m-%d %H%M%S.%2N\""
            cmd | getline l
            close(cmd)
            return l
        }
        $3 == "EV_KEY" && ($5 == "DOWN" || $5 == "UP") {
            q = maintenant()
            jour = substr(q, 1, 10)
            if (jour != ouvert) {
                system("mkdir -p " base "/" jour " 2>/dev/null")
                ouvert = jour
            }
            f = base "/" jour "/actions.tsv"
            printf "%s\ttouche\t%s\t%s\t0\t0\t0\t0\n", substr(q, 12), $4, $5 >> f
            fflush(f)
        }
    '
}

# --- l'arbre des elements -----------------------------------------------------

arbre() {
    jour="$1"
    # L'heure est prise avant le dump : elle doit nommer l'instant de l'ecran,
    # pas celui ou uiautomator a fini de le decrire.
    heure=$(date +%H%M%S)
    uiautomator dump "$TMP_UI" >/dev/null 2>&1
    [ -s "$TMP_UI" ] || return
    m=$(md5sum "$TMP_UI" | cut -d' ' -f1)
    # Ecran inchange depuis le dernier arbre : rien de neuf a ecrire.
    [ "$m" = "$MD5_UI" ] && return
    MD5_UI="$m"
    mkdir -p "$BASE/$jour/ui"
    sed 's/></>\n</g' "$TMP_UI" | awk '
        function attr(nom,   deb, lg) {
            if (match($0, nom "=\"[^\"]*\"")) {
                deb = RSTART + length(nom) + 2
                lg  = RLENGTH - length(nom) - 3
                return substr($0, deb, lg)
            }
            return ""
        }
        function propre(s) { gsub(/[\t\r\n]+/, " ", s); return substr(s, 1, 120) }
        /<node / {
            t = propre(attr("text"))
            d = propre(attr("content-desc"))
            r = attr("resource-id")
            clic = (attr("clickable") == "true" ? 1 : 0)
            # Un noeud sans texte ni description ne se vise pas ; sil nest meme pas
            # cliquable, cest un echafaudage de mise en page. Le garder triplerait
            # le fichier sans rien apporter a une macro.
            if (t == "" && d == "" && !clic) next
            b = attr("bounds")
            gsub(/[^0-9]+/, " ", b)
            if (split(b, c, " ") < 4) next
            sub(/^[^\/]*\//, "", r)
            printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n", c[1], c[2], c[3], c[4], clic, t, d, r
        }
    ' > "$BASE/$jour/ui/$heure.tsv"
}

# On photographie l'arbre quand un geste vient d'avoir lieu ET que l'ecran s'est
# tu depuis. Photographier a intervalle fixe couterait cent fois plus pour rien :
# hors geste, l'ecran ne change pas.
boucle_ui() {
    vu=""
    dernier=0
    while true; do
        sleep 1
        jour=$(date +%Y-%m-%d)
        f="$BASE/$jour/actions.tsv"
        [ -f "$f" ] || continue
        mt=$(stat -c %Y "$f" 2>/dev/null) || continue
        [ "$mt" = "$vu" ] && continue
        now=$(date +%s)
        [ $((now - mt)) -lt "$UI_CALME" ] && continue
        [ $((now - dernier)) -lt "$UI_MINI" ] && continue
        vu="$mt"
        dernier="$now"
        arbre "$jour"
    done
}

# --- au travail ---------------------------------------------------------------

# `getevent` rend la main si son device disparait - mise en veille profonde,
# pilote qui se reinitialise. Sans reprise, l'enregistrement s'arreterait la et
# rien ne le dirait. La pause evite de tourner a vide si le device ne revient pas.
sans_relache() {
    while true; do
        "$1"
        sleep 2
    done
}

sans_relache lire_touches &
boucle_ui &
sans_relache lire_tactile
