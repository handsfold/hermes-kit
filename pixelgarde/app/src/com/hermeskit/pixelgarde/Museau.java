package com.poste.pixelgarde;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.RectF;

/**
 * Le creeper en icones de notification, grande et petite.
 *
 * Demande par USER le 2026-08-30 : « que la notification soit jolie, avec le
 * creeper comme logo ». La tete de la pastille est la signature de l'appli ;
 * une enveloppe grise generique dans la barre d'etat ne disait pas d'ou venait
 * l'avis, et il en tombe assez sur un telephone pour que ca compte.
 *
 * La source est la meme que celle de la pastille : Tete.faceAvant(), 8 texels
 * de cote. Le jour ou le skin change, les deux changent ensemble. Aucun fichier
 * de ressource : cette appli se construit sans gradle, avec un seul aapt2 link,
 * et un drawable de plus voudrait dire un dossier res/ de plus a tenir.
 *
 * Les deux icones ne suivent pas les memes regles, et c'est tout le sujet.
 * La grande est affichee telle quelle, en couleur. La petite est reduite a sa
 * silhouette : Android n'en garde que le canal alpha et repeint le reste a la
 * couleur du systeme. Une face de creeper en couleur y deviendrait un carre
 * blanc plein, meconnaissable. Il faut donc lui rendre ses trous.
 */
final class Museau {

    private Museau() { }

    /**
     * Le grossissement est fait AU PINCEAU, sans filtre.
     *
     * Une face de creeper fait 8 pixels de cote. Agrandie avec un filtre
     * bilineaire, elle devient une bouillie verte ou les yeux bavent : c'est
     * exactement ce que fait Bitmap.createScaledBitmap(..., true) par defaut.
     * Le grain est l'identite du dessin, on le garde net.
     */
    private static void plaquer(Canvas c, Bitmap src, RectF vers) {
        Paint p = new Paint();
        p.setFilterBitmap(false);
        p.setAntiAlias(false);
        p.setDither(false);
        c.drawBitmap(src, new Rect(0, 0, src.getWidth(), src.getHeight()),
                new Rect((int) vers.left, (int) vers.top, (int) vers.right, (int) vers.bottom), p);
    }

    /** La grande icone : la tete en couleur sur une pastille sombre et ronde. */
    static Bitmap grand(int px) {
        Bitmap face = Tete.faceAvant();
        if (face == null) return null;
        Bitmap b = Bitmap.createBitmap(px, px, Bitmap.Config.ARGB_8888);
        Canvas c = new Canvas(b);

        // Un siege sombre, pas transparent : la grande icone se pose sur le
        // fond du panneau de notifications, clair en journee. Un creeper vert
        // pose a nu sur du blanc perd ses bords.
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setColor(Charte.CREEPER_FOND);
        c.drawCircle(px / 2f, px / 2f, px / 2f, p);

        // 62 % du diametre : inscrit dans le cercle avec sa marge, la tete ne
        // touche jamais le bord meme quand le systeme rogne en rond.
        float k = px * 0.62f;
        float o = (px - k) / 2f;
        plaquer(c, face, new RectF(o, o, o + k, o + k));
        return b;
    }

    /**
     * La petite icone : la silhouette, trouee comme un vrai creeper.
     *
     * Le seuil separe le vert du visage du noir des yeux et de la bouche. Il
     * est haut place (95 sur 255) parce que le vert sombre du skin n'est pas
     * si loin du noir : a 60, un lisere d'ombre autour des yeux passait du
     * cote opaque et les trous se refermaient.
     *
     * Rien n'est peint en couleur ici : seul l'alpha compte, Android jette le
     * reste. Le blanc n'est la que pour rendre l'image lisible si on l'ouvre.
     */
    static Bitmap petit(int px) {
        Bitmap face = Tete.faceAvant();
        if (face == null) return null;

        int n = face.getWidth();
        Bitmap masque = Bitmap.createBitmap(n, n, Bitmap.Config.ARGB_8888);
        for (int y = 0; y < n; y++) {
            for (int x = 0; x < n; x++) {
                int c = face.getPixel(x, y);
                int lum = (Color.red(c) * 30 + Color.green(c) * 59 + Color.blue(c) * 11) / 100;
                masque.setPixel(x, y, lum > 95 ? 0xFFFFFFFF : 0x00000000);
            }
        }

        Bitmap b = Bitmap.createBitmap(px, px, Bitmap.Config.ARGB_8888);
        Canvas c = new Canvas(b);
        // La zone sure d'une icone de barre d'etat : le systeme peut la rogner
        // en cercle, et sur l'ecran de verrouillage elle passe dans une pastille
        // encore plus serree. 72 % du cote, centres.
        float k = px * 0.72f;
        float o = (px - k) / 2f;
        plaquer(c, masque, new RectF(o, o, o + k, o + k));
        return b;
    }
}
