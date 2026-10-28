package com.poste.pixelgarde;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

/**
 * Repose la pastille apres un redemarrage du telephone, sans reseau.
 *
 * Le garde de hote-1 la reposait deja, mais seulement s'il tourne et si le
 * telephone est joignable. Au reveil d'un redemarrage, le WiFi met souvent
 * une minute a revenir : la pastille manquait pendant tout ce temps, et
 * indefiniment si hote-1 etait eteint. Ce receveur ne depend de rien.
 *
 * PIEGE : ne PAS ecouter LOCKED_BOOT_COMPLETED. Avant le premier deverrouillage
 * le stockage chiffre par identifiant est indisponible, getSharedPreferences
 * rend un fichier vide, et la pastille reviendrait avec un menu par defaut au
 * lieu du sien. BOOT_COMPLETED arrive apres le deverrouillage : c'est le bon.
 */
public class Demarrage extends BroadcastReceiver {

    @Override
    public void onReceive(final Context ctx, Intent intent) {
        String a = intent.getAction();
        Log.i("pixelgarde", "demarrage " + a);
        // Poser une fenetre d'overlay dans la seconde qui suit BOOT_COMPLETED
        // echoue par intermittence : WindowManager accepte la vue puis le
        // systeme la retire pendant la fin de son propre demarrage. Trois
        // essais espaces couvrent les telephones lents sans rien couter.
        final Handler h = new Handler(Looper.getMainLooper());
        for (int i = 1; i <= 3; i++) {
            final int essai = i;
            h.postDelayed(new Runnable() {
                public void run() {
                    try {
                        Bulle.restaurer(ctx);
                        // Le voile anti-bleu suit le meme chemin : sans
                        // cela un redemarrage de nuit rendrait l'ecran
                        // bleu d'un coup, en pleine obscurite.
                        Filtre.restaurer(ctx);
                    } catch (Exception e) {     // noqa
                        Log.w("pixelgarde", "restauration : " + e);
                    }
                }
            }, essai * ("com.poste.pixel.RESTAURER".equals(a) ? 200L : 4000L));
        }
    }
}
