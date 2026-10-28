package com.poste.pixelgarde;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PathEffect;
import android.graphics.CornerPathEffect;
import android.graphics.RectF;
import android.util.TypedValue;
import android.view.View;

/**
 * Les icones du menu, TRACEES et non prises dans une fonte.
 *
 * Pourquoi : les glyphes Unicode « geometriques » (‖ ▶ ◉ ✕) n'ont ni la meme
 * chasse, ni la meme hauteur d'oeil, ni la meme graisse. Alignes dans une
 * colonne, ils paraissent flotter chacun a sa maniere, et aucune retouche de
 * marge ne rattrape ca : le defaut est dans la fonte. Un emoji, lui, arrive en
 * couleur imposee et casse l'harmonie de la carte.
 *
 * Ici, tout est dessine dans une grille de 24 unites, au meme trait et sur le
 * meme centre optique. La colonne est donc reglee une fois pour toutes, et une
 * icone neuve entre au cordeau sans qu'on retouche quoi que ce soit.
 */
class Icone extends View {

    private final String id;
    private final int couleur;
    private final int cote;

    private final Paint trait = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint plein = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path p = new Path();
    private final RectF r = new RectF();

    Icone(Context c, String id, int couleur, float tailleDp) {
        super(c);
        this.id = id == null ? "" : id;
        this.couleur = couleur;
        this.cote = (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP,
                tailleDp, c.getResources().getDisplayMetrics());
        trait.setStyle(Paint.Style.STROKE);
        trait.setStrokeCap(Paint.Cap.ROUND);
        trait.setStrokeJoin(Paint.Join.ROUND);
        trait.setColor(couleur);
        plein.setStyle(Paint.Style.FILL);
        plein.setColor(couleur);
    }

    @Override
    protected void onMeasure(int wSpec, int hSpec) {
        setMeasuredDimension(cote, cote);
    }

    /** Une unite de la grille de 24. Tout le trace en depend. */
    private float u() {
        return cote / 24f;
    }

    @Override
    protected void onDraw(Canvas c) {
        float u = u();
        trait.setStrokeWidth(u * 1.85f);
        trait.setPathEffect(null);
        plein.setPathEffect(null);
        p.reset();

        if ("stop".equals(id)) {                       // pause : deux barres
            r.set(8.4f * u, 4.6f * u, 10.9f * u, 19.4f * u);
            c.drawRoundRect(r, u * 1.25f, u * 1.25f, plein);
            r.set(13.1f * u, 4.6f * u, 15.6f * u, 19.4f * u);
            c.drawRoundRect(r, u * 1.25f, u * 1.25f, plein);

        } else if ("go".equals(id)) {                  // lecture : triangle
            plein.setPathEffect(new CornerPathEffect(u * 1.6f));
            p.moveTo(8.2f * u, 4.8f * u);
            p.lineTo(18.4f * u, 12f * u);
            p.lineTo(8.2f * u, 19.2f * u);
            p.close();
            c.drawPath(p, plein);

        } else if ("lecprec".equals(id) || "lecsuiv".equals(id)) {
            // Rapport precedent ou suivant : une barre et un triangle, le
            // dessin de toutes les telecommandes. Le suivant est le miroir.
            boolean av = "lecsuiv".equals(id);
            float bx = av ? 17.4f : 6.6f;
            r.set((bx - 1.2f) * u, 5.4f * u, (bx + 1.2f) * u, 18.6f * u);
            c.drawRoundRect(r, u * 1.1f, u * 1.1f, plein);
            plein.setPathEffect(new CornerPathEffect(u * 1.4f));
            float pointe = av ? 15.6f : 8.4f, base = av ? 6.4f : 17.6f;
            p.moveTo(base * u, 5.4f * u);
            p.lineTo(pointe * u, 12f * u);
            p.lineTo(base * u, 18.6f * u);
            p.close();
            c.drawPath(p, plein);

        } else if ("lecstop".equals(id)) {             // arreter la lecture : le carre seul
            r.set(6.6f * u, 6.6f * u, 17.4f * u, 17.4f * u);
            c.drawRoundRect(r, u * 2f, u * 2f, plein);

        } else if ("envoyer".equals(id)) {             // envoyer : fleche vers le haut
            c.drawCircle(12f * u, 12f * u, 9f * u, trait);
            c.drawLine(12f * u, 16.8f * u, 12f * u, 7.4f * u, trait);
            p.moveTo(8.2f * u, 11f * u);
            p.lineTo(12f * u, 7.2f * u);
            p.lineTo(15.8f * u, 11f * u);
            c.drawPath(p, trait);

        } else if ("shot".equals(id)) {                // capture : appareil photo
            p.moveTo(9f * u, 6.6f * u);
            p.lineTo(10.4f * u, 4.2f * u);
            p.lineTo(13.6f * u, 4.2f * u);
            p.lineTo(15f * u, 6.6f * u);
            c.drawPath(p, trait);
            r.set(3.2f * u, 6.6f * u, 20.8f * u, 19.6f * u);
            c.drawRoundRect(r, u * 3.2f, u * 3.2f, trait);
            c.drawCircle(12f * u, 13.1f * u, 3.5f * u, trait);

        } else if ("rec".equals(id)) {                 // enregistrement : le point
            c.drawCircle(12f * u, 12f * u, 8.2f * u, trait);
            c.drawCircle(12f * u, 12f * u, 4.2f * u, plein);

        } else if ("recstop".equals(id)) {             // arret : le carre
            c.drawCircle(12f * u, 12f * u, 8.2f * u, trait);
            r.set(8.4f * u, 8.4f * u, 15.6f * u, 15.6f * u);
            c.drawRoundRect(r, u * 1.4f, u * 1.4f, plein);

        } else if ("voix".equals(id)) {                // micro : mains libres
            r.set(8.9f * u, 2.9f * u, 15.1f * u, 14.3f * u);
            c.drawRoundRect(r, u * 3.1f, u * 3.1f, trait);
            r.set(5.4f * u, 6.6f * u, 18.6f * u, 18.4f * u);
            c.drawArc(r, 20f, 140f, false, trait);
            c.drawLine(12f * u, 17.6f * u, 12f * u, 21.2f * u, trait);

        } else if ("voixannuler".equals(id)) {         // fin du tour : la croix
            c.drawLine(7f * u, 7f * u, 17f * u, 17f * u, trait);
            c.drawLine(17f * u, 7f * u, 7f * u, 17f * u, trait);

        } else if ("qg".equals(id)) {                  // bulle de conversation
            r.set(3.4f * u, 4f * u, 20.6f * u, 16.8f * u);
            p.addRoundRect(r, u * 4.4f, u * 4.4f, Path.Direction.CW);
            c.drawPath(p, trait);
            p.reset();
            p.moveTo(8.6f * u, 16.8f * u);
            p.lineTo(8.6f * u, 21.2f * u);
            p.lineTo(13.6f * u, 16.8f * u);
            c.drawPath(p, trait);

        } else if ("masquer".equals(id)) {             // pousser hors de l'ecran
            c.drawLine(19.4f * u, 4.4f * u, 19.4f * u, 19.6f * u, trait);
            c.drawLine(4.6f * u, 12f * u, 14.6f * u, 12f * u, trait);
            p.moveTo(10.8f * u, 8.2f * u);
            p.lineTo(14.8f * u, 12f * u);
            p.lineTo(10.8f * u, 15.8f * u);
            c.drawPath(p, trait);

        } else if ("rapport".equals(id) || id.startsWith("rapport")) {
            r.set(5.2f * u, 3.2f * u, 18.8f * u, 20.8f * u);
            c.drawRoundRect(r, u * 2.4f, u * 2.4f, trait);
            c.drawLine(8.6f * u, 8.4f * u, 15.4f * u, 8.4f * u, trait);
            c.drawLine(8.6f * u, 12f * u, 15.4f * u, 12f * u, trait);
            c.drawLine(8.6f * u, 15.6f * u, 12.8f * u, 15.6f * u, trait);

        } else if ("voixmodeon".equals(id)) {          // lecture auto : la cloche
            // Une cloche, pas un haut-parleur : ce qui est en jeu n'est pas le
            // volume mais le fait d'etre prevenu sans avoir rien demande.
            p.moveTo(6.4f * u, 16.4f * u);
            p.lineTo(7.8f * u, 14.4f * u);
            p.lineTo(7.8f * u, 10.6f * u);
            p.cubicTo(7.8f * u, 6.8f * u, 16.2f * u, 6.8f * u, 16.2f * u, 10.6f * u);
            p.lineTo(16.2f * u, 14.4f * u);
            p.lineTo(17.6f * u, 16.4f * u);
            p.close();
            c.drawPath(p, trait);
            c.drawLine(12f * u, 4.4f * u, 12f * u, 6.4f * u, trait);
            // Le battant : deux traits sous la robe, qui disent qu'elle sonne.
            c.drawLine(10.4f * u, 19f * u, 13.6f * u, 19f * u, trait);

        } else if ("voixmodeoff".equals(id)) {         // silencieux : cloche barree
            trait.setStrokeWidth(u * 1.85f);
            p.moveTo(6.4f * u, 16.4f * u);
            p.lineTo(7.8f * u, 14.4f * u);
            p.lineTo(7.8f * u, 10.6f * u);
            p.cubicTo(7.8f * u, 6.8f * u, 16.2f * u, 6.8f * u, 16.2f * u, 10.6f * u);
            p.lineTo(16.2f * u, 14.4f * u);
            p.lineTo(17.6f * u, 16.4f * u);
            p.close();
            c.drawPath(p, trait);
            c.drawLine(12f * u, 4.4f * u, 12f * u, 6.4f * u, trait);
            // La barre oblique EST l'information : c'est elle qu'on lit d'abord,
            // avant meme d'avoir identifie la cloche dessous. Un simple grisage
            // ne disait pas « coupe », il disait « indisponible ».
            c.drawLine(4.6f * u, 4.6f * u, 19.4f * u, 19.4f * u, trait);

        } else if ("rejouer".equals(id)) {             // reecouter : fleche en boucle
            // Un cercle ouvert en haut, fleche au bout, lecture au centre.
            r.set(4.4f * u, 4.4f * u, 19.6f * u, 19.6f * u);
            c.drawArc(r, 300f, 290f, false, trait);
            double a = Math.toRadians(230);
            float ex = 12f + 7.6f * (float) Math.cos(a), ey = 12f + 7.6f * (float) Math.sin(a);
            float tx = (float) -Math.sin(a), ty = (float) Math.cos(a);
            float nx = (float) Math.cos(a), ny = (float) Math.sin(a);
            plein.setPathEffect(new CornerPathEffect(u * 0.6f));
            p.moveTo((ex + 3.0f * tx) * u, (ey + 3.0f * ty) * u);
            p.lineTo((ex + 2.4f * nx) * u, (ey + 2.4f * ny) * u);
            p.lineTo((ex - 2.4f * nx) * u, (ey - 2.4f * ny) * u);
            p.close();
            c.drawPath(p, plein);
            p.reset();
            p.moveTo(10.4f * u, 9.2f * u);
            p.lineTo(14.6f * u, 12f * u);
            p.lineTo(10.4f * u, 14.8f * u);
            p.close();
            c.drawPath(p, plein);

        } else if ("bilan".equals(id)) {               // ou j'en suis : la boussole
            c.drawCircle(12f * u, 12f * u, 8.6f * u, trait);
            // L'aiguille en cerf-volant plutot qu'en fleche : elle tient dans
            // 18 dp sans que ses deux pointes se touchent au trace.
            plein.setPathEffect(new CornerPathEffect(u * 0.9f));
            p.moveTo(16.2f * u, 7.8f * u);
            p.lineTo(13.4f * u, 13.4f * u);
            p.lineTo(7.8f * u, 16.2f * u);
            p.lineTo(10.6f * u, 10.6f * u);
            p.close();
            c.drawPath(p, plein);

        } else if ("prive".equals(id)) {               // espace prive : le cadenas
            r.set(5.2f * u, 10.4f * u, 18.8f * u, 20.4f * u);
            c.drawRoundRect(r, u * 2.6f, u * 2.6f, trait);
            r.set(8.4f * u, 4f * u, 15.6f * u, 13.6f * u);
            c.drawArc(r, 180f, 180f, false, trait);

        } else if (id != null && id.startsWith("bleuauto")) {  // le soleil
            c.drawCircle(12f * u, 12f * u, 3.6f * u, trait);
            for (int k = 0; k < 8; k++) {
                double a = Math.toRadians(k * 45);
                float x = 12f * u, y = 12f * u;
                c.drawLine(x + (float) Math.cos(a) * 6f * u,
                        y + (float) Math.sin(a) * 6f * u,
                        x + (float) Math.cos(a) * 8f * u,
                        y + (float) Math.sin(a) * 8f * u, trait);
            }

        } else if ("lireecran".equals(id)) {           // lire l'ecran : le telephone
            // Un smartphone vu de face : corps epais, ECRAN grise dedans (la
            // meme couleur a 30 %), fente du haut-parleur en haut, point
            // d'accueil en bas. Sans lignes de texte : elles le faisaient
            // passer pour une pile ou une liste, USER ne l'a pas reconnu.
            r.set(7.2f * u, 2.4f * u, 16.8f * u, 21.6f * u);
            c.drawRoundRect(r, u * 2.6f, u * 2.6f, trait);
            int alpha = plein.getAlpha();
            plein.setAlpha(78);
            r.set(8.8f * u, 6.2f * u, 15.2f * u, 17.4f * u);
            c.drawRect(r, plein);
            plein.setAlpha(alpha);
            r.set(10.4f * u, 4f * u, 13.6f * u, 5.2f * u);
            c.drawRoundRect(r, u * 0.6f, u * 0.6f, plein);
            c.drawCircle(12f * u, 19.4f * u, 0.85f * u, plein);

        } else if ("lirepresse".equals(id)) {          // presse-papier : « copier »
            // Deux carres decales, le symbole « copier » de tous les systemes.
            // Rien a voir avec le telephone : deux formes larges au lieu d'une
            // etroite, et le carre de devant est plein pour peser plus lourd.
            r.set(4.6f * u, 4.6f * u, 15f * u, 15f * u);
            c.drawRoundRect(r, u * 1.8f, u * 1.8f, trait);
            r.set(9f * u, 9f * u, 19.4f * u, 19.4f * u);
            c.drawRoundRect(r, u * 1.8f, u * 1.8f, plein);

        } else if ("reglages".equals(id)) {            // reglages : 3 curseurs
            // Trois glissieres et leurs boutons decales : le symbole « reglages »
            // des tables de mixage. Choisi contre l'engrenage, illisible a 24 px.
            float[] ys = {7f, 12f, 17f};
            float[] xs = {15f, 9f, 13f};
            for (int i = 0; i < 3; i++) {
                c.drawLine(4f * u, ys[i] * u, 20f * u, ys[i] * u, trait);
                c.drawCircle(xs[i] * u, ys[i] * u, 2.2f * u, plein);
            }

        } else if ("voixvitesse".equals(id)) {         // vitesse : le compteur
            // Un cadran ouvert vers le bas et son aiguille couchee vers la
            // droite : le compteur de vitesse, lisible sans legende. Remplace
            // le chevron, que USER ne distinguait pas des deux portes voisines.
            r.set(3.6f * u, 4.6f * u, 20.4f * u, 21.4f * u);
            c.drawArc(r, 150f, 240f, false, trait);
            c.drawLine(12f * u, 13f * u, 16.4f * u, 8.8f * u, trait);
            c.drawCircle(12f * u, 13f * u, 1.7f * u, plein);

        } else if ("voixstandard".equals(id)) {        // cerveau : l'etincelle
            // L'etoile a 4 branches, devenue le signe commun de l'IA. Un vrai
            // cerveau se reduit a une tache a 24 px. La petite etoile en haut
            // a droite equilibre la grande, decalee en bas a gauche.
            etoile(c, 10.4f * u, 13.4f * u, 7.4f * u, 2.1f * u);
            etoile(c, 18.2f * u, 5.6f * u, 3.4f * u, 1f * u);

        } else if ("bleu".equals(id)) {                // filtre bleu : la lune
            // La lune de l'eclairage nocturne d'Android, le reglage que USER
            // connait deja. Un croissant plein : un disque moins un disque
            // decale, plutot que deux arcs, dont les pointes se boucheraient.
            Path creux = new Path();
            p.addCircle(12f * u, 12f * u, 8.4f * u, Path.Direction.CW);
            creux.addCircle(16.6f * u, 8.2f * u, 7f * u, Path.Direction.CW);
            p.op(creux, Path.Op.DIFFERENCE);
            c.drawPath(p, plein);

        } else if (id.endsWith("fermer")) {            // retour : le chevron gauche
            // Les « Retour » des sous-menus remontent d'un niveau. Un chevron
            // vers la droite, comme les portes, disait l'inverse.
            p.moveTo(14f * u, 6.6f * u);
            p.lineTo(8.6f * u, 12f * u);
            p.lineTo(14f * u, 17.4f * u);
            c.drawPath(p, trait);

        } else if ("conseil".equals(id)) {             // conseil : 3 tetes, 1 table
            // Avant le 2026-10-02, Conseil n'avait pas de glyphe : il tombait
            // sur le chevron par defaut et se lisait comme une porte.
            c.drawCircle(12f * u, 7.4f * u, 2.3f * u, plein);
            c.drawCircle(5.6f * u, 10.4f * u, 2f * u, plein);
            c.drawCircle(18.4f * u, 10.4f * u, 2f * u, plein);
            p.moveTo(4.2f * u, 16.2f * u);
            p.quadTo(12f * u, 20.6f * u, 19.8f * u, 16.2f * u);
            c.drawPath(p, trait);

        } else if ("coche".equals(id)) {               // choix en cours : la coche
            p.moveTo(5.8f * u, 12.4f * u);
            p.lineTo(10f * u, 16.4f * u);
            p.lineTo(18.2f * u, 7.8f * u);
            c.drawPath(p, trait);

        } else if ("vide".equals(id)) {                // colonne tenue, rien dedans
            // Les choix d'une liste n'ont pas d'icone : seule la coche marque
            // celui qui tourne. La colonne reste, pour garder l'alignement.

        } else {                                       // defaut : le chevron
            p.moveTo(10f * u, 6.6f * u);
            p.lineTo(15.4f * u, 12f * u);
            p.lineTo(10f * u, 17.4f * u);
            c.drawPath(p, trait);
        }
    }

    /**
     * Etoile pleine a 4 branches, centree en (x, y). `rayon` va du centre a la
     * pointe, `taille` du centre au creux : plus il est petit, plus l'etoile
     * est fine. Courbes de Bezier vers le centre, pour le galbe des branches.
     */
    private void etoile(Canvas c, float x, float y, float rayon, float taille) {
        Path e = new Path();
        e.moveTo(x, y - rayon);
        e.quadTo(x + taille, y - taille, x + rayon, y);
        e.quadTo(x + taille, y + taille, x, y + rayon);
        e.quadTo(x - taille, y + taille, x - rayon, y);
        e.quadTo(x - taille, y - taille, x, y - rayon);
        e.close();
        c.drawPath(e, plein);
    }
}
