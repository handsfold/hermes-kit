package com.poste.pixelgarde;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;

/**
 * Le liseré rouge qui borde l'ecran pendant un enregistrement.
 *
 * Pourquoi une bordure et pas une teinte : un voile rouge par-dessus tout
 * rendrait le telephone inutilisable pendant qu'on filme, ce qui est
 * exactement le moment ou USER s'en sert. La bordure dit la meme chose et ne
 * mange rien.
 *
 * Elle respire (opacite 1 -> 0,35 en boucle) parce qu'un cadre fixe se
 * confond avec un fond d'ecran au bout de dix secondes. Un battement, non.
 *
 * A SAVOIR : `screenrecord` filme la surface composee, ce cadre compris. Il
 * apparait donc dans la video. C'est assume : mieux vaut une video bordee de
 * rouge qu'un enregistrement qu'on oublie en cours.
 */
class Cadre {

    private static View vue;
    private static ValueAnimator souffle;
    private static final Handler H = new Handler(Looper.getMainLooper());
    private static final Runnable ETEINDRE = new Runnable() {
        public void run() {
            cacher(null);
        }
    };

    private static int dp(Context c, float v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v,
                c.getResources().getDisplayMetrics());
    }

    static void montrer(Context c) {
        montrer(c, Charte.ROUGE, 4f, true);
    }

    /** Un eclair bref : la confirmation visuelle d'une capture figee. */
    static void flash(Context c) {
        montrer(c, Charte.ROUGE, 6f, false);
        H.removeCallbacks(ETEINDRE);
        H.postDelayed(ETEINDRE, 320);
    }

    private static synchronized void montrer(Context ctx, int couleur,
                                             float epaisseur, boolean respire) {
        final Context c = ctx.getApplicationContext();
        H.removeCallbacks(ETEINDRE);
        cacher(c);
        if (Bulle.eteinte(c)) return;
        WindowManager wm = (WindowManager) c.getSystemService(Context.WINDOW_SERVICE);
        if (wm == null) return;

        View v = new View(c);
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.RECTANGLE);
        // Le rayon suit les coins de l'ecran du Pixel : un cadre a angles
        // droits laisse quatre triangles de vide dans les arrondis, et se lit
        // comme un bug d'affichage plutot que comme un temoin.
        g.setCornerRadius(dp(c, 46));
        g.setStroke(dp(c, epaisseur), couleur);
        v.setBackground(g);

        // Bord a bord, barres systeme comprises. MATCH_PARENT s'arrete a la
        // zone de contenu : le cadre laissait alors deux bandes nues, en haut
        // et en bas, et se lisait comme un cadre d'application, pas d'ecran.
        int L = WindowManager.LayoutParams.MATCH_PARENT;
        int H = WindowManager.LayoutParams.MATCH_PARENT;
        try {
            android.graphics.Rect b = wm.getMaximumWindowMetrics().getBounds();
            L = b.width();
            H = b.height();
        } catch (Throwable ignore) {
        }
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(L, H,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                // NOT_TOUCHABLE est vital : sans lui, le cadre avale tous les
                // appuis de l'ecran et le telephone parait gele.
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        try {
            wm.addView(v, lp);
        } catch (Exception e) {
            return;
        }
        vue = v;

        if (!respire) return;
        souffle = ValueAnimator.ofFloat(1f, 0.35f);
        souffle.setDuration(900);
        souffle.setRepeatMode(ValueAnimator.REVERSE);
        souffle.setRepeatCount(ValueAnimator.INFINITE);
        souffle.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            public void onAnimationUpdate(ValueAnimator a) {
                if (vue != null) vue.setAlpha((Float) a.getAnimatedValue());
            }
        });
        souffle.start();
    }

    static synchronized void cacher(Context c) {
        H.removeCallbacks(ETEINDRE);
        if (souffle != null) {
            souffle.cancel();
            souffle = null;
        }
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
