package com.poste.pixelgarde;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

import java.util.Calendar;
import java.util.TimeZone;

/**
 * La bascule du voile au coucher et au lever du soleil.
 *
 * USER a demande le 2026-09-07 que le filtre s'allume seul le soir et s'eteigne
 * seul le matin. Trois facons existaient :
 *
 *   - un cron sur hote-1 qui pousse un broadcast en adb : meurt des que le
 *     telephone quitte le Wi-Fi de la maison, c'est-a-dire tous les soirs ;
 *   - l'API TwilightManager d'Android : reservee au systeme, non publique ;
 *   - le calcul local plus une alarme. C'est ce qui est fait ici.
 *
 * L'heure du soleil vient de l'algorithme de l'Almanac (zenith officiel
 * 90,833 deg, qui inclut la refraction et le demi-diametre du disque). La
 * position est FIGEE sur Bangkok : demander la localisation reelle imposerait
 * la permission ACCESS_COARSE_LOCATION, un dialogue de plus, et un GPS qui
 * tourne pour gagner quelques minutes. A 13,7 deg de latitude, l'ecart entre
 * le solstice d'ete et celui d'hiver n'est que d'une quarantaine de minutes.
 *
 * L'alarme est INEXACTE (setAndAllowWhileIdle). Une alarme exacte demanderait
 * SCHEDULE_EXACT_ALARM sur Android 12+, donc encore un ecran de permission,
 * pour un evenement dont le retard tolerable se compte en minutes.
 *
 * Chaque declenchement replanifie le suivant : il n'y a jamais qu'une alarme
 * en vol, et un redemarrage la repose depuis Demarrage.
 */
class Auto {

    static final String ACTION = "com.poste.pixel.FILTRE_AUTO";

    private static final double LAT = 13.7355;
    private static final double LON = 100.5817;
    private static final String FUSEAU = "Asia/Bangkok";

    private static final String PREFS = "pixelgarde";
    private static final String CLE = "filtre_auto";
    private static final int CODE = 0x7F17;

    static boolean actif(Context c) {
        try {
            SharedPreferences p = c.getApplicationContext()
                    .getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            return p.getBoolean(CLE, false);
        } catch (Throwable t) {
            return false;
        }
    }

    static void definir(Context ctx, boolean on) {
        Context c = ctx.getApplicationContext();
        try {
            c.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit().putBoolean(CLE, on).commit();
        } catch (Throwable ignore) {
        }
        rafraichir(c);
    }

    /**
     * Peint ce que l'heure commande, et repose l'alarme.
     *
     * Sans mode auto, l'intensite choisie s'applique telle quelle : c'est ce
     * qui rend le curseur immediat en plein jour quand USER le regle.
     */
    static void rafraichir(Context ctx) {
        Context c = ctx.getApplicationContext();
        int choisi = Filtre.pct(c);
        boolean auto = actif(c);
        boolean nuit = nuit(System.currentTimeMillis());
        int voulu = (auto && !nuit) ? 0 : choisi;
        double[] b = bornes(System.currentTimeMillis());
        Log.i("pixelgarde", "filtre : choisi=" + choisi + " auto=" + auto
                + " nuit=" + nuit + " lever=" + b[0] + " coucher=" + b[1]
                + " -> pose=" + voulu);
        Filtre.peindre(c, voulu);
        planifier(c);
    }

    /** Vrai entre le coucher et le lever du soleil. */
    static boolean nuit(long instant) {
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone(FUSEAU));
        cal.setTimeInMillis(instant);
        double h = cal.get(Calendar.HOUR_OF_DAY) + cal.get(Calendar.MINUTE) / 60.0;
        double lever = heure(cal, true);
        double coucher = heure(cal, false);
        if (Double.isNaN(lever) || Double.isNaN(coucher)) return false;
        return h < lever || h >= coucher;
    }

    /** L'heure locale, en heures decimales, du prochain evenement du jour. */
    static double[] bornes(long instant) {
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone(FUSEAU));
        cal.setTimeInMillis(instant);
        return new double[]{heure(cal, true), heure(cal, false)};
    }

    private static void planifier(Context c) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am == null) return;
        Intent i = new Intent(c, Recepteur.class).setAction(ACTION);
        PendingIntent pi = PendingIntent.getBroadcast(c, CODE, i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        if (!actif(c)) {
            am.cancel(pi);
            return;
        }
        long quand = prochain(System.currentTimeMillis());
        try {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, quand, pi);
            Log.i("pixelgarde", "filtre auto : prochaine bascule dans "
                    + ((quand - System.currentTimeMillis()) / 60000) + " min");
        } catch (Throwable t) {
            Log.w("pixelgarde", "filtre auto : alarme refusee " + t);
        }
    }

    /** L'instant du prochain lever ou coucher, strictement dans le futur. */
    static long prochain(long depuis) {
        for (int jour = 0; jour <= 2; jour++) {
            Calendar cal = Calendar.getInstance(TimeZone.getTimeZone(FUSEAU));
            cal.setTimeInMillis(depuis);
            cal.add(Calendar.DAY_OF_YEAR, jour);
            double[] hh = {heure(cal, true), heure(cal, false)};
            for (double h : hh) {
                if (Double.isNaN(h)) continue;
                Calendar t = (Calendar) cal.clone();
                t.set(Calendar.HOUR_OF_DAY, (int) h);
                t.set(Calendar.MINUTE, (int) Math.round((h - (int) h) * 60));
                t.set(Calendar.SECOND, 5);
                t.set(Calendar.MILLISECOND, 0);
                if (t.getTimeInMillis() > depuis + 60000L) return t.getTimeInMillis();
            }
        }
        // Aucun evenement trouve (nuit ou jour polaire) : on repasse dans 6 h.
        return depuis + 6 * 3600000L;
    }

    // ------------------------------------------------------------- almanach

    private static final double ZENITH = 90.833;

    /**
     * Heure locale decimale du lever (leve=true) ou du coucher.
     *
     * Algorithme de l'Almanac, dans la forme publiee par le Nautical Almanac
     * Office. Rend NaN quand le soleil ne franchit pas l'horizon ce jour-la.
     */
    private static double heure(Calendar cal, boolean leve) {
        int n = cal.get(Calendar.DAY_OF_YEAR);
        double lngHour = LON / 15.0;
        double t = n + (((leve ? 6.0 : 18.0) - lngHour) / 24.0);

        double m = (0.9856 * t) - 3.289;
        double l = m + (1.916 * sin(m)) + (0.020 * sin(2 * m)) + 282.634;
        l = tour(l);

        double ra = tour(Math.toDegrees(Math.atan(0.91764 * tan(l))));
        double lq = Math.floor(l / 90.0) * 90.0;
        double rq = Math.floor(ra / 90.0) * 90.0;
        ra = (ra + (lq - rq)) / 15.0;

        double sinDec = 0.39782 * sin(l);
        double cosDec = Math.cos(Math.asin(sinDec));

        double cosH = (Math.cos(Math.toRadians(ZENITH))
                - (sinDec * sin(LAT))) / (cosDec * cos(LAT));
        if (cosH > 1 || cosH < -1) return Double.NaN;

        double h = Math.toDegrees(Math.acos(cosH));
        if (leve) h = 360.0 - h;
        h /= 15.0;

        double ut = h + ra - (0.06571 * t) - 6.622;
        ut = ut - lngHour;
        while (ut < 0) ut += 24;
        while (ut >= 24) ut -= 24;

        double decalage = cal.getTimeZone().getOffset(cal.getTimeInMillis()) / 3600000.0;
        double local = ut + decalage;
        while (local < 0) local += 24;
        while (local >= 24) local -= 24;
        return local;
    }

    private static double tour(double d) {
        while (d < 0) d += 360;
        while (d >= 360) d -= 360;
        return d;
    }

    private static double sin(double deg) { return Math.sin(Math.toRadians(deg)); }
    private static double cos(double deg) { return Math.cos(Math.toRadians(deg)); }
    private static double tan(double deg) { return Math.tan(Math.toRadians(deg)); }
}
