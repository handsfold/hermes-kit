package com.poste.pixelgarde;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;

/**
 * Lit le presse-papier et le depose dans files/presse.txt, puis se ferme.
 *
 * Depuis Android 10, seule l'application qui a le focus peut lire le
 * presse-papier : la pastille (fenetre superposee sans focus) et le shell
 * adb en sont incapables. Cette activite transparente prend le focus le
 * temps d'une lecture, ecrit le texte et disparait. Elle est lancee par
 * actions/lirepresse.sh via `am start -n com.poste.pixelgarde/.Presse`.
 *
 * Android affiche a chaque lecture la mention « Pilotage agent a colle
 * depuis votre presse-papier » : c'est le systeme, pas un bug.
 */
public class Presse extends Activity {

    private boolean fait;

    @Override public void onWindowFocusChanged(boolean focus) {
        super.onWindowFocusChanged(focus);
        if (!focus || fait) return;
        fait = true;
        String txt = "";
        try {
            ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            ClipData c = cm == null ? null : cm.getPrimaryClip();
            if (c != null && c.getItemCount() > 0) {
                CharSequence s = c.getItemAt(0).coerceToText(this);
                if (s != null) txt = s.toString();
            }
        } catch (Throwable t) {
            Log.i("pixelgarde", "presse : lecture impossible : " + t);
        }
        File f = new File(getExternalFilesDir(null), "presse.txt");
        try (FileOutputStream o = new FileOutputStream(f)) {
            o.write(txt.getBytes("UTF-8"));
        } catch (Throwable t) {
            Log.i("pixelgarde", "presse : ecriture impossible : " + t);
        }
        Log.i("pixelgarde", "presse : " + txt.length() + " caracteres deposes");
        // Lancee avec --ez lire true : la lecture part d'ici, sans repasser
        // par hote-1 (2026-09-24, USER trouvait le trajet trop long).
        if (getIntent().getBooleanExtra("lire", false)) {
            Intent i = new Intent(this, Lecteur.class).setAction(Lecteur.LIRE_TEXTE)
                    .putExtra("texte", txt.isEmpty() ? "Presse-papier vide." : txt)
                    .putExtra("titre", "Presse-papier")
                    .putExtra("debit", getIntent().getFloatExtra("debit", 1.75f));
            startForegroundService(i);
        }
        finish();
    }
}
