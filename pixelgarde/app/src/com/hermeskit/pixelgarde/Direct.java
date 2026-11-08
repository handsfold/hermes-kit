package com.poste.pixelgarde;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.AudioDeviceInfo;
import android.media.AudioFocusRequest;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.media.audiofx.AcousticEchoCanceler;
import android.media.audiofx.NoiseSuppressor;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Base64;
import android.util.Log;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URL;
import java.net.URLEncoder;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.List;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

/**
 * La conversation directe (2026-11-03) : micro et voix en continu, dans les
 * deux sens a la fois, par un WebSocket vers relais/creeper-live.py sur hote-1.
 *
 * Pourquoi a cote de Voix et pas dedans : le tour de Voix (ECOUTE, TRAVAILLE,
 * PARLE, PRET) mesure 14 s de mediane ; ici la reponse part une demi-seconde
 * apres la fin de la phrase et USER peut couper la parole. Les deux modes
 * coexistent : le tour reste le mode par defaut, celui-ci s'ouvre et se ferme
 * depuis le menu de la bulle.
 *
 * Protocole (voir l'en-tete du serveur) :
 *   telephone -> hote-1 : trames binaires, PCM 16 bits mono 24 kHz, blocs de 100 ms
 *   hote-1 -> telephone : trames binaires (la voix, meme format)
 *                       trames texte JSON {"ev": "pret|parole|coupe|fin|outil|erreur"}
 *
 * Le client WebSocket est ecrit a la main sur SSLSocket (RFC 6455, le
 * minimum) : l'appli n'embarque aucune bibliotheque, et OkHttp n'est pas
 * public dans le SDK.
 *
 * Demarrage : comme Voix, par `am start-foreground-service` venu du garde
 * (actions/direct.sh) : un service micro lance depuis l'arriere-plan
 * n'entendrait que du silence. L'arret, lui, part de la bulle par un simple
 * startService, le service etant deja au premier plan.
 */
public class Direct extends Service {

    public static final String DEMARRER = "com.poste.pixel.DIRECT";
    public static final String ARRETER = "com.poste.pixel.DIRECTFIN";

    private static final String TAG = "pixelgarde";
    private static final String CANAL = "direct";
    private static final int NOTIF = 4203;

    private static final int TAUX = 24000;
    /** 100 ms de micro : 2400 echantillons de 2 octets. */
    private static final int BLOC = 4800;
    /** Une trame recue au-dela est une erreur de protocole, pas de la voix. */
    private static final int TRAME_MAX = 1 << 20;
    /** Le serveur pinge toutes les 20 s : 45 s sans rien, le lien est mort. */
    private static final int LECTURE_MS = 45000;
    private static final int CONNEXION_MS = 10000;
    /** Tranche d'ecriture vers le haut-parleur : 20 ms, la coupure en perd au plus autant. */
    private static final int TRANCHE = 960;
    private static final String GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    /** Vrai des que le service tourne : le second appui arrete. */
    private static volatile boolean actif = false;
    public static boolean actif() { return actif; }

    private final Handler h = new Handler(Looper.getMainLooper());
    private final SecureRandom alea = new SecureRandom();

    private volatile boolean vivant = false;
    /** Vrai apres {"ev":"pret"} : le micro ne part pas avant. */
    private volatile boolean pret = false;
    private volatile Socket sock;
    private volatile OutputStream sortie;
    private final Object verrouSortie = new Object();

    private Thread filSession, filMicro, filHaut;
    private AudioRecord micro;
    private AcousticEchoCanceler aec;
    private NoiseSuppressor ns;
    private AudioTrack haut;
    private AudioFocusRequest focus;
    private int modeAvant = AudioManager.MODE_NORMAL;

    /** La voix recue, en attente du haut-parleur. Videe a la coupure. */
    private final LinkedBlockingQueue<byte[]> file = new LinkedBlockingQueue<byte[]>();
    /** Incremente a chaque coupure : la tranche en cours d'ecriture se perime. */
    private volatile int generation = 0;
    /** Fin estimee de ce qui est deja ecrit dans l'AudioTrack (horloge monotone). */
    private volatile long finPrevue = 0;
    /** Duree totale de la reponse en cours, et son debut, pour l'anneau. */
    private long reponseMs = 0, reponseT0 = 0, anneauVu = 0;
    private volatile boolean parle = false;

    /** Le message a afficher a l'arret, pose par la premiere cause connue. */
    private volatile String raison = null;

    @Override public IBinder onBind(Intent i) { return null; }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        // Lance par start-foreground-service, le service DOIT passer au premier
        // plan sous quelques secondes, quel que soit l'ordre, sinon Android
        // tue l'appli (meme regle que Voix).
        if (!premierPlan()) {
            dire(Langue.t(this, R.string.direct_micro));
            finir();
            return START_NOT_STICKY;
        }
        if (ARRETER.equals(action) || (DEMARRER.equals(action) && actif)) {
            // Un 2e appui sur le meme bouton ferme la conversation.
            arreter(Langue.t(this, R.string.direct_fini));
            return START_NOT_STICKY;
        }
        if (!DEMARRER.equals(action)) {
            if (!actif) finir();
            return START_NOT_STICKY;
        }
        if (Voix.actif()) {
            // Deux services sur le meme micro : le second n'entendrait rien.
            dire(Langue.t(this, R.string.direct_voix_ouverte));
            finir();
            return START_NOT_STICKY;
        }
        final String[] cfg = Relais.config(this);
        if (cfg == null) {
            dire(Langue.t(this, R.string.direct_sans_relais));
            finir();
            return START_NOT_STICKY;
        }
        if (!ouvrirAudio()) {
            dire(Langue.t(this, R.string.direct_micro));
            fermerAudio();
            finir();
            return START_NOT_STICKY;
        }
        actif = true;
        vivant = true;
        raison = null;
        Bulle.direct("voixtravaille");
        Log.i(TAG, "direct : ouverture");
        filSession = new Thread(new Runnable() {
            public void run() { session(cfg); }
        }, "direct-session");
        filMicro = new Thread(new Runnable() {
            public void run() { boucleMicro(); }
        }, "direct-micro");
        filHaut = new Thread(new Runnable() {
            public void run() { boucleHaut(); }
        }, "direct-haut");
        filSession.start();
        filMicro.start();
        filHaut.start();
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        if (actif) arreter(null);
        super.onDestroy();
    }

    // ------------------------------------------------------------- session

    /** Une erreur qui ne merite pas de reessai : le message est deja choisi. */
    private static final class Fatale extends IOException {
        Fatale(String m) { super(m); }
    }

    /** Le serveur a ferme proprement (trame close). */
    private static final class Fermee extends IOException {
        final int code;
        Fermee(int code, String m) { super("close " + code + " " + m); this.code = code; }
    }

    /**
     * Une connexion, puis UN seul reessai si elle tombe, puis l'arret. Jamais
     * de boucle : un serveur arrete ou un jeton faux ne doivent pas faire
     * tourner le micro et la batterie pour rien.
     */
    private void session(String[] cfg) {
        int essais = 0;
        String msg = null;
        while (vivant) {
            try {
                connecter(cfg);
                lireTrames();
                // lireTrames ne rend la main que si vivant est tombe.
                return;
            } catch (Fatale e) {
                Log.w(TAG, "direct : arret " + e.getMessage());
                msg = e.getMessage();
                break;
            } catch (Fermee e) {
                Log.w(TAG, "direct : " + e.getMessage());
                if (e.code == 4401) { msg = Langue.t(this, R.string.direct_jeton); break; }
                msg = Langue.t(this, R.string.direct_reseau);
            } catch (Exception e) {
                if (!vivant) return;
                Log.w(TAG, "direct : lien perdu " + e);
                msg = Langue.t(this, R.string.direct_reseau);
            } finally {
                fermerSocket();
            }
            if (!vivant) return;
            if (essais >= 1) break;
            essais++;
            pret = false;
            couper();
            Bulle.direct("voixtravaille");
            Log.i(TAG, "direct : reessai");
            SystemClock.sleep(1500);
        }
        if (vivant) {
            final String m = msg == null ? Langue.t(this, R.string.direct_reseau) : msg;
            h.post(new Runnable() { public void run() { arreter(m); } });
        }
    }

    private void connecter(String[] cfg) throws Exception {
        URL u = new URL(cfg[0]);
        String hote = u.getHost();
        boolean tls = !"http".equalsIgnoreCase(u.getProtocol());
        int port = u.getPort() > 0 ? u.getPort() : (tls ? 443 : 80);
        String chemin = "/live?jeton=" + URLEncoder.encode(cfg[1], "UTF-8");

        Socket s;
        if (tls) {
            SSLSocketFactory f = (SSLSocketFactory) SSLSocketFactory.getDefault();
            Socket brut = new Socket();
            brut.connect(new InetSocketAddress(hote, port), CONNEXION_MS);
            SSLSocket ss = (SSLSocket) f.createSocket(brut, hote, port, true);
            ss.setSoTimeout(CONNEXION_MS);
            ss.startHandshake();
            // SSLSocketFactory ne verifie pas le nom du certificat : c'est a
            // nous de le faire, sinon n'importe quel certificat valide passe.
            if (!HttpsURLConnection.getDefaultHostnameVerifier().verify(hote, ss.getSession())) {
                ss.close();
                throw new IOException("certificat ne couvre pas " + hote);
            }
            s = ss;
        } else {
            s = new Socket();
            s.connect(new InetSocketAddress(hote, port), CONNEXION_MS);
        }
        s.setSoTimeout(CONNEXION_MS);
        s.setTcpNoDelay(true);
        sock = s;

        byte[] k = new byte[16];
        alea.nextBytes(k);
        String cle = Base64.encodeToString(k, Base64.NO_WRAP);
        String req = "GET " + chemin + " HTTP/1.1\r\n"
                + "Host: " + hote + (u.getPort() > 0 ? ":" + port : "") + "\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Key: " + cle + "\r\n"
                + "Sec-WebSocket-Version: 13\r\n"
                + "User-Agent: Creeper\r\n\r\n";
        OutputStream o = s.getOutputStream();
        o.write(req.getBytes("UTF-8"));
        o.flush();

        String entete = lireEntete(s.getInputStream());
        String premiere = entete.substring(0, Math.max(0, entete.indexOf("\r\n")));
        if (!premiere.contains(" 101")) {
            Log.w(TAG, "direct : refus HTTP " + premiere);
            if (premiere.contains(" 401") || premiere.contains(" 403")) {
                throw new Fatale(Langue.t(this, R.string.direct_jeton));
            }
            throw new IOException("poignee refusee : " + premiere);
        }
        MessageDigest sha = MessageDigest.getInstance("SHA-1");
        String attendu = Base64.encodeToString(sha.digest((cle + GUID).getBytes("UTF-8")), Base64.NO_WRAP);
        if (!entete.toLowerCase(java.util.Locale.ROOT).contains("sec-websocket-accept: " + attendu.toLowerCase(java.util.Locale.ROOT))) {
            throw new IOException("Sec-WebSocket-Accept invalide");
        }
        s.setSoTimeout(LECTURE_MS);
        synchronized (verrouSortie) { sortie = o; }
        Log.i(TAG, "direct : lien ouvert");
    }

    /** L'entete HTTP de la reponse, jusqu'a la ligne vide (8 Ko au plus). */
    private static String lireEntete(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int fin = 0;
        while (b.size() < 8192) {
            int c = in.read();
            if (c < 0) throw new EOFException("entete coupee");
            b.write(c);
            if ((fin == 0 || fin == 2) && c == '\r') fin++;
            else if ((fin == 1 || fin == 3) && c == '\n') fin++;
            else fin = c == '\r' ? 1 : 0;
            if (fin == 4) return b.toString("UTF-8");
        }
        throw new IOException("entete trop longue");
    }

    /** Lit les trames jusqu'a l'arret ou l'erreur. */
    private void lireTrames() throws Exception {
        InputStream in = sock.getInputStream();
        ByteArrayOutputStream morceaux = null;
        int opMessage = 0;
        while (vivant) {
            int b0 = in.read();
            if (b0 < 0) throw new EOFException("fin du flux");
            int b1 = lireOctet(in);
            boolean fin = (b0 & 0x80) != 0;
            int op = b0 & 0x0F;
            boolean masque = (b1 & 0x80) != 0;
            long n = b1 & 0x7F;
            if (n == 126) n = (lireOctet(in) << 8) | lireOctet(in);
            else if (n == 127) {
                n = 0;
                for (int i = 0; i < 8; i++) n = (n << 8) | lireOctet(in);
            }
            if (n < 0 || n > TRAME_MAX) throw new IOException("trame trop longue " + n);
            byte[] m = null;
            if (masque) { m = new byte[4]; lireTout(in, m); }
            byte[] p = new byte[(int) n];
            lireTout(in, p);
            if (m != null) for (int i = 0; i < p.length; i++) p[i] ^= m[i & 3];

            if (op == 0x8) {
                int code = p.length >= 2 ? ((p[0] & 0xFF) << 8) | (p[1] & 0xFF) : 1005;
                String txt = p.length > 2 ? new String(p, 2, p.length - 2, "UTF-8") : "";
                try { envoyer(0x8, p.length >= 2 ? new byte[]{p[0], p[1]} : new byte[0]); } catch (Exception ignore) { }
                throw new Fermee(code, txt);
            } else if (op == 0x9) {
                envoyer(0xA, p);
            } else if (op == 0xA) {
                // pong : rien a faire
            } else if (op == 0x1 || op == 0x2) {
                if (fin) recu(op, p);
                else { opMessage = op; morceaux = new ByteArrayOutputStream(); morceaux.write(p); }
            } else if (op == 0x0) {
                if (morceaux == null) throw new IOException("suite sans debut");
                morceaux.write(p);
                if (morceaux.size() > TRAME_MAX) throw new IOException("message trop long");
                if (fin) { recu(opMessage, morceaux.toByteArray()); morceaux = null; }
            } else {
                throw new IOException("opcode inconnu " + op);
            }
        }
    }

    private static int lireOctet(InputStream in) throws IOException {
        int c = in.read();
        if (c < 0) throw new EOFException("trame coupee");
        return c;
    }

    private static void lireTout(InputStream in, byte[] b) throws IOException {
        int lu = 0;
        while (lu < b.length) {
            int r = in.read(b, lu, b.length - lu);
            if (r < 0) throw new EOFException("trame coupee");
            lu += r;
        }
    }

    /** Une trame client : toujours masquee (RFC 6455, 5.3), jamais fragmentee. */
    private void envoyer(int op, byte[] p) throws IOException {
        int n = p.length;
        int tete = 2 + (n < 126 ? 0 : n < 65536 ? 2 : 8) + 4;
        byte[] t = new byte[tete + n];
        t[0] = (byte) (0x80 | op);
        int i = 1;
        if (n < 126) {
            t[i++] = (byte) (0x80 | n);
        } else if (n < 65536) {
            t[i++] = (byte) (0x80 | 126);
            t[i++] = (byte) (n >> 8);
            t[i++] = (byte) n;
        } else {
            t[i++] = (byte) (0x80 | 127);
            for (int d = 56; d >= 0; d -= 8) t[i++] = (byte) (((long) n) >> d);
        }
        byte[] m = new byte[4];
        alea.nextBytes(m);
        System.arraycopy(m, 0, t, i, 4);
        i += 4;
        for (int j = 0; j < n; j++) t[i + j] = (byte) (p[j] ^ m[j & 3]);
        synchronized (verrouSortie) {
            OutputStream o = sortie;
            if (o == null) throw new IOException("lien ferme");
            o.write(t);
            o.flush();
        }
    }

    /** Un message complet du serveur. */
    private void recu(int op, byte[] p) throws Exception {
        if (op == 0x2) {
            if (p.length > 0) file.offer(p);
            return;
        }
        String ev;
        JSONObject j;
        try {
            j = new JSONObject(new String(p, "UTF-8"));
            ev = j.optString("ev", "");
        } catch (Exception e) {
            Log.w(TAG, "direct : texte illisible");
            return;
        }
        if ("pret".equals(ev)) {
            pret = true;
            Log.i(TAG, "direct : pret");
            Bulle.direct("voix");
        } else if ("coupe".equals(ev)) {
            // USER parle par-dessus : la voix se tait TOUT DE SUITE.
            couper();
            Bulle.direct("voix");
        } else if ("parole".equals(ev) || "outil".equals(ev)) {
            if (!parle) Bulle.direct("voixtravaille");
        } else if ("veille".equals(ev)) {
            // Le relais dort : le mot de reveil est attendu, plus rien ne part chez le fournisseur.
            if (!parle) Bulle.direct("voixveille");
        } else if ("reveil".equals(ev)) {
            if (!parle) Bulle.direct("voix");
        } else if ("fin".equals(ev)) {
            if (!parle) Bulle.direct("voix");
        } else if ("erreur".equals(ev)) {
            Log.w(TAG, "direct : erreur serveur " + j.optString("msg", ""));
            throw new Fatale(Langue.t(this, R.string.direct_erreur));
        }
    }

    // ---------------------------------------------------------------- audio

    /**
     * Micro et haut-parleur ouverts AVANT le reseau : un micro refuse se dit
     * tout de suite, sans attendre une poignee de main pour rien.
     */
    private boolean ouvrirAudio() {
        AudioManager am = getSystemService(AudioManager.class);
        try {
            int min = AudioRecord.getMinBufferSize(TAUX, AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT);
            micro = new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, TAUX,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
                    Math.max(min, BLOC * 4));
            if (micro.getState() != AudioRecord.STATE_INITIALIZED) {
                Log.w(TAG, "direct : AudioRecord non initialise");
                return false;
            }
        } catch (Exception e) {
            Log.w(TAG, "direct : micro " + e);
            return false;
        }
        // L'echo du haut-parleur dans le micro est le risque numero 1 en
        // duplex : sans annulation, le serveur entendrait sa propre voix et se
        // couperait la parole a lui-meme.
        int sid = micro.getAudioSessionId();
        if (AcousticEchoCanceler.isAvailable()) {
            aec = AcousticEchoCanceler.create(sid);
            if (aec != null) aec.setEnabled(true);
            Log.i(TAG, "direct : annulation d'echo " + (aec != null && aec.getEnabled() ? "active" : "refusee"));
        } else {
            Log.w(TAG, "direct : annulation d'echo indisponible");
        }
        if (NoiseSuppressor.isAvailable()) {
            ns = NoiseSuppressor.create(sid);
            if (ns != null) ns.setEnabled(true);
            Log.i(TAG, "direct : reduction de bruit " + (ns != null && ns.getEnabled() ? "active" : "refusee"));
        } else {
            Log.w(TAG, "direct : reduction de bruit indisponible");
        }

        AudioAttributes aa = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build();
        try {
            int min = AudioTrack.getMinBufferSize(TAUX, AudioFormat.CHANNEL_OUT_MONO,
                    AudioFormat.ENCODING_PCM_16BIT);
            haut = new AudioTrack.Builder()
                    .setAudioAttributes(aa)
                    .setAudioFormat(new AudioFormat.Builder()
                            .setSampleRate(TAUX)
                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                            .setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                    .setBufferSizeInBytes(Math.max(min, BLOC * 2))
                    .setTransferMode(AudioTrack.MODE_STREAM)
                    .build();
        } catch (Exception e) {
            Log.w(TAG, "direct : haut-parleur " + e);
            return false;
        }

        // Mode communication : c'est lui qui donne a l'annulation d'echo la
        // voix jouee comme reference. Il enverrait le son a l'ecouteur : on
        // le ramene sur le haut-parleur, sauf si un casque est branche.
        if (am != null) {
            try {
                modeAvant = am.getMode();
                am.setMode(AudioManager.MODE_IN_COMMUNICATION);
                if (Build.VERSION.SDK_INT >= 31) choisirSortie(am);
                else am.setSpeakerphoneOn(true);
            } catch (Exception e) {
                Log.w(TAG, "direct : mode communication " + e);
            }
            try {
                focus = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
                        .setAudioAttributes(aa).build();
                am.requestAudioFocus(focus);
            } catch (Exception e) {
                Log.w(TAG, "direct : focus " + e);
            }
        }
        micro.startRecording();
        haut.play();
        return true;
    }

    /** API 31+ : casque s'il y en a un, sinon haut-parleur. */
    private void choisirSortie(AudioManager am) {
        List<AudioDeviceInfo> l = am.getAvailableCommunicationDevices();
        AudioDeviceInfo hp = null, casque = null;
        for (AudioDeviceInfo d : l) {
            int t = d.getType();
            if (t == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER) hp = d;
            else if (t == AudioDeviceInfo.TYPE_WIRED_HEADSET || t == AudioDeviceInfo.TYPE_WIRED_HEADPHONES
                    || t == AudioDeviceInfo.TYPE_USB_HEADSET || t == AudioDeviceInfo.TYPE_BLUETOOTH_SCO
                    || t == AudioDeviceInfo.TYPE_BLE_HEADSET) {
                if (casque == null) casque = d;
            }
        }
        AudioDeviceInfo c = casque != null ? casque : hp;
        if (c != null) {
            boolean ok = am.setCommunicationDevice(c);
            Log.i(TAG, "direct : sortie " + c.getType() + (ok ? "" : " refusee"));
        }
    }

    /** Envoie le micro par blocs de 100 ms, des que le serveur est pret. */
    private void boucleMicro() {
        byte[] b = new byte[BLOC];
        while (vivant) {
            int lu = 0;
            while (lu < BLOC && vivant) {
                int r;
                try { r = micro.read(b, lu, BLOC - lu); } catch (Exception e) { r = -1; }
                if (r < 0) {
                    Log.w(TAG, "direct : lecture micro " + r);
                    final String m = Langue.t(this, R.string.direct_micro);
                    h.post(new Runnable() { public void run() { arreter(m); } });
                    return;
                }
                lu += r;
            }
            if (!vivant) return;
            if (!pret) continue;
            try {
                envoyer(0x2, b);
            } catch (IOException e) {
                // Le fil de session voit la meme panne et decide du reessai.
            }
        }
    }

    /**
     * Ecrit la voix recue dans l'AudioTrack, par tranches de 20 ms : une
     * coupure ne laisse passer au plus qu'une tranche perimee. Porte aussi les
     * etats PARLE (anneau de lecture) et le retour a l'ECOUTE quand tout est joue.
     */
    private void boucleHaut() {
        while (vivant) {
            byte[] p;
            try { p = file.poll(100, TimeUnit.MILLISECONDS); } catch (InterruptedException e) { return; }
            long now = SystemClock.elapsedRealtime();
            if (p == null) {
                if (parle && now > finPrevue + 150) {
                    parle = false;
                    reponseMs = 0;
                    Bulle.lecture(0);
                    Bulle.direct("voix");
                }
                continue;
            }
            int g = generation;
            if (!parle) {
                parle = true;
                reponseT0 = now;
                reponseMs = 0;
                anneauVu = 0;
                Bulle.direct("voix");
            }
            int ms = p.length / (TAUX * 2 / 1000);
            reponseMs += ms;
            finPrevue = Math.max(finPrevue, now) + ms;
            // L'anneau existant (Tete.setLecture) attend une duree totale : on
            // la reannonce quand elle a grandi, puis on recale la position.
            if (now - anneauVu >= 500) {
                anneauVu = now;
                long joue = Math.max(0, reponseMs - (finPrevue - now));
                Bulle.lecture((int) reponseMs);
                Bulle.lectureA((int) joue);
            }
            for (int o = 0; o < p.length && vivant && g == generation; o += TRANCHE) {
                int n = Math.min(TRANCHE, p.length - o);
                try { haut.write(p, o, n); } catch (Exception e) { break; }
            }
        }
    }

    /** La coupure de parole : pause, flush, play. Sans attente. */
    private void couper() {
        generation++;
        file.clear();
        AudioTrack t = haut;
        if (t != null) {
            try {
                t.pause();
                t.flush();
                t.play();
            } catch (Exception e) {
                Log.w(TAG, "direct : coupure " + e);
            }
        }
        finPrevue = 0;
        if (parle) {
            parle = false;
            reponseMs = 0;
            Bulle.lecture(0);
        }
    }

    private void fermerAudio() {
        try { if (micro != null) { micro.stop(); } } catch (Exception ignore) { }
        try { if (micro != null) micro.release(); } catch (Exception ignore) { }
        micro = null;
        try { if (aec != null) aec.release(); } catch (Exception ignore) { }
        aec = null;
        try { if (ns != null) ns.release(); } catch (Exception ignore) { }
        ns = null;
        try { if (haut != null) { haut.pause(); haut.flush(); haut.release(); } } catch (Exception ignore) { }
        haut = null;
        AudioManager am = getSystemService(AudioManager.class);
        if (am != null) {
            try {
                if (Build.VERSION.SDK_INT >= 31) am.clearCommunicationDevice();
                else am.setSpeakerphoneOn(false);
                am.setMode(modeAvant);
            } catch (Exception ignore) { }
            try { if (focus != null) am.abandonAudioFocusRequest(focus); } catch (Exception ignore) { }
        }
        focus = null;
    }

    private void fermerSocket() {
        synchronized (verrouSortie) { sortie = null; }
        Socket s = sock;
        sock = null;
        if (s != null) try { s.close(); } catch (Exception ignore) { }
    }

    // ----------------------------------------------------------------- arret

    /** Arret propre, depuis n'importe quel fil. Le message s'affiche une fois. */
    private void arreter(final String message) {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            h.post(new Runnable() { public void run() { arreter(message); } });
            return;
        }
        if (!actif && !vivant) { finir(); return; }
        Log.i(TAG, "direct : arret" + (message == null ? "" : " (" + message + ")"));
        vivant = false;
        pret = false;
        actif = false;
        // Une trame close polie si le lien vit encore, puis on coupe.
        final Socket s = sock;
        new Thread(new Runnable() {
            public void run() {
                try { envoyer(0x8, new byte[]{0x03, (byte) 0xE8}); } catch (Exception ignore) { }
                fermerSocket();
                if (s != null) try { s.close(); } catch (Exception ignore) { }
            }
        }, "direct-close").start();
        if (filHaut != null) filHaut.interrupt();
        file.clear();
        fermerAudio();
        Bulle.lecture(0);
        Bulle.direct(null);
        if (message != null) dire(message);
        finir();
    }

    private void finir() {
        try { stopForeground(true); } catch (Exception ignore) { }
        stopSelf();
    }

    private void dire(final String m) {
        h.post(new Runnable() {
            public void run() { Toast.makeText(Direct.this, m, Toast.LENGTH_SHORT).show(); }
        });
    }

    private boolean premierPlan() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) {
            nm.createNotificationChannel(new NotificationChannel(CANAL,
                    Langue.t(this, R.string.direct_canal), NotificationManager.IMPORTANCE_MIN));
        }
        Notification n = new Notification.Builder(this, CANAL)
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setContentTitle(Langue.t(this, R.string.direct_titre))
                .setColor(Charte.VERT)
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= 29) {
            try {
                startForeground(NOTIF, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
                        | ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
            } catch (RuntimeException e) {
                // Micro refuse (lance hors premier plan) : on passe quand meme au
                // premier plan, sinon Android tue l'appli, puis on s'arrete.
                Log.w(TAG, "direct : micro refuse au premier plan " + e);
                try {
                    startForeground(NOTIF, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
                } catch (RuntimeException ignore) { }
                return false;
            }
        } else {
            startForeground(NOTIF, n);
        }
        return true;
    }
}
