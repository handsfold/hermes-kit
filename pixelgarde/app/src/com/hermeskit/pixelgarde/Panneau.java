package com.poste.pixelgarde;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

/**
 * La page « Apps » du panneau : une grille d'icones qu'on touche pour lancer.
 *
 * Remplace l'application Panels. La liste vit dans les preferences de la
 * bulle, sous la cle « apps » (paquets separes par des virgules) : elle se
 * modifie ici, au doigt, sans recompiler ni passer par hote-1.
 *
 * Trois etats : la grille, la grille en edition (un toucher RETIRE l'app),
 * le choix d'une app a ajouter. Chaque case est cliquable sur toute sa
 * surface : aucune zone morte entre l'icone et son nom.
 */
final class Panneau {

    /** Ce que le panneau demande a la bulle. */
    interface Hote {
        /** Lance l'app et referme le panneau. */
        void lancer(String paquet);

        /** L'etat a change : rejouer la page et remesurer la carte. */
        void rafraichir();

        int dp(float v);

        void tic(int ms);

        /** Le champ de recherche a besoin du clavier : la fenetre devient focalisable. */
        void clavier(boolean oui);
    }

    // Les 11 apps de Panels au 06/10/2026 (la lampe jaune est Keep, l'app
    // verte est LINE : lues sur la capture de USER).
    private static final String[] DEPART = {
            "com.grabtaxi.passenger",
            "com.digitalchemy.currencyconverter",
            "com.google.android.youtube",
            "com.android.chrome",
            "org.telegram.messenger",
            "com.google.android.keep",
            "com.dashlane",
            "com.google.android.apps.maps",
            "com.instagram.android",
            "jp.naver.line.android",
            "com.google.android.apps.translate",
    };

    private static final int COLONNES = 2;
    private static final long APPUI_LONG_MS = 450;

    private final Context ctx;
    private final Hote hote;
    private final SharedPreferences prefs;
    private final PackageManager pm;
    private final Handler main = new Handler(Looper.getMainLooper());

    private boolean edition = false;

    /** Les cases d'apps de la page courante : cibles du glisser-deposer. */
    private final ArrayList<View> casesApp = new ArrayList<View>();
    private final ArrayList<String> paquetsApp = new ArrayList<String>();
    private boolean choix = false;

    Panneau(Context ctx, SharedPreferences prefs, Hote hote) {
        this.ctx = ctx;
        this.prefs = prefs;
        this.hote = hote;
        this.pm = ctx.getPackageManager();
    }

    /** A l'ouverture du panneau : retour a la grille simple. */
    void reinitialiser() {
        edition = false;
        choix = false;
    }

    // ------------------------------------------------------------ la liste

    private List<String> lire() {
        String brut = prefs.getString("apps", null);
        ArrayList<String> l = new ArrayList<String>();
        if (brut == null) {
            Collections.addAll(l, DEPART);
            ecrire(l);
            return l;
        }
        for (String p : brut.split(",")) {
            if (p.length() > 0) l.add(p);
        }
        return l;
    }

    private void ecrire(List<String> l) {
        StringBuilder sb = new StringBuilder();
        for (String p : l) {
            if (sb.length() > 0) sb.append(',');
            sb.append(p);
        }
        prefs.edit().putString("apps", sb.toString()).apply();
    }

    private boolean installee(String paquet) {
        return pm.getLaunchIntentForPackage(paquet) != null;
    }

    private String nom(String paquet) {
        try {
            return pm.getApplicationLabel(pm.getApplicationInfo(paquet, 0)).toString();
        } catch (Exception e) {
            return paquet;
        }
    }

    // ------------------------------------------------------------ la page

    View page() {
        if (!choix) hote.clavier(false);
        return choix ? pageChoix() : pageGrille();
    }

    private View pageGrille() {
        LinearLayout col = new LinearLayout(ctx);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(hote.dp(6), hote.dp(4), hote.dp(6), hote.dp(2));
        col.setClipChildren(false);

        // Seules les apps installees comptent : une app desinstallee reste
        // dans la liste (elle reparait si elle revient) mais n'occupe pas
        // de case.
        final List<String> toutes = lire();
        final ArrayList<String> vues = new ArrayList<String>();
        for (String p : toutes) {
            if (installee(p)) vues.add(p);
        }

        // Hors edition la grille ne contient que les apps : le « + » ne prend
        // pas de place (USER, 2026-10-07). Il apparait avec l'edition, avec
        // « OK » ; seule une liste vide le montre, sinon on ne pourrait rien
        // ajouter.
        casesApp.clear();
        paquetsApp.clear();
        int cases = vues.size() + (edition ? 2 : vues.isEmpty() ? 1 : 0);
        LinearLayout rangee = null;
        for (int i = 0; i < cases; i++) {
            if (i % COLONNES == 0) {
                rangee = new LinearLayout(ctx);
                rangee.setOrientation(LinearLayout.HORIZONTAL);
                rangee.setClipChildren(false);
                col.addView(rangee, new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT, hote.dp(edition ? 108 : 80)));
            }
            View c = i < vues.size() ? caseApp(vues.get(i))
                    : caseAjout(edition && i == vues.size() + 1);
            rangee.addView(c, new LinearLayout.LayoutParams(0, hote.dp(edition ? 108 : 80), 1f));
        }
        // Complete la derniere rangee pour que les cases gardent la meme largeur.
        int reste = rangee == null ? 0 : (COLONNES - cases % COLONNES) % COLONNES;
        for (int i = 0; i < reste; i++) {
            rangee.addView(new View(ctx), new LinearLayout.LayoutParams(0, hote.dp(edition ? 108 : 80), 1f));
        }
        return col;
    }

    /** Une app : icone, nom dessous. Toute la case repond au toucher. */
    private View caseApp(final String paquet) {
        LinearLayout c = new LinearLayout(ctx);
        c.setOrientation(LinearLayout.VERTICAL);
        c.setGravity(Gravity.CENTER_HORIZONTAL);
        c.setPadding(hote.dp(2), hote.dp(6), hote.dp(2), hote.dp(4));
        final GradientDrawable f = new GradientDrawable();
        f.setShape(GradientDrawable.RECTANGLE);
        f.setCornerRadius(hote.dp(Charte.RAYON_TUILE));
        f.setColor(android.graphics.Color.TRANSPARENT);
        c.setBackground(f);

        // L'icone dans un cadre : la pastille « retirer » se pose sur son coin.
        android.widget.FrameLayout cadre = new android.widget.FrameLayout(ctx);
        ImageView ic = new ImageView(ctx);
        try {
            ic.setImageDrawable(pm.getApplicationIcon(paquet));
        } catch (Exception ignore) {
        }
        cadre.addView(ic, new android.widget.FrameLayout.LayoutParams(
                hote.dp(56), hote.dp(56), Gravity.CENTER));
        if (edition) {
            TextView moins = new TextView(ctx);
            moins.setText("-");
            moins.setGravity(Gravity.CENTER);
            moins.setTextColor(android.graphics.Color.WHITE);
            moins.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
            moins.setTypeface(Charte.policeMedium());
            GradientDrawable rond = new GradientDrawable();
            rond.setShape(GradientDrawable.OVAL);
            rond.setColor(Charte.ROUGE);
            moins.setBackground(rond);
            android.widget.FrameLayout.LayoutParams mp =
                    new android.widget.FrameLayout.LayoutParams(
                            hote.dp(18), hote.dp(18), Gravity.TOP | Gravity.END);
            moins.setLayoutParams(mp);
            cadre.addView(moins);
        }
        c.addView(cadre, new LinearLayout.LayoutParams(hote.dp(60), hote.dp(60)));

        TextView t = new TextView(ctx);
        t.setText(nom(paquet));
        t.setTextColor(Charte.TEXTE_2);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        t.setTypeface(Charte.police());
        t.setGravity(Gravity.CENTER);
        t.setMaxLines(2);
        t.setEllipsize(android.text.TextUtils.TruncateAt.END);
        t.setLineSpacing(0, 0.92f);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        tp.topMargin = hote.dp(3);
        // Comme Panels : l'icone seule. Le nom ne sert qu'en edition, pour
        // savoir quelle app on retire.
        if (edition) c.addView(t, tp);
        else c.setGravity(Gravity.CENTER);
        if (!edition) c.setTag("app:" + paquet);
        casesApp.add(c);
        paquetsApp.add(paquet);

        brancher(c, f, new Runnable() {
            public void run() {
                if (edition) {
                    retirer(paquet);
                } else {
                    hote.lancer(paquet);
                }
            }
        }, null, paquet);
        return c;
    }

    /** « + » (ajouter) ou « OK » (terminer l'edition, `termine`). */
    private View caseAjout(final boolean termine) {
        LinearLayout c = new LinearLayout(ctx);
        c.setOrientation(LinearLayout.VERTICAL);
        c.setGravity(Gravity.CENTER_HORIZONTAL);
        c.setPadding(hote.dp(2), hote.dp(6), hote.dp(2), hote.dp(4));
        final GradientDrawable f = new GradientDrawable();
        f.setShape(GradientDrawable.RECTANGLE);
        f.setCornerRadius(hote.dp(Charte.RAYON_TUILE));
        f.setColor(android.graphics.Color.TRANSPARENT);
        c.setBackground(f);

        TextView plus = new TextView(ctx);
        plus.setText(termine ? "OK" : "+");
        plus.setGravity(Gravity.CENTER);
        plus.setTextColor(termine ? Charte.TEXTE_SUR_ACCENT : Charte.TEXTE);
        plus.setTextSize(TypedValue.COMPLEX_UNIT_SP, termine ? 14 : 22);
        plus.setTypeface(Charte.policeMedium());
        GradientDrawable rond = new GradientDrawable();
        rond.setShape(GradientDrawable.RECTANGLE);
        rond.setCornerRadius(hote.dp(11));
        rond.setColor(termine ? Charte.VERT : Charte.SURFACE);
        plus.setBackground(rond);
        LinearLayout.LayoutParams pp = new LinearLayout.LayoutParams(hote.dp(56), hote.dp(56));
        pp.topMargin = hote.dp(2);
        pp.bottomMargin = hote.dp(2);
        c.addView(plus, new LinearLayout.LayoutParams(pp));

        TextView t = new TextView(ctx);
        t.setText(Langue.t(ctx, termine ? R.string.panneau_termine : R.string.panneau_ajouter));
        t.setTextColor(Charte.TEXTE_2);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        t.setTypeface(Charte.police());
        t.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        tp.topMargin = hote.dp(3);
        if (edition) c.addView(t, tp);
        else c.setGravity(Gravity.CENTER);

        brancher(c, f, new Runnable() {
            public void run() {
                if (termine) {
                    edition = false;
                } else {
                    choix = true;
                }
                hote.rafraichir();
            }
        }, null, null);
        return c;
    }

    private void retirer(String paquet) {
        List<String> l = lire();
        l.remove(paquet);
        ecrire(l);
        hote.tic(Charte.TIC_CONFIRME);
        hote.rafraichir();
    }

    // -------------------------------------------------------- le choix

    private View pageChoix() {
        LinearLayout col = new LinearLayout(ctx);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(hote.dp(6), hote.dp(2), hote.dp(6), hote.dp(2));

        // Le retour, en haut : on ne descend pas pour remonter.
        LinearLayout dos = new LinearLayout(ctx);
        dos.setGravity(Gravity.CENTER_VERTICAL);
        dos.setPadding(hote.dp(10), 0, hote.dp(10), 0);
        final GradientDrawable fd = new GradientDrawable();
        fd.setShape(GradientDrawable.RECTANGLE);
        fd.setCornerRadius(hote.dp(Charte.RAYON_LIGNE));
        fd.setColor(android.graphics.Color.TRANSPARENT);
        dos.setBackground(fd);
        TextView td = new TextView(ctx);
        td.setText(Langue.t(ctx, R.string.panneau_ajouter_app));
        td.setTextColor(Charte.TEXTE);
        td.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_LIGNE);
        td.setTypeface(Charte.policeMedium());
        dos.addView(td);
        col.addView(dos, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, hote.dp(44)));
        brancher(dos, fd, new Runnable() {
            public void run() {
                choix = false;
                hote.rafraichir();
            }
        }, null, null);

        // Les apps lancables pas encore dans la grille, par ordre alphabetique.
        final List<String> deja = lire();
        Intent q = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        ArrayList<String[]> dispo = new ArrayList<String[]>();
        for (ResolveInfo ri : pm.queryIntentActivities(q, 0)) {
            String p = ri.activityInfo.packageName;
            if (p.equals(ctx.getPackageName()) || deja.contains(p)) continue;
            boolean doublon = false;
            for (String[] d : dispo) if (d[0].equals(p)) doublon = true;
            if (doublon) continue;
            dispo.add(new String[]{p, ri.loadLabel(pm).toString()});
        }
        Collections.sort(dispo, new Comparator<String[]>() {
            public int compare(String[] a, String[] b) {
                return a[1].compareToIgnoreCase(b[1]);
            }
        });

        // Recherche : filtre la liste sur place (la page n'est pas rebatie,
        // le champ garde le clavier).
        final EditText champ = new EditText(ctx);
        champ.setHint(Langue.t(ctx, R.string.panneau_chercher));
        champ.setHintTextColor(Charte.TEXTE_2);
        champ.setTextColor(Charte.TEXTE);
        champ.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_LIGNE);
        champ.setTypeface(Charte.police());
        champ.setSingleLine(true);
        champ.setImeOptions(android.view.inputmethod.EditorInfo.IME_ACTION_DONE
                | android.view.inputmethod.EditorInfo.IME_FLAG_NO_EXTRACT_UI);
        champ.setInputType(android.text.InputType.TYPE_CLASS_TEXT
                | android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        champ.setPadding(hote.dp(12), 0, hote.dp(12), 0);
        GradientDrawable fc = new GradientDrawable();
        fc.setShape(GradientDrawable.RECTANGLE);
        fc.setCornerRadius(hote.dp(Charte.RAYON_LIGNE));
        fc.setColor(Charte.SURFACE);
        champ.setBackground(fc);
        LinearLayout.LayoutParams chp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, hote.dp(44));
        chp.topMargin = hote.dp(2);
        chp.bottomMargin = hote.dp(4);
        chp.leftMargin = chp.rightMargin = hote.dp(4);
        col.addView(champ, chp);
        // Un toucher sur le champ rend la fenetre focalisable puis ouvre le clavier.
        champ.setOnTouchListener(new View.OnTouchListener() {
            public boolean onTouch(View v, MotionEvent ev) {
                if (ev.getAction() == MotionEvent.ACTION_DOWN) {
                    hote.clavier(true);
                    main.postDelayed(new Runnable() {
                        public void run() {
                            champ.requestFocus();
                            android.view.inputmethod.InputMethodManager im =
                                    (android.view.inputmethod.InputMethodManager)
                                            ctx.getSystemService(Context.INPUT_METHOD_SERVICE);
                            if (im != null) im.showSoftInput(champ, 0);
                        }
                    }, 150);
                }
                return false;
            }
        });
        champ.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            public boolean onEditorAction(TextView v, int action, android.view.KeyEvent e) {
                hote.clavier(false);
                return true;
            }
        });

        final LinearLayout liste = new LinearLayout(ctx);
        liste.setOrientation(LinearLayout.VERTICAL);
        final ArrayList<String[]> dispoF = dispo;
        champ.addTextChangedListener(new android.text.TextWatcher() {
            public void beforeTextChanged(CharSequence c, int a, int b, int n) { }
            public void onTextChanged(CharSequence c, int a, int b, int n) { }
            public void afterTextChanged(android.text.Editable e) {
                remplirChoix(liste, dispoF, e.toString());
            }
        });
        remplirChoix(liste, dispo, "");
        // Une liste de 100 apps ne tient pas : elle defile. Le retour reste
        // au-dessus, hors du defilement.
        ScrollView sv = new ScrollView(ctx);
        sv.setVerticalScrollBarEnabled(false);
        sv.setOverScrollMode(View.OVER_SCROLL_NEVER);
        sv.addView(liste);
        col.addView(sv, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, hote.dp(300)));
        return col;
    }

    /** Remplit la liste des apps a ajouter, filtree par `filtre` (nom contenant). */
    private void remplirChoix(LinearLayout liste, List<String[]> dispo, String filtre) {
        liste.removeAllViews();
        String cle = sansAccent(filtre);
        for (final String[] d : dispo) {
            if (cle.length() > 0 && !sansAccent(d[1]).contains(cle)) continue;
            LinearLayout l = new LinearLayout(ctx);
            l.setGravity(Gravity.CENTER_VERTICAL);
            l.setPadding(hote.dp(10), 0, hote.dp(10), 0);
            final GradientDrawable f = new GradientDrawable();
            f.setShape(GradientDrawable.RECTANGLE);
            f.setCornerRadius(hote.dp(Charte.RAYON_LIGNE));
            f.setColor(android.graphics.Color.TRANSPARENT);
            l.setBackground(f);
            ImageView ic = new ImageView(ctx);
            try {
                ic.setImageDrawable(pm.getApplicationIcon(d[0]));
            } catch (Exception ignore) {
            }
            LinearLayout.LayoutParams ip = new LinearLayout.LayoutParams(hote.dp(30), hote.dp(30));
            ip.rightMargin = hote.dp(12);
            l.addView(ic, ip);
            TextView t = new TextView(ctx);
            t.setText(d[1]);
            t.setTextColor(Charte.TEXTE);
            t.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_LIGNE);
            t.setTypeface(Charte.police());
            t.setSingleLine(true);
            t.setEllipsize(android.text.TextUtils.TruncateAt.END);
            l.addView(t);
            liste.addView(l, new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, hote.dp(46)));
            brancher(l, f, new Runnable() {
                public void run() {
                    List<String> l2 = lire();
                    l2.add(d[0]);
                    ecrire(l2);
                    choix = false;
                    hote.tic(Charte.TIC_CONFIRME);
                    hote.rafraichir();
                }
            }, null, null);
        }
        if (liste.getChildCount() == 0) {
            TextView vide = new TextView(ctx);
            vide.setText(Langue.t(ctx, R.string.panneau_aucune));
            vide.setTextColor(Charte.TEXTE_2);
            vide.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_LIGNE);
            vide.setTypeface(Charte.police());
            vide.setPadding(hote.dp(10), hote.dp(12), hote.dp(10), 0);
            liste.addView(vide);
        }
    }

    private static String sansAccent(String t) {
        String n = java.text.Normalizer.normalize(t, java.text.Normalizer.Form.NFD);
        return n.replaceAll("\\p{M}+", "").toLowerCase(java.util.Locale.ROOT).trim();
    }

    // ------------------------------------------------------------ le deplacement

    /** La case d'app sous le doigt (coordonnees ecran), hors la case portee. */
    private View caseSous(float x, float y, View portee) {
        int[] xy = new int[2];
        for (View c : casesApp) {
            if (c == portee) continue;
            c.getLocationOnScreen(xy);
            if (x >= xy[0] && x <= xy[0] + c.getWidth()
                    && y >= xy[1] && y <= xy[1] + c.getHeight()) {
                return c;
            }
        }
        return null;
    }

    private void surligner(View c, boolean oui) {
        if (c == null) return;
        if (c.getBackground() instanceof GradientDrawable) {
            ((GradientDrawable) c.getBackground()).setColor(
                    oui ? Charte.SURLIGNE : android.graphics.Color.TRANSPARENT);
        }
    }

    /** Echange 2 apps dans la liste complete (apps absentes comprises). */
    private void echanger(String a, String b) {
        List<String> toutes = lire();
        int i = toutes.indexOf(a);
        int j = toutes.indexOf(b);
        if (i < 0 || j < 0) return;
        Collections.swap(toutes, i, j);
        ecrire(toutes);
    }

    // ------------------------------------------------------------ le toucher

    /**
     * Toucher / appui long, sur toute la surface de la vue.
     *
     * Le toucher agit au relachement, a condition que le doigt soit reste
     * dans la vue (meme geste que les lignes du menu). Un glissement vertical
     * rend la main au parent : la liste defile sans lancer d'app.
     */
    private void brancher(final View v, final GradientDrawable f,
                          final Runnable action, final Runnable appuiLong,
                          final String paquet) {
        final boolean[] enCours = {false};
        // Glisser-deposer d'une app (paquet != null) : l'appui long souleve
        // la case, le doigt la porte, le relachement l'echange avec la case
        // visee. Le meme listener recoit tout le geste, meme hors de la case.
        final boolean[] drag = {false};
        final View[] cible = {null};
        final float[] raw = new float[2];
        final Runnable declencheLong = new Runnable() {
            public void run() {
                if (!enCours[0]) return;
                enCours[0] = false;
                f.setColor(android.graphics.Color.TRANSPARENT);
                if (paquet != null) {
                    drag[0] = true;
                    hote.tic(Charte.TIC_GESTE);
                    if (v.getParent() != null) {
                        v.getParent().requestDisallowInterceptTouchEvent(true);
                    }
                    v.animate().scaleX(1.15f).scaleY(1.15f).alpha(0.85f)
                            .setDuration(Charte.PRESSE_MS).start();
                    return;
                }
                v.animate().scaleX(1f).scaleY(1f).setDuration(Charte.PRESSE_MS).start();
                if (appuiLong != null) appuiLong.run();
            }
        };
        final float[] depart = new float[2];
        v.setOnTouchListener(new View.OnTouchListener() {
            public boolean onTouch(View vue, MotionEvent ev) {
                switch (ev.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        enCours[0] = true;
                        depart[0] = ev.getX();
                        depart[1] = ev.getY();
                        raw[0] = ev.getRawX();
                        raw[1] = ev.getRawY();
                        drag[0] = false;
                        f.setColor(Charte.SURLIGNE);
                        vue.animate().scaleX(0.96f).scaleY(0.96f)
                                .setDuration(Charte.PRESSE_MS).start();
                        if (appuiLong != null || paquet != null) {
                            main.postDelayed(declencheLong, APPUI_LONG_MS);
                        }
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        if (drag[0]) {
                            vue.setTranslationX(ev.getRawX() - raw[0]);
                            vue.setTranslationY(ev.getRawY() - raw[1]);
                            View vise = caseSous(ev.getRawX(), ev.getRawY(), vue);
                            if (vise != cible[0]) {
                                surligner(cible[0], false);
                                cible[0] = vise;
                                surligner(vise, true);
                            }
                            return true;
                        }
                        if (!enCours[0]) return true;
                        if (Math.abs(ev.getY() - depart[1]) > hote.dp(10)
                                || Math.abs(ev.getX() - depart[0]) > hote.dp(10)) {
                            enCours[0] = false;
                            main.removeCallbacks(declencheLong);
                            f.setColor(android.graphics.Color.TRANSPARENT);
                            vue.animate().scaleX(1f).scaleY(1f)
                                    .setDuration(Charte.PRESSE_MS).start();
                            if (vue.getParent() != null) {
                                vue.getParent().requestDisallowInterceptTouchEvent(false);
                            }
                            return false;
                        }
                        return true;
                    case MotionEvent.ACTION_UP:
                        main.removeCallbacks(declencheLong);
                        if (drag[0]) {
                            drag[0] = false;
                            View vise = cible[0];
                            cible[0] = null;
                            surligner(vise, false);
                            vue.setTranslationX(0);
                            vue.setTranslationY(0);
                            vue.setScaleX(1f);
                            vue.setScaleY(1f);
                            vue.setAlpha(1f);
                            if (vise != null) {
                                int a = casesApp.indexOf(vue);
                                int b = casesApp.indexOf(vise);
                                if (a >= 0 && b >= 0) {
                                    echanger(paquetsApp.get(a), paquetsApp.get(b));
                                    hote.tic(Charte.TIC_CONFIRME);
                                }
                            }
                            // Le mode deplacement reste ouvert : « + » et « OK » y paraissent.
                            edition = true;
                            hote.rafraichir();
                            return true;
                        }
                        f.setColor(android.graphics.Color.TRANSPARENT);
                        vue.animate().scaleX(1f).scaleY(1f)
                                .setDuration(Charte.PRESSE_MS).start();
                        if (enCours[0] && ev.getX() >= 0 && ev.getX() <= vue.getWidth()
                                && ev.getY() >= 0 && ev.getY() <= vue.getHeight()) {
                            enCours[0] = false;
                            action.run();
                        }
                        enCours[0] = false;
                        return true;
                    case MotionEvent.ACTION_CANCEL:
                        enCours[0] = false;
                        main.removeCallbacks(declencheLong);
                        if (drag[0]) {
                            drag[0] = false;
                            surligner(cible[0], false);
                            cible[0] = null;
                            vue.setTranslationX(0);
                            vue.setTranslationY(0);
                            vue.setAlpha(1f);
                        }
                        f.setColor(android.graphics.Color.TRANSPARENT);
                        vue.animate().scaleX(1f).scaleY(1f)
                                .setDuration(Charte.PRESSE_MS).start();
                        return true;
                }
                return true;
            }
        });
    }
}
