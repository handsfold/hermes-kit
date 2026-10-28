package com.poste.pixelgarde;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.util.Log;

/**
 * L'icone Creeper du lanceur : rallume la barre et la bulle apres un
 * Masquer total (Bulle.masquer), puis ouvre l'Accueil (Missions.java).
 */
public class Reveil extends Activity {

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        try {
            Bulle.reveiller(getApplicationContext());
        } catch (Throwable t) {
            Log.w("pixelgarde", "reveil : " + t);
        }
        // USER (2026-10-07) : l'icone atterrit sur l'Accueil, pas sur un ecran vide.
        Intent i = new Intent(this, Missions.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(i);
        finish();
    }
}
