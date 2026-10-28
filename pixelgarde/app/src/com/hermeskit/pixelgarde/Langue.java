package com.poste.pixelgarde;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import java.util.Locale;

/**
 * La langue de l'appli : un seul reglage pour tout le systeme.
 * Ordre : la langue donnee par le relais (fichier d'etat Hermes, "en" ou "fr"),
 * sinon celle du telephone si elle est prise en charge, sinon l'anglais.
 *
 * Usage partout : Langue.t(ctx, R.string.xxx, args...). Pas besoin d'envelopper
 * chaque composant : le texte est resolu a l'appel, donc un changement de
 * langue est pris en compte au texte suivant.
 */
public final class Langue {
  private static final String PREFS = "langue";
  private static final String CLE = "code";
  private static volatile String courante;
  private static Context cache;
  private static String cacheCode;
  /** Appele (sur le thread de l'appelant) quand la langue change vraiment. */
  public static volatile Runnable surChangement;

  private Langue() {}

  /** "en" ou "fr". Jamais autre chose. */
  public static String code(Context c) {
    String v = courante;
    if (v != null) return v;
    Context app = c.getApplicationContext() != null ? c.getApplicationContext() : c;
    String p = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(CLE, null);
    if (valide(p)) v = p;
    else v = "fr".equals(Locale.getDefault().getLanguage()) ? "fr" : "en";
    courante = v;
    return v;
  }

  private static boolean valide(String s) {
    return "en".equals(s) || "fr".equals(s);
  }

  /** Fixe la langue (venue du relais). Vide ou inconnue : on revient a la langue du telephone. */
  public static boolean definir(Context c, String demande) {
    Context app = c.getApplicationContext() != null ? c.getApplicationContext() : c;
    SharedPreferences sp = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    String v = demande == null ? "" : demande.trim().toLowerCase(Locale.ROOT);
    String avant = code(app);
    if (valide(v)) sp.edit().putString(CLE, v).apply();
    else sp.edit().remove(CLE).apply();
    courante = null;
    String apres = code(app);
    if (!apres.equals(avant)) {
      Runnable r = surChangement;
      if (r != null) r.run();
      return true;
    }
    return false;
  }

  /** Le contexte dans la bonne langue, pour getString, inflate, etc. */
  public static synchronized Context ctx(Context c) {
    String code = code(c);
    Context app = c.getApplicationContext() != null ? c.getApplicationContext() : c;
    if (cache == null || !code.equals(cacheCode)) {
      Configuration cfg = new Configuration(app.getResources().getConfiguration());
      cfg.setLocale(new Locale(code));
      cache = app.createConfigurationContext(cfg);
      cacheCode = code;
    }
    return cache;
  }

  public static String t(Context c, int id, Object... args) {
    String s = ctx(c).getResources().getString(id);
    return args.length == 0 ? s : String.format(Locale.ROOT, s, args);
  }

  /** Pour les voix et les dates : la Locale correspondante. */
  public static Locale locale(Context c) {
    return new Locale(code(c));
  }
}
