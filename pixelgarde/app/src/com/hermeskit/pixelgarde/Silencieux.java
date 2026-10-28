package com.poste.pixelgarde;

import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Log;

/**
 * Fait taire l'avertissement systeme de superposition.
 *
 * Android poste lui-meme, sous le paquet « android » (uid 1000), une
 * notification permanente « Pilotage agent s'affiche par-dessus les autres
 * applications » des qu'une fenetre TYPE_APPLICATION_OVERLAY est ajoutee.
 * Elle est incontournable par les moyens habituels :
 *
 *   - ce n'est pas notre notification, `nm.cancel` ne l'atteint pas ;
 *   - couper POST_NOTIFICATION de notre paquet ne la touche pas, elle
 *     appartient au systeme ;
 *   - `cmd notification` n'a aucun sous-ordre pour bloquer un canal ;
 *   - bloquer le canal a la main dans les reglages exige de la trouver, et
 *     une reinstallation la ramene.
 *
 * Un ecouteur de notifications, lui, peut annuler n'importe quelle
 * notification qu'il voit, y compris celles du systeme. C'est le seul chemin
 * qui tient sur un telephone non roote. On n'annule que la notre, reconnue a
 * son etiquette, et on ne lit rien d'autre.
 */
public class Silencieux extends NotificationListenerService {

    private static final String MARQUE =
            "AlertWindowNotification - " + "com.poste.pixelgarde";

    @Override
    public void onListenerConnected() {
        // Au branchement, le systeme ne rejoue pas les notifications deja
        // posees : sans ce balayage, celle d'avant le demarrage survivrait.
        balayer();
        // Le relais reseau vit dans ce processus, que le systeme garde en vie
        // tant que l'ecouteur est branche : c'est son meilleur point d'ancrage.
        Relais.demarrer(this);
        // Le filet le plus rapide, et le seul qui ne depende de rien.
        // Android rebranche tout seul un ecouteur de notifications dans les
        // deux secondes qui suivent la mort de son processus : on s'en sert
        // pour reposer la pastille, mesure a ~2 s contre 20 s pour le garde de
        // hote-1 et un reseau. Bulle.restaurer respecte le masquage voulu.
        try {
            Bulle.restaurer(this);
        } catch (Exception e) {          // noqa
            Log.w("pixelgarde", "restauration a la reconnexion : " + e);
        }
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (concerne(sbn)) annuler(sbn);
    }

    private void balayer() {
        StatusBarNotification[] actives;
        try {
            actives = getActiveNotifications();
        } catch (SecurityException e) {
            Log.w("pixelgarde", "ecouteur pas encore autorise");
            return;
        }
        if (actives == null) return;
        for (StatusBarNotification sbn : actives) {
            if (concerne(sbn)) annuler(sbn);
        }
    }

    private boolean concerne(StatusBarNotification sbn) {
        String tag = sbn.getTag();
        return tag != null && tag.contains(MARQUE);
    }

    /** Trente jours. Au reveil elle est repostee, donc rendormie aussitot. */
    private static final long SOMMEIL = 30L * 24 * 60 * 60 * 1000;

    private void annuler(StatusBarNotification sbn) {
        // PIEGE : cancelNotification() ne marche PAS ici. L'avertissement porte
        // FLAG_ONGOING_EVENT, et NotificationManagerService refuse a tout
        // ecouteur d'annuler une notification permanente (mustNotHaveFlags =
        // FLAG_ONGOING_EVENT dans cancelNotificationFromListenerLocked). L'appel
        // part sans erreur et ne fait rien : c'est le piege, il a l'air de
        // marcher. La mise en veille, elle, n'a pas ce garde-fou.
        snoozeNotification(sbn.getKey(), SOMMEIL);
        Log.i("pixelgarde", "avertissement de superposition endormi 30 jours");
    }
}
