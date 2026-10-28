package com.poste.pixelgarde;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.graphics.drawable.Icon;
import android.util.Log;

/**
 * Le bouton d'arret de USER, pose dans la zone de notification.
 *
 * Le shell adb ne peut pas creer de PendingIntent (getIntentSender refuse
 * l'uid 2000) : `cmd notification post -c` est donc mort-ne. Il faut une vraie
 * application pour porter un bouton cliquable. Celle-ci ne fait que ca.
 *
 * Le garde, sur hote-1, pilote la notification par diffusion adb, et entend les
 * appuis en relisant le journal d'ActivityManager, qui trace toute diffusion.
 */
public class Recepteur extends BroadcastReceiver {

    private static final String CANAL = "pilotage";
    private static final int ID = 4201;
    public static final String SHOW = "com.poste.pixel.SHOW";
    public static final String HIDE = "com.poste.pixel.HIDE";
    public static final String STOP = "com.poste.pixel.STOP";
    public static final String GO = "com.poste.pixel.GO";
    public static final String BULLE = "com.poste.pixel.BULLE";
    public static final String CACHER = "com.poste.pixel.CACHER";
    /** Le lisere rouge d'enregistrement : --es on 1 pour l'allumer, 0 sinon. */
    public static final String CADRE = "com.poste.pixel.CADRE";
    /**
     * Le voile ambre anti-bleu.
     *
     * --es niveau  : 0..100, un nom de palier, ou un vieux chiffre 0..4.
     * --es auto    : "1" ou "0", la bascule coucher/lever du soleil.
     * Sans extra, l'etat enregistre est repose tel quel.
     */
    public static final String FILTRE = "com.poste.pixel.FILTRE";
    /** Une vibration, --es ms <duree>. Remplace `cmd vibrator_manager`, qui exige ADB. */
    public static final String VIBRE = "com.poste.pixel.VIBRE";

    @Override
    public void onReceive(Context ctx, Intent intent) {
        String action = intent.getAction();
        if (action == null) return;
        Log.i("pixelgarde", "recu " + action);
        Relais.demarrer(ctx);

        if (VIBRE.equals(action)) {
            long ms = 120;
            try { ms = Long.parseLong(intent.getStringExtra("ms").trim()); } catch (Exception e) { }
            android.os.Vibrator v = ctx.getSystemService(android.os.Vibrator.class);
            if (v != null) v.vibrate(android.os.VibrationEffect.createOneShot(
                    Math.max(10, Math.min(ms, 2000)), android.os.VibrationEffect.DEFAULT_AMPLITUDE));
            return;
        }

        if (Auto.ACTION.equals(action)) {
            // L'alarme du coucher ou du lever. rafraichir() repeint ET repose
            // l'alarme suivante : c'est ce qui fait tourner la boucle.
            Auto.rafraichir(ctx);
            return;
        }

        if (FILTRE.equals(action)) {
            String a = intent.getStringExtra("auto");
            if (a != null) Auto.definir(ctx, "1".equals(a.trim())
                    || "on".equals(a.trim()) || "oui".equals(a.trim()));
            String n = intent.getStringExtra("niveau");
            // Sans extra lisible on repose l'etat enregistre : c'est
            // le chemin du redemarrage et celui du chien de garde.
            int v = Filtre.lire(n);
            if (v < 0) {
                if (a == null) Filtre.restaurer(ctx);
            } else {
                Filtre.definir(ctx, v);
            }
            return;
        }

        if (CADRE.equals(action)) {
            String on = intent.getStringExtra("on");
            if ("flash".equals(on)) Cadre.flash(ctx);
            else if ("1".equals(on)) Cadre.montrer(ctx);
            else Cadre.cacher(ctx);
            return;
        }

        // La pastille flottante : meme etat, autre surface.
        if (CACHER.equals(action)) {
            // --es poignee 1 : masquage a la maniere de USER, un cil reste au
            // bord. Sans l'extra, retrait total, celui que hote-1 sait defaire.
            if ("1".equals(intent.getStringExtra("poignee"))) Bulle.masquer(ctx);
            else Bulle.retirer(ctx);
            return;
        }
        if (BULLE.equals(action)) {
            Bulle.poser(ctx, intent.getStringExtra("etat"),
                        intent.getStringExtra("menu"),
                        intent.getStringExtra("forme"),
                        intent.getStringExtra("tetes"));
            return;
        }

        // L'avis de rapport en attente. Voir Avis.java : il faut une classe
        // de l'appli pour porter un PendingIntent, le shell adb n'y a pas
        // droit, donc le garde ne peut que diffuser et laisser faire.
        if (Avis.POSER.equals(action)) {
            Avis.poser(ctx, intent.getStringExtra("titre"),
                       intent.getStringExtra("texte"),
                       intent.getStringExtra("fichier"));
            return;
        }

        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        if (nm == null) return;

        if (HIDE.equals(action)) {
            nm.cancel(ID);
            return;
        }

        // STOP et GO arrivent du bouton lui-meme : on repose l'etat inverse.
        boolean suspendu;
        if (STOP.equals(action)) suspendu = true;
        else if (GO.equals(action)) suspendu = false;
        else suspendu = "suspendu".equals(intent.getStringExtra("etat"));
        // La notification ne connait que deux etats : suspendu, ou pas. Les
        // nuances veille/pilote/attente vivent sur la pastille, qui se voit.

        NotificationChannel canal = new NotificationChannel(
                CANAL, Langue.t(ctx, R.string.recepteur_canal), NotificationManager.IMPORTANCE_LOW);
        canal.setDescription(Langue.t(ctx, R.string.recepteur_canal_desc));
        nm.createNotificationChannel(canal);

        String titre = Langue.t(ctx, suspendu ? R.string.recepteur_titre_pause : R.string.recepteur_titre_actif);
        String texte = Langue.t(ctx, suspendu ? R.string.recepteur_texte_pause : R.string.recepteur_texte_actif);
        String bouton = Langue.t(ctx, suspendu ? R.string.recepteur_reprendre : R.string.recepteur_arreter);
        String cible = suspendu ? GO : STOP;

        Intent i = new Intent(cible).setPackage(ctx.getPackageName());
        PendingIntent pi = PendingIntent.getBroadcast(
                ctx, suspendu ? 1 : 0, i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification n = new Notification.Builder(ctx, CANAL)
                .setSmallIcon(suspendu ? android.R.drawable.ic_lock_idle_lock
                                       : android.R.drawable.ic_media_pause)
                .setContentTitle(titre)
                .setContentText(texte)
                .setOngoing(true)
                .setShowWhen(false)
                .setStyle(new Notification.BigTextStyle().bigText(texte))
                .addAction(new Notification.Action.Builder(
                        Icon.createWithResource("android", android.R.drawable.ic_media_pause),
                        bouton, pi).build())
                .build();
        nm.notify(ID, n);
    }
}
