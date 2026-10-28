package com.poste.pixelgarde;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;

import java.util.HashMap;
import java.util.Map;

/**
 * L'ecran Missions (2026-10-03) : qui travaille, ou ca en est, le quota, et
 * les boutons Lancer et Arreter. USER veut se balader dans le plan, la feuille
 * de route et les rapports comme dans des dossiers.
 *
 * La page vit sur hote-1 (bin/pixel/missions/index.html), servie par le relais
 * sous /missions/. Une WebView plutot que des vues natives : la page evolue
 * sans reconstruire l'APK, et une nouvelle mission d'un autre topic y apparait
 * seule (registre ~/.hermes/missions.json).
 *
 * Connexion : la 1re requete porte le jeton du relais en Bearer ; le relais
 * repond avec un cookie HttpOnly limite a /missions, que la page renvoie
 * ensuite seule. Le jeton ne passe jamais dans une URL.
 */
public class Missions extends Activity {
    private static final int FOND = 0xFF111216;
    private WebView web;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(FOND);
        getWindow().setNavigationBarColor(FOND);
        String[] conf = Relais.config(this);
        if (conf == null) {
            TextView t = new TextView(this);
            t.setText(Langue.t(this, R.string.missions_sans_relais));
            t.setTextColor(Charte.TEXTE_2);
            t.setBackgroundColor(FOND);
            t.setGravity(Gravity.CENTER);
            t.setPadding(48, 48, 48, 48);
            setContentView(t);
            return;
        }
        final String base = conf[0].replaceAll("/+$", "");
        final String hote = Uri.parse(base).getHost();
        web = new WebView(this);
        web.setBackgroundColor(FOND);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        CookieManager.getInstance().setAcceptCookie(true);
        web.setWebViewClient(new WebViewClient() {
            // Un lien vers un autre site (un fil Reddit, une page Stripe)
            // s'ouvre dans le navigateur : la WebView reste l'ecran Missions.
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (hote != null && hote.equals(u.getHost())) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (Exception e) {
                    // Pas d'appli pour ce lien : rien a faire.
                }
                return true;
            }
        });
        web.addJavascriptInterface(new Pont(), "Creeper");
        setContentView(web);
        Map<String, String> h = new HashMap<>();
        h.put("Authorization", "Bearer " + conf[1]);
        web.loadUrl(base + "/missions/", h);
    }

    /** La croix de la page ferme l'ecran. */
    private class Pont {
        @JavascriptInterface
        public void fermer() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    finish();
                }
            });
        }
    }

    /** Le retour remonte d'un dossier ; a la racine, il ferme. */
    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
