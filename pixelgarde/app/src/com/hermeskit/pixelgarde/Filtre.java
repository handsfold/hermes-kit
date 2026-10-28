package com.poste.pixelgarde;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.PixelFormat;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;

/**
 * Le voile ambre qui retire le bleu de l'ecran.
 *
 * Pourquoi une fenetre et pas un reglage Android : l'eclairage nocturne du
 * Pixel s'arrete a 2596 K, sa borne la plus chaude, et USER y etait deja le
 * 2026-09-07 quand il a demande « encore moins de bleu ». Au-dela, le systeme
 * n'offre plus rien sans root ni service d'accessibilite, et les services
 * d'accessibilite sont exclus depuis que les applis bancaires les refusent.
 * Reste la seule voie qui ne demande aucune permission neuve : SYSTEM_ALERT_
 * WINDOW, que la pastille porte deja.
 *
 * La couleur ne contient aucun bleu (composante B a zero). Le compositeur
 * Android ne sait melanger les fenetres qu'en SRC_OVER : on ne peut donc pas
 * soustraire le bleu du contenu, seulement poser de l'ambre par-dessus. Plus
 * l'opacite monte, moins le bleu d'origine ressort. C'est exactement ce que
 * font les filtres du Play Store, sans leurs permissions.
 *
 * NOT_TOUCHABLE est vital : sans lui le voile avalerait tous les appuis et le
 * telephone paraitrait gele. Voir la meme note dans Cadre.java.
 *
 * L'intensite est un POURCENTAGE 0..100, pas un palier : USER a demande un
 * curseur le 2026-09-07 apres avoir essaye les cinq crans. 100 % vaut 0,80
 * d'opacite ; au-dela l'ecran devient illisible et le curseur ne sert plus a
 * rien sur sa moitie haute.
 *
 * MESURE du 2026-09-07, moyenne RVB d'une capture plein ecran : sans voile
 * R=58 V=59 B=75, a 48 % R=94 V=70 B=59, a 92 % R=128 V=81 B=44. Le bleu perd
 * 41 % au maximum, et cesse d'etre la composante dominante des le premier
 * quart. Le voile SORT dans `adb exec-out screencap` : une capture suffit a
 * verifier qu'il est pose, inutile de filmer l'ecran. Seule exception vue :
 * quand une carte floutee du systeme est ouverte par-dessus, la capture rend
 * les couleurs d'origine. Mesurer alors ecran nu.
 */
class Filtre {

    /** Ambre sans bleu : R max, V a mi-course, B nul. */
    private static final int TEINTE = 0x00FF7A00;

    /** Opacite atteinte a 100 %. Au-dela, l'ecran n'est plus lisible. */
    private static final float PLAFOND = 0.80f;

    /** Les paliers nommes, pour le CLI et les vieux appels. */
    static final String[] NOMS = {"aucun", "doux", "moyen", "fort", "extreme"};
    static final int[] PALIERS = {0, 25, 48, 70, 92};

    private static final String PREFS = "pixelgarde";
    private static final String CLE = "filtre_pct";

    private static View vue;

    static int borner(int n) {
        if (n < 0) return 0;
        if (n > 100) return 100;
        return n;
    }

    /** Le nom du palier le plus proche, pour l'afficher dans la pastille. */
    static String nom(int pct) {
        int p = borner(pct);
        int meilleur = 0;
        int ecart = Integer.MAX_VALUE;
        for (int i = 0; i < PALIERS.length; i++) {
            int d = Math.abs(PALIERS[i] - p);
            if (d < ecart) { ecart = d; meilleur = i; }
        }
        return NOMS[meilleur];
    }

    /** L'intensite choisie par USER, independamment de ce qui est peint. */
    static int pct(Context c) {
        try {
            SharedPreferences p = c.getApplicationContext()
                    .getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            return borner(p.getInt(CLE, 0));
        } catch (Throwable t) {
            return 0;
        }
    }

    /**
     * Traduit un mot, un pourcentage ou un vieux chiffre de palier.
     *
     * Un entier de 0 a 4 est ambigu : c'est aussi un pourcentage. Les anciens
     * paliers gagnent, parce que « 3 » venait toujours du CLI d'avant et que
     * 3 % de voile ne se voit pas.
     */
    static int lire(String s) {
        if (s == null) return -1;
        String v = s.trim().toLowerCase().replace("%", "");
        if (v.isEmpty()) return -1;
        for (int i = 0; i < NOMS.length; i++) {
            if (NOMS[i].equals(v)) return PALIERS[i];
        }
        if ("off".equals(v) || "non".equals(v)) return 0;
        try {
            int n = Integer.parseInt(v);
            if (n >= 0 && n <= 4) return PALIERS[n];
            return borner(n);
        } catch (NumberFormatException e) {
            return -1;
        }
    }

    /** Enregistre l'intensite voulue, puis laisse Auto decider de la peindre. */
    static void definir(Context ctx, int pct) {
        Context c = ctx.getApplicationContext();
        try {
            c.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    // commit() et non apply() : le processus de la pastille
                    // peut etre tue juste apres un broadcast, et une ecriture
                    // differee se perd alors sans bruit. Le voile revenait
                    // a zero au recalcul suivant (2026-09-07).
                    .edit().putInt(CLE, borner(pct)).commit();
        } catch (Throwable ignore) {
        }
        Auto.rafraichir(c);
    }

    /** Peint le voile a l'instant, sans rien enregistrer. */
    static synchronized void peindre(Context ctx, int pct) {
        final Context c = ctx.getApplicationContext();
        int n = borner(pct);
        if (n == 0 || Bulle.eteinte(c)) {
            retirer();
            return;
        }
        int alpha = (int) (n / 100f * PLAFOND * 255f);
        int couleur = TEINTE | (alpha << 24);
        // Reteinter une fenetre deja posee evite le clignotement noir d'un
        // retrait suivi d'un ajout : le curseur repeint a chaque pixel glisse.
        if (vue != null) {
            try {
                vue.setBackgroundColor(couleur);
                return;
            } catch (Throwable ignore) {
                retirer();
            }
        }
        WindowManager wm = (WindowManager) c.getSystemService(Context.WINDOW_SERVICE);
        if (wm == null) return;
        View v = new View(c);
        v.setBackgroundColor(couleur);

        int L = WindowManager.LayoutParams.MATCH_PARENT;
        int H = WindowManager.LayoutParams.MATCH_PARENT;
        try {
            android.graphics.Rect b = wm.getMaximumWindowMetrics().getBounds();
            // Deborder d'un ecran entier : sinon la rotation laisse une bande
            // nue le temps que la fenetre soit remesuree, et l'oeil la voit.
            L = b.width() + b.height();
            H = b.width() + b.height();
        } catch (Throwable ignore) {
        }
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(L, H,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        try {
            wm.addView(v, lp);
            vue = v;
        } catch (Exception ignore) {
        }
    }

    /** Repose l'etat enregistre : appele au demarrage et par le garde. */
    static void restaurer(Context c) {
        Auto.rafraichir(c);
    }

    private static void retirer() {
        if (vue == null) return;
        try {
            WindowManager wm = (WindowManager) vue.getContext()
                    .getSystemService(Context.WINDOW_SERVICE);
            if (wm != null) wm.removeView(vue);
        } catch (Exception ignore) {
        }
        vue = null;
    }
}
