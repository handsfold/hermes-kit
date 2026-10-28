package com.poste.pixelgarde;

import android.content.Context;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.util.DisplayMetrics;
import android.view.animation.Interpolator;
import android.view.animation.PathInterpolator;

/**
 * La charte graphique du Creeper : toutes les valeurs visuelles en un lieu.
 *
 * Aucun fichier ne pose plus une couleur, une taille ou une duree en dur :
 * il prend le jeton ici. Un jeton change, toute l'appli suit.
 *
 * Choix de fond :
 *  - canvas sombre et neutre, traits fins, pas de gris bleute ni de noir pur ;
 *  - 6 couleurs d'etat reglees a la meme clarte percue, pour qu'aucune ne
 *    crie plus fort que les autres sur fond sombre ;
 *  - une seule famille de police (Google Sans sur Pixel, sans-serif ailleurs),
 *    deux graisses : normal et medium ;
 *  - grille de 4 dp, trois rayons (ligne, tuile, carte) et la pilule ;
 *  - une seule courbe de mouvement et trois durees.
 */
final class Charte {
    private Charte() {
    }

    // ----- Neutres : du plus profond au plus clair -----
    static final int CARTE = 0xF718191E;          // fond de la carte, presque opaque
    static final int SURFACE = 0xFF23252B;        // tuiles, piste du curseur, boutons neutres
    static final int SURFACE_HAUTE = 0xFF2E3138;  // appui, poignee de retour
    static final int TRAIT = 0x1AFFFFFF;          // separateur, contour fin
    static final int CONTOUR = 0x24FFFFFF;        // contour d'une pilule neutre
    static final int SURLIGNE = 0x1AFFFFFF;       // voile d'appui sur une ligne

    // ----- Texte : trois niveaux, jamais de blanc pur -----
    static final int TEXTE = 0xFFF2F3F5;
    static final int TEXTE_2 = 0xFFA3A8B2;        // libelles secondaires, valeurs
    static final int TEXTE_3 = 0xFF6E737D;        // chevrons, indices
    static final int TEXTE_SUR_ACCENT = 0xFF0E1A13; // texte pose sur un bouton vert

    // ----- Etats : meme clarte, chroma moderee -----
    static final int VERT = 0xFF3DC27A;           // je pilote, oui
    static final int AMBRE = 0xFFE6B13F;          // tu as la main, j'attends
    static final int ORANGE = 0xFFF07A4C;         // arret, retrait
    static final int BLEU = 0xFF5F8FEF;           // on se parle
    static final int BLEU_CLAIR = 0xFFA6C2FF;     // icone sur un conteneur bleu
    static final int ROUGE = 0xFFEF5350;          // l'ecran est enregistre
    static final int GRIS = 0xFF6E737D;           // repos, personne n'agit
    static final int VEILLE = 0xFF8E939C;         // la barre au repos

    // ----- Dessin sur la tete (indicateurs, badge, compte a rebours) -----
    static final int ENCRE = 0xFFFFFFFF;            // trait blanc sur le creeper
    static final int OMBRE_LEGERE = 0x66000000;     // fond d'un indicateur
    static final int OMBRE = 0x99000000;            // fond d'un chiffre
    static final int OMBRE_FORTE = 0xCC111111;      // disque du compte a rebours
    static final int OMBRE_TEXTE = 0xAA000000;      // ombre portee d'un chiffre
    static final int CREEPER_FOND = 0xFF15361F;     // vert de l'icone de l'appli

    // ----- Grille, rayons -----
    static final float RAYON_LIGNE = 12;
    static final float RAYON_TUILE = 14;
    static final float RAYON_CARTE = 24;
    static final float RAYON_PILULE = 22;         // = demi-hauteur d'un bouton de 44

    // ----- Mouvement : une courbe, trois durees -----
    static final long PRESSE_MS = 90;
    static final long CONTENU_MS = 180;
    static final long OUVERTURE_MS = 260;
    static final long FERMETURE_MS = 140;

    /** Courbe « emphasized decelerate » : part vite, se pose en douceur. */
    static Interpolator courbe() {
        return new PathInterpolator(0.05f, 0.7f, 0.1f, 1f);
    }

    /** Courbe de sortie : part doucement, disparait vite. */
    static Interpolator courbeSortie() {
        return new PathInterpolator(0.3f, 0f, 0.8f, 0.15f);
    }

    // ----- Retours haptiques -----
    static final int TIC_LEGER = 8;
    static final int TIC_CONFIRME = 15;
    static final int TIC_GESTE = 20;

    // ----- Police : une famille, deux graisses -----
    private static Typeface normale, medium;

    static Typeface police() {
        if (normale == null) {
            Typeface t = Typeface.create("google-sans", Typeface.NORMAL);
            if (t == null || t.equals(Typeface.DEFAULT)) t = Typeface.SANS_SERIF;
            normale = t;
        }
        return normale;
    }

    static Typeface policeMedium() {
        if (medium == null) {
            Typeface base = police();
            Typeface t = Typeface.create(base, 500, false);
            if (t == null || t.equals(base)) t = Typeface.create("sans-serif-medium", Typeface.NORMAL);
            medium = t;
        }
        return medium;
    }

    // ----- Echelle typographique (sp) -----
    static final float TAILLE_TITRE = 15.5f;      // titre d'un sous-menu
    static final float TAILLE_LIGNE = 14f;        // ligne de menu
    static final float TAILLE_VALEUR = 12.5f;     // valeur a droite, pourcentage
    static final float TAILLE_ETAT = 12.5f;       // phrase d'etat de l'en-tete
    static final float TAILLE_TUILE = 11.5f;      // libelle sous une icone
    static final float TAILLE_BOUTON = 15f;       // Oui, Detail

    /** Une couleur avec une autre opacite (0 a 255). */
    static int teinte(int couleur, int alpha) {
        return (couleur & 0x00FFFFFF) | (alpha << 24);
    }

    /** Un fond arrondi d'une couleur, pret a poser. */
    static GradientDrawable fond(Context ctx, int couleur, float rayonDp) {
        GradientDrawable f = new GradientDrawable();
        f.setShape(GradientDrawable.RECTANGLE);
        f.setCornerRadius(dp(ctx, rayonDp));
        f.setColor(couleur);
        return f;
    }

    static int dp(Context ctx, float v) {
        DisplayMetrics m = ctx.getResources().getDisplayMetrics();
        return Math.round(v * m.density);
    }
}
