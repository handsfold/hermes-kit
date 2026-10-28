package com.poste.pixelgarde;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Lecture a voix haute d'un texte, phrase par phrase, avec le moteur vocal du
 * telephone (Speech Services by Google). Ne a la demande de USER du 2026-09-24 :
 * la premiere version passait par edge-tts sur hote-1 (synthese du texte
 * entier, push d'un mp3, lecture) et faisait attendre 5 a 20 s ; elle ne se
 * coupait qu'en reappuyant sur la pastille. Ici la voix part en moins d'une
 * seconde, et une notification media (MediaSession) porte les commandes :
 * lecture/pause, phrase precedente, phrase suivante, curseur, arret.
 *
 * Deux entrees :
 *   LIRE      --es fichier <nom dans files/> [--es titre X] [--ef debit 1.75]
 *   LIRETEXTE --es texte "<texte>"  (depuis l'activite Presse, sans detour)
 * Une nouvelle demande pendant une lecture la REMPLACE.
 *
 * Le curseur de la notification compte des phrases, pas des secondes : la
 * "duree" vaut N phrases x 1000 ms, la position vaut l'index x 1000. Le
 * systeme dessine sa barre, et onSeekTo() rend l'index. Aucun autre moyen,
 * sans fichier audio, de laisser USER choisir ou reprendre.
 */
public class Lecteur extends Service {

    public static final String LIRE = "com.poste.pixel.LIRE";
    public static final String LIRE_TEXTE = "com.poste.pixel.LIRETEXTE";
    static final String PAUSE = "com.poste.pixel.LECT_PAUSE";
    static final String JOUER = "com.poste.pixel.LECT_JOUER";
    static final String PREC = "com.poste.pixel.LECT_PREC";
    static final String SUIV = "com.poste.pixel.LECT_SUIV";
    static final String STOP = "com.poste.pixel.LECT_STOP";
    /** Pause ou reprise, comme le toucher de la bulle sur un rapport. */
    static final String BASCULE = "com.poste.pixel.LECT_BASCULE";

    // Etat lu par la bulle, meme contrat que Voix.parle() et Voix.enPauseVue() :
    // USER, 2026-10-02 : « des qu'il y a de la lecture, ca doit etre uniformise ».
    private static volatile boolean actif = false;
    private static volatile boolean pauseVue = false;
    private static volatile long finLecture = 0;
    static boolean actif() { return actif; }
    static boolean enPauseVue() { return actif && pauseVue; }
    /** Un toucher dans les 3 s apres la fin vise la pause, pas le menu. */
    static boolean vientDeLire() {
        return finLecture != 0 && android.os.SystemClock.elapsedRealtime() - finLecture < 3000;
    }

    private static final String CANAL = "lecture";
    private static final int NOTIF = 7;
    /** Longueur maximale d'une phrase parlee : au-dela, on coupe a la virgule. */
    private static final int PHRASE_MAX = 220;
    /** Vitesse moyenne de la voix a 1.0, pour l'anneau de la pastille. */
    private static final double CAR_PAR_S = 15.0;

    private TextToSpeech tts;
    private boolean pret;
    private MediaSession session;
    private AudioManager am;
    private AudioFocusRequest focus;
    private final Handler h = new Handler(Looper.getMainLooper());

    private List<String> phrases = new ArrayList<>();
    private int index;
    private boolean enLecture;
    private String titre = null;

    private String titre() {
        return titre != null ? titre : Langue.t(this, R.string.lecteur_titre);
    }
    private float debit = 1.75f;
    /** Texte arrive avant que le moteur soit pret : on le garde au chaud. */
    private Runnable enAttente;
    /**
     * Numero de la file en cours. tts.stop() fait remonter onDone/onError des
     * phrases abandonnees APRES que la file suivante est partie : sans ce
     * numero, la fin de l'ancienne derniere phrase eteignait la nouvelle
     * lecture (vu le 24/09 en testant "precedent").
     */
    private int generation;

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public void onCreate() {
        super.onCreate();
        am = getSystemService(AudioManager.class);
        session = new MediaSession(this, "pixelgarde-lecture");
        session.setCallback(new MediaSession.Callback() {
            @Override public void onPlay() { jouer(); }
            @Override public void onPause() { pause(); }
            @Override public void onSkipToNext() { aller(index + 1); }
            @Override public void onSkipToPrevious() { aller(index - 1); }
            @Override public void onStop() { arreter(); }
            @Override public void onSeekTo(long pos) { aller((int) (pos / 1000)); }
            @Override public void onCustomAction(String action, Bundle extras) {
                if (STOP.equals(action)) arreter();
            }
        });
        tts = new TextToSpeech(this, new TextToSpeech.OnInitListener() {
            public void onInit(int status) {
                pret = status == TextToSpeech.SUCCESS;
                Log.i("pixelgarde", "lecteur : moteur " + (pret ? "pret" : "absent"));
                if (!pret) { arreter(); return; }
                tts.setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override public void onStart(final String id) {
                        h.post(new Runnable() { public void run() { debutPhrase(id); } });
                    }
                    @Override public void onDone(final String id) {
                        h.post(new Runnable() { public void run() { finPhrase(id); } });
                    }
                    @Override public void onError(String id) {
                        h.post(new Runnable() { public void run() { finPhrase(id); } });
                    }
                });
                if (enAttente != null) { Runnable r = enAttente; enAttente = null; r.run(); }
            }
        });
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        String a = intent == null ? null : intent.getAction();
        if (a == null) return START_NOT_STICKY;
        Log.i("pixelgarde", "lecteur : " + a.substring(a.lastIndexOf('.') + 1));
        // Le premier plan tout de suite : un service demarre par
        // start-foreground-service a 5 s pour s'y mettre, moteur pret ou non.
        premierPlan();
        switch (a) {
            case LIRE: {
                String nom = intent.getStringExtra("fichier");
                String t = intent.getStringExtra("titre");
                if (t != null) titre = t;
                debit = intent.getFloatExtra("debit", debit);
                charger(lireFichier(nom));
                break;
            }
            case LIRE_TEXTE: {
                String t = intent.getStringExtra("titre");
                if (t != null) titre = t;
                debit = intent.getFloatExtra("debit", debit);
                charger(intent.getStringExtra("texte"));
                break;
            }
            case PAUSE: pause(); break;
            case JOUER: jouer(); break;
            case BASCULE: if (enLecture) pause(); else jouer(); break;
            case PREC: aller(index - 1); break;
            case SUIV: aller(index + 1); break;
            case STOP: arreter(); break;
            default: break;
        }
        return START_NOT_STICKY;
    }

    private String lireFichier(String nom) {
        if (nom == null) return "";
        File f = new File(getExternalFilesDir(null), nom);
        try (FileInputStream in = new FileInputStream(f)) {
            byte[] b = new byte[(int) Math.min(f.length(), 200_000)];
            int n = in.read(b);
            return n <= 0 ? "" : new String(b, 0, n, "UTF-8");
        } catch (Throwable t) {
            Log.i("pixelgarde", "lecteur : fichier illisible " + nom + " : " + t);
            return "";
        }
    }

    /** Remplace le texte en cours et part de la premiere phrase. */
    private void charger(final String texte) {
        if (!pret) {
            enAttente = new Runnable() { public void run() { charger(texte); } };
            return;
        }
        tts.stop();
        phrases = decouper(texte == null ? "" : texte);
        if (phrases.isEmpty()) phrases.add(Langue.t(this, R.string.lecteur_rien, titre()));
        index = 0;
        Log.i("pixelgarde", "lecteur : " + phrases.size() + " phrases, debit " + debit);
        int total = 0;
        for (String p : phrases) total += p.length();
        Bulle.lecture((int) (total / (CAR_PAR_S * debit) * 1000));
        actif = true;
        // Une seule voix a la fois : un rapport en cours se met en pause.
        if (Voix.parle() && !Voix.enPauseVue()) {
            try { startService(new Intent(this, Voix.class).setAction(Voix.BASCULE)); }
            catch (Throwable ignore) { }
        }
        jouer();
    }

    /**
     * Coupe en phrases : fin de ligne, point, point d'interrogation ou
     * d'exclamation suivis d'un blanc. Les miettes (moins de 25 caracteres)
     * se collent a la suivante pour que "precedent" garde un sens ; une phrase
     * trop longue se coupe a la virgule la plus proche de PHRASE_MAX.
     */
    static List<String> decouper(String texte) {
        List<String> out = new ArrayList<>();
        String[] brut = texte.replace("\r", "").split("(?<=[.!?…])\\s+|\\n+");
        StringBuilder cour = new StringBuilder();
        for (String s : brut) {
            s = s.trim();
            if (s.isEmpty()) continue;
            if (cour.length() > 0) cour.append(' ');
            cour.append(s);
            if (cour.length() < 25) continue;
            vider(out, cour.toString());
            cour.setLength(0);
        }
        if (cour.length() > 0) vider(out, cour.toString());
        return out;
    }

    private static void vider(List<String> out, String s) {
        while (s.length() > PHRASE_MAX) {
            int c = s.lastIndexOf(", ", PHRASE_MAX);
            if (c < 40) c = s.lastIndexOf(' ', PHRASE_MAX);
            if (c < 40) c = PHRASE_MAX;
            out.add(s.substring(0, c).trim());
            s = s.substring(c).trim();
            if (s.startsWith(",")) s = s.substring(1).trim();
        }
        if (!s.isEmpty()) out.add(s);
    }

    private void jouer() {
        if (!pret || phrases.isEmpty()) return;
        if (index < 0) index = 0;
        if (index >= phrases.size()) index = 0;
        tts.stop();
        tts.setSpeechRate(debit);
        prendreFocus();
        enLecture = true;
        pauseVue = false;
        Bulle.lectureA(msAvant(index));
        Bulle.lecturePause(false);
        generation++;
        for (int i = index; i < phrases.size(); i++) {
            String p = phrases.get(i);
            tts.setLanguage(langue(p));
            tts.speak(p, TextToSpeech.QUEUE_ADD, null, "g" + generation + "p" + i);
        }
        etat();
    }

    /** Thai si la phrase porte un caractere thai, sinon la langue de l'appli. */
    private Locale langue(String p) {
        for (int i = 0; i < p.length(); i++) {
            char c = p.charAt(i);
            if (c >= 0x0E00 && c <= 0x0E7F) return new Locale("th", "TH");
        }
        return Langue.locale(this);
    }

    private void pause() {
        if (!enLecture) return;
        tts.stop();
        enLecture = false;
        pauseVue = true;
        Bulle.lecturePause(true);
        etat();
    }

    /** Position estimee, en ms, du debut de la phrase i : l'anneau s'y cale. */
    private int msAvant(int i) {
        int c = 0;
        for (int k = 0; k < i && k < phrases.size(); k++) c += phrases.get(k).length();
        return (int) (c / (CAR_PAR_S * debit) * 1000);
    }

    private void aller(int i) {
        if (phrases.isEmpty()) return;
        if (i < 0) i = 0;
        if (i >= phrases.size()) { arreter(); return; }
        index = i;
        jouer();
    }

    /** L'index porte par un identifiant "g<gen>p<i>", ou -1 s'il est perime. */
    private int indexDe(String id) {
        try {
            int p = id.indexOf('p');
            if (Integer.parseInt(id.substring(1, p)) != generation) return -1;
            return Integer.parseInt(id.substring(p + 1));
        } catch (RuntimeException e) { return -1; }
    }

    private void debutPhrase(String id) {
        int i = indexDe(id);
        if (i < 0) return;
        index = i;
        etat();
    }

    private void finPhrase(String id) {
        int i = indexDe(id);
        if (i < 0) return;
        if (enLecture && i >= phrases.size() - 1) {
            Log.i("pixelgarde", "lecteur : fin de lecture");
            arreter();
        }
    }

    private void arreter() {
        Log.i("pixelgarde", "lecteur : arret a la phrase " + (index + 1) + "/" + phrases.size());
        enLecture = false;
        if (actif) finLecture = android.os.SystemClock.elapsedRealtime();
        actif = false;
        pauseVue = false;
        generation++;
        if (tts != null) tts.stop();
        Bulle.lecturePause(false);
        Bulle.lecture(0);
        lacherFocus();
        session.setActive(false);
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    private void prendreFocus() {
        if (am == null || focus != null) return;
        focus = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
                .setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .build();
        am.requestAudioFocus(focus);
    }

    private void lacherFocus() {
        if (am != null && focus != null) am.abandonAudioFocusRequest(focus);
        focus = null;
    }

    /** Session et notification refletent l'index et l'etat, a chaque phrase. */
    private void etat() {
        int n = Math.max(1, phrases.size());
        String courante = phrases.isEmpty() ? "" : phrases.get(Math.min(index, n - 1));
        session.setMetadata(new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, titre() + " " + (index + 1) + "/" + n)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, courante)
                .putLong(MediaMetadata.METADATA_KEY_DURATION, n * 1000L)
                .build());
        long actions = PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
                | PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_STOP
                | PlaybackState.ACTION_SKIP_TO_NEXT | PlaybackState.ACTION_SKIP_TO_PREVIOUS
                | PlaybackState.ACTION_SEEK_TO;
        session.setPlaybackState(new PlaybackState.Builder()
                .setActions(actions)
                .addCustomAction(new PlaybackState.CustomAction.Builder(
                        STOP, Langue.t(this, R.string.lecteur_arreter), R.drawable.arreter).build())
                .setState(enLecture ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED,
                        index * 1000L, 0f)
                .build());
        session.setActive(true);
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) nm.notify(NOTIF, notification(courante, n));
    }

    private Notification notification(String courante, int n) {
        Notification.Builder b = new Notification.Builder(this, CANAL)
                .setSmallIcon(android.R.drawable.ic_lock_silent_mode_off)
                .setColor(Charte.VERT)
                .setContentTitle(titre() + " " + (index + 1) + "/" + n)
                .setContentText(courante)
                .setOnlyAlertOnce(true)
                .setOngoing(enLecture)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setDeleteIntent(pi(STOP, 5))
                .setStyle(new Notification.MediaStyle()
                        .setMediaSession(session.getSessionToken())
                        .setShowActionsInCompactView(0, 1, 2));
        // Sur Android 13 et plus, les boutons viennent du PlaybackState ; ces
        // actions ne servent qu'aux versions anterieures et a quelques
        // surcouches. Elles ne coutent rien.
        b.addAction(action(android.R.drawable.ic_media_previous, Langue.t(this, R.string.lecteur_precedent), PREC, 1));
        if (enLecture) b.addAction(action(android.R.drawable.ic_media_pause, Langue.t(this, R.string.lecteur_pause), PAUSE, 2));
        else b.addAction(action(android.R.drawable.ic_media_play, Langue.t(this, R.string.lecteur_lire), JOUER, 2));
        b.addAction(action(android.R.drawable.ic_media_next, Langue.t(this, R.string.lecteur_suivant), SUIV, 3));
        b.addAction(action(android.R.drawable.ic_delete, Langue.t(this, R.string.lecteur_arreter), STOP, 4));
        return b.build();
    }

    private Notification.Action action(int icone, String libelle, String act, int req) {
        return new Notification.Action.Builder(
                android.graphics.drawable.Icon.createWithResource(this, icone),
                libelle, pi(act, req)).build();
    }

    private PendingIntent pi(String act, int req) {
        Intent i = new Intent(this, Lecteur.class).setAction(act);
        return PendingIntent.getForegroundService(this, req, i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private void premierPlan() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) {
            NotificationChannel c = new NotificationChannel(
                    CANAL, Langue.t(this, R.string.lecteur_canal), NotificationManager.IMPORTANCE_LOW);
            c.setSound(null, null);
            nm.createNotificationChannel(c);
        }
        Notification n = notification("", Math.max(1, phrases.size()));
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIF, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        } else {
            startForeground(NOTIF, n);
        }
    }

    @Override public void onDestroy() {
        enLecture = false;
        actif = false;
        pauseVue = false;
        if (tts != null) { tts.stop(); tts.shutdown(); }
        lacherFocus();
        if (session != null) session.release();
        super.onDestroy();
    }
}
