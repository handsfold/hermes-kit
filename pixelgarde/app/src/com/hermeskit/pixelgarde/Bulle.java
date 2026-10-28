package com.poste.pixelgarde;

import android.animation.ArgbEvaluator;
import android.animation.ValueAnimator;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.FileObserver;
import android.os.Handler;
import android.os.SystemClock;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.util.DisplayMetrics;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.animation.AccelerateInterpolator;
import android.view.animation.DecelerateInterpolator;
import android.view.animation.OvershootInterpolator;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;

/**
 * La pastille flottante : un menu d'actions pose par-dessus toutes les apps.
 *
 * Pourquoi pas un Service : depuis Android 14, demarrer un service de premier
 * plan depuis un BroadcastReceiver en arriere-plan leve
 * BackgroundServiceStartNotAllowedException. Une vue d'overlay, elle, s'ajoute
 * directement depuis onReceive, et le systeme monte l'importance du processus
 * qui en detient une (hasOverlayUi). Le garde rediffuse toutes les 2 min, ce
 * qui la repose si Android a fini par tuer le processus.
 *
 * Le contenu du menu n'est PAS code ici : il arrive dans l'extra "menu" sous la
 * forme "id:Libelle|id2:Libelle". Ajouter un bouton = editer menu.txt sur hote-1,
 * jamais recompiler.
 */
public class Bulle {

    private static Bulle vivante;

    private final Context ctx;
    private final WindowManager wm;
    private final DisplayMetrics dm;
    private final Handler h = new Handler(Looper.getMainLooper());
    private final SharedPreferences prefs;

    private LinearLayout racine;
    /** La pastille : un TextView dont Tete surcharge le dessin. */
    private Tete pastille;
    private FrameLayout menu;
    /** Le voile noir du panneau lateral et la case surlignee par la barre. */
    private View voile;
    private View caseSurvol;
    private android.graphics.drawable.Drawable caseSurvolFond;
    private int carteL;
    /** La carte dessinee, a l'interieur de menu, qui n'est qu'un cadre a ombre. */
    private LinearLayout carteVue;
    /** Page du panneau : 0 = Apps, 1 = Creeper. */
    private int page = 0;
    private Panneau panneau;
    private WindowManager.LayoutParams lp;
    private WindowManager.LayoutParams lpMenu;
    /** Instant du dernier repli declenche par un appui hors du menu. */
    private long fermeDehors;
    /** Taille mesuree du menu ouvert, pour le faire suivre pendant un glisser. */
    private int menuL, menuH;

    private boolean ouvert;
    /** Taille d'ecran du dernier placement, pour detecter une rotation. */
    private int dernL, dernH;
    /** veille | pilote | attente | suspendu. Voir peindrePastille(). */
    private String etat = "veille";
    /**
     * Les deux libelles du bouton d'etat, poses par hote-1 (actions/etat.txt).
     *
     * L'appli en a besoin des DEUX : quand USER met en pause depuis la pastille,
     * elle doit retourner le bouton sur-le-champ, sans attendre que la station
     * lui renvoie le libelle inverse.
     */
    private String tetePause = "stop:Mettre en pause";
    private String teteReprise = "go:Reprendre";
    /** auto | rond | barre. En auto, seule une action reelle fait un rond. */
    private String forme = "auto";
    private int xAncre, yAncre;
    private String[][] entrees = new String[0][];
    /**
     * Vrai quand un appui est parti vers hote-1 sans reponse.
     *
     * Le 31/08/2026 le lien adb est tombe pendant une demi-heure. USER appuyait
     * sur Reprendre, la pastille ne bougeait pas, et rien sur le telephone ne
     * disait pourquoi : il a fallu lire les journaux de hote-1 pour l'apprendre.
     * Un blocage doit se nommer la ou il se voit.
     */
    private boolean lienMuet;
    /** Delai au-dela duquel un appui sans reponse est declare perdu. */
    private static final long PATIENCE_MS = 20000;

    private static final int VERT = Charte.VERT;      // je pilote
    private static final int GRIS = Charte.GRIS;      // repos, personne n'agit
    private static final int AMBRE = Charte.AMBRE;     // tu as la main, j'attends
    private static final int ORANGE = Charte.ORANGE;    // arret d'urgence
    private static final int BLEU = Charte.BLEU;      // on se parle
    private static final int ROUGE = Charte.ROUGE;     // l'ecran est enregistre
    private static final int ARDOISE = Charte.CARTE;   // fond de la carte
    private static final int SURLIGNE = Charte.SURLIGNE;  // appui sur une ligne
    private static final int TRAIT = Charte.TRAIT;     // separateur
    private static final int TEXTE = Charte.TEXTE;
    private static final int SOURDINE = Charte.TEXTE_2;  // libelles secondaires

    /** Couleur reellement peinte : elle rejoint la cible par un fondu. */
    private int couleurAffichee = GRIS;
    private ValueAnimator fondu;
    /** Forme au dernier trace, pour n'animer que les vrais changements. */
    private boolean etaitDiscret = true;

    /** Zone tactile, invisible : elle ne change jamais, le dessin oui. */
    private static final float TOUCHE_L = 58, TOUCHE_H = 64;
    private static final float ROND = 46;
    private static final float BARRE_L = 4, BARRE_H = 34;
    /** Marge transparente autour de la carte, pour que son ombre tienne. */
    private static final float MARGE = 12;
    /**
     * Espace VISIBLE entre le bord du rond et le bord de la carte.
     *
     * A ne pas confondre avec MARGE, qui est du vide transparent porte par la
     * fenetre du menu. L'ecart se calcule depuis le ROND, pas depuis la
     * fenetre de la pastille : celle-ci fait TOUCHE_L de large pour rester
     * attrapable au doigt, et viser son bord ajoutait la difference des deux
     * en pur vide. C'est ce qui faisait paraitre le menu detache.
     */
    private static final float ECART = 3;
    /** Largeur de la carte du menu. Voir ouvrir() : elle ne peut pas etre libre. */
    // Elargie de 212 a 236 le 27/08/2026 : une ligne de reglage porte un titre
    // ET sa valeur, et a 212 le titre se faisait rogner sa derniere lettre.
    private static final float CARTE_L = 248;
    /** Largeur de la carte sur la page Apps : etroite et haute, comme Panels. */
    private static final float CARTE_APPS = 184;

    private Bulle(Context c) {
        ctx = c.getApplicationContext();
        wm = (WindowManager) ctx.getSystemService(Context.WINDOW_SERVICE);
        dm = ctx.getResources().getDisplayMetrics();
        prefs = ctx.getSharedPreferences("bulle", Context.MODE_PRIVATE);
        appliquerTetes(prefs.getString("tetes", null));
        purgerApercusMorts();
    }

    /**
     * Jette une seule fois le dossier files/apercus, laisse par la grille des
     * applications recentes retiree le 2026-08-30. Plus rien ne l'alimente ni
     * ne le lit : sans ce coup de balai il resterait indefiniment sur le
     * telephone, et `adb run-as` ne peut pas l'effacer, l'APK n'etant pas
     * debuggable. C'est donc l'application qui nettoie derriere elle.
     */
    private void purgerApercusMorts() {
        if (prefs.getBoolean("apercus_morts_purges", false)) return;
        try {
            java.io.File d = new java.io.File(ctx.getFilesDir(), "apercus");
            java.io.File[] fs = d.listFiles();
            if (fs != null) for (java.io.File f : fs) f.delete();
            d.delete();
        } catch (Throwable t) { /* rien a sauver ici */ }
        prefs.edit().putBoolean("apercus_morts_purges", true).apply();
    }

    private void appliquerTetes(String tetes) {
        if (tetes == null || tetes.length() == 0) return;
        String[] d = tetes.split("\\|");
        if (d.length < 2) return;
        tetePause = d[0];
        teteReprise = d[1];
        prefs.edit().putString("tetes", tetes).apply();
    }

    /** Point d'entree unique : cree la bulle si besoin, sinon la rafraichit. */
    public static void poser(Context c, String etat, String menuBrut, String forme) {
        poser(c, etat, menuBrut, forme, null);
    }

    public static void poser(Context c, String etat, String menuBrut, String forme,
                             String tetes) {
        // Masquage de USER : rien ne repose une fenetre, pas meme hote-1.
        if (eteinte(c)) return;
        if (vivante == null) {
            vivante = new Bulle(c);
            vivante.construire();
        }
        vivante.appliquerTetes(tetes);
        vivante.signeDeVie();
        vivante.rafraichir(etat, menuBrut, forme);
        Poignee.retirer(c);
        memoire(c).edit().putBoolean("masquee", false).apply();
    }

    /**
     * Masquage par USER : TOUT s'eteint. Plus de pastille, de barre, de cil, de
     * cadre ni de voile. Les applications bancaires refusent de tourner quand
     * un overlay est affiche (USER, 2026-10-06). Le retour passe par l'icone
     * du lanceur (Reveil), seule porte qui ne depend ni du reseau ni de hote-1.
     */
    public static void masquer(Context c) {
        memoire(c).edit().putBoolean("masquee", true)
                .putBoolean("eteinte", true).commit();
        Poignee.retirer(c);
        if (vivante != null) {
            vivante.detruire();
            vivante = null;
        }
        Cadre.cacher(c);
        Filtre.peindre(c, 0);
    }

    /** Vrai apres un masquage voulu par USER : aucune fenetre ne doit se poser. */
    public static boolean eteinte(Context c) {
        return c != null && memoire(c).getBoolean("eteinte", false);
    }

    /** Defait masquer() : appele par l'icone du lanceur. */
    public static void reveiller(Context c) {
        memoire(c).edit().putBoolean("eteinte", false)
                .putBoolean("masquee", false).commit();
        restaurer(c);
        Filtre.restaurer(c);
        // Le garde tient son propre marqueur de masquage sur hote-1.
        commande(c, "revenir");
    }

    public static void retirer(Context c) {
        Poignee.retirer(c);
        if (vivante != null) {
            vivante.detruire();
            vivante = null;
        }
        // Masquage VOULU : il doit survivre au redemarrage, sinon le receveur
        // de demarrage ramenerait une pastille que USER vient d'ecarter.
        if (c != null) memoire(c).edit().putBoolean("masquee", true).apply();
    }

    /**
     * Efface la pastille le temps d'une capture d'ecran.
     *
     * takeScreenshot photographie TOUT ce qui est affiche, nos propres
     * overlays compris. Sans cette eclipse, chaque apercu de la grille portait
     * la pastille collee dans un coin, comme un defaut d'impression repete
     * quatre fois. On l'efface, on capture, on la remet. La capture arrive
     * pendant l'animation d'ouverture d'une application : l'absence passe
     * inapercue.
     */
    public static void eclipser(long ms) {
        final Bulle b = vivante;
        if (b == null || b.racine == null) return;
        try {
            final View r = b.racine;
            r.setVisibility(View.INVISIBLE);
            r.postDelayed(new Runnable() {
                public void run() {
                    try { r.setVisibility(View.VISIBLE); } catch (Throwable t) { }
                }
            }, ms);
        } catch (Throwable t) { }
    }

    /**
     * La langue vient de changer (Langue.surChangement) : repeint le menu s'il
     * est ouvert. Les phrases d'etat et les titres se resolvent a l'affichage ;
     * les libelles venus de hote-1 (menu.txt) attendent sa prochaine diffusion.
     */
    static void relangue() {
        final Bulle b = vivante;
        if (b == null) return;
        b.h.post(new Runnable() {
            public void run() {
                if (b.ouvert && !b.glisse) b.majMenu();
            }
        });
    }

    private static SharedPreferences memoire(Context c) {
        return c.getApplicationContext()
                .getSharedPreferences("bulle", Context.MODE_PRIVATE);
    }

    /**
     * Repose la pastille telle qu'elle etait, SANS hote-1.
     *
     * Appele au demarrage du telephone et apres mise a jour de l'appli. Le
     * menu n'est pas code ici : c'est le dernier menu recu qui est rejoue,
     * enregistre a chaque rafraichissement. Le garde le corrigera a son
     * premier passage s'il a change entre-temps.
     */
    public static void restaurer(Context c) {
        Relais.demarrer(c);
        if (eteinte(c)) return;
        SharedPreferences p = memoire(c);
        // Masquee : on ne ramene pas la pastille, mais on repose le cil. Sans
        // lui, un redemarrage du telephone laisserait USER sans aucun retour.
        if (p.getBoolean("masquee", false)) {
            Poignee.montrer(c);
            return;
        }
        String menu = p.getString("menu", "stop:" + Langue.t(c, R.string.bulle_menu_arreter) + "|masquer:" + Langue.t(c, R.string.bulle_menu_masquer));
        // L'etat n'est PAS restaure tel quel : apres un redemarrage l'agent
        // n'agit pas. Seul l'arret d'urgence merite de survivre, il est
        // deliberé ; veille est le bon defaut pour tout le reste.
        String etat = "suspendu".equals(p.getString("etat", "veille"))
                ? "suspendu" : "veille";
        poser(c, etat, menu, p.getString("forme", "auto"), p.getString("tetes", null));
    }

    // ---------------------------------------------------------------- vues

    private int dp(float v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, dm);
    }

    private void construire() {
        ecouterRegard();
        pastille = new Tete(ctx);
        pastille.setText("");
        pastille.setTypeface(Typeface.DEFAULT_BOLD);
        pastille.setTextColor(Charte.ENCRE);
        pastille.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        pastille.setGravity(Gravity.CENTER);

        // Le conteneur garde une zone tactile de doigt meme quand le dessin
        // se reduit a un trait de 4 dp : sans lui, la barrette serait
        // intouchable. Il est transparent, on ne vise donc que du vide.
        // Une LinearLayout nue n'apprend jamais qu'on a tourne le telephone.
        // Une vue posee par le WindowManager, elle, recoit
        // onConfigurationChanged : c'est le seul signal de rotation qu'un
        // overlay sans Activity puisse capter.
        racine = new LinearLayout(ctx) {
            @Override public void onConfigurationChanged(android.content.res.Configuration c) {
                super.onConfigurationChanged(c);
                // Les bornes de l'ecran ne sont pas encore permutees a
                // l'instant du callback : on replace au tour suivant.
                h.post(replacement);
                h.postDelayed(replacement, 150);
            }
        };
        racine.setOrientation(LinearLayout.HORIZONTAL);
        racine.setLayoutParams(new LinearLayout.LayoutParams(dp(TOUCHE_L), dp(TOUCHE_H)));
        racine.setMinimumWidth(dp(TOUCHE_L));
        racine.setMinimumHeight(dp(TOUCHE_H));
        // La tete deborde du cercle : sans cela le parent lui couperait les
        // coins des que le cube tourne de trois quarts.
        racine.setClipChildren(false);
        racine.setClipToPadding(false);
        racine.addView(pastille);
        couleurAffichee = couleurCible();
        etaitDiscret = discret();
        peindrePastille();

        lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        forme = prefs.getString("forme", "auto");
        dernL = ecranL();
        dernH = ecranH();
        lp.x = prefs.getInt("x", dernL - dp(TOUCHE_L));
        // Reaimantation a la creation : une position enregistree par une
        // version anterieure gardait une marge de 4 dp, et la barrette
        // flottait a cote du bord au lieu d'en sortir.
        lp.x = xAncre = (lp.x + dp(TOUCHE_L) / 2 < dernL / 2)
                ? 0 : dernL - dp(TOUCHE_L);
        lp.y = yAncre = prefs.getInt("y", dernH / 3);

        // Le geste est ecoute sur le conteneur, pas sur le dessin : en mode
        // barrette le dessin ne fait que 4 dp de large.
        racine.setOnTouchListener(new Glisser());
        // La barre AVANT la pastille : celle-ci reste au-dessus si elles se touchent.
        Barre.montrer(ctx, this);
        wm.addView(racine, lp);
        estomperPlusTard();
    }

    /**
     * Largeur de l'ecran MAINTENANT, pas a la creation de la bulle.
     *
     * dm est fige au constructeur : apres une rotation il rendait encore la
     * largeur du portrait, et la pastille s'aimantait donc a un bord qui
     * n'existait plus, c'est-a-dire au milieu de l'ecran.
     */
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

    /**
     * Recolle la pastille au bord apres une rotation.
     *
     * Le cote est lu sur l'ANCIENNE largeur, sinon une pastille de droite en
     * portrait se retrouverait a gauche en paysage. La hauteur est reportee
     * en proportion : le doigt la retrouve la ou il l'avait laissee.
     */
    private final Runnable replacement = new Runnable() {
        @Override public void run() {
            if (lp == null || racine == null) return;
            int L = ecranL(), H = ecranH();
            if (L == dernL && H == dernH) return;
            int taille = dp(TOUCHE_L);
            boolean gauche = dernL > 0
                    ? lp.x + taille / 2 < dernL / 2
                    : lp.x + taille / 2 < L / 2;
            float part = dernH > 0 ? (float) lp.y / dernH : 0.33f;
            dernL = L;
            dernH = H;
            lp.x = gauche ? 0 : L - taille;
            lp.y = Math.max(dp(24), Math.min(H - dp(80), Math.round(part * H)));
            xAncre = lp.x;
            yAncre = lp.y;
            // Le menu porte une gravite figee et une position calculee sur
            // l'ancien ecran : le rouvrir coute moins cher que le rattraper.
            fermerNet();
            Barre.replacer();
            try {
                wm.updateViewLayout(racine, lp);
            } catch (Exception ignore) {
            }
            peindrePastille();
            prefs.edit().putInt("x", lp.x).putInt("y", lp.y).apply();
        }
    };

    private boolean estSuspendu() {
        return "suspendu".equals(etat);
    }

    /** La couleur dit qui a la main, a l'instant : c'est tout son role. */
    private int couleurEtat() {
        if ("suspendu".equals(etat)) return ORANGE;
        if ("attente".equals(etat)) return AMBRE;
        if ("pilote".equals(etat)) return VERT;
        // La voix passe AVANT le gris mais APRES l'ambre et l'orange : un
        // arret d'urgence ou une main humaine priment toujours sur une
        // conversation en cours. Les trois sous-etats (ecoute, traitement,
        // pret) restent dans la meme famille de couleur : c'est la phrase et
        // la posture qui les distinguent, pas la teinte.
        if ("voix".equals(etat) || "voixtravaille".equals(etat)
                || "voixpret".equals(etat)) return BLEU;
        // L'enregistrement passe apres l'arret d'urgence et la main humaine,
        // mais avant tout le reste : c'est le seul etat qui laisse une trace
        // sur le disque, USER doit pouvoir le voir d'un coup d'oeil.
        if ("capture".equals(etat)) return ROUGE;
        return GRIS;
    }

    /**
     * Une lecture est en cours, rapport (Voix) ou texte (Lecteur : presse-papier,
     * ecran). USER, 2026-10-02 : toute lecture se pilote pareil, toucher pour la
     * pause, notification pour le curseur, precedent, suivant et arret.
     */
    static boolean lit() { return Voix.parle() || Lecteur.actif(); }
    static boolean enPauseLecture() {
        return Voix.parle() ? Voix.enPauseVue() : Lecteur.enPauseVue();
    }

    private String libelleEtat() {
        if ("suspendu".equals(etat)) return "II";
        if ("attente".equals(etat)) return "TOI";
        if ("pilote".equals(etat)) return "ON";
        // Une voix joue : ce n'est pas encore « a toi », quoi que dise hote-1.
        if (lit()) return enPauseLecture() ? "II" : "QG";
        if ("voix".equals(etat)) return "QG";
        if ("voixtravaille".equals(etat)) return "...";
        if ("voixpret".equals(etat)) return "OK";
        if ("capture".equals(etat)) return "REC";
        // Le menu ferme, le point d'exclamation est le seul indice que
        // quelque chose ne passe pas. Il invite a l'ouvrir pour lire pourquoi.
        if (lienMuet) return "!";
        return "AI";
    }

    /**
     * L'etat en toutes lettres, en tete du menu.
     *
     * La couleur seule ne suffisait pas : USER ne savait pas dire si le pilotage
     * etait arrete ou simplement au repos. Une phrase leve le doute.
     */
    private String phraseEtat() {
        // Avant tout le reste : si hote-1 ne repond plus, aucune autre phrase
        // n'est vraie, et c'est CELLE-LA que USER a besoin de lire.
        if (lienMuet) return Langue.t(ctx, R.string.bulle_etat_muet);
        if ("suspendu".equals(etat)) return Langue.t(ctx, R.string.bulle_etat_pause);
        if ("attente".equals(etat)) return Langue.t(ctx, R.string.bulle_etat_attente);
        if ("pilote".equals(etat)) return Langue.t(ctx, R.string.bulle_etat_actif);
        // Les trois phrases de la conversation vocale : c'etait la moitie du
        // probleme que USER n'ait aucun signal pour savoir si le micro ecoute,
        // si le QG travaille, ou s'il attend un appui pour reprendre.
        if (lit()) return enPauseLecture() ? Langue.t(ctx, R.string.bulle_etat_lecture_pause)
                : Langue.t(ctx, R.string.bulle_etat_lecture);
        if ("voix".equals(etat)) return Langue.t(ctx, R.string.bulle_etat_ecoute);
        if ("voixtravaille".equals(etat)) return Langue.t(ctx, R.string.bulle_etat_reflechit);
        if ("voixpret".equals(etat)) return Langue.t(ctx, R.string.bulle_etat_pret);
        if ("capture".equals(etat)) return Langue.t(ctx, R.string.bulle_etat_capture);
        return Langue.t(ctx, R.string.bulle_etat_veille);
    }

    /** Vrai quand rien ne se passe : la pastille se retire en trait de bord. */
    private boolean discret() {
        if (ouvert) return false;                 // menu ouvert : on veut le rond
        if (lienMuet) return false;               // un blocage se montre
        if ("rond".equals(forme)) return false;
        // La tete reste affichee au repos (retour de USER, 2026-10-07) : elle ne
        // se replie plus en barrette que si la forme "barre" est demandee.
        return "barre".equals(forme);
    }

    /** Cote de l'ecran ou la pastille est aimantee. */
    private boolean aGauche() {
        return lp == null || (lp.x + dp(TOUCHE_L) / 2) < ecranL() / 2;
    }

    /** Couleur visee par l'etat courant, avant fondu. */
    private int couleurCible() {
        // Gris moyen plutot que le gris sombre du rond : a 30 % d'opacite, un
        // trait sombre disparait sur un fond noir et un trait clair disparait
        // sur un fond blanc. Celui-ci survit aux deux.
        if (discret() && "veille".equals(etat)) return Charte.VEILLE;
        return couleurEtat();
    }

    /**
     * Rejoindre la couleur cible par un fondu de 260 ms.
     *
     * Un changement sec se lit comme un artefact d'affichage ; un fondu se lit
     * comme un changement d'etat. Le cout est nul : tout se passe sur le
     * telephone, hote-1 n'envoie qu'un mot.
     */
    private void versCouleur() {
        final int cible = couleurCible();
        if (fondu != null) fondu.cancel();
        if (couleurAffichee == cible) {
            peindrePastille();
            return;
        }
        fondu = ValueAnimator.ofObject(new ArgbEvaluator(), couleurAffichee, cible);
        fondu.setDuration(260);
        fondu.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            public void onAnimationUpdate(ValueAnimator a) {
                couleurAffichee = (Integer) a.getAnimatedValue();
                peindrePastille();
            }
        });
        fondu.start();
    }

    private void peindrePastille() {
        boolean d = discret();
        GradientDrawable f = new GradientDrawable();
        if (d) {
            // Barrette collee au bord : meme information, un dixieme de la
            // surface. Les coins ne sont arrondis que du cote interieur, elle
            // parait donc sortir de l'ecran plutot que flotter dessus.
            f.setShape(GradientDrawable.RECTANGLE);
            float r = dp(BARRE_L);
            f.setCornerRadii(aGauche()
                    ? new float[]{0, 0, r, r, r, r, 0, 0}
                    : new float[]{r, r, 0, 0, 0, 0, r, r});
            // Gris moyen plutot que le gris sombre du rond : a 30 %
            // d'opacite, un trait sombre disparait sur un fond noir et un
            // trait clair disparait sur un fond blanc. Celui-ci survit aux deux.
            f.setColor(couleurAffichee);
            pastille.setText("");
        } else {
            f.setShape(GradientDrawable.OVAL);
            // Le disque devient un SIEGE, plus un voyant plein.
            //
            // A pleine saturation il avalait la tete : un creeper vert sur un
            // rond vert ne se lit pas. Assombri, il garde sa teinte donc son
            // etat reste lisible de loin, et le dessin ressort dessus. La
            // couleur franche passe dans l'anneau, ou elle ne gene rien.
            // Fond entierement transparent : le siege sombre avalait la
            // tete et se voyait comme une tache sur le fond d'ecran. Seul
            // l'anneau porte desormais l'etat, en trait fin.
            f.setColor(0x00000000);
            // Au repos, la tete seule : l'anneau ne sert qu'a signaler un etat.
            if (!"veille".equals(etat)) {
                f.setStroke(Math.max(1, dp(1.2f)), couleurAffichee);
            }
            // Plus de mot dans le rond : la tete l'occupe. L'etat se lit
            // desormais a deux endroits, la couleur du disque et la POSTURE
            // de la tete. Le mot faisait double emploi avec la couleur et ne
            // laissait pas la place au dessin.
            pastille.setText("");
        }
        // La tete ne se dessine qu'en rond : dans la barrette de 4 dp de
        // large, il n'y a pas de place, et faire tourner une boucle
        // d'animation pour rien viderait la batterie au repos.
        pastille.setEtat(etat);
        pastille.setActif(!d);
        pastille.setBackground(f);

        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                d ? dp(BARRE_L) : dp(ROND), d ? dp(BARRE_H) : dp(ROND));
        p.gravity = Gravity.CENTER_VERTICAL
                | (d ? (aGauche() ? Gravity.START : Gravity.END) : Gravity.CENTER_HORIZONTAL);
        pastille.setLayoutParams(p);
        racine.setGravity(p.gravity);
        if (racine.getParent() != null) racine.setAlpha(ouvert ? 1f : alphaRepos());

        // Le trait qui devient rond (ou l'inverse) est un vrai changement
        // d'etat : il merite un ressort, pas un saut. On n'anime QUE la
        // bascule, sinon la pastille tressauterait a chaque repeinte du fondu.
        if (d != etaitDiscret && racine.getParent() != null) {
            etaitDiscret = d;
            pastille.setScaleX(d ? 1.6f : 0.55f);
            pastille.setScaleY(d ? 0.75f : 0.55f);
            pastille.animate().scaleX(1f).scaleY(1f).setDuration(220)
                    .setInterpolator(new OvershootInterpolator(1.4f)).start();
        }
    }

    /** Au repos, un trait gris doit se laisser oublier ; l'orange, non. */
    private float alphaRepos() {
        // Le rond porte maintenant un dessin, pas deux lettres. A 45 % il
        // devenait une tache : on ne distinguait plus la tete du fond.
        // Le siege sombre a disparu : c'est la tete elle-meme qui doit
        // rester lisible sur n'importe quel fond d'ecran.
        if (!discret()) return 1f;
        return "suspendu".equals(etat) ? 0.55f : 0.28f;
    }

    private void detruire() {
        h.removeCallbacksAndMessages(null);
        if (oeilFichier != null) {
            oeilFichier.stopWatching();
            oeilFichier = null;
        }
        cacherChoix();
        if (fondu != null) fondu.cancel();
        fermerNet();
        Barre.retirer();
        try {
            wm.removeView(racine);
        } catch (Exception ignore) {
        }
    }

    /**
     * Rend les accents que le garde a ecrits en \\uXXXX.
     *
     * Le menu voyage dans un `adb shell` : le garde n'y met que de l'ASCII et
     * ecrit chaque autre caractere en sequence \\u. Avant le 2026-10-02 il les
     * aplatissait : « Ou j'en suis », « Reglages ».
     */
    static String decoder(String s) {
        if (s == null || s.indexOf("\\u") < 0) return s;
        StringBuilder b = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '\\' && i + 5 < s.length() && s.charAt(i + 1) == 'u') {
                try {
                    b.append((char) Integer.parseInt(s.substring(i + 2, i + 6), 16));
                    i += 5;
                    continue;
                } catch (NumberFormatException ignore) {
                }
            }
            b.append(c);
        }
        return b.toString();
    }

    /** Rapports en attente, lus sur le menu du garde. */
    private int nonLus = 0;
    /** L'id du plus recent : le garde les trie du plus recent au plus ancien. */
    private String dernierRapport = null;

    /**
     * Le chiffre de la bulle. Les rapports viennent tels que le garde les
     * pose : `rapport<id>` pour chacun des 5 plus recents, et
     * `rapportsuite:+N plus anciens` pour le reste.
     */
    private void compterRapports() {
        int n = 0;
        String premier = null;
        for (String[] e : entrees) {
            String id = e[0];
            if (id.matches("rapport\\d+")) {
                n++;
                if (premier == null) premier = id;
            } else if ("rapportsuite".equals(id) && e[1] != null) {
                java.util.regex.Matcher m = java.util.regex.Pattern.compile("\\+(\\d+)").matcher(e[1]);
                if (m.find()) n += Integer.parseInt(m.group(1));
            }
        }
        nonLus = n;
        dernierRapport = premier;
        if (pastille != null) pastille.setNonLus(n);
    }

    private void rafraichir(String e, String menuBrut, String f) {
        boolean memeEtat = etat.equals(e);
        if (e != null && e.length() > 0) etat = e;
        if (f != null && f.length() > 0 && !f.equals(forme)) {
            forme = f;
            prefs.edit().putString("forme", f).apply();
        }
        boolean memeMenu = true;
        if (menuBrut != null && menuBrut.length() > 0) {
            memeMenu = menuBrut.equals(prefs.getString("menu", ""));
            String[] morceaux = menuBrut.split("\\|");
            String[][] lues = new String[morceaux.length][];
            int n = 0;
            for (String m : morceaux) {
                int sep = m.indexOf(':');
                if (sep <= 0) continue;
                lues[n++] = new String[]{m.substring(0, sep), decoder(m.substring(sep + 1))};
            }
            String[][] propres = new String[n][];
            System.arraycopy(lues, 0, propres, 0, n);
            entrees = propres;
            compterRapports();
            prefs.edit().putString("menu", menuBrut).apply();
        }
        prefs.edit().putString("etat", etat).apply();
        versCouleur();
        // Reconstruire le CONTENU, pas la fenetre : refermer puis rouvrir
        // rejouait les deux animations coup sur coup, et le menu clignotait a
        // chaque battement du garde.
        // Un menu identique ne se reconstruit pas : la carte est deja a jour,
        // et rebatir un curseur sous le doigt le fait sauter en arriere.
        if (ouvert && !memeMenu) {
            if (glisse) majEnAttente = true;
            else majMenu();
        }
        // Se rallumer a chaque rafraichissement ferait clignoter la pastille
        // pendant tout un pilotage : on ne reveille que sur vrai changement.
        if (!memeEtat) reveiller();
    }

    // ------------------------------------------------------------- opacite

    private final Runnable estompe = new Runnable() {
        public void run() {
            if (!ouvert) racine.setAlpha(alphaRepos());
        }
    };

    private void estomperPlusTard() {
        h.removeCallbacks(estompe);
        h.postDelayed(estompe, 4000);
    }

    private void reveiller() {
        racine.setAlpha(1f);
        estomperPlusTard();
    }

    // ---------------------------------------------------------------- menu

    /**
     * La colonne des icones, en dp.
     *
     * Une seule constante pour l'entete ET les lignes : c'est elle qui garantit
     * que le point d'etat, en tete de carte, tombe sur le meme axe vertical que
     * les icones en dessous. Deux valeurs separees avaient diverge, et la
     * colonne partait de travers de 9 dp.
     */
    private static final float COL = 20;
    /** Retrait a gauche de la colonne, identique pour l'entete et les lignes. */
    private static final float RETRAIT = 8;
    /** Vide entre la colonne et le texte, identique lui aussi. */
    private static final float ECART_TEXTE = 10;

    /**
     * Vrai quand ce bouton ne peut PAS marcher dans l'etat courant.
     *
     * En pause, le CLI de hote-1 refuse tout adb : capture, enregistrement,
     * voix et lecture de rapport partent dans le vide. Ils restaient pourtant
     * affiches comme les autres, et un appui ne produisait rien du tout, sans
     * un mot. Un bouton qui ne peut pas marcher doit le dire.
     *
     * Seuls survivent les ids que l'appli traite elle-meme, sans la station.
     */
    private boolean morte(String id) {
        // Les tuiles de lecture se traitent sur le telephone : rien ne les tue.
        if (estLecture(id)) return false;
        // Lien coupe : exactement les memes boutons tombent qu'en pause, pour
        // exactement la meme raison. Ils ont besoin de la station.
        if (lienMuet) {
            return !("masquer".equals(id) || "revenir".equals(id)
                    || "stop".equals(id) || "go".equals(id));
        }
        if (!"suspendu".equals(etat)) return false;
        return !("masquer".equals(id) || "revenir".equals(id)
                || "stop".equals(id) || "go".equals(id));
    }

    /** Couleur d'accent d'une ligne : seule l'action d'etat en porte une. */
    private int accent(String id) {
        if ("stop".equals(id)) return ORANGE;
        if ("go".equals(id)) return VERT;
        if ("rec".equals(id)) return ROUGE;
        // L'etat d'un reglage se lit a la COULEUR, pas au libelle : allume il
        // porte l'ambre, coupe il reste sourdine sous sa barre. Deux signaux
        // pour la meme information, parce qu'un seul se rate en diagonale.
        if ("voixmodeon".equals(id)) return VERT;
        if ("voixmodeoff".equals(id)) return ORANGE;
        if ("voixannuler".equals(id)) return ORANGE;
        if ("recstop".equals(id)) return ROUGE;
        // Le voile est ambre : son curseur l'est aussi, sinon rien ne relie
        // la glissiere a la couleur qu'elle pose sur l'ecran.
        if (id != null && id.startsWith("bleuval")) return ORANGE;
        if ("bleuautoon".equals(id)) return VERT;
        if ("regverrouon".equals(id)) return VERT;
        return SOURDINE;
    }

    // ------------------------------------------------- refonte du 2026-10-02
    //
    // Demandee par USER : « inspire-toi des meilleurs designers d'application ».
    // Ce qui a ete repris, et pourquoi :
    //  - iOS (menus contextuels, Control Center) : les 3 gestes du quotidien
    //    en tuiles larges en tete. Loi de Fitts : la cible la plus frequente
    //    est la plus grosse et la plus proche du doigt.
    //  - Material 3 et Linear : des groupes separes par un trait fin plutot
    //    qu'une colonne de 9 lignes egales. Loi de Hick : on choisit d'abord
    //    un groupe, puis une ligne, au lieu de tout relire.
    //  - Convention iOS des sous-menus : retour et titre EN HAUT, chevron a
    //    droite des portes, coche sur le choix en cours.
    //  - Une croix toujours visible (charte de USER : tout panneau se ferme).

    /** Fond d'une tuile au repos : a peine plus clair que la carte. */
    private static final int TUILE = Charte.SURFACE;
    /** Fond de la tuile principale : le bleu de la conversation, voile. */
    private static final int TUILE_VOIX = Charte.teinte(Charte.BLEU, 0x30);

    /** Les gestes du quotidien, poses en tuiles en tete de carte. */
    private static boolean estTuile(String id) {
        return "voix".equals(id) || "voixannuler".equals(id)
                || "bilan".equals(id) || "conseil".equals(id) || estLecture(id);
    }

    /**
     * Les tuiles de lecture, posees par l'appli elle-meme pendant qu'une voix
     * parle : hote-1 n'en sait rien et n'a pas a en savoir. USER, 2026-10-02 :
     * un menu qui suit le moment, les commandes de lecture en haut.
     */
    private static boolean estLecture(String id) {
        return "lecprec".equals(id) || "lecbascule".equals(id)
                || "lecsuiv".equals(id) || "lecstop".equals(id);
    }

    /** Vrai pendant une pause de lecture, Voix ou Lecteur : l'icone suit. */
    private static volatile boolean enPause = false;

    /** Vrai pour une porte : l'appui ouvre une liste au lieu d'agir. */
    private static boolean ouvreSousMenu(String id) {
        return "reglages".equals(id) || "voixvitesse".equals(id)
                || "voixstandard".equals(id) || "bleu".equals(id);
    }

    /** Vrai pour un choix exclusif d'une liste : palier de vitesse, cerveau. */
    private static boolean estChoix(String id) {
        if (id == null || id.endsWith("fermer")) return false;
        return id.startsWith("vit") || id.startsWith("std");
    }

    /** Le titre d'un sous-menu, lu sur l'id de son retour. */
    private String titreSousMenu(String retour) {
        if ("vitfermer".equals(retour)) return Langue.t(ctx, R.string.bulle_titre_vitesse);
        if ("stdfermer".equals(retour)) return Langue.t(ctx, R.string.bulle_titre_cerveau);
        if ("blufermer".equals(retour)) return Langue.t(ctx, R.string.bulle_titre_bleu);
        return Langue.t(ctx, R.string.bulle_titre_reglages);
    }

    /**
     * Le libelle court d'une tuile : une tuile fait 70 dp de large.
     * « Envoyer maintenant » ou « Annuler la reponse » y passaient sur 3 lignes.
     */
    private String libelleTuile(String id, String libelle) {
        if ("voixannuler".equals(id)) return Langue.t(ctx, R.string.bulle_tuile_annuler);
        if ("lecprec".equals(id)) return Langue.t(ctx, R.string.bulle_tuile_precedent);
        if ("lecsuiv".equals(id)) return Langue.t(ctx, R.string.bulle_tuile_suivant);
        if ("lecstop".equals(id)) return Langue.t(ctx, R.string.bulle_tuile_arreter);
        if ("lecbascule".equals(id)) return enPause ? Langue.t(ctx, R.string.bulle_tuile_reprendre) : Langue.t(ctx, R.string.bulle_tuile_pause);
        if ("voix".equals(id)) {
            return libelle != null && (libelle.startsWith("Envoyer") || libelle.startsWith("Send")) ? Langue.t(ctx, R.string.bulle_tuile_envoyer) : Langue.t(ctx, R.string.bulle_tuile_parler);
        }
        return libelle;
    }

    /**
     * Le retour tactile commun aux tuiles et aux entetes.
     *
     * Meme geste que les lignes : surligne et leger enfoncement a l'appui,
     * action au relachement, et seulement si le doigt est reste dans la vue.
     */
    private void brancherAppui(final View v, final GradientDrawable f, final int repos,
                               final boolean morte, final Runnable action) {
        v.setOnTouchListener(new View.OnTouchListener() {
            public boolean onTouch(View vue, MotionEvent ev) {
                switch (ev.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        if (morte) {
                            vibrer(8);
                            return true;
                        }
                        f.setColor(SURLIGNE);
                        vue.animate().scaleX(0.96f).scaleY(0.96f).setDuration(Charte.PRESSE_MS).start();
                        return true;
                    case MotionEvent.ACTION_UP:
                        if (morte) return true;
                        f.setColor(repos);
                        vue.animate().scaleX(1f).scaleY(1f).setDuration(Charte.PRESSE_MS).start();
                        if (ev.getX() >= 0 && ev.getX() <= vue.getWidth()
                                && ev.getY() >= 0 && ev.getY() <= vue.getHeight()) {
                            action.run();
                        }
                        return true;
                    case MotionEvent.ACTION_CANCEL:
                        f.setColor(repos);
                        vue.animate().scaleX(1f).scaleY(1f).setDuration(Charte.PRESSE_MS).start();
                        return true;
                }
                return true;
            }
        });
    }

    /** La croix de fermeture, a droite de l'entete. Cible de 40 dp. */
    private View croix() {
        LinearLayout zone = new LinearLayout(ctx);
        zone.setGravity(Gravity.CENTER);
        GradientDrawable f = new GradientDrawable();
        f.setShape(GradientDrawable.OVAL);
        f.setColor(Color.TRANSPARENT);
        zone.setBackground(f);
        Icone x = new Icone(ctx, "voixannuler", SOURDINE, 16);
        x.setLayoutParams(new LinearLayout.LayoutParams(dp(16), dp(16)));
        zone.addView(x);
        zone.setLayoutParams(new LinearLayout.LayoutParams(dp(40), dp(40)));
        brancherAppui(zone, f, Color.TRANSPARENT, false, new Runnable() {
            public void run() {
                fermer();
            }
        });
        return zone;
    }

    /** L'entete de la carte : la pastille dit la couleur, ceci dit le mot. */
    private View entete(boolean avecCroix) {
        LinearLayout l = new LinearLayout(ctx);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        l.setPadding(dp(RETRAIT + 4), dp(4), dp(2), dp(2));

        // Le point vit dans un conteneur de la largeur EXACTE de la colonne des
        // icones, centre dedans. C'est ce qui le pose sur leur axe : une simple
        // marge droite le calait sur le texte, jamais sur les icones.
        // Le point d'etat porte un halo : la couleur se lit sans crier.
        View point = new View(ctx);
        GradientDrawable rond = new GradientDrawable();
        rond.setShape(GradientDrawable.OVAL);
        rond.setColor(couleurEtat());
        point.setBackground(rond);
        point.setLayoutParams(new LinearLayout.LayoutParams(dp(8), dp(8)));

        LinearLayout halo = new LinearLayout(ctx);
        halo.setGravity(Gravity.CENTER);
        GradientDrawable brume = new GradientDrawable();
        brume.setShape(GradientDrawable.OVAL);
        brume.setColor(Charte.teinte(couleurEtat(), 0x38));
        halo.setBackground(brume);
        halo.addView(point);
        halo.setLayoutParams(new LinearLayout.LayoutParams(dp(16), dp(16)));

        LinearLayout colonne = new LinearLayout(ctx);
        colonne.setGravity(Gravity.CENTER);
        colonne.addView(halo);
        LinearLayout.LayoutParams pp = new LinearLayout.LayoutParams(
                dp(COL), LinearLayout.LayoutParams.WRAP_CONTENT);
        pp.rightMargin = dp(ECART_TEXTE);
        colonne.setLayoutParams(pp);

        TextView t = new TextView(ctx);
        t.setText(phraseEtat());
        t.setTextColor("veille".equals(etat) ? SOURDINE : TEXTE);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_ETAT);
        t.setTypeface(Charte.policeMedium());
        t.setMaxLines(2);
        t.setLayoutParams(new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        l.addView(colonne);
        l.addView(t);
        if (avecCroix) l.addView(croix());
        l.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));
        return l;
    }

    /**
     * L'entete d'un sous-menu : le retour ET le titre, en haut.
     *
     * Avant, « Retour » etait la derniere ligne de la liste : il fallait
     * descendre pour remonter, et rien ne disait ou l'on se trouvait.
     */
    private View enteteSousMenu(final String retour) {
        LinearLayout l = new LinearLayout(ctx);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        l.setPadding(dp(4), dp(4), dp(2), dp(2));

        final LinearLayout dos = new LinearLayout(ctx);
        dos.setOrientation(LinearLayout.HORIZONTAL);
        dos.setGravity(Gravity.CENTER_VERTICAL);
        dos.setPadding(dp(RETRAIT), 0, dp(8), 0);
        GradientDrawable f = new GradientDrawable();
        f.setShape(GradientDrawable.RECTANGLE);
        f.setCornerRadius(dp(Charte.RAYON_LIGNE));
        f.setColor(Color.TRANSPARENT);
        dos.setBackground(f);

        LinearLayout puce = new LinearLayout(ctx);
        puce.setGravity(Gravity.CENTER);
        GradientDrawable fp = new GradientDrawable();
        fp.setShape(GradientDrawable.OVAL);
        fp.setColor(Charte.SURFACE);
        puce.setBackground(fp);
        Icone g = new Icone(ctx, retour, TEXTE, 16);
        g.setLayoutParams(new LinearLayout.LayoutParams(dp(16), dp(16)));
        puce.addView(g);
        LinearLayout.LayoutParams gp = new LinearLayout.LayoutParams(dp(28), dp(28));
        gp.rightMargin = dp(ECART_TEXTE);
        puce.setLayoutParams(gp);
        dos.addView(puce);

        TextView t = new TextView(ctx);
        t.setText(titreSousMenu(retour));
        t.setTextColor(TEXTE);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_TITRE);
        t.setTypeface(Charte.policeMedium());
        t.setSingleLine(true);
        // Le titre partage la ligne avec la puce retour et la croix. Un titre
        // trop long finit en points de suspension, jamais en lettre rognee.
        t.setEllipsize(android.text.TextUtils.TruncateAt.END);
        dos.addView(t);

        dos.setLayoutParams(new LinearLayout.LayoutParams(0, dp(44), 1f));
        brancherAppui(dos, f, Color.TRANSPARENT, false, new Runnable() {
            public void run() {
                declencher(retour);
            }
        });
        l.addView(dos);
        l.addView(croix());
        l.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));
        return l;
    }

    /** Une tuile : grosse icone, libelle court dessous. */
    private View tuile(final String id, String libelle) {
        final boolean morte = morte(id);
        boolean voix = id.startsWith("voix");
        final int repos = voix ? TUILE_VOIX : TUILE;

        LinearLayout t = new LinearLayout(ctx);
        t.setOrientation(LinearLayout.VERTICAL);
        t.setGravity(Gravity.CENTER);
        t.setPadding(dp(2), dp(8), dp(2), dp(6));
        GradientDrawable f = new GradientDrawable();
        f.setShape(GradientDrawable.RECTANGLE);
        f.setCornerRadius(dp(Charte.RAYON_TUILE));
        f.setColor(repos);
        t.setBackground(f);

        int teinte = "voixannuler".equals(id) ? ORANGE : voix ? Charte.BLEU_CLAIR : TEXTE;
        // L'icone suit l'action, pas l'id : la meme tuile « voix » parle ou
        // envoie, la meme tuile de lecture met en pause ou reprend.
        String dessin = id;
        if ("lecbascule".equals(id)) dessin = enPause ? "go" : "stop";
        else if ("voix".equals(id) && libelle != null && (libelle.startsWith("Envoyer") || libelle.startsWith("Send"))) dessin = "envoyer";
        Icone g = new Icone(ctx, dessin, morte ? SOURDINE : teinte, 22);
        g.setLayoutParams(new LinearLayout.LayoutParams(dp(22), dp(22)));
        t.addView(g);

        TextView x = new TextView(ctx);
        x.setText(libelleTuile(id, libelle));
        x.setTextColor(voix ? TEXTE : SOURDINE);
        x.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_TUILE);
        x.setTypeface(Charte.police());
        x.setGravity(Gravity.CENTER);
        x.setMaxLines(2);
        x.setLineSpacing(0, 0.92f);
        LinearLayout.LayoutParams xp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        xp.topMargin = dp(5);
        x.setLayoutParams(xp);
        t.addView(x);
        if (morte) {
            g.setAlpha(0.38f);
            x.setAlpha(0.38f);
        }

        brancherAppui(t, f, repos, morte, new Runnable() {
            public void run() {
                declencher(id);
            }
        });
        return t;
    }

    /** La rangee des tuiles, de largeurs egales. */
    private View rangeeTuiles(java.util.List<String[]> tuiles) {
        LinearLayout r = new LinearLayout(ctx);
        r.setOrientation(LinearLayout.HORIZONTAL);
        for (int i = 0; i < tuiles.size(); i++) {
            View t = tuile(tuiles.get(i)[0], tuiles.get(i)[1]);
            LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(0, dp(68), 1f);
            if (i > 0) tp.leftMargin = dp(6);
            t.setLayoutParams(tp);
            r.addView(t);
        }
        LinearLayout.LayoutParams rp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        rp.leftMargin = dp(6);
        rp.rightMargin = dp(6);
        rp.topMargin = dp(4);
        rp.bottomMargin = dp(2);
        r.setLayoutParams(rp);
        return r;
    }

    /** Le trait sous l'entete. */
    private View trait() {
        View v = new View(ctx);
        v.setBackgroundColor(TRAIT);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, Math.max(1, dp(0.5f)));
        p.leftMargin = dp(10);
        p.rightMargin = dp(10);
        p.bottomMargin = dp(4);
        v.setLayoutParams(p);
        return v;
    }

    /** Le trait entre deux groupes : plus d'air que sous l'entete. */
    private View separation() {
        View v = new View(ctx);
        v.setBackgroundColor(TRAIT);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, Math.max(1, dp(0.5f)));
        p.leftMargin = dp(14);
        p.rightMargin = dp(14);
        p.topMargin = dp(5);
        p.bottomMargin = dp(6);
        v.setLayoutParams(p);
        return v;
    }

    /**
     * Une ligne du menu : glyphe + libelle, toutes de meme gabarit.
     *
     * Les puces d'avant etaient des pastilles de largeurs differentes, dont une
     * en aplat orange : trois formes pour trois boutons. Ici tout partage la
     * meme hauteur et la meme largeur, et seule la couleur du glyphe distingue
     * l'action d'etat.
     */
    /**
     * Une ligne a curseur : titre, valeur en pourcentage, glissiere dessous.
     *
     * Demandee par USER le 2026-09-07 : les cinq paliers de la lumiere bleue lui
     * donnaient un cran trop clair et le suivant trop sombre. Le format du
     * libelle est "Titre^valeur", ou valeur est un entier de 0 a 100.
     *
     * Le voile se repeint a CHAQUE pixel glisse, en direct dans ce processus,
     * sans passer par hote-1. Un aller-retour par logcat prend parfois plusieurs
     * secondes : un curseur qui repond en differe ne se regle pas, il se
     * devine. Seul le relachement previent la station, qui enregistre.
     */
    private View curseur(final String id, String libelle) {
        int tilde = libelle.indexOf('^');
        String titre = libelle.substring(0, tilde);
        int depart = 0;
        try {
            depart = Integer.parseInt(libelle.substring(tilde + 1).trim());
        } catch (Exception ignore) {
        }
        if (depart < 0) depart = 0;
        if (depart > 100) depart = 100;
        // Le voile est la verite locale : le chiffre du garde peut dater
        // (garde relance, appui perdu en route). Retour de USER, 2026-10-03 :
        // curseur affiche a 92 % pendant que l'ecran etait a 0.
        if (id.startsWith("bleuval")) depart = Filtre.pct(ctx);

        LinearLayout l = new LinearLayout(ctx);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(dp(RETRAIT), dp(6), dp(18), dp(2));

        LinearLayout haut = new LinearLayout(ctx);
        haut.setOrientation(LinearLayout.HORIZONTAL);
        haut.setGravity(Gravity.CENTER_VERTICAL);

        TextView t = new TextView(ctx);
        t.setText(titre);
        t.setTextColor(TEXTE);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_LIGNE);
        t.setTypeface(Charte.police());
        t.setSingleLine(true);
        t.setLayoutParams(new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        haut.addView(t);

        final TextView v = new TextView(ctx);
        v.setText(Langue.t(ctx, R.string.bulle_pct, depart));
        v.setTextColor(accent(id));
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_VALEUR);
        v.setTypeface(Charte.policeMedium());
        v.setFontFeatureSettings("tnum");
        v.setSingleLine(true);
        haut.addView(v);
        l.addView(haut);

        // Piste epaisse et arrondie, poignee en trait : le curseur ressemble
        // au reste de la carte, pas au widget d'usine.
        SeekBar barre = new SeekBar(ctx);
        barre.setMax(100);
        barre.setProgress(depart);
        barre.setProgressDrawable(pisteCurseur(accent(id)));
        barre.setThumb(poigneeCurseur(accent(id)));
        barre.setThumbOffset(dp(3));
        barre.setSplitTrack(false);
        barre.setPadding(dp(3), dp(10), dp(3), dp(10));
        if (android.os.Build.VERSION.SDK_INT >= 29) {
            barre.setMinHeight(dp(8));
            barre.setMaxHeight(dp(8));
        }
        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(36));
        barre.setLayoutParams(bp);
        // Le parent ne doit pas confisquer le glissement : sans cela, la
        // carte pourrait recuperer le doigt et la barre ne verrait que
        // l'appui initial.
        barre.setOnTouchListener(new View.OnTouchListener() {
            public boolean onTouch(View vue, MotionEvent ev) {
                if (vue.getParent() != null) {
                    vue.getParent().requestDisallowInterceptTouchEvent(true);
                }
                return false;
            }
        });
        final android.os.Handler main =
                new android.os.Handler(android.os.Looper.getMainLooper());
        final Runnable[] enAttente = new Runnable[1];
        barre.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar b, int n, boolean parLUtilisateur) {
                v.setText(Langue.t(ctx, R.string.bulle_pct, n));
                if (!parLUtilisateur) return;
                // Repeindre le voile ICI, dans la passe tactile de la barre,
                // avale son invalidate() : le fond suivait le doigt mais le
                // pouce restait fige (retour de USER, 2026-09-07). On differe
                // d'une trame, et on ecrase la peinture precedente pour ne
                // pas empiler un appel par pixel parcouru.
                final int val = n;
                if (enAttente[0] != null) main.removeCallbacks(enAttente[0]);
                enAttente[0] = new Runnable() {
                    public void run() {
                        Filtre.peindre(ctx, val);
                    }
                };
                main.postDelayed(enAttente[0], 16);
            }

            public void onStartTrackingTouch(SeekBar b) {
                glisse = true;
                vibrer(8);
            }

            public void onStopTrackingTouch(SeekBar b) {
                // definir() enregistre et laisse Auto decider : en mode auto et
                // en plein jour, le voile choisi ne se pose pas tout de suite.
                Filtre.definir(ctx, b.getProgress());
                commande(ctx, id + "=" + b.getProgress());
                glisse = false;
                if (majEnAttente) {
                    majEnAttente = false;
                    majMenu();
                }
            }
        });
        l.addView(barre);

        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        p.leftMargin = dp(4);
        p.rightMargin = dp(4);
        p.bottomMargin = dp(2);
        l.setLayoutParams(p);
        return l;
    }

    /** Piste du curseur : fond de surface, portion active a l'accent. */
    private android.graphics.drawable.Drawable pisteCurseur(int accent) {
        GradientDrawable fond = Charte.fond(ctx, Charte.SURFACE, 4);
        GradientDrawable plein = Charte.fond(ctx, accent, 4);
        android.graphics.drawable.ClipDrawable clip =
                new android.graphics.drawable.ClipDrawable(
                        plein, Gravity.START, android.graphics.drawable.ClipDrawable.HORIZONTAL);
        android.graphics.drawable.LayerDrawable piste =
                new android.graphics.drawable.LayerDrawable(
                        new android.graphics.drawable.Drawable[]{fond, clip});
        piste.setId(0, android.R.id.background);
        piste.setId(1, android.R.id.progress);
        return piste;
    }

    /** Poignee du curseur : un trait vertical arrondi, 4 x 28 dp. */
    private android.graphics.drawable.Drawable poigneeCurseur(int accent) {
        GradientDrawable g = Charte.fond(ctx, accent, 2);
        g.setSize(dp(4), dp(28));
        return g;
    }

    private View ligne(final String id, String libelle) {
        final boolean morte = morte(id);
        final LinearLayout l = new LinearLayout(ctx);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        l.setPadding(dp(RETRAIT), 0, dp(14), 0);

        final GradientDrawable f = new GradientDrawable();
        f.setShape(GradientDrawable.RECTANGLE);
        f.setCornerRadius(dp(Charte.RAYON_LIGNE));
        f.setColor(Color.TRANSPARENT);
        l.setBackground(f);

        // Un libelle peut porter sa VALEUR apres un tilde : "Rapports~muet".
        // Elle part alors a droite, dans la couleur de l'accent. C'est ce qui
        // fait qu'un reglage se lit comme un reglage et non comme une action :
        // « Rapports en silencieux » sur une seule ligne debordait la carte et
        // se faisait tronquer, ce qui coupait justement le mot qui informe.
        String titre = libelle;
        String valeur = null;
        int tilde = libelle.indexOf('~');
        if (tilde > 0) {
            titre = libelle.substring(0, tilde);
            valeur = libelle.substring(tilde + 1);
        }

        // Un choix de liste (palier, cerveau) n'a pas d'icone propre. Celui
        // qui tourne porte la coche dans la colonne, a la place du mot « en
        // cours » d'avant : l'oeil cherche une coche, il ne lit pas un mot.
        // Refonte du 2026-10-02, sur le modele des menus d'iOS.
        boolean choix = estChoix(id);
        boolean coche = choix && ("en cours".equals(valeur) || "current".equals(valeur));
        if (coche) valeur = null;
        String glyphe = choix ? (coche ? "coche" : "vide") : id;
        int teinte = coche ? VERT : accent(id);

        // 18 dp de dessin dans une colonne de 20 : l'icone respire un peu, et
        // toutes partagent le meme centre optique quelle que soit leur forme.
        Icone g = new Icone(ctx, glyphe, morte ? SOURDINE : teinte, 18);
        LinearLayout.LayoutParams gp = new LinearLayout.LayoutParams(dp(COL), dp(COL));
        gp.gravity = Gravity.CENTER_VERTICAL;
        gp.rightMargin = dp(ECART_TEXTE);
        g.setLayoutParams(gp);

        TextView t = new TextView(ctx);
        t.setText(titre);
        t.setTextColor(TEXTE);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14.5f);
        t.setSingleLine(true);
        // Points de suspension plutot qu'une lettre rognee au bord.
        t.setEllipsize(android.text.TextUtils.TruncateAt.END);
        // Un grisage franc, pas une nuance : a 38 % la ligne se lit encore,
        // mais elle ne se confond plus une seconde avec une ligne vivante.
        if (morte) { g.setAlpha(0.38f); t.setAlpha(0.38f); }

        l.addView(g);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        t.setLayoutParams(tp);
        l.addView(t);

        if (valeur != null) {
            TextView v = new TextView(ctx);
            v.setText(valeur);
            v.setTextColor(morte ? SOURDINE : accent(id));
            v.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_VALEUR);
            v.setTypeface(Charte.policeMedium());
            v.setFontFeatureSettings("tnum");
            v.setSingleLine(true);
            if (morte) v.setAlpha(0.38f);
            // Sans cette marge, une valeur longue vient toucher le titre : les
            // deux se lisent alors comme une seule phrase collee.
            LinearLayout.LayoutParams vp = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT);
            vp.leftMargin = dp(10);
            v.setLayoutParams(vp);
            l.addView(v);
        }

        // Une porte vers un sous-menu porte le chevron a droite, apres sa
        // valeur. Sans lui, « Reglages » ou « Vitesse » se lisaient comme des
        // actions, et l'appui qui ouvrait une liste surprenait.
        if (ouvreSousMenu(id)) {
            Icone ch = new Icone(ctx, "porte", Charte.TEXTE_3, 14);
            LinearLayout.LayoutParams cp = new LinearLayout.LayoutParams(dp(14), dp(14));
            cp.gravity = Gravity.CENTER_VERTICAL;
            cp.leftMargin = dp(valeur != null ? 4 : 8);
            ch.setLayoutParams(cp);
            if (morte) ch.setAlpha(0.38f);
            l.addView(ch);
        }

        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(44));
        p.leftMargin = dp(4);
        p.rightMargin = dp(4);
        p.bottomMargin = dp(2);
        l.setLayoutParams(p);

        // Un OnClickListener ne donne aucun retour visuel sur une vue
        // d'overlay : pas de ripple, pas de selecteur d'etat. On peint donc
        // l'appui a la main, sinon on ne sait pas si le doigt a porte.
        if (morte) {
            // Pas d'appui muet : un tres court retour dit que le doigt a bien
            // porte, et que c'est l'action qui est refusee, pas la pastille qui
            // a rate le geste.
            l.setOnTouchListener(new View.OnTouchListener() {
                public boolean onTouch(View v, MotionEvent ev) {
                    if (ev.getAction() == MotionEvent.ACTION_DOWN) vibrer(8);
                    return true;
                }
            });
            return l;
        }

        // Une ligne de rapport se balaye pour l'ecarter. USER en recoit
        // plusieurs d'affilee et n'a pas envie de tous les entendre : sans ce
        // geste, le seul moyen de vider la file etait de lire chaque rapport.
        final boolean balayable = estRapport(id);
        l.setOnTouchListener(new View.OnTouchListener() {
            float x0, y0;
            boolean glisse;

            public boolean onTouch(View v, MotionEvent ev) {
                switch (ev.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        x0 = ev.getRawX();
                        y0 = ev.getRawY();
                        glisse = false;
                        f.setColor(SURLIGNE);
                        l.animate().scaleX(0.97f).scaleY(0.97f).setDuration(Charte.PRESSE_MS).start();
                        return true;
                    case MotionEvent.ACTION_MOVE: {
                        if (!balayable) return true;
                        float dx = ev.getRawX() - x0;
                        float dy = ev.getRawY() - y0;
                        // Le glissement ne prend la main qu'apres 12 dp ET
                        // seulement s'il est franchement horizontal : un appui
                        // un peu traînant doit rester un appui, sinon USER
                        // ecarterait le rapport qu'il voulait ecouter.
                        if (!glisse && Math.abs(dx) > dp(12)
                                && Math.abs(dx) > Math.abs(dy)) {
                            glisse = true;
                            f.setColor(Color.TRANSPARENT);
                            l.animate().cancel();
                            l.setScaleX(1f);
                            l.setScaleY(1f);
                        }
                        if (glisse) {
                            l.setTranslationX(dx);
                            // La ligne s'efface a mesure qu'elle sort : le
                            // doigt voit ou en est le geste, et peut renoncer.
                            float w = Math.max(1f, v.getWidth());
                            l.setAlpha(Math.max(0.15f, 1f - Math.abs(dx) / w));
                        }
                        return true;
                    }
                    case MotionEvent.ACTION_UP:
                        f.setColor(Color.TRANSPARENT);
                        l.animate().scaleX(1f).scaleY(1f).setDuration(Charte.PRESSE_MS).start();
                        if (glisse) {
                            float dx = ev.getRawX() - x0;
                            // Plus d'un tiers de la largeur : en dessous, le
                            // geste revient a sa place, on n'ecarte rien par
                            // accident.
                            if (Math.abs(dx) > v.getWidth() * 0.38f) {
                                ecarter(l, id, dx > 0);
                            } else {
                                l.animate().translationX(0f).alpha(1f)
                                        .setDuration(140).start();
                            }
                            return true;
                        }
                        // La vue garde le doigt jusqu'au relachement, meme
                        // sorti d'elle : sans ce test, glisser depuis "Mettre
                        // en pause" vers le vide le declenchait quand meme. On
                        // veut pouvoir renoncer en ecartant le doigt.
                        if (ev.getX() >= 0 && ev.getX() <= v.getWidth()
                                && ev.getY() >= 0 && ev.getY() <= v.getHeight()) {
                            declencher(id);
                        }
                        return true;
                    case MotionEvent.ACTION_CANCEL:
                        f.setColor(Color.TRANSPARENT);
                        l.animate().scaleX(1f).scaleY(1f).setDuration(Charte.PRESSE_MS).start();
                        if (glisse) {
                            l.animate().translationX(0f).alpha(1f)
                                    .setDuration(140).start();
                        }
                        return true;
                }
                return true;
            }
        });
        return l;
    }

    /** Vrai pour une puce « rapportN », la seule qu'un balayage peut ecarter. */
    private static boolean estRapport(String id) {
        if (id == null || !id.startsWith("rapport") || id.length() <= 7) return false;
        for (int i = 7; i < id.length(); i++) {
            if (!Character.isDigit(id.charAt(i))) return false;
        }
        return true;
    }

    /**
     * Sort le rapport de la file : la ligne part par le bord, hote-1 le rejette.
     *
     * La ligne dispararait sans attendre la reponse de la station, pour la
     * meme raison que basculerLocal() : le trajet passe par logcat et prend
     * parfois des secondes. La prochaine peinture de hote-1 fait foi, et le
     * menu ne reste jamais faux plus d'un tour.
     */
    private void ecarter(final View l, final String id, boolean versDroite) {
        vibrer(20);
        final String ordre = "rapportsuppr" + id.substring(7);
        deposer(ordre);
        // Le garde ecoute logcat : la trace EST le canal de commande rapide.
        Log.i("pixelgarde", "recu com.poste.pixel.ACTION action=" + ordre);
        float fin = (versDroite ? 1f : -1f) * Math.max(l.getWidth(), dp(220));
        l.animate().translationX(fin).alpha(0f).setDuration(160)
                .withEndAction(new Runnable() {
                    public void run() {
                        oublierEntree(id);
                        majMenu();
                    }
                }).start();
    }

    /** Retire une puce du menu courant, pour que majMenu() ne la repose pas. */
    private void oublierEntree(String id) {
        java.util.ArrayList<String[]> reste = new java.util.ArrayList<String[]>();
        for (String[] e : entrees) {
            if (!id.equals(e[0])) reste.add(e);
        }
        entrees = reste.toArray(new String[reste.size()][]);
        compterRapports();
    }

    /**
     * Vrai pour les puces d'un sous-menu, son ouverture comprise.
     *
     * Un appui a l'interieur d'un sous-menu ne doit pas refermer la carte : USER
     * essaie un reglage, le juge, en essaie un autre. Oublier une famille ici
     * la fait se replier a chaque essai. C'est ce qui est arrive au sous-menu
     * de la lumiere bleue le 2026-09-07, ajoute sans passer par cette liste.
     */
    private static boolean dansSousMenu(String id) {
        if (id == null) return false;
        return id.startsWith("vit") || "voixvitesse".equals(id)
                || id.startsWith("std") || "voixstandard".equals(id)
                || id.startsWith("bleu") || id.startsWith("blu")
                || "reglages".equals(id) || id.startsWith("reg");
    }

    private void declencher(String id) {
        // Les commandes de lecture restent sur le telephone : passer par hote-1
        // ajouterait plusieurs secondes a une pause, qui doit etre immediate.
        if (estLecture(id)) {
            lireIci(id);
            return;
        }
        // L'ecran Missions s'ouvre ici meme : la page charge ses donnees seule
        // aupres du relais, inutile de passer par le garde.
        if ("missions".equals(id)) {
            fermer();
            vibrer(15);
            Intent i = new Intent(ctx, Missions.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            ctx.startActivity(i);
            return;
        }
        // Le micro ecoute : « Envoyer » part d'ici, sans aller-retour par le
        // garde. ENVOYER ne fait rien hors ecoute, un double appui est sans
        // danger.
        if ("voix".equals(id) && Voix.ecoute()) {
            fermer();
            envoyerIci();
            return;
        }
        // Un appui a l'interieur du sous-menu des vitesses n'en sort pas : USER
        // choisit un palier, l'entend, en veut un autre. Refermer la carte
        // l'obligeait a rouvrir la pastille puis a redescendre dans Vitesse a
        // chaque essai. La station repeindra le menu par-dessus celui-ci.
        if (!dansSousMenu(id)) fermer();
        // Un hochement, tout de suite : l'appui est accuse par le dessin
        // avant meme que hote-1 en sache quoi que ce soit.
        if (pastille != null) pastille.saluer();
        // Retour IMMEDIAT, avant meme de prevenir hote-1.
        //
        // Le trajet aller-retour passe par logcat, lu a distance par le garde,
        // qui rediffuse ensuite l'etat en adb. Quand le lien dort ou que le
        // garde redemarre, ce trajet prend plusieurs secondes, parfois des
        // minutes. La pastille gardait alors sa couleur : l'appui paraissait
        // sans effet, USER appuyait encore, et l'etat revenait tout seul plus
        // tard. C'est le defaut qu'il a signale le 2026-08-25.
        //
        // La station reste maitresse : sa prochaine diffusion corrige la
        // pastille si elle n'a pas suivi. On affiche l'intention, pas un fait.
        if ("stop".equals(id) || "go".equals(id)) basculerLocal("stop".equals(id));
        else vibrer(15);
        // Deux canaux pour un meme appui, voir deposer().
        deposer(id);
        if ("masquer".equals(id)) {
            Log.i("pixelgarde", "recu com.poste.pixel.ACTION action=masquer");
            masquer(ctx);
            return;
        }
        // Le garde ecoute logcat : la trace EST le canal de commande rapide.
        Log.i("pixelgarde", "recu com.poste.pixel.ACTION action=" + id);
        Intent i = new Intent(Bulle.ACTION_ID).setPackage(ctx.getPackageName());
        i.putExtra("action", id);
        ctx.sendBroadcast(i);
    }

    /**
     * Bascule l'etat sur place, sans hote-1.
     *
     * Depuis le 26/08/2026, la pause n'a plus de bouton : elle est sur l'appui
     * long de la pastille. Ce sont donc la couleur, la posture de la tete et la
     * phrase d'entete qui accusent l'appui, plus un libelle qui se retourne.
     */
    private void basculerLocal(boolean pause) {
        etat = pause ? "suspendu" : "veille";
        prefs.edit().putString("etat", etat).apply();
        versCouleur();
        // Le menu ouvert doit suivre : c'est lui qui grise les actions
        // devenues impossibles, et qui porte la phrase d'etat.
        if (ouvert) majMenu();
        reveiller();
        // Une pastille qui change de couleur sous le pouce est cachee par le
        // pouce. La vibration, elle, se sent.
        vibrer(pause ? 45 : 20);
    }

    /**
     * L'id de l'action d'etat a declencher maintenant : mettre en pause, ou
     * reprendre. Lu dans les libelles poses par hote-1 (actions/etat.txt) plutot
     * que code ici, pour que les deux cotes ne puissent pas diverger.
     */
    private String idEtat() {
        String tete = "suspendu".equals(etat) ? teteReprise : tetePause;
        int sep = tete.indexOf(':');
        return sep > 0 ? tete.substring(0, sep) : ("suspendu".equals(etat) ? "go" : "stop");
    }

    /**
     * Declare le lien mort quand hote-1 n'a rien renvoye a temps.
     *
     * La station confirme TOUT appui par une diffusion BULLE, qui repasse par
     * signeDeVie(). Passe PATIENCE_MS sans un mot, c'est que le telephone
     * n'est plus joignable : debogage sans fil eteint, Tailscale coupe, ou
     * garde arrete. L'appui n'est pas perdu pour autant, il attend dans
     * cmd.txt et sera rejoue a la reconnexion.
     */
    private final Runnable guetLien = new Runnable() {
        public void run() {
            if (lienMuet) return;
            lienMuet = true;
            versCouleur();
            if (ouvert) majMenu();
        }
    };

    /**
     * hote-1 vient de parler : le lien est vivant.
     *
     * Appele a chaque diffusion recue, quelle qu'elle soit. C'est le seul
     * signal fiable dont l'application dispose : elle ne peut pas sonder la
     * station, c'est la station qui la pilote.
     */
    private void signeDeVie() {
        h.removeCallbacks(guetLien);
        if (!lienMuet) return;
        lienMuet = false;
        versCouleur();
        if (ouvert) majMenu();
    }

    private void vibrer(int ms) {
        try {
            Vibrator v = (Vibrator) ctx.getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null) {
                v.vibrate(VibrationEffect.createOneShot(
                        ms, VibrationEffect.DEFAULT_AMPLITUDE));
            }
        } catch (Exception ignore) {
        }
    }

    /**
     * Depose la commande dans un fichier que le garde relit.
     *
     * logcat est un FLUX : coupe, endormi, ou repris apres un redemarrage du
     * garde, il perd tout ce qui est passe pendant l'absence, car il reprend a
     * l'instant present. Un appui tombe dans ce trou etait perdu pour de bon.
     *
     * Ce fichier, lui, attend. Le garde le relit a chaque reconnexion et
     * toutes les 5 s, et ne rejoue que ce qu'il n'a pas deja vu. Le flux reste
     * la voie rapide, le fichier est le rattrapage.
     */
    private void deposer(String id) {
        ecrireCommande(ctx, id);
        // On attend la confirmation de hote-1. Sans elle, le menu le dira.
        h.removeCallbacks(guetLien);
        h.postDelayed(guetLien, PATIENCE_MS);
    }

    /**
     * Emet une commande vers hote-1 depuis n'importe quel composant de l'appli.
     *
     * La pastille n'est pas la seule a avoir des choses a dire : le service de
     * voix annonce ses debuts, ses tours et ses fins. Il emprunte exactement le
     * meme couple de canaux, plutot que d'en inventer un troisieme :
     *
     *   - logcat, la voie rapide, que le garde lit en flux ;
     *   - cmd.txt, le rattrapage, que le garde relit toutes les 5 s.
     *
     * Le garde ignore les doublons : il compare l'horodatage a celui du
     * dernier appui joue. Emettre sur les deux ne joue donc jamais deux fois.
     */
    static void ecrireCommande(Context ctx, String id) {
        try {
            File d = ctx.getExternalFilesDir(null);
            if (d != null) {
                String ligne = System.currentTimeMillis() + " " + id;
                FileOutputStream f = new FileOutputStream(new File(d, "cmd.txt"));
                f.write((ligne + "\n").getBytes("UTF-8"));
                f.close();
                // Par le reseau aussi : sans ADB, c'est la seule voie.
                Relais.appui(ctx, ligne);
            }
        } catch (Exception ignore) {
        }
    }

    /**
     * L'avancement d'une lecture, porte a la pastille (0 pour la fin).
     *
     * Demande par USER le 2026-08-30 : voir l'anneau se vider pendant qu'un
     * rapport se fait lire. Le service de voix ne connait pas la pastille, et
     * la pastille ne connait pas le service : ce couloir statique est le seul
     * lien, comme commande() l'est dans l'autre sens.
     *
     * Silencieux quand la bulle est masquee ou pas encore posee : une lecture
     * peut tres bien partir sans pastille a l'ecran, ce n'est pas une erreur.
     */
    static void lecture(final int dureeMs) {
        if (dureeMs > 0) enPause = false;
        final Bulle b = vivante;
        if (b == null || b.pastille == null) return;
        // Par le handler et non en direct : la fin de lecture peut venir du fil
        // d'ecoute du micro, et une vue ne se touche que depuis le fil principal.
        b.h.post(new Runnable() {
            public void run() {
                if (dureeMs > 0) b.cacherChoix();
                b.pastille.setLecture(dureeMs);
                b.peindrePastille();
                // Le menu ouvert gagne ou perd ses commandes de lecture.
                if (b.ouvert && !b.glisse) b.majMenu();
            }
        });
    }

    /** Le curseur de la notification a bouge : l'anneau suit. */
    static void lectureA(final int posMs) {
        final Bulle b = vivante;
        if (b == null || b.pastille == null) return;
        b.h.post(new Runnable() {
            public void run() { b.pastille.setLectureA(posMs); }
        });
    }

    /** Pause (vrai) ou reprise (faux) de l'anneau, meme couloir que lecture(). */
    static void lecturePause(final boolean p) {
        enPause = p;
        final Bulle b = vivante;
        if (b == null || b.pastille == null) return;
        b.h.post(new Runnable() {
            public void run() { b.pastille.setLecturePause(p); b.peindrePastille(); }
        });
    }

    /** Le compte a rebours d'envoi, meme couloir que lecture(). */
    static void compte(final int dureeMs) {
        final Bulle b = vivante;
        if (b == null || b.pastille == null) return;
        b.h.post(new Runnable() {
            public void run() { b.pastille.setCompte(dureeMs); }
        });
    }

    // ------------------------------------------------- les boutons du rapport

    /**
     * « Oui » et « Detail » poses au-dessus de la pastille, a la fin d'un
     * rapport. Demande de USER le 2026-10-02 : ne plus avoir a dire « oui je
     * valide » pour confirmer, ni « detail » pour entendre le rapport entier.
     *
     * Un appui fait exactement ce que ferait la phrase : le mot part au
     * standard, qui propose l'envoi avec son compte a rebours, ou lit le
     * detail. Les boutons s'effacent seuls au bout de CHOIX_MS, ou des que USER
     * touche la bulle, parle, ou qu'une autre lecture commence.
     *
     * quoi : "oui,detail", "oui" ou "detail". Null efface.
     * pour : ce que les boutons visent, l'id du rapport ou t<secondes> pour
     * un tour du standard. Chaque appui le renvoie (« voixb1:1375 ») : hote-1
     * ne devine plus la cible d'apres ce qu'il a lu en dernier (bug du
     * 2026-10-06, la reponse au rapport 1375 partie avec celui de 1376).
     */
    static void choix(String quoi) { choix(quoi, null); }

    static void choix(final String quoi, final String pour) {
        final Bulle b = vivante;
        if (b == null || b.pastille == null) return;
        b.h.post(new Runnable() {
            public void run() {
                if (quoi == null) b.cacherChoix(); else b.montrerChoix(quoi, pour);
            }
        });
    }

    private static final int CHOIX_MS = 8000;
    private LinearLayout choixVue;
    private final Runnable finChoix = new Runnable() {
        public void run() { cacherChoix(); }
    };

    private void cacherChoix() {
        h.removeCallbacks(finChoix);
        if (choixVue == null) return;
        try { wm.removeView(choixVue); } catch (Exception ignore) { }
        choixVue = null;
    }

    private void montrerChoix(String quoi, String pour) {
        cacherChoix();
        // Un id hors format ne part pas : le bouton redevient sans cible.
        final String suffixe = pour != null && pour.matches("[a-z0-9]{1,12}") ? ":" + pour : "";
        // Menu ouvert : USER a deja la main, deux surfaces a la fois embrouillent.
        if (ouvert || racine == null) return;
        LinearLayout l = new LinearLayout(ctx);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        // La marge transparente agrandit la zone tactile sans grossir le dessin.
        l.setPadding(dp(4), dp(4), dp(4), dp(4));
        l.setClipToPadding(false);
        // Format « id:Libelle|id:Libelle ». Les reponses viennent du standard,
        // qui devine ce que USER va dire : la premiere est la plus probable,
        // seule en vert. L'ancien format « oui,detail » reste compris.
        java.util.List<String[]> liste = new java.util.ArrayList<String[]>();
        for (String bout : quoi.split(quoi.indexOf('|') >= 0 || quoi.indexOf(':') >= 0 ? "\\|" : ",")) {
            bout = bout.trim();
            int deux = bout.indexOf(':');
            String id = deux > 0 ? bout.substring(0, deux).trim() : bout;
            String libelle = deux > 0 ? bout.substring(deux + 1).trim() : "";
            if (!Voix.idChoixValide(id)) continue;
            if (libelle.isEmpty()) libelle = libelleChoixDefaut(id);
            liste.add(new String[] {id, libelle});
            if (liste.size() == 3) break;
        }
        if (liste.isEmpty()) return;
        // Toujours en colonne, une reponse par ligne, collee au bord de
        // l'ecran du cote de la pastille (USER, 2026-10-03 : la rangee a cote
        // de la bulle mangeait la largeur, et la 3e sortait vide). Au-dessus
        // de la bulle ; sans la place, dessous. La plus probable reste au plus
        // pres de la bulle.
        l.setOrientation(LinearLayout.VERTICAL);
        l.setGravity(aGauche() ? Gravity.START : Gravity.END);
        int haut1 = dp(44) * liste.size() + dp(8) * (liste.size() - 1) + dp(8);
        boolean dessous = lp.y - haut1 < dp(24);
        for (int k = 0; k < liste.size(); k++) {
            int i = dessous ? k : liste.size() - 1 - k;
            String[] c = liste.get(i);
            l.addView(boutonChoix(c[0] + suffixe, c[1], i == 0, k < liste.size() - 1, true));
        }
        l.measure(View.MeasureSpec.UNSPECIFIED, View.MeasureSpec.UNSPECIFIED);
        int largeur = l.getMeasuredWidth(), hauteur = l.getMeasuredHeight();
        WindowManager.LayoutParams p = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                PixelFormat.TRANSLUCENT);
        p.gravity = Gravity.TOP | Gravity.START;
        p.x = aGauche() ? 0 : Math.max(0, ecranL() - largeur);
        p.y = dessous ? lp.y + dp(TOUCHE_H) : lp.y - hauteur;
        try {
            wm.addView(l, p);
        } catch (Exception e) {
            return;
        }
        choixVue = l;
        l.setAlpha(0f);
        l.animate().alpha(1f).setDuration(160).start();
        h.postDelayed(finChoix, CHOIX_MS);
    }

    /** Libelle d'un bouton de reponse que le standard n'a pas nomme. */
    private String libelleChoixDefaut(String id) {
        if ("detail".equals(id)) return Langue.t(ctx, R.string.bulle_choix_detail);
        if ("oui".equals(id)) return Langue.t(ctx, R.string.bulle_choix_oui);
        if ("non".equals(id)) return Langue.t(ctx, R.string.bulle_choix_non);
        return id.substring(0, 1).toUpperCase() + id.substring(1);
    }

    private View boutonChoix(final String mot, String libelle, boolean oui,
                             boolean marge, boolean pile) {
        TextView t = new TextView(ctx);
        t.setText(libelle);
        t.setSingleLine(true);
        t.setEllipsize(android.text.TextUtils.TruncateAt.END);
        t.setMaxWidth(ecranL() * 3 / 4);
        t.setTextColor(oui ? Charte.TEXTE_SUR_ACCENT : TEXTE);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_BOUTON);
        t.setTypeface(Charte.policeMedium());
        t.setGravity(Gravity.CENTER);
        t.setMinWidth(dp(76));
        t.setPadding(dp(20), 0, dp(20), 0);
        final GradientDrawable f = new GradientDrawable();
        f.setShape(GradientDrawable.RECTANGLE);
        f.setCornerRadius(dp(Charte.RAYON_PILULE));
        f.setColor(oui ? VERT : Charte.SURFACE);
        f.setStroke(Math.max(1, dp(0.75f)), oui ? Charte.teinte(Color.WHITE, 0x2A) : Charte.CONTOUR);
        t.setBackground(f);
        t.setElevation(dp(4));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dp(44));
        if (marge) {
            if (pile) p.bottomMargin = dp(8); else p.leftMargin = dp(8);
        }
        t.setLayoutParams(p);
        t.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                // Un seul appui par rangee : le 2e doigt arrive souvent avant
                // que la vue soit retiree, et partirait en double tour.
                android.view.ViewParent rangee = v.getParent();
                if (!(rangee instanceof View) || ((View) rangee).getTag() != null) return;
                ((View) rangee).setTag("touche");
                vibrer(15);
                cacherChoix();
                try {
                    ctx.startService(new Intent(ctx, Voix.class)
                            .setAction(Voix.CHOISIR).putExtra("mot", mot));
                } catch (Exception e) {
                    Log.i("pixelgarde", "choix : " + e);
                }
            }
        });
        return t;
    }

    /** Le couple complet : le fichier de rattrapage, puis la trace rapide. */
    static void commande(Context ctx, String id) {
        ecrireCommande(ctx, id);
        Log.i("pixelgarde", "recu com.poste.pixel.ACTION action=" + id);
    }

    static final String ACTION_ID = "com.poste.pixel.ACTION";

    /**
     * Vrai tant qu'un doigt tient un curseur. Le garde renvoie le menu a
     * chaque battement, et majMenu() reconstruisait alors la carte, curseur
     * compris, a l'ancienne valeur : le pouce restait sur place pendant que
     * le voile changeait (USER, 2026-09-07). Pendant un glissement, la carte ne
     * se reconstruit pas ; un rafraichissement arrive s'applique au lacher.
     */
    private boolean glisse = false;
    private boolean majEnAttente = false;

    /** Le contenu de la carte : entete, separateur, puis une ligne par action. */
    private GradientDrawable halo;

    /** Les deux pages du panneau, en pilules, et la croix. */
    private View onglets() {
        LinearLayout l = new LinearLayout(ctx);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        l.setPadding(dp(6), dp(4), dp(2), dp(2));
        l.addView(pilule(Langue.t(ctx, R.string.bulle_onglet_apps), 0, false));
        l.addView(pilule("Creeper", 1, true));
        View vide = new View(ctx);
        vide.setLayoutParams(new LinearLayout.LayoutParams(0, 1, 1f));
        l.addView(vide);
        l.addView(croix());
        l.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));
        return l;
    }

    /** Une pilule d'onglet. Celle du Creeper porte le point d'etat. */
    private View pilule(String texte, final int cible, boolean point) {
        boolean actif = page == cible;
        LinearLayout p = new LinearLayout(ctx);
        p.setGravity(Gravity.CENTER);
        p.setPadding(dp(10), 0, dp(10), 0);
        final GradientDrawable f = new GradientDrawable();
        f.setShape(GradientDrawable.RECTANGLE);
        f.setCornerRadius(dp(Charte.RAYON_PILULE));
        final int repos = actif ? Charte.SURFACE_HAUTE : Color.TRANSPARENT;
        f.setColor(repos);
        p.setBackground(f);
        if (point) {
            View d = new View(ctx);
            GradientDrawable rond = new GradientDrawable();
            rond.setShape(GradientDrawable.OVAL);
            rond.setColor(couleurEtat());
            d.setBackground(rond);
            LinearLayout.LayoutParams dpar = new LinearLayout.LayoutParams(dp(7), dp(7));
            dpar.rightMargin = dp(7);
            p.addView(d, dpar);
        }
        TextView t = new TextView(ctx);
        t.setText(texte);
        t.setTextColor(actif ? TEXTE : SOURDINE);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, Charte.TAILLE_LIGNE);
        t.setTypeface(actif ? Charte.policeMedium() : Charte.police());
        p.addView(t);
        LinearLayout.LayoutParams pp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dp(40));
        pp.rightMargin = dp(4);
        p.setLayoutParams(pp);
        brancherAppui(p, f, repos, false, new Runnable() {
            public void run() {
                changerPage(cible);
            }
        });
        return p;
    }

    /**
     * Le fond de la carte : ardoise presque opaque, contour fin, et en haut un
     * voile de la couleur d'etat qui s'eteint sur 96 dp. C'est l'element
     * memorable de la carte : l'etat colore l'air du menu, pas ses lettres.
     */
    private android.graphics.drawable.Drawable fondCarte() {
        GradientDrawable fond = Charte.fond(ctx, Charte.CARTE, Charte.RAYON_CARTE);
        fond.setStroke(Math.max(1, dp(0.5f)), Charte.TRAIT);
        float ray = dp(Charte.RAYON_CARTE);
        fond.setCornerRadii(new float[]{ray, ray, 0, 0, 0, 0, ray, ray});
        halo = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{Charte.teinte(couleurEtat(), 0x2E), 0x00000000});
        halo.setCornerRadii(new float[]{ray, ray, 0, 0, 0, 0, 0, 0});
        android.graphics.drawable.LayerDrawable couches =
                new android.graphics.drawable.LayerDrawable(
                        new android.graphics.drawable.Drawable[]{fond, halo});
        couches.setLayerGravity(1, Gravity.TOP | Gravity.FILL_HORIZONTAL);
        couches.setLayerHeight(1, dp(96));
        couches.setLayerInset(1, dp(0.5f), dp(0.5f), dp(0.5f), 0);
        return couches;
    }

    private void peindreHalo() {
        if (halo == null) return;
        halo.setColors(new int[]{Charte.teinte(couleurEtat(), 0x2E), 0x00000000});
    }

    private void remplirMenu() {
        carteVue.removeAllViews();
        String retour = null;
        java.util.ArrayList<String[]> tuiles = new java.util.ArrayList<String[]>();
        for (String[] e : entrees) {
            if (e[0].endsWith("fermer")) retour = e[0];
            else if (estTuile(e[0])) tuiles.add(e);
        }
        peindreHalo();
        if (retour != null) {
            carteVue.addView(enteteSousMenu(retour));
            carteVue.addView(trait());
        } else {
            // Deux pages : Apps (la grille) et Creeper (l'etat et les actions).
            carteVue.addView(onglets());
            carteVue.addView(trait());
            if (page == 0) {
                carteVue.addView(panneau.page());
                return;
            }
            carteVue.addView(entete(false));
        }

        // Les groupes : les tuiles, les rapports en attente, puis ceux que
        // menu.txt separe par une ligne "-:-". Un trait n'est pose qu'entre
        // deux groupes garnis, jamais en tete ni en queue.
        boolean garni = false;
        boolean couper = false;
        boolean avantRapport = false;
        // Une voix parle : ses commandes passent AVANT tout le reste. C'est
        // le seul moment ou elles servent, et le moment ou USER ouvre le menu.
        if (retour == null && (Voix.occupe() || Lecteur.actif())) {
            java.util.ArrayList<String[]> lec = new java.util.ArrayList<String[]>();
            lec.add(new String[]{"lecprec", ""});
            lec.add(new String[]{"lecbascule", ""});
            lec.add(new String[]{"lecsuiv", ""});
            lec.add(new String[]{"lecstop", ""});
            carteVue.addView(rangeeTuiles(lec));
            garni = true;
            couper = true;
        }
        if (!tuiles.isEmpty()) {
            carteVue.addView(rangeeTuiles(tuiles));
            garni = true;
            couper = true;
        }
        for (String[] e : entrees) {
            String id = e[0];
            if (id.endsWith("fermer") || estTuile(id)) continue;
            if ("-".equals(id)) {
                couper = true;
                continue;
            }
            boolean rap = id.startsWith("rapport");
            if (rap != avantRapport) couper = true;
            if (couper && garni) carteVue.addView(separation());
            couper = false;
            if (e[1] != null && e[1].indexOf('^') > 0) carteVue.addView(curseur(id, e[1]));
            else carteVue.addView(ligne(id, e[1]));
            garni = true;
            avantRapport = rap;
        }
    }

    /**
     * Rejoue le contenu du menu deja ouvert, sans toucher a sa fenetre.
     *
     * Sert quand l'etat change sous les doigts de USER (ARRETER devient
     * REPRENDRE) ou quand la pastille passe d'un bord a l'autre.
     */
    private void majMenu() {
        if (!ouvert || menu == null) return;
        if (transition) {
            majPendante = true;
            return;
        }
        remplirMenu();
    }

    /** La pastille ouvre le panneau sur la page Creeper. */
    private void ouvrir() {
        ouvrirPage(1, false);
    }

    /**
     * Fait venir le panneau lateral : une fenetre plein ecran (le voile qui
     * assombrit et capte tous les touchers) et, ancree au bord droit, la carte
     * qui glisse. Avec suivre, la carte part fermee et le doigt de la barre la
     * tire (voir barreSuit) ; sinon elle entre seule.
     */
    private void ouvrirPage(int depart, boolean suivre) {
        if (ouvert || menu != null) return;
        cacherChoix();
        carteL = largeurPage(depart);

        menu = new FrameLayout(ctx);
        voile = new View(ctx);
        voile.setBackgroundColor(0xFF000000);
        voile.setAlpha(0f);
        // Un toucher sur le voile replie le panneau, et ne traverse pas.
        voile.setOnTouchListener(new View.OnTouchListener() {
            public boolean onTouch(View v, MotionEvent ev) {
                if (ev.getAction() == MotionEvent.ACTION_DOWN
                        || ev.getAction() == MotionEvent.ACTION_MOVE) suivreDoigt(ev);
                if (ev.getAction() == MotionEvent.ACTION_UP) {
                    fermeDehors = System.currentTimeMillis();
                    fermer();
                }
                return true;
            }
        });
        menu.addView(voile, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));

        final int pas = Math.round(dp(60));
        carteVue = new LinearLayout(ctx) {
            private float ax, ay;
            private boolean tire;

            /** La tete suit le doigt sur tout le panneau, tuiles comprises. */
            @Override
            public boolean dispatchTouchEvent(MotionEvent ev) {
                int a = ev.getActionMasked();
                if (a == MotionEvent.ACTION_DOWN || a == MotionEvent.ACTION_MOVE) suivreDoigt(ev);
                return super.dispatchTouchEvent(ev);
            }

            @Override
            public boolean onInterceptTouchEvent(MotionEvent ev) {
                switch (ev.getActionMasked()) {
                    case MotionEvent.ACTION_DOWN:
                        ax = ev.getRawX();
                        ay = ev.getRawY();
                        tire = false;
                        break;
                    case MotionEvent.ACTION_MOVE:
                        float dx = ev.getRawX() - ax;
                        float dy = ev.getRawY() - ay;
                        float seuil = 2 * android.view.ViewConfiguration.get(ctx).getScaledTouchSlop();
                        if (Math.abs(dx) > seuil && Math.abs(dx) > Math.abs(dy)) {
                            tire = true;
                            return true;
                        }
                        break;
                }
                return false;
            }

            @Override
            public boolean onTouchEvent(MotionEvent ev) {
                // La carte consomme tout : un toucher dans sa marge ne doit pas
                // atteindre le voile et la replier.
                if (ev.getActionMasked() == MotionEvent.ACTION_DOWN) {
                    ax = ev.getRawX();
                    ay = ev.getRawY();
                    return true;
                }
                if (ev.getActionMasked() == MotionEvent.ACTION_UP) {
                    float dx = ev.getRawX() - ax;
                    if (dx <= -pas && page == 0) changerPage(1);
                    else if (dx >= pas) {
                        if (page == 1) changerPage(0);
                        else fermer();
                    }
                }
                return true;
            }
        };
        carteVue.setOrientation(LinearLayout.VERTICAL);
        carteVue.setPadding(dp(4), dp(2), dp(4), dp(6));
        carteVue.setBackground(fondCarte());
        carteVue.setElevation(dp(12));
        FrameLayout.LayoutParams cp = new FrameLayout.LayoutParams(
                carteL, FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.END | Gravity.CENTER_VERTICAL);
        cp.topMargin = cp.bottomMargin = dp(24);
        menu.addView(carteVue, cp);

        if (panneau == null) {
            panneau = new Panneau(ctx, prefs, new Panneau.Hote() {
                public void lancer(String paquet) {
                    lancerApp(paquet);
                }

                public void rafraichir() {
                    majMenu();
                }

                public int dp(float v) {
                    return Bulle.this.dp(v);
                }

                public void tic(int ms) {
                    vibrer(ms);
                }

                public void clavier(boolean oui) {
                    Bulle.this.clavier(oui);
                }
            });
        }
        clavierOuvert = false;
        transition = false;
        majPendante = false;
        panneau.reinitialiser();
        page = depart;
        remplirMenu();

        lpMenu = new WindowManager.LayoutParams(
                ecranL(), ecranH(),
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        lpMenu.gravity = Gravity.TOP | Gravity.START;
        if (android.os.Build.VERSION.SDK_INT >= 28) {
            lpMenu.layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
        }
        carteVue.setTranslationX(carteL + dp(MARGE));
        try {
            wm.addView(menu, lpMenu);
        } catch (Exception e) {
            menu = null;
            return;
        }
        ouvert = true;
        if (!suivre) glisserCarte(0, voileMax());
        versCouleur();
        reveiller();
        surLePanneau();
    }

    /**
     * La pastille reste DEVANT le panneau (USER, 2026-10-07 : « je ne peux plus
     * la bouger »). Sur un meme type de fenetre, la derniere ajoutee passe
     * dessus : on retire la pastille et on la repose apres le panneau.
     */
    private void surLePanneau() {
        try {
            wm.removeView(racine);
            wm.addView(racine, lp);
        } catch (Exception ignore) {
        }
        // Retirer la fenetre arrete la boucle de dessin de la tete
        // (Tete.onDetachedFromWindow) : sans cette relance, elle s'effaçait
        // a l'ouverture du panneau (USER, 2026-10-07).
        pastille.setActif(false);
        pastille.setActif(!discret());
        pastille.invalidate();
    }

    private boolean clavierOuvert = false;

    /**
     * Le champ de recherche du panneau. La fenetre est NOT_FOCUSABLE (elle ne
     * doit pas voler le focus aux autres apps) : elle ne devient focalisable
     * que le temps de la saisie, et la carte monte en haut pour ne pas finir
     * sous le clavier.
     */
    private void clavier(boolean oui) {
        if (menu == null || lpMenu == null || oui == clavierOuvert) return;
        clavierOuvert = oui;
        if (oui) lpMenu.flags &= ~WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE;
        else lpMenu.flags |= WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE;
        try {
            wm.updateViewLayout(menu, lpMenu);
        } catch (Exception ignore) {
        }
        if (carteVue != null && carteVue.getLayoutParams() instanceof FrameLayout.LayoutParams) {
            FrameLayout.LayoutParams cp = (FrameLayout.LayoutParams) carteVue.getLayoutParams();
            cp.gravity = Gravity.END | (oui ? Gravity.TOP : Gravity.CENTER_VERTICAL);
            cp.topMargin = dp(oui ? 56 : 24);
            carteVue.setLayoutParams(cp);
        }
        if (!oui) {
            try {
                android.view.inputmethod.InputMethodManager im =
                        (android.view.inputmethod.InputMethodManager)
                                ctx.getSystemService(Context.INPUT_METHOD_SERVICE);
                if (im != null) im.hideSoftInputFromWindow(menu.getWindowToken(), 0);
            } catch (Exception ignore) {
            }
        }
    }

    private float voileMax() {
        return 0.75f;
    }

    /** Anime la carte vers sa position (0 = ouverte) et le voile vers son opacite. */
    private void glisserCarte(float versX, float versVoile) {
        if (carteVue == null || voile == null) return;
        float reste = Math.abs(carteVue.getTranslationX() - versX);
        // Duree de Panels : la distance en dp, entre 150 et 350 ms.
        long ms = Math.max(150, Math.min(350, Math.round(reste / dp(1))));
        carteVue.animate().translationX(versX).setDuration(ms)
                .setInterpolator(Charte.courbe()).start();
        voile.animate().alpha(versVoile).setDuration(ms).start();
    }

    private boolean transition = false;
    private boolean majPendante = false;
    private android.animation.ValueAnimator animPage;

    /**
     * Passe d'une page a l'autre sans saut (USER, 2026-10-07 : les deux pages
     * n'ont pas la meme taille, le changement sec n'etait « pas naturel »).
     * L'ancien contenu s'efface, la carte glisse vers sa nouvelle largeur et sa
     * nouvelle hauteur, puis le nouveau contenu entre depuis le cote d'ou
     * vient la page.
     */
    private void changerPage(final int cible) {
        if (page == cible || transition) return;
        if (carteVue == null || menu == null || carteVue.getHeight() == 0) {
            page = cible;
            appliquerLargeur();
            panneau.reinitialiser();
            majMenu();
            return;
        }
        transition = true;
        final int sens = cible > page ? 1 : -1;
        for (int i = 2; i < carteVue.getChildCount(); i++) {
            carteVue.getChildAt(i).animate().alpha(0f).setDuration(90).start();
        }
        h.postDelayed(new Runnable() {
            public void run() {
                morpher(cible, sens);
            }
        }, 90);
    }

    private void morpher(final int cible, final int sens) {
        if (menu == null || carteVue == null) {
            transition = false;
            return;
        }
        final int l0 = carteVue.getWidth();
        final int h0 = carteVue.getHeight();
        page = cible;
        carteL = largeurPage(cible);
        panneau.reinitialiser();
        remplirMenu();
        final int decalage = dp(18) * sens;
        final int l1 = carteL;
        // Le contenu garde sa largeur FINALE pendant tout le morphing : seule
        // la carte change de taille, et elle le rogne. Sans cela les tuiles
        // se resserraient avec la carte et « Ou j'en suis » passait sur 2
        // lignes le temps de l'animation (retour de USER, 2026-10-07).
        final int interieur = l1 - carteVue.getPaddingLeft() - carteVue.getPaddingRight();
        final int[] largeurs = new int[carteVue.getChildCount()];
        for (int i = 2; i < carteVue.getChildCount(); i++) {
            View v = carteVue.getChildAt(i);
            v.setAlpha(0f);
            v.setTranslationX(decalage);
            android.view.ViewGroup.LayoutParams vp = v.getLayoutParams();
            largeurs[i] = vp.width;
            if (vp instanceof LinearLayout.LayoutParams) {
                LinearLayout.LayoutParams lv = (LinearLayout.LayoutParams) vp;
                lv.width = interieur - lv.leftMargin - lv.rightMargin;
            } else {
                vp.width = interieur;
            }
        }
        carteVue.measure(
                View.MeasureSpec.makeMeasureSpec(l1, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(Math.max(h0, ecranH() - dp(48)),
                        View.MeasureSpec.AT_MOST));
        final int h1 = carteVue.getMeasuredHeight();
        final android.view.ViewGroup.LayoutParams lpc = carteVue.getLayoutParams();
        lpc.width = l0;
        lpc.height = h0;
        carteVue.setLayoutParams(lpc);

        animPage = android.animation.ValueAnimator.ofFloat(0f, 1f);
        animPage.setDuration(300);
        animPage.setInterpolator(Charte.courbe());
        animPage.addUpdateListener(new android.animation.ValueAnimator.AnimatorUpdateListener() {
            public void onAnimationUpdate(android.animation.ValueAnimator a) {
                if (carteVue == null) return;
                float t = (Float) a.getAnimatedValue();
                lpc.width = Math.round(l0 + (l1 - l0) * t);
                lpc.height = Math.round(h0 + (h1 - h0) * t);
                carteVue.setLayoutParams(lpc);
                float c = Math.max(0f, Math.min(1f, (t - 0.3f) / 0.7f));
                for (int i = 2; i < carteVue.getChildCount(); i++) {
                    View v = carteVue.getChildAt(i);
                    v.setAlpha(c);
                    v.setTranslationX(decalage * (1f - c));
                }
            }
        });
        animPage.addListener(new android.animation.AnimatorListenerAdapter() {
            public void onAnimationEnd(android.animation.Animator a) {
                transition = false;
                if (carteVue == null) return;
                lpc.width = l1;
                lpc.height = android.view.ViewGroup.LayoutParams.WRAP_CONTENT;
                carteVue.setLayoutParams(lpc);
                for (int i = 2; i < carteVue.getChildCount() && i < largeurs.length; i++) {
                    View v = carteVue.getChildAt(i);
                    v.setAlpha(1f);
                    v.setTranslationX(0f);
                    v.getLayoutParams().width = largeurs[i];
                    v.requestLayout();
                }
                if (majPendante) {
                    majPendante = false;
                    majMenu();
                }
            }
        });
        animPage.start();
    }

    /** La carte est etroite sur Apps, plus large sur Creeper. */
    private int largeurPage(int p) {
        return dp(p == 0 ? CARTE_APPS : CARTE_L);
    }

    private void appliquerLargeur() {
        carteL = largeurPage(page);
        if (carteVue != null && carteVue.getLayoutParams() != null) {
            carteVue.getLayoutParams().width = carteL;
            carteVue.requestLayout();
        }
    }

    // Les 4 gestes de la barre (voir Barre.java).
    int barreLargeur() {
        return dp(CARTE_APPS);
    }

    void barreDebut() {
        if (ouvert) return;
        ouvrirPage(0, true);
    }

    /** ouvert : distance parcourue par le doigt depuis le bord, en px. */
    void barreSuit(float ouvertPx) {
        if (carteVue == null || voile == null) return;
        float part = Math.max(0f, Math.min(1f, ouvertPx / carteL));
        carteVue.animate().cancel();
        voile.animate().cancel();
        carteVue.setTranslationX((1f - part) * (carteL + dp(MARGE)));
        voile.setAlpha(part * voileMax());
    }

    void barreFin(boolean ouvrir) {
        if (ouvrir) glisserCarte(0, voileMax());
        else fermer();
    }

    /** Surligne l'icone sous le doigt (x < 0 : rien). */
    void barreSurvol(float x, float y) {
        View cible = x < 0 ? null : caseSous(x, y);
        if (cible == caseSurvol) return;
        if (caseSurvol != null) caseSurvol.setBackground(caseSurvolFond);
        caseSurvol = cible;
        if (cible != null) {
            caseSurvolFond = cible.getBackground();
            GradientDrawable g = new GradientDrawable();
            g.setCornerRadius(dp(Charte.RAYON_TUILE));
            g.setColor(0x33FFFFFF);
            cible.setBackground(g);
            vibrer(Charte.TIC_GESTE);
        }
    }

    /** Doigt leve : lance l'icone dessous. Vrai si une app est partie. */
    boolean barreRelache(float x, float y) {
        View c = caseSous(x, y);
        if (c == null) return false;
        lancerApp(String.valueOf(c.getTag()).substring(4));
        return true;
    }

    private View caseSous(float x, float y) {
        if (carteVue == null || page != 0) return null;
        return caseDans(carteVue, x, y);
    }

    private View caseDans(View v, float x, float y) {
        Object t = v.getTag();
        if (t instanceof String && ((String) t).startsWith("app:")) {
            int[] p = new int[2];
            v.getLocationOnScreen(p);
            if (x >= p[0] && x <= p[0] + v.getWidth() && y >= p[1] && y <= p[1] + v.getHeight()) return v;
            return null;
        }
        if (v instanceof ViewGroup) {
            ViewGroup g = (ViewGroup) v;
            for (int i = 0; i < g.getChildCount(); i++) {
                View r = caseDans(g.getChildAt(i), x, y);
                if (r != null) return r;
            }
        }
        return null;
    }

    /** Le point ecran tombe-t-il dans la fenetre de la pastille ? */
    private boolean surLaPastille(float x, float y) {
        int[] p = new int[2];
        racine.getLocationOnScreen(p);
        return x >= p[0] && x <= p[0] + racine.getWidth()
                && y >= p[1] && y <= p[1] + racine.getHeight();
    }

    /** Le panneau est plein ecran : rien a poser contre la pastille. */
    private void positionnerMenu() {
    }

    /** Lance une app de la grille et replie le panneau. */
    private void lancerApp(String paquet) {
        Intent i = ctx.getPackageManager().getLaunchIntentForPackage(paquet);
        fermer();
        if (i == null) return;
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
        try {
            ctx.startActivity(i);
        } catch (Exception ignore) {
        }
    }

    private void fermer() {
        if (!ouvert) return;
        ouvert = false;
        if (animPage != null) animPage.cancel();
        transition = false;
        final View partant = menu;
        final View c = carteVue;
        final View vo = voile;
        menu = null;
        versCouleur();
        estomperPlusTard();
        if (partant == null) return;
        caseSurvol = null;
        if (c != null) c.animate().cancel();
        if (vo != null) vo.animate().cancel();
        float reste = c == null ? 0 : Math.abs(c.getTranslationX() - (carteL + dp(MARGE)));
        long ms = Math.max(150, Math.min(350, Math.round(reste / dp(1))));
        if (vo != null) vo.animate().alpha(0f).setDuration(ms).start();
        if (c == null) {
            try {
                wm.removeView(partant);
            } catch (Exception ignore) {
            }
            return;
        }
        c.animate().translationX(carteL + dp(MARGE)).setDuration(ms)
                .setInterpolator(Charte.courbeSortie())
                .withEndAction(new Runnable() {
                    public void run() {
                        try {
                            wm.removeView(partant);
                        } catch (Exception ignore) {
                        }
                    }
                }).start();
    }

    /** Repli sans animation : la vue doit avoir disparu au retour. */
    private void fermerNet() {
        ouvert = false;
        if (menu == null) return;
        try {
            wm.removeView(menu);
        } catch (Exception ignore) {
        }
        menu = null;
    }

    // ------------------------------------------------------------- glisser

    private FileObserver oeilFichier;
    private long dernierRegard;

    /**
     * La vraie position du doigt, venue du garde (2026-10-07).
     *
     * Android cache a l'appli l'endroit d'un toucher dans une autre appli :
     * le coup d'oeil par ACTION_OUTSIDE n'a donc qu'une direction fixe, et la
     * tete avait l'air morte. Le garde de hote-1 lit deja le tactile
     * (/dev/input) : il ecrit "x y" en permilles d'ecran dans files/regard.txt,
     * et ce fichier est surveille ici. Aucun service d'accessibilite.
     * Sans ADB le fichier ne bouge plus et le coup d'oeil reprend la main.
     */
    private void ecouterRegard() {
        final java.io.File d = ctx.getExternalFilesDir(null);
        if (d == null || oeilFichier != null) return;
        oeilFichier = new FileObserver(d.getPath(),
                FileObserver.MODIFY | FileObserver.CLOSE_WRITE) {
            @Override
            public void onEvent(int ev, String nom) {
                if (!"regard.txt".equals(nom)) return;
                try {
                    java.io.BufferedReader r = new java.io.BufferedReader(
                            new java.io.FileReader(new java.io.File(d, nom)));
                    String l = r.readLine();
                    r.close();
                    if (l == null) return;
                    String[] m = l.trim().split(" ");
                    if (m.length < 2) return;
                    final float px = Float.parseFloat(m[0]) / 1000f;
                    final float py = Float.parseFloat(m[1]) / 1000f;
                    h.post(new Runnable() {
                        public void run() { viserEcran(px, py); }
                    });
                } catch (Exception e) {
                    Log.i("pixelgarde", "regard erreur " + e);
                }
            }
        };
        oeilFichier.startWatching();
    }

    /** Regard vers un point de l'ecran, en fraction (0..1) de sa largeur et hauteur. */
    private void viserEcran(float fx, float fy) {
        if (pastille == null || lp == null) return;
        dernierRegard = SystemClock.uptimeMillis();
        float cx = (lp.x + dp(TOUCHE_L) / 2f) / ecranL();
        float cy = (lp.y + dp(TOUCHE_H) / 2f) / ecranH();
        // Un demi-ecran de distance = regard au maximum.
        pastille.viser((fx - cx) * 2f * 1.4f, (fy - cy) * 2f * 1.2f);
    }

    /**
     * Traduit la position du doigt en direction de regard.
     *
     * Mesuree depuis le CENTRE de la pastille et rapportee a sa taille : une
     * valeur en pixels aurait donne un regard qui depend de la densite de
     * l'ecran, et un doigt pose a 3 cm aurait tordu le cou a la tete.
     */
    private void coupDOeil(MotionEvent ev) {
        if (lp == null) return;
        // Le garde donne la vraie position : le coup d'oeil a l'aveugle se tait.
        if (SystemClock.uptimeMillis() - dernierRegard < 3000) return;
        // Coordonnees nulles : on regarde du cote de l'ecran, vers l'interieur.
        if (ev.getRawX() > 1f || ev.getRawY() > 1f) {
            suivreDoigt(ev);
            return;
        }
        boolean droite = lp.x + dp(TOUCHE_L) / 2 > ecranL() / 2;
        pastille.viser(droite ? -1.3f : 1.3f, 0.15f);
    }

    private void suivreDoigt(MotionEvent ev) {
        if (pastille == null || lp == null) return;
        float cx = lp.x + dp(TOUCHE_L) / 2f;
        float cy = lp.y + dp(TOUCHE_H) / 2f;
        float r = dp(ROND);
        pastille.viser((ev.getRawX() - cx) / r, (ev.getRawY() - cy) / r);
    }

    /**
     * Rouvre le micro sur le telephone meme, sans aller-retour par hote-1.
     *
     * Le service Voix tourne deja (la conversation reste ouverte en « pret »),
     * donc un simple startService suffit : il connait son etat et passe de
     * pret a ecoute. Passer par le garde coutait un aller-retour adb, et un
     * appui doit repondre sous le doigt.
     *
     * Service mort (appli reinstallee, telephone redemarre) alors que hote-1
     * croit encore la conversation en « pret » : on passe par le garde, qui
     * relance le service au premier plan comme le bouton du menu. Un
     * startForegroundService d'ici risquerait le refus d'Android pour un
     * micro lance hors premier plan.
     */
    /** Clot la phrase en cours et l'envoie. Sans effet hors ecoute. */
    private void envoyerIci() {
        try {
            ctx.startService(new Intent(ctx, Voix.class).setAction(Voix.ENVOYER));
        } catch (Exception ignore) {
        }
        if (pastille != null) pastille.saluer();
        etat = "voixtravaille";
        peindrePastille();
    }

    /**
     * Une tuile de lecture, vers la voix qui parle : la conversation (Voix)
     * ou la lecture d'ecran (Lecteur). Le menu reste ouvert pour enchainer,
     * et se repeint pour que Pause devienne Reprendre.
     */
    private void lireIci(String id) {
        vibrer(12);
        Intent i;
        if (Voix.occupe()) {
            String a = "lecprec".equals(id) ? Voix.PRECEDENT
                    : "lecsuiv".equals(id) ? Voix.SUIVANT
                    : "lecstop".equals(id) ? Voix.TAIRE : Voix.BASCULE;
            i = new Intent(ctx, Voix.class).setAction(a);
        } else if (Lecteur.actif()) {
            String a = "lecprec".equals(id) ? Lecteur.PREC
                    : "lecsuiv".equals(id) ? Lecteur.SUIV
                    : "lecstop".equals(id) ? Lecteur.STOP : Lecteur.BASCULE;
            i = new Intent(ctx, Lecteur.class).setAction(a);
        } else {
            fermer();
            return;
        }
        try {
            ctx.startService(i);
        } catch (Exception ignore) {
        }
        if ("lecstop".equals(id)) {
            fermer();
            return;
        }
        if ("lecbascule".equals(id)) enPause = !enPause;
        // Le service confirme la pause par lecturePause() ; ce second passage
        // repeint sur l'etat reel si l'intention locale s'est trompee.
        majMenu();
        h.postDelayed(new Runnable() {
            public void run() { majMenu(); }
        }, 400);
    }

    private boolean parlerIci() {
        try {
            if (Voix.actif()) {
                ctx.startService(new Intent(ctx, Voix.class).setAction(Voix.DEMARRER));
            } else {
                commande(ctx, "voix");
                vibrer(15);
            }
        } catch (Exception e) {
            return false;
        }
        etat = "voix";
        peindrePastille();
        return true;
    }

    /**
     * L'appui long a porte la pause du 26/08 au 27/08/2026. USER l'a refusee :
     * un geste sans etiquette ne se retient pas. Le bouton d'etat est revenu
     * dans le menu, en PIED de liste et non en tete, pour ne pas rendre a
     * l'arret la premiere place, celle qui tombe sous le pouce.
     *
     * Depuis le 2026-10-01, l'appui long revient, mais seulement comme porte
     * du menu : il n'arrete ni ne detruit rien. Il sert quand la bulle attend
     * la voix, ou l'appui court fait parler.
     */
    private class Glisser implements View.OnTouchListener {
        private int xDepart, yDepart;
        private float toucheX, toucheY;
        private long debut;
        private boolean bouge;
        /** Vrai quand l'appui long a deja agi : le lacher ne rouvre rien. */
        private boolean longFait;
        /** Vrai quand cet appui long a ouvert le micro, facon talkie-walkie. */
        private boolean pttFait;

        /**
         * Appui long : PARLER, comme un talkie-walkie. USER, 2026-10-02 (la
         * proposition n° 1). On tient, on parle, on lache : la phrase part.
         * Un lacher rapide laisse le micro ouvert, mains libres ; un toucher
         * l'envoie ensuite.
         *
         * Seulement quand parler a un sens : rien ne joue, rien n'ecoute deja,
         * aucun envoi n'est arme, la conversation n'est pas en plein travail.
         * Sinon l'appui long ouvre le menu, qui porte alors les commandes du
         * moment (lecture, Envoyer, Annuler).
         */
        private final Runnable appuiLong = new Runnable() {
            public void run() {
                if (bouge || ouvert) return;
                longFait = true;
                pastille.presser(false);
                if (peutParler() && parlerIci()) {
                    pttFait = true;
                    vibrer(30);
                    return;
                }
                vibrer(25);
                ouvrir();
            }
        };

        /** Le micro peut s'ouvrir sans rien casser de ce qui se passe. */
        private boolean peutParler() {
            if (lienMuet || "suspendu".equals(etat)) return false;
            if (Voix.envoiArme() || Voix.occupe() || Voix.ecoute()) return false;
            if (Lecteur.actif()) return false;
            // Voix active hors ecoute = en plein travail, sauf si elle attend
            // USER : DEMARRER y couperait la reponse en cours.
            return !Voix.actif() || "voixpret".equals(etat);
        }

        public boolean onTouch(View v, MotionEvent ev) {
            switch (ev.getAction()) {
                case MotionEvent.ACTION_OUTSIDE:
                    // USER touche ailleurs. Android ne donne ni l'endroit ni
                    // l'appli (sinon n'importe quelle appli lirait tes
                    // touches) : la tete jette un coup d'oeil vers l'ecran.
                    if (!ouvert && pastille != null) coupDOeil(ev);
                    return false;
                case MotionEvent.ACTION_DOWN:
                    cacherChoix();
                    xDepart = lp.x;
                    yDepart = lp.y;
                    toucheX = ev.getRawX();
                    toucheY = ev.getRawY();
                    debut = System.currentTimeMillis();
                    bouge = false;
                    longFait = false;
                    pttFait = false;
                    h.postDelayed(appuiLong, 450);
                    reveiller();
                    pastille.presser(true);
                    suivreDoigt(ev);
                    return true;

                case MotionEvent.ACTION_MOVE: {
                    int dx = (int) (ev.getRawX() - toucheX);
                    int dy = (int) (ev.getRawY() - toucheY);
                    // Le seuil se calcule TOUJOURS, meme repliee : sans lui,
                    // bouge restait faux et le relachement d'un glisser
                    // ouvrait le menu comme un simple appui.
                    if (Math.abs(dx) > dp(8) || Math.abs(dy) > dp(8)) {
                        bouge = true;
                        h.removeCallbacks(appuiLong);
                    }
                    suivreDoigt(ev);
                    // Repliee, la pastille est FIXE : un glisser dessus ne la
                    // deplace pas. Sinon elle partait au moindre frolement,
                    // alors qu'on visait juste le menu.
                    if (!ouvert) return true;
                    if (!bouge) return true;
                    lp.x = xDepart + dx;
                    lp.y = Math.max(dp(24), Math.min(ecranH() - dp(80), yDepart + dy));
                    try {
                        wm.updateViewLayout(racine, lp);
                        // Le menu suit le doigt au lieu d'etre referme : on
                        // voit ou on pose l'ensemble.
                        if (menu != null) {
                            positionnerMenu();
                            wm.updateViewLayout(menu, lpMenu);
                        }
                    } catch (Exception ignore) {
                    }
                    return true;
                }

                case MotionEvent.ACTION_UP:
                    h.removeCallbacks(appuiLong);
                    pastille.presser(false);
                    if (longFait) {
                        // Talkie-walkie : le lacher envoie. Mais seulement si
                        // le micro tourne depuis plus d'une seconde : un lacher
                        // plus rapide veut dire « mains libres », et le micro
                        // reste ouvert jusqu'au toucher qui envoie.
                        if (pttFait && Voix.ecoute()
                                && System.currentTimeMillis() - Voix.ecouteDepuis() > 1000) {
                            envoyerIci();
                        }
                        return true;
                    }
                    // Un envoi au QG est arme : l'appui court l'ANNULE, avant
                    // toute autre lecture du geste. USER, 2026-10-01 : « que
                    // j'aie a cliquer sur la bulle pour annuler l'envoi ».
                    if (!bouge && !ouvert && Voix.envoiArme()) {
                        pastille.setCompte(0);
                        try {
                            ctx.startService(new Intent(ctx, Voix.class).setAction(Voix.ANNULER_ENVOI));
                        } catch (Exception ignore) {
                        }
                        return true;
                    }
                    // La voix parle : l'appui court la met en pause, le
                    // suivant la relance. USER, 2026-10-02 : « en cliquant sur
                    // le creeper pendant qu'il est en train de parler », puis
                    // « je peux pas la relancer si je rappuie dessus ».
                    // Le menu reste a l'appui long, l'arret dans la notification.
                    // occupe() couvre aussi la voix prete mais retenue par une
                    // dictee : sans lui, ce toucher ouvrait le micro.
                    // Le micro ecoute : le toucher ENVOIE. Le silence ne fait
                    // plus partir la phrase (USER, 2026-10-02 : « des fois je
                    // fais des pauses »), c'est ce geste qui le fait.
                    if (!bouge && !ouvert && Voix.ecoute()) {
                        envoyerIci();
                        return true;
                    }
                    if (!bouge && !ouvert && Voix.occupe()) {
                        try {
                            ctx.startService(new Intent(ctx, Voix.class).setAction(Voix.BASCULE));
                        } catch (Exception ignore) {
                        }
                        return true;
                    }
                    // Plus de « toucher = parler », ni de toucher mort apres
                    // la voix. USER, 2026-10-03 : apres un rapport, il voulait
                    // ouvrir le menu et le micro s'ouvrait. Le toucher ouvre
                    // TOUJOURS le menu (Parler y est en tete) ; parler, c'est
                    // l'appui long, facon talkie-walkie.
                    // La lecture d'ecran joue : le toucher la met en pause.
                    if (!bouge && !ouvert && Lecteur.actif()) {
                        try {
                            ctx.startService(new Intent(ctx, Lecteur.class).setAction(Lecteur.BASCULE));
                        } catch (Exception ignore) {
                        }
                        return true;
                    }
                    // Des rapports attendent : le toucher OUVRE le menu, ou ils
                    // sont en tete. Du 2026-10-02 22:08 a 22:30, il lisait le
                    // plus recent a la place. USER : « je peux pas ouvrir le menu
                    // quand il y a le ! ». Un toucher fait toujours la meme
                    // chose, quel que soit le chiffre affiche.
                    if (!bouge) {
                        // Un appui sur la pastille menu ouvert arrive APRES
                        // l'ACTION_OUTSIDE qui vient de le fermer : sans ce
                        // delai de garde, le menu se rouvrirait aussitot.
                        if (ouvert) fermer();
                        else if (System.currentTimeMillis() - fermeDehors > 250) ouvrir();
                        return true;
                    }
                    // Glisser sur une pastille repliee : le menu, si le geste
                    // est franc (3 fois le seuil). C'est la porte du menu quand
                    // le toucher lit un rapport et que l'appui long parle.
                    // Un frolement de moins de 24 dp ne fait toujours rien.
                    if (!ouvert) {
                        float gx = ev.getRawX() - toucheX, gy = ev.getRawY() - toucheY;
                        if (Math.hypot(gx, gy) > dp(24)
                                && System.currentTimeMillis() - fermeDehors > 250) ouvrir();
                        return true;
                    }
                    // Aimantation au bord, sans marge : la barrette doit
                    // toucher le bord de l'ecran pour se lire comme un onglet.
                    boolean gaucheAvant = aGauche();
                    int taille = dp(TOUCHE_L);
                    int large = ecranL();
                    lp.x = (lp.x + taille / 2 < large / 2) ? 0 : large - taille;
                    dernL = large;
                    dernH = ecranH();
                    try {
                        wm.updateViewLayout(racine, lp);
                    } catch (Exception ignore) {
                    }
                    peindrePastille();   // le cote a pu changer
                    xAncre = lp.x;
                    yAncre = lp.y;
                    prefs.edit().putInt("x", lp.x).putInt("y", lp.y).apply();
                    if (ouvert) {
                        if (gaucheAvant != aGauche()) {
                            // Le menu a change de bord : sa gravite interne est
                            // figee a la construction, il faut la rejouer. Mais
                            // en place : le refermer pour le rouvrir aurait
                            // relance les deux animations en plein glisser.
                            majMenu();
                        } else {
                            positionnerMenu();
                            try {
                                wm.updateViewLayout(menu, lpMenu);
                            } catch (Exception ignore) {
                            }
                        }
                    }
                    estomperPlusTard();
                    return true;

                case MotionEvent.ACTION_CANCEL:
                    // Une autre fenetre a pris le geste (volet de notifications,
                    // appel entrant) : on rend la pastille a son repos.
                    h.removeCallbacks(appuiLong);
                    pastille.presser(false);
                    return true;
            }
            return false;
        }
    }
}
