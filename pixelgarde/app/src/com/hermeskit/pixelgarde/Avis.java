package com.poste.pixelgarde;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.drawable.Icon;
import android.util.Log;
import android.widget.RemoteViews;

/**
 * L'avis de rapport en attente, et son appui qui lance la lecture.
 *
 * Demande par USER le 2026-08-30, dans le meme souffle que la garde du verrou :
 * « ca met une notification aussi, ah tiens voila j'ai un rapport en attente,
 * je peux cliquer dessus pour lire le rapport directement ». C'est la
 * contrepartie de la garde : puisque le rapport ne parle plus tout seul quand
 * le telephone dort, il faut qu'il se signale et se laisse reprendre.
 *
 * POURQUOI UNE CLASSE DANS L'APPLI, et pas `cmd notification post` : le shell
 * adb tourne en uid 2000 et n'a pas le droit de creer un PendingIntent. Une
 * notification posee au shell ne peut donc porter aucune destination : on
 * pourrait l'afficher, pas la rendre cliquable. C'est deja la raison d'etre du
 * Recepteur, et c'est la meme ici.
 *
 * L'appui vise le service Voix directement, en getForegroundService. Un
 * BroadcastReceiver intermediaire serait plus souple mais ne tiendrait pas :
 * depuis Android 14 un receveur en arriere-plan ne peut pas demarrer un
 * service de premier plan. Le tap d'une notification, lui, porte l'exemption
 * qu'il faut, a condition que le PendingIntent vise le service sans detour.
 */
public class Avis {

    /** L'action de diffusion, cote hote-1 : voir bin/pixel/actions/rapport.sh. */
    public static final String POSER = "com.poste.pixel.AVIS";

    /**
     * Le suffixe compte. Un canal de notification est fige a sa creation :
     * changer l'importance dans le code ne bouge rien tant que l'ancien existe,
     * et le supprimer ne suffit pas non plus, Android restaure ses reglages
     * quand un canal du meme identifiant reapparait. Seul un identifiant neuf
     * prend. Premiere version en IMPORTANCE_LOW, essayee le 2026-08-30 : l'avis
     * tombait dans la section « Silencieux » du panneau, sans icone de barre
     * d'etat, exactement l'endroit ou USER ne l'aurait jamais vu.
     */
    private static final String CANAL = "rapports2";

    /**
     * IMPORTANCE_DEFAULT, mais muet.
     *
     * DEFAULT pour la place : c'est elle qui donne l'icone dans la barre d'etat
     * et le rang normal dans le panneau. Sans elle l'avis existe sans se voir,
     * ce qui ne sert a rien puisque tout son interet est de dire « tiens, j'ai
     * un rapport ».
     *
     * Muet parce que l'avis se pose surtout quand l'ecran dort, donc souvent la
     * nuit : un son a 3 h annulerait le benefice de la garde qu'on vient
     * d'ajouter, dont le seul but est de ne pas reveiller la piece. Le son et
     * la vibration sont donc coupes au niveau du canal, pas de la notification,
     * pour que le reglage tienne meme si USER ouvre les parametres.
     */
    private static void canal(Context ctx, NotificationManager nm) {
        NotificationChannel c = new NotificationChannel(
                CANAL, Langue.t(ctx, R.string.avis_canal), NotificationManager.IMPORTANCE_DEFAULT);
        c.setDescription(Langue.t(ctx, R.string.avis_canal_desc));
        c.setSound(null, null);
        c.enableVibration(false);
        c.setShowBadge(true);
        nm.createNotificationChannel(c);
    }

    /**
     * Un identifiant stable par rapport, derive du nom du fichier audio.
     *
     * Stable et non incremental : le meme rapport repose la meme notification
     * au lieu d'en empiler une seconde, et Voix sait laquelle annuler quand la
     * lecture part. Deux rapports differents, eux, coexistent : USER peut en
     * avoir trois en attente au reveil et vouloir choisir.
     */
    private static int identifiant(String fichier) {
        return 5100 + Math.abs((fichier == null ? "" : fichier).hashCode() % 800);
    }

    /** Pose l'avis. `fichier` est le mp3 deja depose dans files/voix/. */
    public static void poser(Context ctx, String titre, String texte, String fichier) {
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        if (nm == null || fichier == null || fichier.isEmpty()) return;
        canal(ctx, nm);

        Intent i = new Intent(ctx, Voix.class)
                .setAction(Voix.DIRE)
                .putExtra("fichier", fichier);
        // FLAG_IMMUTABLE : rien dans le systeme n'a de raison de reecrire cette
        // destination, et Android 12+ refuse un PendingIntent qui ne tranche
        // pas. UPDATE_CURRENT parce qu'un meme identifiant peut viser un
        // fichier different apres une refabrication de la voix.
        PendingIntent pi = PendingIntent.getForegroundService(
                ctx, identifiant(fichier), i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        String t = (titre == null || titre.isEmpty()) ? Langue.t(ctx, R.string.avis_defaut) : titre;
        String x = (texte == null) ? "" : texte;

        // Le creeper, pas l'enveloppe generique d'Android. Demande par USER le
        // 2026-08-30 : « que la notification soit jolie, avec le creeper comme
        // logo ». Voir Museau : la petite icone est reduite a sa silhouette,
        // Museau.grand sert ailleurs. Repli sur une icone du systeme si le
        // skin ne se decode pas, plutot qu'une notification sans icone, qu'
        // Android refuse d'afficher.
        Bitmap petit = Museau.petit(96);

        Notification.Builder b = new Notification.Builder(ctx, CANAL);
        if (petit != null) b.setSmallIcon(Icon.createWithBitmap(petit));
        else b.setSmallIcon(android.R.drawable.ic_dialog_email);
        // PAS de setLargeIcon. Verifie en capture le 2026-08-30 : la grande
        // icone ajoutait un SECOND creeper a droite de la carte repliee, en
        // face de celui de l'en-tete, et volait la centaine de pixels qui
        // manquait au resume pour tenir sur sa ligne. Un seul creeper suffit a
        // reconnaitre l'avis ; la place gagnee sert au texte.

        // POURQUOI DEUX VUES SUR MESURE, et pas un addAction.
        //
        // Verifie en capture le 2026-08-30 : Android n'affiche les boutons d'un
        // addAction QUE si la carte est depliee. Repliee, l'avis se resumait a
        // « ReadC... . Rapp... . Maintenant » et une premiere ligne coupee : ni
        // le sujet en entier, ni la moindre trace du fait qu'on pouvait lancer
        // la lecture. Or c'est justement replie que USER le voit passer.
        //
        // Une RemoteViews reprend la main sur le corps de la carte, bouton
        // compris, dans les deux etats. DecoratedCustomViewStyle garde par
        // dessus l'en-tete standard d'Android, donc le creeper, le nom de
        // l'appli et l'heure : on ne redessine que ce qu'on a besoin de
        // changer, le reste continue de suivre le theme du systeme.
        RemoteViews vueRepliee = new RemoteViews(ctx.getPackageName(), R.layout.avis);
        vueRepliee.setTextViewText(R.id.avis_titre, t);
        vueRepliee.setTextViewText(R.id.avis_texte, x);
        // Le bouton ET le corps visent la meme destination : viser le bouton
        // seul obligerait a le toucher au pixel pres.
        vueRepliee.setTextViewText(R.id.avis_lire, Langue.t(ctx, R.string.avis_lire));
        vueRepliee.setOnClickPendingIntent(R.id.avis_lire, pi);

        RemoteViews vueDepliee = new RemoteViews(ctx.getPackageName(), R.layout.avis_grand);
        vueDepliee.setTextViewText(R.id.avis_titre, t);
        vueDepliee.setTextViewText(R.id.avis_texte, x);
        vueDepliee.setTextViewText(R.id.avis_lire, Langue.t(ctx, R.string.avis_lire_rapport));
        vueDepliee.setOnClickPendingIntent(R.id.avis_lire, pi);

        Notification n = b
                // Titre et texte restent renseignes bien que les vues les
                // portent deja : ils alimentent la synthese vocale du systeme,
                // la montre, et le repli d'Android si une vue ne s'inflate pas.
                .setContentTitle(t)
                .setContentText(x)
                // setSubText a saute. C'est lui qui volait la place de
                // l'en-tete et tronquait le sujet en « ReadC... ». Le titre
                // porte le SUJET, USER l'a valide le 2026-08-30 ; il doit tenir
                // en entier, c'est la seule chose qui dit d'ou vient l'avis.
                // Le vert du creeper : il teinte la petite icone et le nom de
                // l'appli. Une notification se reconnait a sa couleur avant
                // d'etre lue.
                .setColor(Charte.VERT)
                .setStyle(new Notification.DecoratedCustomViewStyle())
                .setCustomContentView(vueRepliee)
                .setCustomBigContentView(vueDepliee)
                .setContentIntent(pi)
                // L'avis disparait des qu'il a servi : le laisser trainer
                // ferait croire a un second rapport en attente.
                .setAutoCancel(true)
                .setShowWhen(true)
                .build();
        nm.notify(identifiant(fichier), n);
        Log.i("pixelgarde", "avis pose pour " + fichier);
    }

    /**
     * Retire l'avis d'un rapport dont la lecture vient de partir.
     *
     * Appele par Voix a chaque VOIXDIRE, que la lecture vienne d'un appui sur
     * l'avis ou du garde qui reprend un differe. Dans les deux cas l'avis n'a
     * plus lieu d'etre, et setAutoCancel ne couvre que le premier.
     */
    public static void consommer(Context ctx, String fichier) {
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        if (nm != null && fichier != null) nm.cancel(identifiant(fichier));
        // Et on le dit a hote-1 : sans ce mot, le garde garde son jeton differe
        // et relancerait la meme lecture au prochain tour, cinq secondes plus
        // tard. Le canal est celui des appuis de la pastille, pas un troisieme.
        Bulle.commande(ctx, "avislu");
    }
}
