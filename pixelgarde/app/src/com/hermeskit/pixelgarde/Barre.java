package com.poste.pixelgarde;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.RectF;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.WindowManager;

import java.util.Collections;

/**
 * La barre laterale : une poignee contre le bord droit, qu'on tire vers
 * l'interieur pour faire venir le panneau. Elle prend la place de l'app
 * Panels, dont elle reprend les mesures relevees sur le Pixel de USER.
 *
 * Mesures de Panels : zone tactile 24 dp x 171 dp, centre a 44 % de la
 * hauteur ; trait visible de 4 dp, gris translucide ; seuil de glisse de
 * 8 dp ; retour haptique une fois par geste ; exclusion du geste Retour du
 * systeme sur le bord.
 *
 * « Glisser et tenir » : le panneau suit le doigt ; si le doigt reste 90 ms
 * panneau ouvert, puis passe sur une icone et se leve, l'app se lance. Se
 * lever ailleurs laisse le panneau ouvert.
 */
final class Barre {

    private static final float LARGEUR = 24;
    private static final float HAUTEUR = 171;
    private static final float TRAIT = 4;
    private static final float TRAIT_LONG = 100;
    private static final float SEUIL = 8;
    private static final long TENUE_MS = 90;

    private static Barre vivante;

    private final Context ctx;
    private final WindowManager wm;
    private final Bulle bulle;
    private final View vue;
    private final WindowManager.LayoutParams lp;

    private float x0, y0, dernX;
    private long dernT;
    private float vitesse;
    private boolean glisse;
    private long pleinDepuis;

    private Barre(Context c, Bulle b) {
        ctx = c;
        bulle = b;
        wm = (WindowManager) c.getSystemService(Context.WINDOW_SERVICE);
        final float d = c.getResources().getDisplayMetrics().density;
        final Paint peinture = new Paint(Paint.ANTI_ALIAS_FLAG);
        peinture.setColor(0x99A8A8B0);
        vue = new View(c) {
            @Override
            protected void onDraw(Canvas cv) {
                float l = TRAIT * d;
                float h = Math.min(getHeight(), TRAIT_LONG * d);
                float haut = (getHeight() - h) / 2f;
                // Arrondi cote interieur seulement : le trait sort du bord.
                RectF r = new RectF(getWidth() - l, haut, getWidth() + l, haut + h);
                cv.drawRoundRect(r, l, l, peinture);
            }
        };
        vue.setOnTouchListener(new View.OnTouchListener() {
            public boolean onTouch(View v, MotionEvent e) {
                return toucher(v, e);
            }
        });
        vue.addOnLayoutChangeListener(new View.OnLayoutChangeListener() {
            public void onLayoutChange(View v, int l, int t, int r, int b,
                                       int ol, int ot, int or, int ob) {
                // Le geste Retour du systeme part aussi du bord : on lui
                // retire la zone de la poignee, 200 dp de haut au plus.
                if (android.os.Build.VERSION.SDK_INT >= 29) {
                    try {
                        v.setSystemGestureExclusionRects(Collections.singletonList(
                                new Rect(0, 0, r - l, Math.min(b - t, Math.round(200 * d)))));
                    } catch (Throwable ignore) {
                    }
                }
            }
        });
        int ecranL = ecranL();
        int ecranH = ecranH();
        lp = new WindowManager.LayoutParams(
                Math.round(LARGEUR * d), Math.round(HAUTEUR * d),
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.x = ecranL - lp.width;
        lp.y = Math.round(ecranH * 0.44f) - lp.height / 2;
    }

    private int ecranL() {
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            try {
                return wm.getCurrentWindowMetrics().getBounds().width();
            } catch (Throwable ignore) {
            }
        }
        return ctx.getResources().getDisplayMetrics().widthPixels;
    }

    private int ecranH() {
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            try {
                return wm.getCurrentWindowMetrics().getBounds().height();
            } catch (Throwable ignore) {
            }
        }
        return ctx.getResources().getDisplayMetrics().heightPixels;
    }

    /** Pose la barre. Sans effet si elle y est deja. */
    static void montrer(Context c, Bulle b) {
        if (vivante != null) return;
        Barre n = new Barre(c, b);
        try {
            n.wm.addView(n.vue, n.lp);
            vivante = n;
        } catch (Exception ignore) {
        }
    }

    /** Remet la barre a sa place (rotation de l'ecran). */
    static void replacer() {
        Barre b = vivante;
        if (b == null) return;
        b.lp.x = b.ecranL() - b.lp.width;
        b.lp.y = Math.round(b.ecranH() * 0.44f) - b.lp.height / 2;
        try {
            b.wm.updateViewLayout(b.vue, b.lp);
        } catch (Exception ignore) {
        }
    }

    static void retirer() {
        Barre b = vivante;
        vivante = null;
        if (b == null) return;
        try {
            b.wm.removeView(b.vue);
        } catch (Exception ignore) {
        }
    }

    private boolean toucher(View v, MotionEvent e) {
        float seuil = Math.max(ViewConfiguration.get(ctx).getScaledTouchSlop(),
                SEUIL * ctx.getResources().getDisplayMetrics().density);
        float largeurCarte = bulle.barreLargeur();
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                x0 = dernX = e.getRawX();
                y0 = e.getRawY();
                dernT = SystemClock.uptimeMillis();
                vitesse = 0;
                glisse = false;
                pleinDepuis = 0;
                return true;

            case MotionEvent.ACTION_MOVE: {
                // Vers l'interieur = vers la gauche : dx positif.
                float dx = x0 - e.getRawX();
                float dy = Math.abs(e.getRawY() - y0);
                long t = SystemClock.uptimeMillis();
                if (t > dernT) {
                    vitesse = (dernX - e.getRawX()) / (t - dernT);   // px par ms
                    dernX = e.getRawX();
                    dernT = t;
                }
                if (!glisse) {
                    if (dx < seuil || dx <= dy) return true;
                    glisse = true;
                    v.performHapticFeedback(1);
                    bulle.barreDebut();
                }
                if (pleinDepuis == 0) {
                    bulle.barreSuit(dx);
                    if (dx >= largeurCarte) pleinDepuis = t;
                } else if (t - pleinDepuis >= TENUE_MS) {
                    // Panneau ouvert et verrouille : le doigt choisit une icone.
                    bulle.barreSurvol(e.getRawX(), e.getRawY());
                }
                return true;
            }

            case MotionEvent.ACTION_UP: {
                if (!glisse) return true;
                glisse = false;
                float dx = x0 - e.getRawX();
                // Doigt pose sur une icone apres la tenue : on la lance.
                if (pleinDepuis != 0 && SystemClock.uptimeMillis() - pleinDepuis >= TENUE_MS
                        && bulle.barreRelache(e.getRawX(), e.getRawY())) {
                    return true;
                }
                boolean ouvrir = pleinDepuis != 0 || dx > largeurCarte * 0.3f || vitesse > 0.6f;
                if (pleinDepuis == 0 && vitesse < -0.6f) ouvrir = false;
                bulle.barreFin(ouvrir);
                return true;
            }

            case MotionEvent.ACTION_CANCEL:
                if (glisse) {
                    glisse = false;
                    bulle.barreFin(false);
                }
                return true;
        }
        return false;
    }
}
