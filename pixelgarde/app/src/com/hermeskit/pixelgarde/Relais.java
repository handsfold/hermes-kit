package com.poste.pixelgarde;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Le Creeper ecoute hote-1 par le reseau, sans ADB ni Tailscale.
 *
 * POURQUOI (2026-10-03)
 * Jusque-la hote-1 poussait les mp3 et lancait les intents par ADB : debogage
 * sans fil coupe, Tailscale coupe ou telephone redemarre, la bulle devenait
 * muette. USER la veut vivante a la maison comme en 4G. L'appli interroge donc
 * elle-meme le relais de hote-1 (bin/pixel/creeper-relais.py), en HTTPS, par
 * le tunnel exemple.tld, avec un jeton secret.
 *
 * Le protocole rejoue exactement ce que faisait ADB, pour ne rien changer
 * aux scripts de hote-1 :
 *   - push : un fichier a poser sous files/ (les mp3 des rapports) ;
 *   - am   : une ligne `am broadcast|start-foreground-service|start`,
 *            deja decoupee par hote-1, rejouee ici en Intent.
 * Chaque ordre est accuse. Sans accuse dans les delais, hote-1 retombe sur ADB
 * et annule l'ordre : jamais de double lecture.
 *
 * Dans l'autre sens (etape 2), les appuis de USER et ses tours de voix
 * remontent par POST /appui et POST /depot. Un seul fil d'envoi, dans
 * l'ordre : le WAV d'un tour arrive toujours avant l'appui `voixtour` qui le
 * signale. cmd.txt et le fichier local restent ecrits : si le reseau manque,
 * ADB les rattrape comme avant.
 *
 * URL et jeton arrivent une seule fois par files/relais.txt (deux lignes),
 * deposes par ADB a l'installation, puis ranges dans les preferences et le
 * fichier efface. Ils ne sont jamais dans le code.
 */
public class Relais {

    private static final String TAG = "pixelgarde";
    private static Thread fil;
    private static final ExecutorService ENVOI = Executors.newSingleThreadExecutor();
    private static volatile String etat = "eteint";

    static String etat() { return etat; }

    /** Idempotent : tout composant de l'appli peut l'appeler a son reveil. */
    static synchronized void demarrer(Context c) {
        final Context ctx = c.getApplicationContext();
        if (fil != null && fil.isAlive()) return;
        if (config(ctx) == null) { etat = "sans config"; return; }
        Langue.surChangement = new Runnable() {
            public void run() { Bulle.relangue(); }
        };
        fil = new Thread(new Runnable() {
            public void run() { boucle(ctx); }
        }, "relais");
        fil.setDaemon(true);
        fil.start();
        ecouterEcran(ctx);
    }

    /**
     * L'etat de l'ecran, remonte a hote-1 (2026-10-03). Sans ADB, hote-1 ne peut
     * plus lancer dumpsys pour savoir si USER a le telephone en main. Chaque
     * appel /evenements porte donc l'etat, et chaque allumage, extinction ou
     * deverrouillage le pousse tout de suite, sans attendre l'appel suivant.
     */
    private static boolean ecoute;

    static String etatEcran(Context ctx) {
        android.os.PowerManager pm = ctx.getSystemService(android.os.PowerManager.class);
        android.app.KeyguardManager km = ctx.getSystemService(android.app.KeyguardManager.class);
        boolean on = pm != null && pm.isInteractive();
        boolean verrou = km == null || km.isDeviceLocked();
        return "ecran=" + (on ? 1 : 0) + "&verrou=" + (verrou ? 1 : 0)
                + "&casque=" + (casque(ctx) ? 1 : 0);
    }

    /**
     * Des ecouteurs sont-ils branches ? (2026-10-10) USER : « si j'ai mes
     * ecouteurs ca doit jouer automatiquement », meme telephone verrouille.
     * Filaire, USB, Bluetooth A2DP ou LE Audio. La voiture compte aussi :
     * son autoradio est une sortie A2DP, et le rapport y est entendu.
     */
    static boolean casque(Context ctx) {
        android.media.AudioManager am = ctx.getSystemService(android.media.AudioManager.class);
        if (am == null) return false;
        for (android.media.AudioDeviceInfo d : am.getDevices(android.media.AudioManager.GET_DEVICES_OUTPUTS)) {
            switch (d.getType()) {
                case android.media.AudioDeviceInfo.TYPE_WIRED_HEADSET:
                case android.media.AudioDeviceInfo.TYPE_WIRED_HEADPHONES:
                case android.media.AudioDeviceInfo.TYPE_USB_HEADSET:
                case android.media.AudioDeviceInfo.TYPE_BLUETOOTH_A2DP:
                case android.media.AudioDeviceInfo.TYPE_BLE_HEADSET:
                    return true;
                default:
            }
        }
        return false;
    }

    /** Pousse l'etat tout de suite, sans attendre l'appel suivant. */
    private static void pousserEtat(final Context ctx) {
        ENVOI.execute(new Runnable() {
            public void run() {
                String[] cfg = config(ctx);
                if (cfg == null) return;
                try {
                    poster(cfg, "/etat?" + etatEcran(ctx), "application/json",
                            "{}".getBytes("UTF-8"));
                } catch (Exception e) {
                    Log.w(TAG, "relais : etat non remonte " + e);
                }
            }
        });
    }

    private static synchronized void ecouterEcran(final Context ctx) {
        if (ecoute) return;
        ecoute = true;
        android.content.IntentFilter f = new android.content.IntentFilter();
        f.addAction(Intent.ACTION_SCREEN_ON);
        f.addAction(Intent.ACTION_SCREEN_OFF);
        f.addAction(Intent.ACTION_USER_PRESENT);
        ctx.registerReceiver(new android.content.BroadcastReceiver() {
            public void onReceive(Context c, Intent i) {
                pousserEtat(ctx);
            }
        }, f);
        // Ecouteurs branches ou retires : l'etat part dans la seconde.
        android.media.AudioManager am = ctx.getSystemService(android.media.AudioManager.class);
        if (am != null) {
            am.registerAudioDeviceCallback(new android.media.AudioDeviceCallback() {
                public void onAudioDevicesAdded(android.media.AudioDeviceInfo[] a) { pousserEtat(ctx); }
                public void onAudioDevicesRemoved(android.media.AudioDeviceInfo[] r) { pousserEtat(ctx); }
            }, new android.os.Handler(android.os.Looper.getMainLooper()));
        }
    }

    /** Un appui de USER, la meme ligne que cmd.txt : "<ms> <id>". */
    static void appui(Context c, final String ligne) {
        final Context ctx = c.getApplicationContext();
        ENVOI.execute(new Runnable() {
            public void run() {
                String[] cfg = config(ctx);
                if (cfg == null) return;
                try {
                    JSONObject o = new JSONObject();
                    o.put("ligne", ligne);
                    poster(cfg, "/appui", "application/json",
                            o.toString().getBytes("UTF-8"));
                } catch (Exception e) {
                    Log.w(TAG, "relais : appui non remonte " + e);
                }
            }
        });
    }

    /** Un tour de voix de USER (tour-<ms>.wav), remonte avant son appui. */
    static void deposerFichier(Context c, final File f) {
        final Context ctx = c.getApplicationContext();
        ENVOI.execute(new Runnable() {
            public void run() {
                String[] cfg = config(ctx);
                if (cfg == null) return;
                try {
                    byte[] b = new byte[(int) f.length()];
                    FileInputStream in = new FileInputStream(f);
                    int lu = 0, n;
                    while (lu < b.length && (n = in.read(b, lu, b.length - lu)) > 0) lu += n;
                    in.close();
                    poster(cfg, "/depot?nom=" + f.getName(), "audio/wav", b);
                } catch (Exception e) {
                    Log.w(TAG, "relais : tour non remonte " + e);
                }
            }
        });
    }

    private static void poster(String[] cfg, String chemin, String type, byte[] corps)
            throws Exception {
        HttpURLConnection h = ouvrir(cfg, chemin);
        h.setRequestMethod("POST");
        h.setDoOutput(true);
        h.setFixedLengthStreamingMode(corps.length);
        h.setRequestProperty("Content-Type", type);
        OutputStream out = h.getOutputStream();
        out.write(corps);
        out.close();
        int code = h.getResponseCode();
        h.disconnect();
        if (code != 200) throw new Exception("HTTP " + code);
    }

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("relais", Context.MODE_PRIVATE);
    }

    /** {url, jeton}, ou null. Absorbe files/relais.txt s'il vient d'arriver. */
    static String[] config(Context c) {
        SharedPreferences p = prefs(c);
        try {
            File d = c.getExternalFilesDir(null);
            File f = d == null ? null : new File(d, "relais.txt");
            if (f != null && f.isFile()) {
                BufferedReader r = new BufferedReader(new InputStreamReader(
                        new FileInputStream(f), "UTF-8"));
                String url = r.readLine(), jeton = r.readLine();
                r.close();
                if (url != null && jeton != null) {
                    p.edit().putString("url", url.trim())
                            .putString("jeton", jeton.trim()).apply();
                }
                f.delete();
            }
        } catch (Exception e) {
            Log.w(TAG, "relais : config illisible " + e);
        }
        String url = p.getString("url", null), jeton = p.getString("jeton", null);
        return url == null || jeton == null ? null : new String[]{url, jeton};
    }

    private static void boucle(Context ctx) {
        long apres = 0, pause = 2000;
        while (true) {
            String[] cfg = config(ctx);
            if (cfg == null) { etat = "sans config"; return; }
            try {
                HttpURLConnection h = ouvrir(cfg, "/evenements?apres=" + apres + "&attente=25&" + etatEcran(ctx));
                h.setReadTimeout(45000);
                int code = h.getResponseCode();
                if (code != 200) throw new Exception("HTTP " + code);
                JSONObject rep = new JSONObject(lire(h.getInputStream()));
                h.disconnect();
                etat = "relie";
                pause = 2000;
                // La langue unique du systeme, lue par le relais dans l'etat
                // d'Hermes. Absente (vieux relais) : on garde le reglage actuel.
                if (rep.has("langue")) Langue.definir(ctx, rep.optString("langue", ""));
                JSONArray evs = rep.getJSONArray("evenements");
                for (int i = 0; i < evs.length(); i++) {
                    JSONObject ev = evs.getJSONObject(i);
                    long seq = ev.getLong("seq");
                    String note = traiter(ctx, cfg, ev);
                    accuser(cfg, seq, note == null, note);
                    apres = Math.max(apres, seq);
                }
            } catch (Exception e) {
                etat = "coupe : " + e.getClass().getSimpleName();
                Log.w(TAG, "relais : " + e);
                try { Thread.sleep(pause); } catch (InterruptedException ie) { return; }
                pause = Math.min(pause * 2, 30000);
            }
        }
    }

    private static HttpURLConnection ouvrir(String[] cfg, String chemin) throws Exception {
        HttpURLConnection h = (HttpURLConnection) new URL(cfg[0] + chemin).openConnection();
        h.setConnectTimeout(15000);
        h.setReadTimeout(30000);
        h.setUseCaches(false);
        h.setRequestProperty("Authorization", "Bearer " + cfg[1]);
        return h;
    }

    private static String lire(InputStream in) throws Exception {
        StringBuilder sb = new StringBuilder();
        BufferedReader r = new BufferedReader(new InputStreamReader(in, "UTF-8"));
        String l;
        while ((l = r.readLine()) != null) sb.append(l).append('\n');
        r.close();
        return sb.toString();
    }

    private static void accuser(String[] cfg, long seq, boolean ok, String note) {
        try {
            HttpURLConnection h = ouvrir(cfg, "/accuse");
            h.setRequestMethod("POST");
            h.setDoOutput(true);
            h.setRequestProperty("Content-Type", "application/json");
            JSONObject o = new JSONObject();
            o.put("seq", seq).put("ok", ok).put("note", note == null ? "" : note);
            OutputStream out = h.getOutputStream();
            out.write(o.toString().getBytes("UTF-8"));
            out.close();
            h.getResponseCode();
            h.disconnect();
        } catch (Exception e) {
            Log.w(TAG, "relais : accuse perdu " + e);
        }
    }

    /** null si tout s'est bien passe, sinon la raison de l'echec. */
    private static String traiter(Context ctx, String[] cfg, JSONObject ev) {
        try {
            String type = ev.getString("type");
            if ("push".equals(type)) return poser(ctx, cfg, ev.getLong("seq"), ev.getString("rel"));
            if ("am".equals(type)) return lancer(ctx, ev.getJSONArray("args"));
            return "type inconnu " + type;
        } catch (Throwable t) {
            Log.w(TAG, "relais : ordre rate " + t);
            return t.toString();
        }
    }

    private static String poser(Context ctx, String[] cfg, long seq, String rel) throws Exception {
        if (rel.startsWith("/") || ("/" + rel + "/").contains("/../")) return "chemin refuse";
        File base = ctx.getExternalFilesDir(null);
        File cible = new File(base, rel);
        File dossier = cible.getParentFile();
        if (dossier != null) dossier.mkdirs();
        File tmp = new File(dossier, "." + cible.getName() + ".part");
        HttpURLConnection h = ouvrir(cfg, "/fichier/" + seq);
        if (h.getResponseCode() != 200) return "fichier HTTP " + h.getResponseCode();
        InputStream in = h.getInputStream();
        FileOutputStream out = new FileOutputStream(tmp);
        byte[] b = new byte[16384];
        int n;
        while ((n = in.read(b)) > 0) out.write(b, 0, n);
        out.close();
        in.close();
        h.disconnect();
        if (!tmp.renameTo(cible)) return "renommage impossible";
        return null;
    }

    /** Rejoue une ligne `am` deja decoupee. */
    private static String lancer(Context ctx, JSONArray a) throws Exception {
        String sous = a.getString(1);
        Intent it = new Intent();
        for (int i = 2; i < a.length(); i++) {
            String o = a.getString(i);
            switch (o) {
                case "-n": {
                    String v = a.getString(++i);
                    ComponentName cn = ComponentName.unflattenFromString(v);
                    if (cn == null || !ctx.getPackageName().equals(cn.getPackageName()))
                        return "composant refuse " + v;
                    it.setComponent(cn);
                    break;
                }
                case "-a": it.setAction(a.getString(++i)); break;
                case "-d": it.setData(Uri.parse(a.getString(++i))); break;
                case "-c": it.addCategory(a.getString(++i)); break;
                case "-f": it.addFlags(Integer.decode(a.getString(++i))); break;
                case "--es": it.putExtra(a.getString(++i), a.getString(++i)); break;
                case "--esn": it.putExtra(a.getString(++i), (String) null); break;
                case "--ez": {
                    String k = a.getString(++i), v = a.getString(++i);
                    it.putExtra(k, "true".equalsIgnoreCase(v) || "1".equals(v));
                    break;
                }
                case "--ei": it.putExtra(a.getString(++i), Integer.parseInt(a.getString(++i))); break;
                case "--el": it.putExtra(a.getString(++i), Long.parseLong(a.getString(++i))); break;
                case "--ef": it.putExtra(a.getString(++i), Float.parseFloat(a.getString(++i))); break;
                case "--eu": it.putExtra(a.getString(++i), Uri.parse(a.getString(++i))); break;
                case "--user": i++; break;
                case "-W": case "--receiver-foreground": break;
                default: return "option inconnue " + o;
            }
        }
        if (it.getComponent() == null) return "sans composant";
        switch (sous) {
            case "broadcast":
                ctx.sendBroadcast(it);
                return null;
            case "start-foreground-service": case "startforegroundservice":
                ctx.startForegroundService(it);
                return null;
            case "startservice": case "start-service":
                ctx.startService(it);
                return null;
            case "start": case "start-activity":
                it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                ctx.startActivity(it);
                return null;
            default:
                return "sous-commande " + sous;
        }
    }
}
