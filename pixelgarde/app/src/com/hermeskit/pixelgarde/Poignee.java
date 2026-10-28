package com.poste.pixelgarde;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.util.DisplayMetrics;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.LinearLayout;

/**
 * Ce qui reste quand USER masque la pastille : un cil de 3 dp contre le bord.
 *
 * Le defaut corrige ici (signale le 2026-08-26) : « Masquer » retirait la
 * pastille pour de bon, et le seul chemin de retour passait par hote-1
 * (`pixel bulle`). Un bouton qu'on ne peut pas defaire depuis le telephone
 * n'est pas un bouton, c'est un piege. Le lien peut dormir, ou USER etre
 * dehors : il fallait un retour qui ne demande rien a personne.
 *
 * La poignee est presque invisible (12 % d'opacite) mais porte une zone
 * tactile de doigt entiere. Le retour repose la pastille sur-le-champ, sans
 * attendre hote-1, et previent la station pour qu'elle leve son marqueur.
 *
 * Il faut un appui MAINTENU (600 ms) pour la ramener. Le 2026-08-29, USER :
 * « il reapparait vraiment trop facilement [...] j'aimerais que ce soit
 * vraiment volontaire ». Un simple relachement suffisait, or cette zone fait
 * un doigt de large et vit contre le bord, la ou passent le pouce qui tient
 * le telephone et tous les defilements : elle se declenchait toute seule, et
 * USER passait son temps a remasquer. Ce que ce cil ouvre - une pastille qui
 * revient par-dessus tout - merite une seconde d'intention.
 */
class Poignee {

    private static View vue;

    private static int dp(Context c, float v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v,
                c.getResources().getDisplayMetrics());
    }

    static synchronized void montrer(Context ctx) {
        final Context c = ctx.getApplicationContext();
        retirer(c);
        WindowManager wm = (WindowManager) c.getSystemService(Context.WINDOW_SERVICE);
        if (wm == null) return;
        DisplayMetrics dm = c.getResources().getDisplayMetrics();
        SharedPreferences p = c.getSharedPreferences("bulle", Context.MODE_PRIVATE);

        boolean gauche = p.getInt("x", dm.widthPixels) + dp(c, 26) < dm.widthPixels / 2;
        final int large = dp(c, 52);
        int y = p.getInt("y", dm.heightPixels / 3);

        View cil = new View(c);
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.RECTANGLE);
        float r = dp(c, 3);
        g.setCornerRadii(gauche
                ? new float[]{0, 0, r, r, r, r, 0, 0}
                : new float[]{r, r, 0, 0, 0, 0, r, r});
        g.setColor(Charte.VEILLE);
        cil.setBackground(g);
        LinearLayout.LayoutParams cp = new LinearLayout.LayoutParams(dp(c, 3), dp(c, 40));
        cp.gravity = Gravity.CENTER_VERTICAL | (gauche ? Gravity.START : Gravity.END);
        cil.setLayoutParams(cp);

        // Le cil se voit a peine ; la zone qui l'attrape fait un doigt. Sans ce
        // conteneur, il faudrait viser 3 dp de large.
        LinearLayout zone = new LinearLayout(c);
        zone.setGravity(cp.gravity);
        zone.addView(cil);
        zone.setAlpha(0.12f);

        // 52 dp de large, comme la pastille, et non 26 : le bord de l'ecran
        // est mange sur une vingtaine de dp par le geste de retour d'Android,
        // qui prend le pas sur toute fenetre d'overlay. Une poignee etroite
        // tombait entierement dans cette bande et ne recevait jamais le doigt.
        final WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                dp(c, 52), dp(c, 56),
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.x = gauche ? 0 : dm.widthPixels - large;
        lp.y = y;

        // Le retour se merite : 600 ms de doigt pose. Pendant la charge, la
        // poignee s'eclaire progressivement, pour que l'attente se voie et ne
        // passe pas pour une panne. Un vrai appui long d'Android tourne autour
        // de 500 ms ; on prend un peu plus, parce qu'ici l'erreur est visible
        // (la pastille revient par-dessus l'ecran) et son annulation coute un
        // geste de plus.
        final int GARDE = 600;
        final int DERIVE = dp(c, 20);
        final Handler h = new Handler(Looper.getMainLooper());
        zone.setOnTouchListener(new View.OnTouchListener() {
            private final boolean[] armee = {false};
            private float x0, y0;
            private Runnable armer;

            private void relacher(View v) {
                if (armer != null) h.removeCallbacks(armer);
                armer = null;
                armee[0] = false;
                v.animate().cancel();
                v.setAlpha(0.12f);
            }

            public boolean onTouch(final View v, MotionEvent ev) {
                switch (ev.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        x0 = ev.getRawX();
                        y0 = ev.getRawY();
                        armee[0] = false;
                        // La montee d'opacite EST la jauge de charge : elle dure
                        // exactement le temps de garde.
                        v.setAlpha(0.12f);
                        v.animate().alpha(0.85f).setDuration(GARDE).start();
                        armer = new Runnable() {
                            public void run() {
                                armee[0] = true;
                                v.animate().cancel();
                                v.setAlpha(1f);
                                vibrer(c);
                            }
                        };
                        h.postDelayed(armer, GARDE);
                        return true;

                    case MotionEvent.ACTION_MOVE:
                        // Un pouce qui defile le long du bord traverse la zone
                        // sans vouloir rien ouvrir : au-dela de 20 dp, on lache.
                        if (!armee[0]
                                && (Math.abs(ev.getRawX() - x0) > DERIVE
                                 || Math.abs(ev.getRawY() - y0) > DERIVE)) {
                            relacher(v);
                        }
                        return true;

                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        boolean prete = armee[0];
                        relacher(v);
                        if (!prete) return true;
                        // 120 ms de retard : la pastille reparait APRES la fin
                        // du geste. Posee dans la foulee, elle recevait le
                        // relachement du meme doigt et ouvrait son menu dans
                        // l'elan.
                        h.postDelayed(new Runnable() {
                            public void run() {
                                ramener(c);
                            }
                        }, 120);
                        return true;
                }
                return true;
            }
        });

        try {
            wm.addView(zone, lp);
            vue = zone;
        } catch (Exception ignore) {
        }
    }

    /** Le petit coup sec qui dit « c'est arme, tu peux lacher ». */
    private static void vibrer(Context c) {
        try {
            Vibrator v = (Vibrator) c.getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null && v.hasVibrator()) {
                v.vibrate(VibrationEffect.createOneShot(18,
                        VibrationEffect.DEFAULT_AMPLITUDE));
            }
        } catch (Exception ignore) {
        }
    }

    /** Repose la pastille tout de suite, et previent hote-1 apres coup. */
    private static void ramener(Context c) {
        retirer(c);
        c.getSharedPreferences("bulle", Context.MODE_PRIVATE)
                .edit().putBoolean("masquee", false).apply();
        Bulle.restaurer(c);
        // Le garde tient son propre marqueur de masquage sur hote-1 : sans cet
        // avis, il continuerait de croire la pastille ecartee et cesserait de
        // la reposer si Android tuait le processus.
        Bulle.commande(c, "revenir");
    }

    /** Meme eclipse que la pastille : le cil ne doit pas marquer les apercus. */
    static synchronized void eclipser(long ms) {
        final View v = vue;
        if (v == null) return;
        try {
            v.setVisibility(View.INVISIBLE);
            v.postDelayed(new Runnable() {
                public void run() {
                    try { v.setVisibility(View.VISIBLE); } catch (Throwable t) { }
                }
            }, ms);
        } catch (Throwable t) { }
    }

    static synchronized void retirer(Context ctx) {
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
