package com.poste.pixelgarde;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LightingColorFilter;
import android.graphics.Paint;
import android.util.Base64;
import android.widget.TextView;

/**
 * La tete du skin Minecraft de USER, en volume, posee a la place du mot « AI ».
 *
 * POURQUOI UNE VUE ET PAS UNE IMAGE
 * Une image figee aurait suffi a montrer la tete, pas a la faire vivre. Or
 * c'est le mouvement qui porte l'information : la couleur dit l'etat, la
 * posture dit ce que l'agent est en train de faire. Un cube texture se calcule
 * en quelques centaines d'operations par image, il n'y avait pas de raison de
 * s'en priver.
 *
 * POURQUOI drawBitmapMesh ET PAS OpenGL
 * Une GLSurfaceView dans une fenetre de superposition demande sa propre
 * surface, son propre contexte et son propre fil. Pour six quadrilateres de
 * 40 dp, c'est hors de proportion, et une surface supplementaire au-dessus de
 * toutes les applis est exactement ce qu'on ne veut pas. drawBitmapMesh fait
 * la meme chose sur le Canvas deja alloue : on lui donne la grille de sommets
 * projetes, il deforme la texture dedans.
 *
 * ELLE HERITE DE TextView, ET CE N'EST PAS UN CAPRICE
 * La pastille etait un TextView, et tout le reste de Bulle en depend : le
 * fond degrade qui porte la couleur d'etat, les parametres de disposition, le
 * fondu d'alpha, le ressort de bascule rond/barrette. En heritant, le dessin
 * s'ajoute par-dessus sans toucher a une seule de ces mecaniques. Une vue
 * neuve aurait demande de reecrire tout le placement pour un gain nul.
 */
final class Tete extends TextView {

    // ---------------------------------------------------------------- skin

    /**
     * Le skin de USER, de 2013 : creeper mi-organique mi-robotique, moitie
     * gauche vegetale, joue droite en plaque de metal avec un oeil-ecran
     * rouge. Retrouve dans l'archive de son ancien PC.
     *
     * Il est encode ici plutot que pose en ressource parce que l'appli se
     * construit sans dossier res/ : aapt2 ne lie que le manifeste, il n'y a
     * aucun endroit ou un PNG serait empaquete. 2,4 Ko de texture pesent
     * moins qu'une chaine de construction supplementaire.
     */
    private static final String SKIN_B64 = ""
            + "iVBORw0KGgoAAAANSUhEUgAAAEAAAAAgCAYAAACinX6EAAAAAXNSR0IArs4c6QAAAARnQU1BAACx"
            + "jwv8YQUAAAAJcEhZcwAADsQAAA7EAZUrDhsAAAkMSURBVGhD3VlrUFTnGX72LLssu9yRmxi5JFhi"
            + "GwUZYxwxyWgaITgB84MOnWScac2lxnRo2ml1plOSaby006S59EfTZsokQUxTM5KO0NpGp02KLQQT"
            + "bVBHxIAtIpdlQWDdG+x2n699d46AnDgdZ9O+zJmz+33fed/3ed7L953FFAwGQ1hA7nlnFe677X4s"
            + "11ZgzDKO9EA69j32ArKzs+FwOKA9PoGvJj2KJvOrSPQmYvh4ALUVDyHNugj+8WlsvKN8IfUwmUwL"
            + "zt/sSc3IgK8POHr0A3wS/DvaTe/hr/Y/RB5xu91wjY3jmcd2o/vrTlgn4vCNim14/XATXK4xuOzD"
            + "RuqjPm9IQHJpDBxrgVMdp5HsT4WvJ4TGxkZcvnxZOe/c41fZwOv4rtN49eCvUFSRhbfcr8EasEQd"
            + "oJEDhgTkJuYhLbgIFp8NTv8InMFhDJr7I3qlFFgO/NzXfBEBzwy8zhn0e/5pZD/q84YEjLhGMTA2"
            + "iCc3bEdt2tfgMMfjO7U7Iz2AwBelp6pLSGh74gySzixBQdytUQdo5IAhAa7Oq8hOyEK3dhKvtb6B"
            + "U/W9EfACXJXCiAvsCSyNlc/mw5IZgzhbgpH9qM8bEvDk5iewKbkaj3/0bXgL/fM6rAdfUJuHiuwt"
            + "iPuSFy1Db0cdoJEDhgQ0DR3EsakWpWfkB85roj+f8pT7THjjaBPiUm0IuQ3VG/l30+dND3xUFooZ"
            + "seLBjC143/1H+CcD0D5JgmPdDDzTPpQ7qvHNnjqsta+Cc7fHkAApB73nUhrcPboDXWgNvo2gB/jH"
            + "++M4/HTrTQe5kAHN4XIAJx0Y04YxdOoqpkxuFG+6HX1T/ShMLMJzx/di85IH4I5x486X7lA1TkBM"
            + "+/lEyoFrZktheyF2HH8aDrcDgalp3H/v+qiCp3HNf8aKPZV7kWe/FVVl5XhwaQ1aDr8H/+nwbHAa"
            + "S1cl408/PQbP64EwIV9QDtcdacZXDuyf47y+FwhREv36n9Wr9b22XvR6B3Bbykr0+M5Hn4DB/cOw"
            + "Jdjwm6km/EU7hiRLIr63pQ415Q8hK+4WWKyxCPlNaP/1SXR525XDy8JXYuy/O7+IHnx9w3fx/MF9"
            + "Klt4rd9bDM0RQqY9DfGaHV+OrUbLB79Hx7fORJ0AU3V1dYhOlrxSgJ93H8Ca1FIU5mTC5b+Cu6z3"
            + "whr+67l0Givz1mDfzj0wzWjIcRZEeoEgkEg3NDSg0fISQhMmLIkpgNliwYnzf8OOwl345fiPYfXa"
            + "UZFXhe/XPqd0HDp0KKokaHJ4+fipT7HmlTU4P/kpzF4N7gEfCmy5yEEWnH0eND77Ji79dhT9LSNz"
            + "HBbw9zxfgoSEBHjGffBO+rEs4XYkWBIw2DOFgWAffDPTGD7rxbvTB6IKWm9c05/gGJHCF5ah99IA"
            + "Ni7dAOfUMJYm5yPDnqVKQKS9vT3SDPXNrufDIexq3amiX5dfj8TJRbglmI8kRzJ+0voi7D47dm/e"
            + "jQ8fuTAng6LFiNqohQTJBt+PLPgiSvC7tj9jv/sXyFlvR8baNLx86od45+MDWFKZDnNNKFLjLKFH"
            + "GmpQvmkjnrprByxaLMZmnHjx2Ms46G5A0p1BJFiTUJa7ATU1NZ8b8MTOl/Frfg9YsWIFPB4PZmZm"
            + "1Nn+3Llz6j49PQ2v14tAIKCCxff4UCgUuUsES0tL/6tgnjhxYsHnZ+vvDGejXkwxMTdkf85RbWpq"
            + "CmazWQEmCXFxcRgbG1Pf7XZ7RDnBU+R+Q1Y/R4vnEECgExMT0DRNRVx+sWFW/K+DnY/3OQSkp6er"
            + "Gg3/VAZLeAtjynMsOTlZZcT/m5iKi4tDjDQjTtAx4RpyOp1qO6OwyzP6HGcJkIjBwUGVHRkZGUhM"
            + "TLyGE645cuQIbDYbTGGdlMlwRlmtVqxbt24Of8wwXrQ9n9Au5ycnJ5VO6mFPuno1fGwPl6vP50Ns"
            + "bKy6EwPt8xmWMQPGHWshUecARpmpz4hTGUFSARXSOJVL/fv9fqSmpiInJ0etny0EUllZibNnz4KQ"
            + "2CkuXLiAsrKyef2QsiIw2qA/ItRPe5SkpCQF/sqVKyooXEv/2KO4hnf6Sb9JAOc+S8lqZImA4uPj"
            + "lQEKneDFMaY/lZMIGqVSRp8id70hjnE9Sewm+PBFUvXASLb+/ECnuYZR5fO0Qx0cJzhm3Pj4uJoj"
            + "SEaejZmZyXkGkJ/pLwni/NDQkPpsJBqVkml9Cup/qqYBvfMEK+wTJOfpjMvlUgAodGbbtm1gAfCd"
            + "auvWrSrDKATAdKYecZAA+DyDwXk24dHR0ci2yzIjYZynr0IMvzPSHKM+YmCZSPaSECPRRJl+oaQW"
            + "o8L5lJQUBVou6Rc0OjIyokigk5KuJJXPPnr33WAnoYMkgLo4x4yTGqVdEsC0FYL0Jces5DMMAgHS"
            + "Nu3ITsUx6pb+RT0k5no9ZTYh5sWLFz/DB8icPEQl0lSYDTTAeRE5BJEA1ibB8pJzA51kFnBd5/Ll"
            + "KuIco14CYjSpTzXK//QYjhOY1K8QItlIW5yXqIo93iksGelZ1CXNU36+v14mqDbNaMgJj99Fqb5B"
            + "iQKSJJ1XUo0kELCUhhBAoB0dHSqDOEZhmQhwGZM7HZd+QBsUzlEPfRF/SDTXcaciUGYYs0Tmpakb"
            + "pb/SP98iKqOB+USM6+eYjhIxcYggSWRRUZECLABknGAJjs5KlvEugRD7HGPJUK8ERupcHxQpVxJH"
            + "W7KNG5EwLwGMMh2UxqVXIjsFQUt60iF9k5N3BOppa2tTc1I2BCZ9h7q4hmktZPCzNDrJRq7r6upS"
            + "fYZzvJht8p3g+Vl2n8zMTFWa+rK9HhGm8MvFnH+O6huUEYOc19cxgRAEs4g1S+d5Zrh48WKkvvWR"
            + "5hqWBddxnBlGArnDUOq2b/8sLlx3Tc3DDy/4vKmkpCREBxgJSRt+pzOSBUwrfifDjCadppPSyPgc"
            + "tzRGhgToX6Y6OztRVVWF/v5+1clZz+wJ1Ek7vEgY9fE50cG9nGS829yM3NxcBYIk3qjk5ecvTEC4"
            + "tkKsLwKTNGb6kBA6IcdL3glSTlp0lPOrV69W0WITlOf1DZXWCZBrRaRL64mW4zZ1SB/hfPMCP5kJ"
            + "MbMR6okyIuBfHgDN/diinDcAAAAASUVORK5CYII=";

    private static Bitmap skin;
    /** Les six faces, decoupees une fois : 8x8 texels chacune. */
    private static Bitmap[] faces;

    // -------------------------------------------------------------- geometrie

    private static final float S = 0.5f;
    /**
     * Les six faces du cube, dans l'ordre du skin Minecraft.
     *
     * Chaque ligne : u, v dans la texture, puis les quatre coins dans l'ordre
     * haut-gauche, haut-droit, bas-droit, bas-gauche VUS DE L'EXTERIEUR. Cet
     * ordre est ce qui fait tenir a la fois le placage et le test de dos
     * cache : la normale se deduit du sens de parcours, on n'a pas a la
     * stocker.
     *
     * Le deroule du skin fait le tour de la tete : droite, face, gauche, dos.
     * C'est pourquoi le u de la face droite va vers l'arriere et celui de la
     * face gauche vers l'avant : leurs bords se raccordent a ceux de la face
     * avant.
     */
    private static final float[][] GEO = {
        // u,  v,   TL              TR              BR              BL
        {  8,  8,  -S,-S, S,   S,-S, S,   S, S, S,  -S, S, S },  // face
        { 24,  8,   S,-S,-S,  -S,-S,-S,  -S, S,-S,   S, S,-S },  // dos
        {  0,  8,  -S,-S,-S,  -S,-S, S,  -S, S, S,  -S, S,-S },  // sa droite
        { 16,  8,   S,-S, S,   S,-S,-S,   S, S,-S,   S, S, S },  // sa gauche
        {  8,  0,  -S,-S,-S,   S,-S,-S,   S,-S, S,  -S,-S, S },  // dessus
        { 16,  0,  -S, S, S,   S, S, S,   S, S,-S,  -S, S,-S },  // dessous
    };

    /**
     * Une teinte par face, du ciel au sol.
     *
     * Minecraft eclaire ainsi : pas de normale par pixel, une valeur fixe par
     * orientation. C'est ce qui donne le volume sans jamais trahir le grain
     * de la texture, et ca coute un filtre de couleur au lieu d'un calcul.
     */
    private static final float[] LUM = { 0.88f, 0.66f, 0.72f, 0.80f, 1.00f, 0.50f };

    /** L'angle de repos, qui donne le volume. Voir conduire(). */
    private static final float BIAIS_LACET = 0.30f;
    private static final float BIAIS_TANGAGE = -0.07f;

    /**
     * PROJECTION ORTHOGRAPHIQUE, ET C'EST UN CHOIX MESURE
     *
     * La premiere version placait une camera a distance finie et deformait
     * chaque face par une maille de sommets projetes un a un, via
     * drawBitmapMesh. C'etait juste, et c'etait cher : 3,9 ms par image, soit
     * 23 % d'un coeur en continu. Reduire la maille de 8 a 4 n'a rien change,
     * ce qui a designe le coupable : drawBitmapMesh ne passe pas par le GPU,
     * son cout tient a l'appel, pas au nombre de sommets.
     *
     * Sans perspective, une face de cube est EXACTEMENT un parallelogramme.
     * Un parallelogramme se pose avec une matrice affine, donc avec un
     * drawBitmap ordinaire, accelere et quasi gratuit. La tete fait 40 dp :
     * la fuite qu'on abandonne s'y compte en fractions de pixel, et Minecraft
     * dessine ses propres tetes d'inventaire de la meme facon.
     *
     * Mesure apres bascule : voir plus bas.
     */
    /**
     * Debordement de chaque face dans son propre plan.
     *
     * Sans lui, deux faces voisines partagent une arete au pixel pres et
     * l'arrondi y laisse passer le fond : une couture claire court le long de
     * chaque arete, tres visible sur une texture sombre.
     */
    private static final float COUTURE = 1.02f;

    // -------------------------------------------------------------- animation

    /** veille | pilote | attente | voix | voixtravaille | voixpret | capture | suspendu. */
    private String etat = "veille";
    private boolean actif;

    private float lacet, tangage, roulis, souffle;
    private float lacetC, tangageC, roulisC, souffleC;
    /** Ecrasement a l'appui : 1 au repos. */
    private float presse = 1f;

    /**
     * L'avancement de la lecture, peint en anneau autour de la tete.
     *
     * Demande par USER le 2026-08-30 : « que je voie l'avancement de la lecture
     * quelque part, le rond de la bulle, une barre qui diminue ». Un rapport
     * lu dure de quinze secondes a deux minutes, et rien ne le disait : on
     * entendait une voix sans savoir si elle finissait ou commencait.
     *
     * Deux instants et non un pourcentage : la pastille se repeint trente fois
     * par seconde de son cote, elle n'a pas besoin qu'on la tienne au courant.
     * Le service dit une duree une fois, au demarrage du lecteur, et l'anneau
     * se vide tout seul. Rien a synchroniser, rien a rattraper si un message
     * se perd.
     */
    private long lectureT0, lectureT1;
    /**
     * Instant de la pause, 0 hors pause. USER, 2026-10-02 : l'anneau doit se
     * FIGER a la pause et repartir du meme point a la reprise, pas se vider
     * puis repartir plein.
     */
    private long lecturePause;

    /**
     * Le compte a rebours d'envoi (USER, 2026-10-01). Tant qu'il court, la tete
     * cede la place a un gros chiffre : les secondes avant que la demande
     * parte. L'anneau orange se vide en meme temps. Un compte se lit d'un
     * coup d'oeil, une tete qui bouge non.
     */
    private long compteT0, compteT1;
    private final Paint pChiffre = new Paint(Paint.ANTI_ALIAS_FLAG);
    /** Regard force vers le doigt, en fraction d'ecran, et sa duree de vie. */
    private float viseX, viseY;
    private long viseJusqua;
    /** Hochement ponctuel : instant de depart, 0 si aucun. */
    private long salueDepuis;

    private long t0;
    private long dernier;

    private final Paint p = new Paint();
    /**
     * Un filtre par face, construit une fois.
     *
     * Il n'en depend que de LUM, qui est constant : en fabriquer six par
     * image, soit trois cent soixante par seconde, ne servait qu'a nourrir le
     * ramasse-miettes.
     */
    private static final LightingColorFilter[] OMBRE = new LightingColorFilter[6];
    static {
        for (int i = 0; i < 6; i++) {
            int m = (int) (LUM[i] * 255f);
            OMBRE[i] = new LightingColorFilter(
                    0xFF000000 | (m << 16) | (m << 8) | m, 0);
        }
    }
    /**
     * Le signal au-dessus de la tete : trois langages distincts pour trois
     * etats, tous lisibles d'un coup d'oeil sans lire la phrase d'entete.
     *
     * Blanc et carre plutot que rond ou colore : la couleur de l'etat est
     * deja portee par l'anneau de la pastille (voir Bulle.couleurEtat), un
     * second porteur de couleur ferait double emploi et se lirait comme un
     * desaccord si les deux divergeaient jamais. Des carres, parce que la
     * tete elle-meme est un cube : le meme grain que le skin, pas un rond
     * qui jurerait avec le reste du dessin.
     */
    private final Paint pIndic = new Paint(Paint.ANTI_ALIAS_FLAG);
    /** Le chiffre des rapports en attente, et sa pastille. */
    private final Paint pBadge = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint pBadgeTexte = new Paint(Paint.ANTI_ALIAS_FLAG);
    private int nonLus = 0;
    /** Reutilise a chaque image : un RectF neuf par dessin ferait du dechet. */
    private final android.graphics.RectF arcLecture = new android.graphics.RectF();
    private final android.graphics.Matrix mat = new android.graphics.Matrix();
    private final float[] mv = new float[9];
    private final float[] c3 = new float[12];
    private final int[] ordre = new int[6];
    private final float[] prof = new float[6];

    Tete(Context c) {
        super(c);
        charger();
        p.setFilterBitmap(false);   // le grain du skin, pas une bouillie lissee
        p.setAntiAlias(false);
        p.setDither(false);
        pIndic.setColor(Charte.ENCRE);
        pIndic.setStyle(Paint.Style.FILL);
        setWillNotDraw(false);
        t0 = System.nanoTime();
    }

    private static synchronized void charger() {
        if (faces != null) return;
        byte[] o = Base64.decode(SKIN_B64, Base64.DEFAULT);
        Bitmap b = BitmapFactory.decodeByteArray(o, 0, o.length);
        // Un skin de 2013 fait 64x32. Seule la moitie haute nous interesse :
        // la tete y tient entiere, le format 64x64 n'a rien change pour elle.
        skin = b;
        faces = new Bitmap[6];
        for (int i = 0; i < 6; i++) {
            faces[i] = Bitmap.createBitmap(skin, (int) GEO[i][0], (int) GEO[i][1], 8, 8);
        }
    }

    /**
     * La face avant du creeper, 8x8 texels bruts.
     *
     * Museau s'en sert pour les icones de notification : le logo doit etre LA
     * meme tete que la pastille, pas un dessin qui lui ressemble. Une seule
     * source, donc une seule chose a changer le jour ou le skin change.
     */
    static Bitmap faceAvant() {
        charger();
        return faces == null ? null : faces[0];
    }

    // ------------------------------------------------------------ pilotage

    /**
     * L'etat ne change pas seulement la couleur du fond : il change la facon
     * dont la tete se tient. C'est la moitie de l'information.
     */
    void setEtat(String e) {
        if (e == null) e = "veille";
        if (!e.equals(etat)) {
            etat = e;
            // Tout changement d'etat merite d'etre remarque : la tete se
            // tourne vers USER une fois, puis reprend sa conduite propre.
            salueDepuis = System.nanoTime();
            // ET IL FAUT LA REVEILLER. La veille et la pause arretent la
            // boucle pour ne rien couter ; sans cette ligne, elles ne la
            // rendent jamais. Mesure du defaut : passage a « pilote » apres
            // une pause, 0,2 % d'un coeur et une tete figee. Le voyant
            // changeait de couleur, le dessin restait mort.
            dernier = 0;
            postInvalidateOnAnimation();
        }
    }

    /** Le dessin ne tourne que quand la tete est visible : voir discret(). */
    void setActif(boolean a) {
        if (actif == a) return;
        actif = a;
        if (a) {
            dernier = 0;
            postInvalidateOnAnimation();
        }
    }

    /** Une lecture demarre (duree en ms) ou s'acheve (0). */
    void setLecture(int dureeMs) {
        lecturePause = 0;
        if (dureeMs <= 0) {
            lectureT0 = lectureT1 = 0;
        } else {
            lectureT0 = System.nanoTime();
            lectureT1 = lectureT0 + dureeMs * 1000000L;
        }
        // Comme setEtat : sans ce reveil, une lecture qui commence pendant la
        // veille ne peindrait jamais son anneau, la boucle etant a l'arret.
        dernier = 0;
        postInvalidateOnAnimation();
    }

    /** Le curseur a bouge : l'anneau saute a la position (ms), pause comprise. */
    void setLectureA(int posMs) {
        if (lectureT1 == 0) return;
        long duree = lectureT1 - lectureT0;
        long n = lecturePause != 0 ? lecturePause : System.nanoTime();
        lectureT0 = n - posMs * 1000000L;
        lectureT1 = lectureT0 + duree;
        dernier = 0;
        postInvalidateOnAnimation();
    }

    /** Pause : l'anneau se fige. Reprise : il repart du meme point. */
    void setLecturePause(boolean p) {
        if (lectureT1 == 0) return;
        long n = System.nanoTime();
        if (p) {
            if (lecturePause == 0) lecturePause = n;
        } else if (lecturePause != 0) {
            long d = n - lecturePause;
            lectureT0 += d;
            lectureT1 += d;
            lecturePause = 0;
        }
        dernier = 0;
        postInvalidateOnAnimation();
    }

    /**
     * Le nombre de rapports en attente. USER, 2026-10-02 (la proposition
     * n° 2) : le chiffre dit combien attendent, un toucher lit le dernier.
     */
    void setNonLus(int n) {
        if (n == nonLus) return;
        nonLus = Math.max(0, n);
        postInvalidateOnAnimation();
    }

    /**
     * Le chiffre en haut a droite, comme sur une icone d'appli : la forme
     * que tout le monde lit sans apprendre. Orange plein, chiffre blanc,
     * « 9+ » au-dela pour tenir dans le rond.
     */
    private void dessinerNonLus(Canvas canvas, int w, int h) {
        if (nonLus <= 0) return;
        float r = Math.min(w, h) * 0.19f;
        float x = w - r * 0.95f, y = r * 0.95f;
        pBadge.setColor(Charte.ORANGE);
        canvas.drawCircle(x, y, r, pBadge);
        pBadgeTexte.setColor(Charte.ENCRE);
        pBadgeTexte.setFakeBoldText(true);
        pBadgeTexte.setTextAlign(Paint.Align.CENTER);
        String t = nonLus > 9 ? "9+" : String.valueOf(nonLus);
        pBadgeTexte.setTextSize(r * (t.length() > 1 ? 1.0f : 1.25f));
        Paint.FontMetrics fm = pBadgeTexte.getFontMetrics();
        canvas.drawText(t, x, y - (fm.ascent + fm.descent) / 2f, pBadgeTexte);
    }

    /** Un compte d'envoi demarre (duree en ms) ou s'acheve (0). */
    void setCompte(int dureeMs) {
        if (dureeMs <= 0) {
            compteT0 = compteT1 = 0;
        } else {
            compteT0 = System.nanoTime();
            compteT1 = compteT0 + dureeMs * 1000000L;
        }
        dernier = 0;
        postInvalidateOnAnimation();
    }

    /** Meme garde-fou que lit() : un compte ne survit pas a sa duree. */
    private boolean enCompte() {
        if (compteT1 == 0) return false;
        if (System.nanoTime() >= compteT1) { compteT0 = compteT1 = 0; return false; }
        return true;
    }

    /**
     * Une lecture est-elle en cours ? La peremption se fait ici.
     *
     * Le service annonce toujours la fin, mais il peut mourir avant : un
     * anneau fige a mi-course resterait des heures. La duree annoncee sert
     * donc aussi de garde-fou.
     */
    private boolean lit() {
        if (lectureT1 == 0) return false;
        // En pause, l'anneau reste : le service le liberera au bout de 10 min.
        if (lecturePause != 0) return true;
        if (System.nanoTime() >= lectureT1) { lectureT0 = lectureT1 = 0; return false; }
        return true;
    }

    /**
     * Le doigt est un point d'interet : la tete le suit.
     *
     * dx, dy sont mesures depuis le centre de la pastille, en fraction de sa
     * taille. La vise s'eteint d'elle-meme au bout d'une seconde et demie :
     * sans peremption, un glisser laisserait la tete figee de travers.
     */
    void viser(float dx, float dy) {
        viseX = Math.max(-1.6f, Math.min(1.6f, dx));
        viseY = Math.max(-1.2f, Math.min(1.2f, dy));
        viseJusqua = System.nanoTime() + 1500L * 1000000L;
        postInvalidateOnAnimation();
    }

    /** Appui : la tete s'ecrase un peu, comme un objet qu'on presse. */
    void presser(boolean oui) {
        presse = oui ? 0.88f : 1f;
        postInvalidateOnAnimation();
    }

    /** Un hochement, une fois : accuse reception d'une action. */
    void saluer() {
        salueDepuis = System.nanoTime();
        postInvalidateOnAnimation();
    }

    // -------------------------------------------------------------- conduite

    /**
     * La posture visee, par etat. C'est ici que la pastille cesse d'etre un
     * voyant et devient quelqu'un.
     */
    private void conduire(float t) {
        float l = 0, g = 0, r = 0, s = 0;
        if ("pilote".equals(etat)) {
            // Au travail : elle balaie, comme on cherche quelque chose du
            // regard. Deux sinus de periodes premieres entre elles, sinon le
            // va-et-vient devient une horloge et se lit comme une animation.
            l = 0.52f * (float) Math.sin(t * 1.15f) + 0.14f * (float) Math.sin(t * 2.7f);
            g = 0.10f * (float) Math.sin(t * 1.9f) - 0.04f;
            s = 0.5f * (float) Math.sin(t * 2.3f);
        } else if ("attente".equals(etat)) {
            // Elle te fait face, menton legerement leve, et hoche lentement :
            // la posture de quelqu'un qui attend une reponse.
            l = -0.16f + 0.07f * (float) Math.sin(t * 0.8f);
            g = -0.05f + 0.09f * (float) Math.sin(t * 1.6f);
            r = 0.05f * (float) Math.sin(t * 0.55f);
        } else if ("voix".equals(etat)) {
            // Ecoute : face a toi, un balancement plus vif et une
            // inclinaison alternee, qui est ce qu'on fait en parlant.
            g = 0.07f * (float) Math.sin(t * 4.1f);
            r = 0.10f * (float) Math.sin(t * 1.35f);
            l = -0.10f + 0.09f * (float) Math.sin(t * 0.9f);
            s = 1.2f * (float) Math.sin(t * 4.1f);
        } else if ("voixtravaille".equals(etat)) {
            // Traitement : tete baissee, derive lente et fermee - differente
            // du balayage actif de "pilote", pour se lire comme une
            // reflexion et non comme une recherche.
            l = 0.18f + 0.05f * (float) Math.sin(t * 0.6f);
            g = 0.06f * (float) Math.sin(t * 0.9f);
            r = 0.08f * (float) Math.sin(t * 0.4f);
        } else if ("voixpret".equals(etat)) {
            // Pret : la meme posture que "attente", menton leve, hochement
            // lent - c'est litteralement une invitation a reprendre la
            // parole sans rouvrir le micro tout seul.
            l = -0.16f + 0.07f * (float) Math.sin(t * 0.8f);
            g = -0.05f + 0.09f * (float) Math.sin(t * 1.6f);
            r = 0.05f * (float) Math.sin(t * 0.55f);
        } else if ("capture".equals(etat)) {
            // L'enregistrement est le seul etat qui laisse une trace sur le
            // disque. Elle se fige, droite et frontale : l'immobilite tranche
            // sur tout le reste et se remarque plus qu'un mouvement de plus.
            l = 0f; g = 0f; r = 0f;
            s = 0.25f * (float) Math.sin(t * 1.1f);
        } else if ("suspendu".equals(etat)) {
            // En pause : tete baissee, detournee. Elle ne te regarde plus.
            l = 0.30f; g = 0.34f; r = -0.06f;
        } else {
            // Veille : IMMOBILE.
            //
            // Elle derivait lentement au depart. Deux raisons de l'arreter.
            // La mesure : une fenetre posee par-dessus toutes les applis coute
            // 0,4 % d'un coeur par image et par seconde, quoi qu'elle
            // dessine ; une derive permanente, c'est 7 % toute la journee pour
            // un mouvement que personne ne regarde. Et le sens : si la tete
            // bouge au repos, son mouvement ne veut plus rien dire. Immobile,
            // le moindre frisson devient un signal.
            l = 0f; g = 0.08f; r = 0f; s = 0f;
        }

        // TROIS QUARTS PERMANENT
        //
        // A lacet nul on ne voit qu'une face : la tete redevient un
        // autocollant, tout le calcul de volume ne sert a rien. Un biais
        // constant garde toujours un cote et un bout de dessus visibles,
        // c'est ce qui la fait lire comme un objet. Les etats se contentent
        // ensuite de rouler autour.
        l += BIAIS_LACET;
        g += BIAIS_TANGAGE;

        // Le hochement d'accuse de reception prime pendant 700 ms.
        if (salueDepuis != 0) {
            float a = (System.nanoTime() - salueDepuis) / 1e9f;
            if (a > 0.7f) {
                salueDepuis = 0;
            } else {
                float k = 1f - a / 0.7f;
                l = l * (1 - k);
                g = g * (1 - k) + k * 0.30f * (float) Math.sin(a * 18f);
            }
        }

        // Le doigt prime sur tout le reste : quand USER touche, elle le suit.
        if (viseJusqua != 0) {
            long reste = viseJusqua - System.nanoTime();
            if (reste <= 0) {
                viseJusqua = 0;
            } else {
                float k = Math.min(1f, reste / 4e8f);   // relachement en 400 ms
                l = l * (1 - k) + k * (viseX * 0.45f);
                g = g * (1 - k) + k * (-viseY * 0.30f);
            }
        }

        lacet = l; tangage = g; roulis = r; souffle = s;
    }

    /**
     * Ressort amorti vers la valeur visee.
     *
     * Un simple lissage exponentiel donnait un mouvement mou, sans inertie :
     * la tete glissait au lieu de se tourner. Le depassement leger d'un
     * ressort est ce qui fait la difference entre un objet et un curseur.
     */
    private static float suivre(float actuel, float cible, float dt, float vitesse) {
        float k = 1f - (float) Math.exp(-vitesse * dt);
        float v = actuel + (cible - actuel) * k;
        // Un ressort exponentiel n'atteint jamais sa cible : sans ce collage,
        // pose() reste faux pour l'eternite et la veille ne s'endort pas.
        return Math.abs(cible - v) < 1e-4f ? cible : v;
    }

    // ---------------------------------------------------------------- dessin

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);           // le fond d'etat, pose par Bulle
        if (!actif || faces == null) return;

        long maintenant = System.nanoTime();
        float dt = dernier == 0 ? 0.016f : (maintenant - dernier) / 1e9f;
        dernier = maintenant;
        if (dt > 0.1f) dt = 0.1f;       // reprise apres ecran eteint

        float t = (maintenant - t0) / 1e9f;
        conduire(t);
        lacetC = suivre(lacetC, lacet, dt, 7f);
        tangageC = suivre(tangageC, tangage, dt, 7f);
        roulisC = suivre(roulisC, roulis, dt, 6f);
        souffleC = suivre(souffleC, souffle, dt, 9f);

        int w = getWidth(), h = getHeight();
        if (enCompte()) { dessinerCompte(canvas, w, h); cadencer(); return; }
        float cx = w / 2f;
        float cy = h / 2f + souffleC * dp(0.9f);
        // La tete deborde du disque : c'est ce qui la pose DESSUS au lieu de
        // la coller DEDANS, et ce qui lui donne son relief.
        float taille = Math.min(w, h) * 0.60f * presse;

        // L'anneau AVANT la tete : il borde la pastille, elle se pose dessus.
        if (lit()) dessinerLecture(canvas, w, h);

        float cl = (float) Math.cos(lacetC), sl = (float) Math.sin(lacetC);
        float cg = (float) Math.cos(tangageC), sg = (float) Math.sin(tangageC);
        float cr = (float) Math.cos(roulisC), sr = (float) Math.sin(roulisC);

        // Tri par profondeur : six faces, un tri par insertion suffit et
        // n'alloue rien. Un comparateur aurait cree un objet par image.
        int n = 0;
        for (int i = 0; i < 6; i++) {
            tourner(i, cl, sl, cg, sg, cr, sr);
            // Dos cache : la normale ecran se lit dans le sens de parcours.
            float ux = c3[3] - c3[0], uy = c3[4] - c3[1];
            float vx = c3[9] - c3[0], vy = c3[10] - c3[1];
            if (ux * vy - uy * vx <= 0) continue;
            float d = (c3[2] + c3[5] + c3[8] + c3[11]) / 4f;
            int j = n++;
            while (j > 0 && prof[j - 1] > d) {
                prof[j] = prof[j - 1]; ordre[j] = ordre[j - 1]; j--;
            }
            prof[j] = d; ordre[j] = i;
        }

        for (int k = 0; k < n; k++) {
            int i = ordre[k];
            tourner(i, cl, sl, cg, sg, cr, sr);
            // Le parallelogramme se lit dans les coins : origine en haut a
            // gauche, un vecteur vers la droite, un vers le bas. La texture
            // fait 8 texels de cote, d'ou la division.
            float ox = cx + c3[0] * taille, oy = cy + c3[1] * taille;
            float ux = (c3[3] - c3[0]) * taille / 8f, uy = (c3[4] - c3[1]) * taille / 8f;
            float vx = (c3[9] - c3[0]) * taille / 8f, vy = (c3[10] - c3[1]) * taille / 8f;
            mv[0] = ux; mv[1] = vx; mv[2] = ox;
            mv[3] = uy; mv[4] = vy; mv[5] = oy;
            mv[6] = 0; mv[7] = 0; mv[8] = 1;
            mat.setValues(mv);
            p.setColorFilter(OMBRE[i]);
            canvas.drawBitmap(faces[i], mat, p);
        }

        dessinerIndicateur(canvas, cx, cy, taille, t);
        dessinerNonLus(canvas, w, h);

        cadencer();
    }

    /**
     * Le signal au-dessus de la tete, propre a chaque etat.
     *
     * Pas dans conduire() : ceci ne pilote pas la posture, ca se surimprime
     * dessus. Quatre lectures, quatre langages distincts :
     *
     *  - pilote et voixtravaille (ca reflechit) : trois points carres, a la
     *    Minecraft, qui s'allument l'un apres l'autre en boucle. Le meme
     *    signal pour les deux, parce que c'est la meme chose pour USER : un
     *    agent qui travaille, qu'il s'agisse d'un outil ou d'une reponse.
     *  - voix (le micro ecoute) : un halo qui respire doucement au-dessus de
     *    la tete, pour ne jamais se confondre avec le clignotement vif d'un
     *    niveau sonore, l'ecoute n'a rien d'urgent.
     *  - attente (un rapport patiente) : un point d'exclamation qui rebondit
     *    lentement, assez pour attirer l'oeil sans lire comme une alerte.
     *  - voixpret (a toi de parler) : un micro qui respire lentement, une
     *    invite discrete plutot qu'une alerte. Le toucher fait parler.
     *
     * Les postures de tete restent inchangees (voir conduire()) : ceci
     * ajoute un second niveau de lecture, il ne remplace pas le premier.
     */
    /**
     * L'anneau qui se vide, sur le bord meme de la pastille.
     *
     * Il se peint PAR-DESSUS l'anneau d'etat pose par Bulle, qui lui sert donc
     * de piste : on lit d'un coup d'oeil la part deja dite et la part qui
     * reste. Depart en haut, sens des aiguilles, comme un minuteur.
     *
     * Le lisere sombre sous le blanc n'est pas decoratif : la pastille flotte
     * sur ce que USER regarde, et un trait blanc sur une page blanche n'existe
     * pas. Meme correctif que les trois points de reflexion, vu en capture le
     * 2026-08-29.
     */
    private void dessinerLecture(Canvas canvas, int w, int h) {
        long maintenant = lecturePause != 0 ? lecturePause : System.nanoTime();
        float reste = (lectureT1 - maintenant) / (float) (lectureT1 - lectureT0);
        if (reste < 0f) reste = 0f;
        if (reste > 1f) reste = 1f;

        float ep = dp(2.4f);
        float m = ep / 2f + dp(0.4f);
        arcLecture.set(m, m, w - m, h - m);

        pIndic.setStyle(Paint.Style.STROKE);
        pIndic.setStrokeCap(Paint.Cap.ROUND);

        pIndic.setStrokeWidth(ep + dp(1.6f));
        pIndic.setColor(Charte.OMBRE_LEGERE);
        canvas.drawArc(arcLecture, -90f, 360f * reste, false, pIndic);

        pIndic.setStrokeWidth(ep);
        pIndic.setColor(Charte.ENCRE);
        pIndic.setAlpha(235);
        canvas.drawArc(arcLecture, -90f, 360f * reste, false, pIndic);

        // Le pinceau est partage avec l'indicateur, qui le veut plein et
        // opaque : on le rend comme on l'a pris.
        pIndic.setStyle(Paint.Style.FILL);
        pIndic.setColor(Charte.ENCRE);
    }

    private void dessinerCompte(Canvas canvas, int w, int h) {
        long reste = compteT1 - System.nanoTime();
        float part = reste / (float) (compteT1 - compteT0);
        if (part < 0f) part = 0f;
        if (part > 1f) part = 1f;

        // Un disque sombre sous le chiffre : la pastille est transparente, et
        // un chiffre blanc sur un fond d'ecran clair ne se lirait pas.
        pIndic.setStyle(Paint.Style.FILL);
        pIndic.setColor(Charte.OMBRE_FORTE);
        canvas.drawCircle(w / 2f, h / 2f, Math.min(w, h) / 2f - dp(1f), pIndic);

        float ep = dp(3f);
        float m = ep / 2f + dp(0.4f);
        arcLecture.set(m, m, w - m, h - m);
        pIndic.setStyle(Paint.Style.STROKE);
        pIndic.setStrokeCap(Paint.Cap.ROUND);
        pIndic.setStrokeWidth(ep);
        pIndic.setColor(Charte.AMBRE);
        canvas.drawArc(arcLecture, -90f, 360f * part, false, pIndic);
        pIndic.setStyle(Paint.Style.FILL);
        pIndic.setColor(Charte.ENCRE);

        int secondes = (int) Math.ceil(reste / 1e9);
        pChiffre.setColor(Charte.ENCRE);
        pChiffre.setTextAlign(Paint.Align.CENTER);
        pChiffre.setFakeBoldText(true);
        pChiffre.setTextSize(Math.min(w, h) * 0.46f);
        pChiffre.setShadowLayer(dp(2f), 0, dp(0.5f), Charte.OMBRE_TEXTE);
        Paint.FontMetrics fm = pChiffre.getFontMetrics();
        float y = h / 2f - (fm.ascent + fm.descent) / 2f;
        canvas.drawText(String.valueOf(Math.max(1, secondes)), w / 2f, y, pChiffre);
    }

    private void dessinerIndicateur(Canvas canvas, float cx, float cy, float taille, float t) {
        boolean reflexion = "voixtravaille".equals(etat) || "pilote".equals(etat);
        boolean ecoute = "voix".equals(etat);
        boolean pret = "voixpret".equals(etat);
        boolean attente = "attente".equals(etat);
        if (!reflexion && !ecoute && !pret && !attente) return;

        // Au-dessus du cube, jamais dedans : le cube deborde deja de son
        // disque, le signal doit rester au-dessus de ce debordement pour ne
        // jamais se confondre avec une septieme face.
        //
        // Le plancher a dp(7) n'est pas cosmetique : la fenetre de la pastille
        // fait 130x144 px et la tete en occupe presque toute la hauteur.
        // Sans lui, le signal se calculait a y = -2, hors des bornes, et
        // Android le rognait : les carres sortaient noirs et la barre du
        // point d'exclamation disparaissait entierement. Vu en capture le
        // 2026-08-29. Il mord donc un peu sur le sommet du crane, ce que le
        // lisere sombre rend lisible.
        float y = Math.max(dp(7f), cy - taille * 0.95f);

        if (reflexion) {
            float cote = dp(3.8f);
            float ecart = dp(6.8f);
            for (int i = 0; i < 3; i++) {
                // Un sinus par point, dephase : chacun s'allume a son tour,
                // jamais les trois ensemble. La partie negative est ecretee
                // a zero, d'ou l'attente entre deux passages.
                float a = Math.max(0f, (float) Math.sin(t * 3.0f - i * 1.05f));
                // Plancher a 70 : les trois points restent VISIBLES en
                // permanence, seul le plus vif se deplace. Vu en capture le
                // 2026-08-29 : sans plancher, le creux du sinus les effacait
                // tous les trois pendant un instant, et la pastille avait
                // l'air eteinte au milieu d'un travail en cours.
                float s = cote * (0.72f + 0.28f * a);
                float x = cx + (i - 1) * ecart;
                // Un liseré sombre sous le blanc : la pastille flotte sur ce
                // que USER regarde, et un signal blanc sur une page blanche ne
                // se voit pas. Vu en capture le 2026-08-29, sur un fond clair.
                float m = dp(1.1f);
                pIndic.setStyle(Paint.Style.FILL);
                pIndic.setColor(Charte.OMBRE_LEGERE);
                canvas.drawRect(x - s / 2f - m, y - s / 2f - m, x + s / 2f + m, y + s / 2f + m,
                        pIndic);
                pIndic.setColor(Charte.ENCRE);
                pIndic.setAlpha((int) (150 + 105 * a));
                canvas.drawRect(x - s / 2f, y - s / 2f, x + s / 2f, y + s / 2f, pIndic);
                pIndic.setColor(Charte.ENCRE);
            }
        } else if (ecoute) {
            // Un halo qui respire : rayon et transparence montent et
            // redescendent ensemble sur un rythme lent, comme une
            // inspiration. Un cercle plutot que des carres, pour trancher
            // visuellement avec la reflexion et ne jamais se confondre avec
            // elle d'un coup d'oeil.
            float respire = 0.5f + 0.5f * (float) Math.sin(t * 1.8f);
            float rayon = dp(2.8f) + dp(1.8f) * respire;
            pIndic.setStyle(Paint.Style.STROKE);
            pIndic.setColor(Charte.OMBRE);
            pIndic.setStrokeWidth(dp(3.2f));
            canvas.drawCircle(cx, y, rayon, pIndic);
            pIndic.setColor(Charte.ENCRE);
            pIndic.setStrokeWidth(dp(1.6f));
            pIndic.setAlpha((int) (140 + 100 * respire));
            canvas.drawCircle(cx, y, rayon, pIndic);
            pIndic.setColor(Charte.ENCRE);
            pIndic.setStyle(Paint.Style.FILL);   // remis pour les autres etats
        } else if (attente) {
            // Un point d'exclamation qui rebondit : quelque chose attend d'etre
            // lu. Grossi et redescendu le 2026-08-29 : a 2,2 dp de large il ne
            // se voyait pas du tout, et cale trop haut il sortait de la fenetre
            // de 130x144 px, ou Android le rognait jusqu'a n'en laisser qu'un
            // point. Il lui faut sa propre hauteur de reference, plus basse que
            // les autres signaux, parce que c'est le seul qui soit haut.
            float yb = Math.max(y, dp(11f));
            float rebond = Math.max(0f, (float) Math.sin(t * 1.4f));
            float yy = yb - dp(1.6f) * rebond;
            float largeur = dp(3.2f);
            pIndic.setStyle(Paint.Style.FILL);
            // Deux passes : un lisere sombre, puis le blanc. La pastille flotte
            // sur ce que USER regarde, et un signal blanc sur une page blanche ne
            // se voit pas.
            for (int passe = 0; passe < 2; passe++) {
                float m = passe == 0 ? dp(1.2f) : 0f;
                pIndic.setColor(passe == 0 ? Charte.OMBRE : Charte.ENCRE);
                if (passe == 1) pIndic.setAlpha(245);
                // Rayon fixe, et non la moitie de la largeur : entierement
                // arrondie, la barre devenait un rond et le signe se lisait
                // « 8 » au lieu de « ! ».
                canvas.drawRoundRect(cx - largeur / 2f - m, yy - dp(9f) - m,
                        cx + largeur / 2f + m, yy - dp(2.6f) + m,
                        dp(1.1f) + m, dp(1.1f) + m, pIndic);
                canvas.drawCircle(cx, yy + dp(0.8f), dp(1.5f) + m, pIndic);
            }
            pIndic.setColor(Charte.ENCRE);
        } else {
            // Pret : un micro, qui respire au lieu de clignoter. Il remplace
            // le chevron du 27/08 : USER voyait une fleche et ne savait pas
            // quoi en faire (2026-10-01). Le micro dit le geste, comme le
            // rond de Siri ou de ChatGPT voix : on le touche, il ecoute.
            // Un battement franc aurait l'air d'une alerte, alors que c'est
            // une invite : personne ne presse USER de reprendre la parole.
            float a = 0.4f + 0.6f * Math.abs((float) Math.sin(t * 1.3f));
            pIndic.setStrokeCap(Paint.Cap.ROUND);
            float yc = Math.max(y, dp(10f));
            float cl = dp(2.2f), ch = dp(3.4f);       // demi-largeur, demi-hauteur de la capsule
            float yCap = yc - dp(3.2f);               // centre de la capsule
            float ra = dp(4.4f);                      // rayon de l'etrier
            // Deux passes : un lisere sombre, puis le blanc. Meme raison que
            // le point d'exclamation : un signe blanc sur une page blanche
            // n'existe pas.
            for (int passe = 0; passe < 2; passe++) {
                float m = passe == 0 ? dp(1.1f) : 0f;
                pIndic.setColor(passe == 0 ? Charte.OMBRE : Charte.ENCRE);
                if (passe == 1) pIndic.setAlpha((int) (120 + a * 135f));
                pIndic.setStyle(Paint.Style.FILL);
                canvas.drawRoundRect(cx - cl - m, yCap - ch - m, cx + cl + m, yCap + ch + m,
                        cl + m, cl + m, pIndic);
                pIndic.setStyle(Paint.Style.STROKE);
                pIndic.setStrokeWidth(dp(1.5f) + 2f * m);
                canvas.drawArc(cx - ra, yCap - ra, cx + ra, yCap + ra, 20f, 140f, false, pIndic);
                canvas.drawLine(cx, yCap + ra, cx, yCap + ra + dp(2f), pIndic);
            }
            pIndic.setColor(Charte.ENCRE);
            pIndic.setStyle(Paint.Style.FILL);   // remis pour les autres etats
        }
    }

    /**
     * Programme l'image suivante, au rythme que l'etat merite.
     *
     * Une boucle a la vitesse de l'ecran pour une tete qui derive a 0,27 Hz
     * est du courant brule pour rien, et la pastille est posee par-dessus
     * TOUTES les applis : c'est le seul dessin de l'appareil qui n'ait aucune
     * raison de s'arreter tout seul. Trois regimes :
     *
     *  - suspendu, une fois la pose atteinte : plus rien du tout. Cet etat
     *    dure des heures et son dessin ne bouge plus.
     *  - veille : quinze images par seconde, assez pour une derive lente.
     *  - le reste : plein rythme, ces etats-la se comptent en minutes.
     *
     * Un geste ou un changement d'etat relance toujours la boucle : l'arret
     * n'est donc jamais definitif.
     */
    private void cadencer() {
        // CE QUI COUTE, C'EST L'IMAGE, PAS LE DESSIN
        //
        // Mesure sur le Pixel : 24 % d'un coeur a 60 images par seconde,
        // 7 % a 19. Soit 0,4 % par image et par seconde, quel que soit le
        // contenu. Passer la maille de 8 a 4, puis abandonner drawBitmapMesh
        // pour un drawBitmap affine, n'a rien change au chiffre : le prix est
        // celui de reveiller une fenetre de superposition et de la
        // recomposer, pas celui de poser six quadrilateres.
        //
        // La conclusion tient en une ligne : on ne cherche pas a dessiner
        // moins, on cherche a dessiner MOINS SOUVENT.
        // PIEGE MESURE ICI : postInvalidateDelayed poste un rendez-vous de
        // plus a CHAQUE passage. Des qu'une invalidation venue d'ailleurs
        // declenche un dessin, celui-ci en poste un deuxieme, et les deux
        // files se cumulent sans jamais se resorber. La veille tournait a
        // 48 images par seconde au lieu des 15 demandees. Un rendez-vous
        // unique, retire avant d'etre repose, ferme la porte.
        removeCallbacks(tic);
        boolean sollicitee = viseJusqua != 0 || salueDepuis != 0;
        // Les deux etats dormants ont une pose fixe : une fois atteinte, plus
        // une seule image. Ce sont ceux qui durent des heures.
        // La lecture retient la boucle : son anneau se vide en continu, et les
        // deux etats dormants sont justement ceux ou un rapport se fait lire
        // sans que personne pilote.
        if (!sollicitee && !lit() && !enCompte() && pose()
                && ("suspendu".equals(etat) || "veille".equals(etat))) return;
        // Ailleurs, trente images par seconde. La tete tourne lentement : au
        // dela, on paie le double pour un mouvement qu'on ne distingue pas.
        postDelayed(tic, 33);
    }

    private final Runnable tic = new Runnable() {
        public void run() {
            invalidate();
        }
    };

    /** Vrai quand les ressorts ont rejoint leur cible : plus rien a animer. */
    private boolean pose() {
        return Math.abs(lacetC - lacet) < 1e-3f
                && Math.abs(tangageC - tangage) < 1e-3f
                && Math.abs(roulisC - roulis) < 1e-3f
                && Math.abs(souffleC - souffle) < 1e-3f;
    }

    /** Fait tourner les 4 coins de la face i dans c3, avec sa marge de couture. */
    private void tourner(int i, float cl, float sl, float cg, float sg, float cr, float sr) {
        float[] g = GEO[i];
        // Centre de la face, pour l'ecarter dans son propre plan.
        float mx = 0, my = 0, mz = 0;
        for (int q = 0; q < 4; q++) { mx += g[2 + q * 3]; my += g[3 + q * 3]; mz += g[4 + q * 3]; }
        mx /= 4; my /= 4; mz /= 4;
        for (int q = 0; q < 4; q++) {
            float x = mx + (g[2 + q * 3] - mx) * COUTURE;
            float y = my + (g[3 + q * 3] - my) * COUTURE;
            float z = mz + (g[4 + q * 3] - mz) * COUTURE;
            // roulis (z), puis tangage (x), puis lacet (y)
            float x1 = x * cr - y * sr, y1 = x * sr + y * cr;
            float y2 = y1 * cg - z * sg, z2 = y1 * sg + z * cg;
            float x3 = x1 * cl + z2 * sl, z3 = -x1 * sl + z2 * cl;
            c3[q * 3] = x3; c3[q * 3 + 1] = y2; c3[q * 3 + 2] = z3;
        }
    }

    private float dp(float v) {
        return v * getResources().getDisplayMetrics().density;
    }

    @Override
    protected void onDetachedFromWindow() {
        super.onDetachedFromWindow();
        actif = false;      // plus de fenetre, plus de boucle
    }
}
