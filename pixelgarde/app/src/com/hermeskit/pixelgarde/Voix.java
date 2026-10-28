package com.poste.pixelgarde;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioRecordingConfiguration;
import android.media.MediaMetadata;
import android.media.MediaPlayer;
import android.media.MediaRecorder;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.util.Log;
import android.widget.Toast;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.util.ArrayDeque;

/**
 * Le mode conversation vocale de la pastille.
 *
 * Pourquoi un service et pas un enregistrement lance depuis la vue d'overlay :
 * depuis Android 11, le micro n'est accessible qu'« en cours d'utilisation ».
 * Un AudioRecord ouvert par un processus en arriere-plan ne leve pas
 * d'exception, il rend du SILENCE. Le defaut serait donc invisible. Seul un
 * service de premier plan de type `microphone` garantit un vrai flux.
 *
 * Pourquoi aucun reseau : l'application n'a meme pas la permission INTERNET, et
 * c'est deliberé. Tout passe par le tuyau adb deja eprouve, exactement comme un
 * appui sur un bouton du menu : on depose un fichier, on ecrit une ligne dans
 * logcat, le garde de hote-1 fait le reste. Ajouter INTERNET ouvrirait une
 * seconde voie a maintenir, avec ses adresses, ses pannes et ses secrets.
 *
 * Le cycle d'un tour :
 *   ECOUTE  -> Envoyer (bouton, toucher, relacher) -> tour-<millis>.wav depose, action `voixtour`
 *   TRAVAILLE -> hote-1 transcrit, fait travailler le QG, synthetise, repousse
 *   PARLE   -> lecture de la reponse, puis PRET : le micro attend un appui
 * Le micro ne se rouvre plus tout seul apres la reponse (USER n'a pas forcement
 * envie de reparler tout de suite) : un appui sur le bouton, en etat PRET,
 * reprend l'ecoute SANS fermer la conversation. Le meme appui, en ECOUTE ou
 * en TRAVAILLE, annule le tour en cours (voir `couper`).
 */
public class Voix extends Service {

    public static final String DEMARRER = "com.poste.pixel.VOIX";
    public static final String REPONSE = "com.poste.pixel.VOIXREP";
    public static final String ARRETER = "com.poste.pixel.VOIXFIN";
    /**
     * Lire un fichier a voix haute SANS ouvrir de conversation.
     *
     * Le bouton « Ou j'en suis » veut une reponse parlee, pas un dialogue :
     * ouvrir la boucle d'ecoute apres l'avoir jouee laisserait le micro armé
     * alors que USER a range son telephone. REPONSE, lui, rend toujours la
     * parole, parce qu'il sert au milieu d'un echange.
     */
    public static final String DIRE = "com.poste.pixel.VOIXDIRE";
    /**
     * Faire patienter : une phrase courte jouee PENDANT que le QG travaille
     * (« Compris, je regarde EntrepriseA »). Elle ne touche a rien d'autre : ni
     * l'etat pret, ni le micro. La vraie reponse arrive ensuite par REPONSE,
     * qui coupe l'accuse s'il joue encore. Sans cette action, l'accuse
     * passerait par jouer(), qui met la pastille sur « pret » alors que le QG
     * n'a pas fini : un bouton qui ment.
     */
    public static final String ATTENTE = "com.poste.pixel.VOIXATTENTE";

    /**
     * Le compte a rebours d'envoi, demande par USER le 2026-10-01.
     *
     * Le standard du QG propose « J'envoie a X : ... ». Avant, il fallait
     * repondre « oui » a voix haute. Desormais la demande part seule a la fin
     * d'un compte de 3 s affiche sur la bulle. Toucher la bulle annule, pendant
     * la lecture comme pendant le compte. Un geste et non un mot : « stop » se
     * perdait a la transcription.
     *
     * Le compte part a la FIN de la lecture, pas au debut (USER, 2026-10-01 :
     * l'envoi s'annoncait alors que la voix expliquait encore ce qu'elle
     * allait faire). Pendant la lecture, l'envoi est seulement en attente.
     *
     * Le minuteur vit ICI, sur le telephone, et pas sur hote-1 : c'est le
     * telephone qui affiche le compte, il doit aussi etre celui qui tranche.
     * Deux horloges finiraient par se contredire.
     */
    public static final String ANNULER_ENVOI = "com.poste.pixel.ENVOIANNULE";

    /**
     * Faire taire la voix, quelle qu'elle soit : reponse, accuse ou rapport.
     *
     * Demande par USER le 2026-10-02 : voir la lecture dans la barre de
     * notification avec un bouton stop, ou couper en touchant la bulle
     * pendant qu'elle parle. Les deux chemins arrivent ici. Seul le son
     * s'arrete : une conversation ouverte le reste, la parole revient a USER.
     */
    public static final String TAIRE = "com.poste.pixel.VOIXTAIRE";
    /**
     * Pause ou reprise de la voix en cours. USER, 2026-10-02 : « ca l'arrete
     * mais je peux pas la relancer si je rappuie dessus ». Le toucher de la
     * bulle et le bouton pause du lecteur basculent ; seul `Arreter` coupe.
     */
    public static final String BASCULE = "com.poste.pixel.VOIXPAUSE";
    /**
     * Reecouter la derniere voix jouee. USER, 2026-10-02 : « pouvoir reecouter
     * un rapport meme apres l'avoir deja ecoute une fois ». Une voix jouee
     * n'est plus effacee : elle se range dans voix/lus, les 10 dernieres
     * restent. Lance par le garde (bouton `Reecouter` du menu de la bulle).
     */
    public static final String REJOUER = "com.poste.pixel.VOIXREJOUER";
    private static final int VOIX_GARDEES = 10;
    /** Le fichier en cours, range dans voix/lus quand le lecteur se libere. */
    private File fichierLu;
    private volatile boolean enPause = false;
    private String titreLecture = "";
    /** Une voix en pause plus de 10 min est oubliee : le service s'eteint. */
    private static final int PAUSE_MAX_MS = 10 * 60 * 1000;
    private final Runnable pausePerimee = new Runnable() {
        public void run() { if (enPause) taire(); }
    };
    private static final int RIEN = 0, REPONSE_LUE = 1, ACCUSE = 2, SEUL = 3;
    /** Ce que joue le lecteur en ce moment : decide ce que « stop » defait. */
    private volatile int sorte = RIEN;
    private static volatile boolean parle = false;
    /** Lu par la bulle : vrai pendant la voix ET pendant sa pause. */
    static boolean parle() { return parle; }
    /**
     * Le micro de reponse ne s'ouvre qu'une fois la voix FINIE. USER,
     * 2026-10-02 : en tapotant la bulle pour la pause, un toucher tombait
     * juste apres la fin (ou pendant l'attente d'une dictee) et ouvrait le
     * micro. La bulle lit ces trois signaux avant d'oser ouvrir l'ecoute.
     */
    private static volatile boolean retenue = false;
    static boolean occupe() { return parle || retenue; }
    private static volatile boolean pauseVue = false;
    static boolean enPauseVue() { return pauseVue; }
    private static final int GRACE_MS = 3000;
    private static volatile long finParole = 0;
    static boolean vientDeParler() {
        return finParole != 0 && SystemClock.elapsedRealtime() - finParole < GRACE_MS;
    }
    /** Avancer ou reculer d'un rapport, comme une piste de musique. */
    public static final String PRECEDENT = "com.poste.pixel.VOIXPREC";
    public static final String SUIVANT = "com.poste.pixel.VOIXSUIV";
    /** Envoyer la phrase en cours : le tour ne part plus au silence. */
    public static final String ENVOYER = "com.poste.pixel.VOIXENVOI";
    /**
     * Un bouton « Oui » ou « Detail » pose au-dessus de la bulle apres un
     * rapport ou d'une reponse (Bulle.choix). Extra "mot" : voir idChoixValide(). Le mot part au
     * standard comme si USER l'avait dit, sans micro ni transcription.
     */
    public static final String CHOISIR = "com.poste.pixel.VOIXCHOIX";
    /** Les boutons a montrer a la fin de la reponse en cours (extra "choix"). */
    private String choixApres;
    /** Ce que ces boutons visent (extra "pour", sinon l'id du rapport). */
    private String pourApres;
    /**
     * Le rapport qui joue (extra "rapport"). Sa fin part vers hote-1 :
     * rapportfini:<id> si le son va au bout, rapportcoupe:<id> s'il est
     * interrompu. C'est la fin du son qui marque le rapport lu (2026-10-06 :
     * marque lu au depart, un rapport coupe etait perdu).
     */
    private String rapportEnCours;
    /*
     * Lecture anticipee (2.18, 2026-10-03). hote-1 pousse la 1re phrase de la
     * reponse des qu'elle est synthetisee (extra "debut", fichier deb-<nom>),
     * puis la reponse complete <nom>, qui commence par les memes octets. La
     * bulle joue la 1re phrase, puis reprend la complete a l'endroit exact ou
     * la phrase s'est arretee : USER entend une seule voix, sans couture.
     */
    /** Nom de la reponse complete attendue apres la 1re phrase, sinon null. */
    private String suiteDe;
    /** La complete est arrivee pendant la 1re phrase : elle attend sa fin. */
    private String suiteNom;
    private boolean suiteCompte;
    private String suiteChoix;
    private String suitePour;
    /** La 1re phrase est finie, la complete n'est pas encore la. */
    private boolean attenteSuite;
    /** Ou reprendre dans la complete : la duree de la 1re phrase. */
    private int posSuite;
    /** USER a coupe la 1re phrase : la complete se range sans se jouer. */
    private boolean debutCoupe;
    /** Instant ou USER a fini de parler, pour mesurer le delai jusqu'a la 1re voix. */
    private long tourDepuis;
    /** Filet : la complete n'arrive jamais (synthese ratee), la parole revient. */
    private final Runnable suitePerdue = new Runnable() { public void run() {
        if (!attenteSuite) return;
        Log.i("pixelgarde", "voix : suite jamais arrivee");
        attenteSuite = false;
        suiteDe = null;
        if (vivant) { pret = true; Bulle.commande(Voix.this, "voixpret"); }
    }};
    /** Idem pour une lecture isolee (VOIXDIRE, hors conversation). */
    private String choixDire;
    private String pourDire;

    /** Dit a hote-1 ce qu'est devenu le rapport en cours, puis l'oublie. */
    private void rapportFin(String quoi) {
        String r = rapportEnCours;
        rapportEnCours = null;
        if (r != null) Bulle.commande(this, quoi + ":" + r);
    }

    /** Un nouveau son prend la place : le rapport qui jouait est coupe. */
    private void prendreRapport(String id) {
        if (rapportEnCours != null && !rapportEnCours.equals(id)) rapportFin("rapportcoupe");
        rapportEnCours = id;
    }

    /**
     * Lecture automatique (extra "auto") alors qu'une voix parle deja, que USER
     * dicte ou qu'un envoi attend : rien ne coupe, le rapport est rendu a hote-1
     * (rapportrefuse), qui le garde en tete de file.
     */
    private boolean voixPrise() {
        return lecteur != null || enEcoute || envoiArme || attenteSuite
                || suiteDe != null || suiteNom != null;
    }

    /**
     * Les identifiants qu'un bouton peut deposer : oui, non, detail (mots
     * fixes, apres un rapport) et b1 a b3 (reponses devinees par le standard,
     * dont hote-1 garde le libelle), suivis de « :<id> », ce que la bulle vise :
     * l'id du rapport, ou t<secondes> pour un tour. Rien d'autre ne part vers
     * cmd.txt.
     */
    static boolean idChoixValide(String id) {
        return id != null && id.matches("(oui|non|detail|b[1-3])(:[a-z0-9]{1,12})?");
    }

    /** Un rapport, par son nom de fichier : qg-pre-<id>.mp3 ou qg-<millis>.mp3. */
    private static boolean estRapport(String nom) {
        return nom != null && cleVoix(nom).startsWith("qg-");
    }

    /**
     * Le nom d'une voix sans dossier ni prefixe horaire. ranger() renomme
     * « qg-2163.mp3 » en « lus/1760100000000-qg-2163.mp3 » : sans ce retrait,
     * une relecture n'etait plus un rapport et finissait sans aucun bouton
     * (USER, 2026-10-10 : « les boutons de choix devraient reapparaitre »).
     */
    private static String cleVoix(String nom) {
        return nom.substring(nom.lastIndexOf('/') + 1).replaceFirst("^\\d+-", "");
    }

    /** La voix en cours de relecture (REJOUER), null sinon. */
    private File relu = null;

    /** Les boutons d'une voix, gardes pour qu'une relecture les rende. */
    private void garderChoix(String nom, String c, String pour) {
        if (nom == null || c == null) return;
        android.content.SharedPreferences sp = getSharedPreferences("choixlus", MODE_PRIVATE);
        android.content.SharedPreferences.Editor e = sp.edit();
        // Les 10 voix rangees suffisent : au-dela, on repart de zero.
        if (sp.getAll().size() > 30) e.clear();
        e.putString(cleVoix(nom), c + "\u0001" + (pour == null ? "" : pour)).apply();
    }

    /** {boutons, pour} d'une voix relue : ceux de sa 1re lecture, sinon Detail. */
    private String[] choixRelu(String nom) {
        String v = getSharedPreferences("choixlus", MODE_PRIVATE).getString(cleVoix(nom), null);
        if (v != null) {
            int i = v.indexOf('\u0001');
            String pour = i < 0 ? "" : v.substring(i + 1);
            return new String[] { i < 0 ? v : v.substring(0, i), pour.isEmpty() ? null : pour };
        }
        if (!estRapport(nom)) return new String[] { null, null };
        java.util.regex.Matcher m = java.util.regex.Pattern.compile("^qg-(?:pre-)?(\\d+)").matcher(cleVoix(nom));
        return new String[] { "detail:" + Langue.t(this, R.string.voix_detail), m.find() ? m.group(1) : null };
    }
    private static final String CANAL_LECTURE = "voixlecture";
    private MediaSession session;
    // 3 s : a 5 s, USER trouvait l attente trop longue (2026-10-02).
    private static final int MARGE_ENVOI_MS = 3000;
    private static volatile boolean envoiArme = false;
    /** Le compte visible court (lancerCompte) : la fin d'une voix ne le relance pas. */
    private volatile boolean compteCourt = false;
    /**
     * Le compte court pendant qu'un AUTRE rapport se lit (USER, 2026-10-10 :
     * « le decompte coupe le rapport que je lis »). Le compte joue sans couper
     * la parole en cours ; Stop annule l'envoi, pas la lecture.
     */
    private volatile boolean envoiParallele = false;
    private final Handler hEnvoi = new Handler(Looper.getMainLooper());

    /**
     * La voix attend que USER ait fini de dicter. USER, 2026-10-02 : « quand je
     * suis en train de dicter, mon micro est allume, il me coupe avec l'audio
     * qui est joue ». Une autre appli tient le micro (dictee du clavier,
     * appel) : la lecture attend, ou se met en pause si elle avait commence.
     * 5 s de calme avant de parler : la dictee de Gboard coupe le micro entre
     * deux phrases, 3 a 4 s mesurees le 2026-10-02 (dumpsys audio).
     */
    private static final int MICRO_CALME_MS = 5000;
    /** Un micro tenu moins longtemps ne met pas la voix en pause : le service
     *  Google (com.google.android.as) l'ouvre 0,4 s toutes les 6 s. */
    private static final int MICRO_TENU_MS = 2000;
    private long microPrisDepuis = 0;
    private static final int MICRO_GUET_MS = 500;
    /** Session de notre propre micro, a ne pas prendre pour une dictee. */
    private volatile int sessionMicro = -1;
    /** Lecture prete, retenue tant que le micro est pris ailleurs. */
    private Runnable departDiffere;
    private long microLibreDepuis = 0;
    /** Pause posee par la dictee, levee seule quand le micro se libere. */
    private boolean pauseMicro = false;
    /** Faux quand USER a relance a la main malgre la dictee : on le laisse. */
    private boolean respecterMicro = true;
    private final Runnable guetMicro = new Runnable() { public void run() { guetter(); } };
    private final Runnable partir = new Runnable() {
        public void run() {
            if (!envoiArme) return;
            envoiArme = false;
            compteCourt = false;
            envoiParallele = false;
            Bulle.compte(0);
            Bulle.commande(getApplicationContext(), "envoiconfirme");
            vibrer(40);
        }
    };

    /** Lu par la bulle : un appui court annule l'envoi au lieu de faire parler. */
    static boolean envoiArme() { return envoiArme; }

    private static final String CANAL = "voix";
    private static final int NOTIF = 4202;

    private static final int TAUX = 16000;           // ce que veut whisper
    // Le seuil de parole n'est plus une constante : un seuil fixe coupait USER
    // en pleine phrase des qu'il baissait la voix, et laissait tourner dans une
    // piece bruyante. Il se calcule maintenant sur le bruit reellement mesure.
    private static final int SEUIL_MIN = 420;        // plancher, piece silencieuse
    private static final double SEUIL_FACTEUR = 3.0; // au-dessus du bruit de fond
    // 1,5 s : a 1,2 s une respiration ou un « euh » faisaient partir le tour
    // avant la fin de la phrase (aout 2026). A 2 s, chaque tour payait une
    // demi-seconde d'attente pour rien (mesure du 2026-10-01). Un tour coupe
    // trop tot se rattrape : le bouton envoie, il ne jette pas.
    //
    // 2026-10-02 : le silence NE CLOT PLUS le tour. USER : « des fois je fais
    // des pauses », et un silence de 1,5 s envoyait sa phrase a moitie dite.
    // Le tour part desormais sur un geste : le bouton Envoyer, un toucher sur
    // la bulle, ou le relacher d'un appui long. Le silence ne sert plus qu'a
    // rattraper un oubli : une minute sans un mot, on envoie ce qui a ete dit.
    private static final int OUBLI_MS = 60000;       // pause oubliee : on envoie
    private static final int PREMIER_MOT_MS = 20000; // rien dit : on renonce
    private static final int TOUR_MAX_MS = 300000;   // garde-fou, 5 min
    // On garde en reserve ce qui precede la detection : sans cela, l'attaque du
    // premier mot est jetee, et whisper entend « ...jour » pour « bonjour ».
    private static final int PREROLL_MS = 600;

    /** Vrai des que le service tourne : le second appui coupe au lieu d'ouvrir. */
    private static volatile boolean actif = false;
    public static boolean actif() { return actif; }

    /**
     * Le micro ecoute, vu de la bulle : un toucher y vaut alors « envoyer ».
     * Statique parce que la bulle ne tient pas le service, elle lui parle par
     * intents ; il lui faut lire l'etat sans aller-retour.
     */
    private static volatile boolean ecouteVue = false;
    private static volatile long ecouteDepuis = 0;
    public static boolean ecoute() { return ecouteVue; }
    /** Instant d'ouverture du micro, 0 hors ecoute. */
    public static long ecouteDepuis() { return ecouteDepuis; }

    private volatile boolean vivant = false;
    /**
     * Vrai entre la fin d'une reponse jouee et la reprise de l'ecoute.
     * Le micro ne se rouvre plus tout seul : c'est un appui de USER sur le
     * meme bouton qui le fait passer de "pret" a "ecoute" a nouveau. Sans
     * ce drapeau, ce meme appui coupait la conversation au lieu de la
     * reprendre.
     */
    private volatile boolean pret = false;
    /**
     * Vrai tant que la boucle micro tourne. Sert a distinguer les deux
     * situations que le meme bouton recouvrait : pendant l'ECOUTE il y a une
     * phrase a envoyer, pendant le TRAVAIL il n'y a rien a sauver.
     */
    private volatile boolean enEcoute = false;
    /**
     * Demande de cloture immediate de la prise en cours. USER appuie parce que
     * la detection de silence n'a pas vu qu'il avait fini : sa phrase doit
     * PARTIR, pas etre jetee. Avant le 2026-08-27, cet appui annulait tout.
     */
    private volatile boolean clore = false;
    private Thread ecoute;
    private MediaPlayer lecteur;

    @Override public IBinder onBind(Intent i) { return null; }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();

        // L'arret d'urgence envoie ces 3 ordres par start-foreground-service,
        // que la voix parle ou non. Android exige alors startForeground() sous
        // quelques secondes, sinon il tue l'appli (plantage vu sur l'emulateur
        // le 2026-10-06, voix eteinte). Le service passe donc au premier plan,
        // obeit, puis s'eteint s'il n'a plus rien en cours.
        if (ARRETER.equals(action) || TAIRE.equals(action) || ANNULER_ENVOI.equals(action)) {
            premierPlan();
            if (ARRETER.equals(action)) couper();
            else if (TAIRE.equals(action)) taire();
            else annulerEnvoi();
            if (!actif && lecteur == null && !envoiArme && !enEcoute) {
                stopForeground(true);
                stopSelf();
            }
            return START_NOT_STICKY;
        }

        if (BASCULE.equals(action)) { basculer(); return START_NOT_STICKY; }

        if (PRECEDENT.equals(action)) { sauter(-1); return START_NOT_STICKY; }

        // Le bouton Envoyer : clot la prise en cours et l'envoie. Hors
        // ecoute il ne fait RIEN, contrairement a DEMARRER qui relancerait le
        // micro ou couperait une reponse : un double toucher ne casse rien.
        if (ENVOYER.equals(action)) {
            if (enEcoute) { clore = true; vibrer(15); }
            return START_NOT_STICKY;
        }

        if (SUIVANT.equals(action)) { sauter(1); return START_NOT_STICKY; }

        if (REJOUER.equals(action)) {
            File f = dernierLu();
            String nom = f == null ? null : "lus/" + f.getName();
            relu = f;
            if (nom == null) Toast.makeText(this, Langue.t(this, R.string.voix_rien_reecouter), Toast.LENGTH_SHORT).show();
            // En conversation, meme circuit qu'un rapport : la parole revient apres.
            if (actif) { if (nom != null) jouer(nom, false); return START_NOT_STICKY; }
            premierPlan();
            direSeul(nom);
            return START_NOT_STICKY;
        }

        if (REPONSE.equals(action)) {
            if (!actif) {
                // Reponse orpheline : la conversation est morte entre-temps
                // (appli reinstallee, process relance). Lance par
                // start-foreground-service, le service doit passer au premier
                // plan avant de s'eteindre, sinon Android tue l'appli
                // (plantage du 2026-10-01 19:26, juste apres une installation).
                premierPlan();
                stopForeground(true);
                stopSelf();
                return START_NOT_STICKY;
            }
            String nomRep = intent.getStringExtra("fichier");
            boolean compteRep = intent.getIntExtra("compte", 0) > 0;
            String rapRep = intent.getStringExtra("rapport");
            String pourRep = intent.getStringExtra("pour");
            if (pourRep == null) pourRep = rapRep;
            if (rapRep != null && intent.getBooleanExtra("auto", false) && voixPrise()) {
                Log.i("pixelgarde", "voix : rapport " + rapRep + " refuse, voix occupee");
                Bulle.commande(this, "rapportrefuse:" + rapRep);
                return START_NOT_STICKY;
            }
            if (intent.getBooleanExtra("debut", false)) {
                // 1re phrase seule : la complete suivra sous le nom "suite".
                hEnvoi.removeCallbacks(suitePerdue);
                suiteDe = intent.getStringExtra("suite");
                suiteNom = null; suiteChoix = null; suitePour = null; suiteCompte = false;
                attenteSuite = false; debutCoupe = false; posSuite = 0;
                jouerDebut(nomRep);
                return START_NOT_STICKY;
            }
            if (nomRep != null && nomRep.equals(suiteDe)) {
                suiteDe = null;
                String ch = intent.getStringExtra("choix");
                if (debutCoupe) {
                    // USER a fait taire la voix : rien ne repart, mais la reponse
                    // reste reecoutable.
                    debutCoupe = false;
                    ranger(new File(new File(getExternalFilesDir(null), "voix"), nomRep));
                    return START_NOT_STICKY;
                }
                if (attenteSuite) {
                    hEnvoi.removeCallbacks(suitePerdue);
                    attenteSuite = false;
                    choixApres = ch;
                    pourApres = pourRep;
                    jouer(nomRep, compteRep, posSuite);
                } else {
                    // La 1re phrase joue encore : la complete prendra le relais.
                    suiteNom = nomRep; suiteCompte = compteRep; suiteChoix = ch;
                    suitePour = pourRep;
                }
                return START_NOT_STICKY;
            }
            if (compteRep && lecteur != null && sorte == REPONSE_LUE && !envoiArme) {
                // Un rapport se lit deja : « J'envoie a X » ne le coupe pas.
                // Le compte court tout de suite sur la bulle, l'envoi part a
                // zero, Stop l'annule (USER, 2026-10-10).
                Log.i("pixelgarde", "voix : compte en parallele, lecture gardee");
                if (nomRep != null) {
                    ranger(new File(new File(getExternalFilesDir(null), "voix"), nomRep));
                }
                envoiParallele = true;
                armerEnvoi();
                lancerCompte(MARGE_ENVOI_MS);
                return START_NOT_STICKY;
            }
            choixApres = intent.getStringExtra("choix");
            pourApres = pourRep;
            prendreRapport(rapRep);
            jouer(nomRep, compteRep);
            return START_NOT_STICKY;
        }

        if (CHOISIR.equals(action)) {
            String mot = intent.getStringExtra("mot");
            if (!idChoixValide(mot)) return START_NOT_STICKY;
            if (!actif) {
                // Rapport lu hors conversation (bouton Lire, lecture auto) :
                // le bouton ouvre la conversation, micro ferme. La reponse du
                // standard arrivera par REPONSE, qui exige un service actif.
                premierPlan();
                actif = true;
                vivant = true;
            }
            pret = false;
            Log.i("pixelgarde", "voix : bouton " + mot);
            Bulle.commande(this, "voix" + mot);
            return START_NOT_STICKY;
        }

        if (ATTENTE.equals(action)) {
            if (!actif) {
                // Conversation coupee entre-temps. Lance par
                // start-foreground-service, le service DOIT passer au premier
                // plan avant de s'eteindre, sinon Android tue l'appli.
                premierPlan();
                stopForeground(true);
                stopSelf();
                return START_NOT_STICKY;
            }
            patienter(intent.getStringExtra("fichier"));
            return START_NOT_STICKY;
        }

        if (DIRE.equals(action)) {
            // L'avis a servi, quel que soit le chemin : un appui de USER dessus,
            // ou le garde qui reprend un differe. setAutoCancel ne couvre que
            // le premier, et un avis survivant ferait croire a un rapport de
            // plus en attente. C'est aussi ici que hote-1 apprend que la lecture
            // est partie, donc qu'il peut lacher son jeton.
            Avis.consommer(this, intent.getStringExtra("fichier"));
            // En pleine conversation, une lecture isolee n'a pas de sens : on
            // la fait passer par le circuit normal, qui rendra la parole apres.
            // Les boutons devines pour ce rapport (extra "choix", calcule a la
            // prefabrication de sa voix). Sans lui, Oui Non Detail.
            String ch = intent.getStringExtra("choix");
            String rapDire = intent.getStringExtra("rapport");
            if (rapDire != null && intent.getBooleanExtra("auto", false) && voixPrise()) {
                // Le service tourne deja au premier plan : rien a promettre.
                Log.i("pixelgarde", "voix : rapport " + rapDire + " refuse, voix occupee");
                Bulle.commande(this, "rapportrefuse:" + rapDire);
                return START_NOT_STICKY;
            }
            String pourD = intent.getStringExtra("pour");
            if (pourD == null) pourD = rapDire;
            prendreRapport(rapDire);
            if (actif) {
                choixApres = ch;
                pourApres = pourD;
                jouer(intent.getStringExtra("fichier"), false);
                return START_NOT_STICKY;
            }
            choixDire = ch;
            pourDire = pourD;
            premierPlan();
            direSeul(intent.getStringExtra("fichier"));
            return START_NOT_STICKY;
        }

        // Une conversation qui s'ouvre par une voix (bouton « Conseil » : la
        // premiere question). La voix joue d'abord, la parole revient apres,
        // comme apres une reponse du QG. Conversation deja ouverte : meme
        // circuit, la question remplace l'attente.
        String premiere = DEMARRER.equals(action) ? intent.getStringExtra("fichier") : null;
        if (premiere != null && actif) {
            pret = false;
            jouer(premiere, false);
            return START_NOT_STICKY;
        }

        if (actif) {
            if (pret) {
                // La reponse est finie, USER vient d'appuyer pour reprendre la
                // parole : meme bouton, meme conversation, on ne coupe rien.
                pret = false;
                Bulle.commande(this, "voixecoute");
                vibrer(15);
                ecouter();
            } else if (enEcoute) {
                // USER a fini de parler (le silence ne clot plus rien) :
                // son appui CLOT la prise et l'envoie. L'annuler serait lui
                // faire repeter sa phrase pour rien.
                clore = true;
                vibrer(15);
            } else {
                // En plein traitement : rien a envoyer, l'appui annule.
                couper();
            }
            return START_NOT_STICKY;
        }

        premierPlan();
        actif = true;
        vivant = true;
        pret = false;
        Bulle.commande(this, "voixdebut");
        vibrer(30);
        if (premiere != null) jouer(premiere, false); else ecouter();
        return START_NOT_STICKY;
    }

    // ------------------------------------------------------------- ecoute

    /**
     * Un tour d'ecoute, dans son propre fil.
     *
     * La detection de fin de parole est une simple energie RMS par tranche de
     * 20 ms. Un VAD statistique serait plus fin, mais il faudrait l'embarquer :
     * pour un telephone tenu a la main dans une piece calme, le seuil suffit, et
     * il se regle d'un chiffre.
     */
    private void ecouter() {
        // USER reprend la parole : les boutons du rapport n'ont plus lieu d'etre.
        Bulle.choix(null);
        ecoute = new Thread(new Runnable() { public void run() { boucle(); } });
        ecoute.start();
    }

    private void boucle() {
        int min = AudioRecord.getMinBufferSize(TAUX,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        if (min <= 0) { echec("taille de tampon refusee"); return; }
        int taille = Math.max(min, TAUX / 5 * 2);

        AudioRecord micro;
        try {
            micro = new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION,
                    TAUX, AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT, taille);
        } catch (Throwable t) { echec("micro refuse : " + t); return; }

        if (micro.getState() != AudioRecord.STATE_INITIALIZED) {
            micro.release(); echec("micro non initialise"); return;
        }

        ByteArrayOutputStream pcm = new ByteArrayOutputStream(TAUX * 2 * 10);
        byte[] tampon = new byte[640];               // 20 ms a 16 kHz, 16 bits
        ArrayDeque<byte[]> reserve = new ArrayDeque<byte[]>();
        int reserveMax = PREROLL_MS / 20;
        boolean parle = false;
        double bruit = -1;                           // niveau de fond mesure
        long debut = System.currentTimeMillis();
        long dernierSon = debut;

        enEcoute = true;
        clore = false;
        ecouteDepuis = debut;
        ecouteVue = true;
        try {
            micro.startRecording();
            sessionMicro = micro.getAudioSessionId();
            if (micro.getRecordingState() != AudioRecord.RECORDSTATE_RECORDING) {
                echec("le systeme refuse l'enregistrement"); return;
            }
            while (vivant) {
                int n = micro.read(tampon, 0, tampon.length);
                if (n <= 0) {
                    // ERROR_INVALID_OPERATION est ce que rend un micro vole par
                    // une autre application : ce n'est pas une panne, on sort.
                    echec("flux micro interrompu (" + n + ")"); return;
                }
                long maintenant = System.currentTimeMillis();
                int niveau = rms(tampon, n);
                // Le bruit de fond ne s'apprend QUE hors parole : l'apprendre
                // pendant une phrase ferait monter le seuil jusqu'a la voix
                // elle-meme, et le tour ne se terminerait jamais.
                if (!parle) {
                    bruit = bruit < 0 ? niveau : bruit * 0.92 + niveau * 0.08;
                }
                int seuil = (int) Math.max(SEUIL_MIN,
                        (bruit < 0 ? 0 : bruit) * SEUIL_FACTEUR);

                if (niveau > seuil) {
                    if (!parle) {
                        parle = true;
                        vibrer(15);
                        // L'attaque du premier mot, gardee en reserve.
                        for (byte[] r : reserve) pcm.write(r, 0, r.length);
                        reserve.clear();
                    }
                    dernierSon = maintenant;
                }
                if (parle) {
                    pcm.write(tampon, 0, n);
                } else {
                    byte[] copie = new byte[n];
                    System.arraycopy(tampon, 0, copie, 0, n);
                    reserve.addLast(copie);
                    if (reserve.size() > reserveMax) reserve.removeFirst();
                }

                if (!parle && maintenant - debut > PREMIER_MOT_MS) {
                    Log.i("pixelgarde", "voix : rien dit, sortie du mode");
                    couper(); return;
                }
                // Cloture demandee a la main : elle prime sur la detection.
                if (clore) break;
                if (parle && maintenant - dernierSon > OUBLI_MS) break;
                if (parle && maintenant - debut > TOUR_MAX_MS) break;
            }
        } catch (Throwable t) {
            echec("lecture micro : " + t); return;
        } finally {
            try { micro.stop(); } catch (Throwable ignore) { }
            micro.release();
            enEcoute = false;
            ecouteVue = false;
            ecouteDepuis = 0;
        }

        if (!vivant) return;
        byte[] son = pcm.toByteArray();
        if (son.length < TAUX) {                     // moins d'une demi-seconde
            if (clore) {
                // Appui de cloture sans rien avoir dit : relancer l'ecoute
                // rendrait le bouton inoperant. On sort.
                Log.i("pixelgarde", "voix : cloture sur tour vide, sortie");
                clore = false; couper(); return;
            }
            Log.i("pixelgarde", "voix : tour trop court, ignore");
            ecouter(); return;
        }
        clore = false;
        deposerTour(son);
    }

    /** Energie moyenne d'une tranche, en amplitude 16 bits signee. */
    private static int rms(byte[] b, int n) {
        long somme = 0;
        int ech = n / 2;
        for (int i = 0; i + 1 < n; i += 2) {
            int v = (short) ((b[i] & 0xff) | (b[i + 1] << 8));
            somme += (long) v * v;
        }
        return ech == 0 ? 0 : (int) Math.sqrt((double) somme / ech);
    }

    /**
     * Ecrit le tour en WAV et previent hote-1.
     *
     * WAV et pas un format compresse : whisper le lit tel quel, et l'encodage
     * couterait plus de temps sur le telephone que le transfert n'en gagne. Dix
     * secondes de parole pesent 320 ko, qui passent en adb sans qu'on les voie.
     */
    private void deposerTour(byte[] pcm) {
        try {
            File d = new File(getExternalFilesDir(null), "voix");
            if (!d.exists() && !d.mkdirs()) { echec("dossier voix impossible"); return; }
            // Les tours precedents sont ramasses par hote-1 ; ceux qui restent
            // sont des restes d'un lien coupe, et fausseraient le « plus recent ».
            File[] vieux = d.listFiles();
            if (vieux != null) for (File f : vieux) {
                if (f.getName().startsWith("tour-")) { if (!f.delete()) { /* laisse */ } }
            }
            File f = new File(d, "tour-" + System.currentTimeMillis() + ".wav");
            FileOutputStream o = new FileOutputStream(f);
            o.write(entete(pcm.length));
            o.write(pcm);
            o.close();
            // Remonte par le reseau AVANT l'appui voixtour, meme fil d'envoi.
            Relais.deposerFichier(this, f);
        } catch (Throwable t) { echec("ecriture du tour : " + t); return; }

        vibrer(25);
        tourDepuis = SystemClock.elapsedRealtime();
        // Un nouveau tour efface les restes du precedent (complete jamais venue).
        hEnvoi.removeCallbacks(suitePerdue);
        suiteDe = null; suiteNom = null; suiteChoix = null;
        attenteSuite = false; debutCoupe = false;
        Bulle.commande(this, "voixtour");
    }

    /** L'en-tete WAV canonique de 44 octets, PCM 16 bits mono. */
    private static byte[] entete(int taille) {
        int total = 36 + taille;
        int octetsSec = TAUX * 2;
        return new byte[]{
            'R','I','F','F',
            (byte) total, (byte) (total >> 8), (byte) (total >> 16), (byte) (total >> 24),
            'W','A','V','E','f','m','t',' ',
            16,0,0,0, 1,0, 1,0,
            (byte) TAUX, (byte) (TAUX >> 8), (byte) (TAUX >> 16), (byte) (TAUX >> 24),
            (byte) octetsSec, (byte) (octetsSec >> 8),
            (byte) (octetsSec >> 16), (byte) (octetsSec >> 24),
            2,0, 16,0,
            'd','a','t','a',
            (byte) taille, (byte) (taille >> 8), (byte) (taille >> 16), (byte) (taille >> 24)
        };
    }

    // ------------------------------------------------------------- reponse

    /** Joue la reponse poussee par hote-1, puis rend la parole a USER. */
    private void jouer(String nom, boolean compte) { jouer(nom, compte, 0); }

    private void jouer(String nom, boolean compte, final int depuis) {
        if (!actif) return;
        final String nomJoue = nom;
        if (nom == null) { ecouter(); return; }
        File f = new File(new File(getExternalFilesDir(null), "voix"), nom);
        if (!f.exists()) { echec("reponse absente : " + nom); return; }
        try {
            libererLecteur();
            lecteur = new MediaPlayer();
            fichierLu = f;
            lecteur.setAudioAttributes(ATTR_VOIX);
            lecteur.setDataSource(f.getAbsolutePath());
            lecteur.setOnCompletionListener(new MediaPlayer.OnCompletionListener() {
                public void onCompletion(MediaPlayer mp) {
                    libererLecteur();
                    // La voix a fini : le compte d'envoi part maintenant.
                    if (envoiArme && !compteCourt) lancerCompte(MARGE_ENVOI_MS);
                    // Sinon, apres un rapport ou un detail : les boutons.
                    String c = choixApres;
                    choixApres = null;
                    String pourC = pourApres;
                    pourApres = null;
                    rapportFin("rapportfini");
                    // Relecture : les boutons de la 1re lecture reviennent.
                    if (c == null && nomJoue.startsWith("lus/")) {
                        String[] g = choixRelu(nomJoue);
                        c = g[0];
                        if (pourC == null) pourC = g[1];
                    }
                    garderChoix(nomJoue, c, pourC);
                    // Sans boutons calcules, Detail seul : un Oui sans rien a valider
                    // trompe USER (2026-10-03, « rien a valider dans ce rapport »).
                    if (c == null && estRapport(nomJoue)) c = "detail:" + Langue.t(Voix.this, R.string.voix_detail);
                    if (!envoiArme && c != null) Bulle.choix(c, pourC);
                    // Le micro ne se rouvre plus tout seul : USER n'a pas
                    // forcement envie de repondre tout de suite. La
                    // conversation reste ouverte (vivant/actif inchanges),
                    // seul le micro attend un appui pour reprendre.
                    if (vivant) {
                        pret = true;
                        // Un envoi arme garde le tour : envoiconfirme ou
                        // envoiannule le rendra, pas la fin de la voix.
                        if (!envoiArme) Bulle.commande(Voix.this, "voixpret");
                    }
                }
            });
            lecteur.setOnErrorListener(new MediaPlayer.OnErrorListener() {
                public boolean onError(MediaPlayer mp, int quoi, int extra) {
                    libererLecteur();
                    rapportFin("rapportcoupe");
                    echec("lecture impossible (" + quoi + ")");
                    return true;
                }
            });
            lecteur.prepare();
            final MediaPlayer l = lecteur;
            quandMicroLibre(new Runnable() { public void run() {
                if (lecteur != l) return;
                try {
                    if (depuis > 0) l.seekTo(depuis);
                    prendreFocus();
                    l.start();
                } catch (Throwable t) { echec("lecture : " + t); return; }
                mesurer(nomJoue);
                // L'anneau de la pastille se vide pendant la lecture. La duree ne
                // se connait qu'apres prepare() : avant, getDuration rend -1.
                // Avec un envoi propose, l'envoi est mis en attente : un appui
                // l'annule deja, mais le compte ne partira qu'a la fin de la voix.
                int d = Math.max(0, l.getDuration() - depuis);
                if (compte) armerEnvoi();
                Bulle.lecture(d);
                enLecture(REPONSE_LUE, titreDe(fichierLu, Langue.t(Voix.this, R.string.voix_titre_reponse)), d);
            }});
        } catch (Throwable t) { echec("lecture : " + t); }
    }

    /**
     * Joue la 1re phrase. A sa fin : la complete si elle est la, sinon on
     * attend (25 s au plus). Pas de boutons, pas de compte, pas de micro :
     * c'est la complete qui les porte.
     */
    private void jouerDebut(String nom) {
        if (!actif || nom == null) return;
        final File f = new File(new File(getExternalFilesDir(null), "voix"), nom);
        if (!f.exists()) { Log.i("pixelgarde", "voix : 1re phrase absente " + nom); return; }
        try {
            libererLecteur();
            lecteur = new MediaPlayer();
            // Pas de fichierLu : la 1re phrase ne se range pas dans les
            // reecoutes, la complete la contient deja.
            lecteur.setAudioAttributes(ATTR_VOIX);
            lecteur.setDataSource(f.getAbsolutePath());
            lecteur.setOnCompletionListener(new MediaPlayer.OnCompletionListener() {
                public void onCompletion(MediaPlayer mp) {
                    int pos = mp.getDuration();
                    libererLecteur();
                    if (!f.delete()) { /* le menage l'emportera */ }
                    posSuite = Math.max(0, pos);
                    if (suiteNom != null) {
                        String n = suiteNom;
                        suiteNom = null;
                        choixApres = suiteChoix;
                        suiteChoix = null;
                        pourApres = suitePour;
                        suitePour = null;
                        jouer(n, suiteCompte, posSuite);
                    } else {
                        attenteSuite = true;
                        hEnvoi.postDelayed(suitePerdue, 25000);
                    }
                }
            });
            lecteur.setOnErrorListener(new MediaPlayer.OnErrorListener() {
                public boolean onError(MediaPlayer mp, int quoi, int extra) {
                    // 1re phrase illisible : la complete jouera du debut.
                    libererLecteur();
                    Log.i("pixelgarde", "voix : 1re phrase illisible (" + quoi + ")");
                    posSuite = 0;
                    attenteSuite = true;
                    hEnvoi.postDelayed(suitePerdue, 25000);
                    return true;
                }
            });
            lecteur.prepare();
            final MediaPlayer l = lecteur;
            quandMicroLibre(new Runnable() { public void run() {
                if (lecteur != l) return;
                prendreFocus();
                try { l.start(); } catch (Throwable t) { Log.i("pixelgarde", "voix : 1re phrase : " + t); return; }
                mesurer(f.getName());
                Bulle.lecture(l.getDuration());
                enLecture(REPONSE_LUE, Langue.t(Voix.this, R.string.voix_titre_reponse), l.getDuration());
            }});
        } catch (Throwable t) { Log.i("pixelgarde", "voix : 1re phrase : " + t); }
    }

    /**
     * Delai entre la fin de la parole de USER et la 1re voix qu'il entend,
     * mesure sur le telephone. Une ligne par tour dans voix/delais.log :
     * « <epoch ms> <delai ms> <fichier> ».
     */
    private void mesurer(String nom) {
        if (tourDepuis == 0) return;
        long ms = SystemClock.elapsedRealtime() - tourDepuis;
        tourDepuis = 0;
        Log.i("pixelgarde", "voix : delai 1re voix " + ms + " ms (" + nom + ")");
        try {
            java.io.FileWriter w = new java.io.FileWriter(
                new File(new File(getExternalFilesDir(null), "voix"), "delais.log"), true);
            w.write(System.currentTimeMillis() + " " + ms + " " + nom + "\n");
            w.close();
        } catch (Throwable ignore) { }
    }

    /** Envoi en attente pendant la lecture : annulable, sans minuteur. */
    private void armerEnvoi() {
        hEnvoi.removeCallbacks(partir);
        envoiArme = true;
    }

    /** Fin de la voix : le compte visible demarre, puis l'envoi part seul. */
    private void lancerCompte(int ms) {
        hEnvoi.removeCallbacks(partir);
        compteCourt = true;
        Bulle.compte(ms);
        hEnvoi.postDelayed(partir, ms);
        // Pas de Toast ici : la bulle affiche deja le compte. USER l'a retire le
        // 2026-10-01, « j'ai pas besoin de l'avoir cette notification ».
    }

    /**
     * Appui sur la bulle pendant le compte. La voix se tait aussitot : USER a
     * deja compris, l'ecouter finir sa phrase serait une punition. La
     * conversation reste ouverte, la parole revient a USER.
     */
    private void annulerEnvoi() {
        if (!envoiArme) return;
        // Compte deja lance : la voix d'envoi est finie, toute voix qui joue est une autre.
        boolean parallele = envoiParallele || (compteCourt && lecteur != null);
        envoiArme = false;
        compteCourt = false;
        envoiParallele = false;
        hEnvoi.removeCallbacks(partir);
        Bulle.compte(0);
        Bulle.commande(getApplicationContext(), "envoiannuler");
        vibrer(30);
        if (parallele) {
            // Le rapport en cours n'est pas la voix de l'envoi : il continue.
            // Sa fin rendra la parole (boutons, voixpret). Un 2e appui le taira.
            Toast.makeText(this, Langue.t(this, R.string.voix_envoi_annule), Toast.LENGTH_SHORT).show();
            return;
        }
        libererLecteur();
        if (vivant) {
            pret = true;
            Bulle.commande(this, "voixpret");
        }
        Toast.makeText(this, Langue.t(this, R.string.voix_envoi_annule), Toast.LENGTH_SHORT).show();
    }

    /** Fin de conversation pendant le compte : rien ne part, sans bruit. */
    private void desarmerEnvoi() {
        if (!envoiArme) return;
        envoiArme = false;
        compteCourt = false;
        envoiParallele = false;
        hEnvoi.removeCallbacks(partir);
        Bulle.compte(0);
        Bulle.commande(getApplicationContext(), "envoiannuler");
    }

    /** Joue l'accuse d'attente. Aucun changement d'etat, ni avant ni apres. */
    private void patienter(String nom) {
        // Conversation fermee, ou deja une lecture en cours (la vraie reponse
        // est arrivee la premiere) : l'accuse n'a plus rien a dire.
        if (!actif || pret || enEcoute || lecteur != null || nom == null
            || attenteSuite || suiteDe != null) return;
        File f = new File(new File(getExternalFilesDir(null), "voix"), nom);
        if (!f.exists()) return;
        // USER dicte : un accuse ne vaut pas de le couper, il se tait.
        if (microAilleurs()) return;
        try {
            lecteur = new MediaPlayer();
            lecteur.setAudioAttributes(ATTR_VOIX);
            lecteur.setDataSource(f.getAbsolutePath());
            lecteur.setOnCompletionListener(new MediaPlayer.OnCompletionListener() {
                public void onCompletion(MediaPlayer mp) {
                    libererLecteur();
                    if (!f.delete()) { /* le prochain menage l'emportera */ }
                }
            });
            lecteur.setOnErrorListener(new MediaPlayer.OnErrorListener() {
                public boolean onError(MediaPlayer mp, int quoi, int extra) {
                    // Un accuse rate ne vaut pas de couper la conversation.
                    libererLecteur();
                    Log.i("pixelgarde", "voix : accuse illisible (" + quoi + ")");
                    return true;
                }
            });
            lecteur.prepare();
            prendreFocus();
            lecteur.start();
            mesurer(nom);
            enLecture(ACCUSE, Langue.t(this, R.string.voix_qg_patiente), lecteur.getDuration());
        } catch (Throwable t) {
            libererLecteur();
            Log.i("pixelgarde", "voix : accuse : " + t);
        }
    }

    /** Lit un fichier, puis s'eteint. Aucune ecoute avant, aucune apres. */
    private void direSeul(String nom) {
        final String nomDit = nom;
        File f = nom == null ? null
                : new File(new File(getExternalFilesDir(null), "voix"), nom);
        if (f == null || !f.exists()) {
            Log.i("pixelgarde", "voix : rien a dire (" + nom + ")");
            rapportFin("rapportcoupe");
            stopForeground(true);
            stopSelf();
            return;
        }
        try {
            libererLecteur();
            lecteur = new MediaPlayer();
            fichierLu = f;
            lecteur.setAudioAttributes(ATTR_VOIX);
            lecteur.setDataSource(f.getAbsolutePath());
            lecteur.setOnCompletionListener(new MediaPlayer.OnCompletionListener() {
                public void onCompletion(MediaPlayer mp) {
                    libererLecteur();
                    // Rapport fini : Oui et Detail, quelques secondes.
                    String c = choixDire;
                    choixDire = null;
                    String pourC = pourDire;
                    pourDire = null;
                    rapportFin("rapportfini");
                    if (c == null && nomDit.startsWith("lus/")) {
                        String[] g = choixRelu(nomDit);
                        c = g[0];
                        if (pourC == null) pourC = g[1];
                    }
                    garderChoix(nomDit, c, pourC);
                    // Detail seul sans boutons calcules : voir jouer().
                    if (c != null && (estRapport(nomDit) || nomDit.startsWith("lus/"))) Bulle.choix(c, pourC);
                    else if (estRapport(nomDit)) Bulle.choix("detail:" + Langue.t(Voix.this, R.string.voix_detail), pourC);
                    stopForeground(true);
                    stopSelf();
                }
            });
            lecteur.setOnErrorListener(new MediaPlayer.OnErrorListener() {
                public boolean onError(MediaPlayer mp, int quoi, int extra) {
                    libererLecteur();
                    rapportFin("rapportcoupe");
                    Log.i("pixelgarde", "voix : lecture impossible (" + quoi + ")");
                    stopForeground(true);
                    stopSelf();
                    return true;
                }
            });
            lecteur.prepare();
            final MediaPlayer l = lecteur;
            quandMicroLibre(new Runnable() { public void run() {
                if (lecteur != l) return;
                prendreFocus();
                try { l.start(); } catch (Throwable t) {
                    Log.i("pixelgarde", "voix : dire : " + t);
                    libererLecteur(); rapportFin("rapportcoupe");
                    stopForeground(true); stopSelf(); return;
                }
                // L'anneau de la pastille se vide pendant la lecture. La duree ne
                // se connait qu'apres prepare() : avant, getDuration rend -1.
                Bulle.lecture(l.getDuration());
                enLecture(SEUL, titreDe(fichierLu, Langue.t(Voix.this, R.string.voix_titre_rapport)), l.getDuration());
                vibrer(20);
            }});
        } catch (Throwable t) {
            Log.i("pixelgarde", "voix : dire : " + t);
            rapportFin("rapportcoupe");
            stopForeground(true);
            stopSelf();
        }
    }

    // ------------------------------------------------------------- focus audio

    /** Voix parlee : Android baisse la musique des autres applis, comme Telegram. */
    private static final AudioAttributes ATTR_VOIX = new AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build();
    private AudioFocusRequest focusVoix;
    private final Runnable lacherFocusDiffere = new Runnable() { public void run() { lacherFocus(); } };

    private void prendreFocus() {
        hEnvoi.removeCallbacks(lacherFocusDiffere);
        if (focusVoix != null) return;
        try {
            AudioManager a = getSystemService(AudioManager.class);
            if (a == null) return;
            AudioFocusRequest r = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
                    .setAudioAttributes(ATTR_VOIX).build();
            a.requestAudioFocus(r);
            focusVoix = r;
        } catch (Throwable t) { Log.i("pixelgarde", "voix : focus : " + t); }
    }

    private void lacherFocus() {
        hEnvoi.removeCallbacks(lacherFocusDiffere);
        AudioFocusRequest r = focusVoix;
        focusVoix = null;
        if (r == null) return;
        try { getSystemService(AudioManager.class).abandonAudioFocusRequest(r); } catch (Throwable ignore) { }
    }

    private void libererLecteur() {
        // Un seul point de sortie pour l'anneau : fin normale, erreur, coupure
        // ou lecture suivante passent tous par ici.
        Bulle.lecture(0);
        // Une lecture retenue pour la dictee meurt avec son lecteur.
        departDiffere = null;
        retenue = false;
        pauseMicro = false;
        MediaPlayer l = lecteur;
        lecteur = null;
        if (l != null) { try { l.release(); } catch (Throwable ignore) { } }
        // Rendu en differe : la 1re phrase anticipee enchaine sur la reponse
        // complete, la musique ne doit pas remonter entre les deux.
        hEnvoi.removeCallbacks(lacherFocusDiffere);
        hEnvoi.postDelayed(lacherFocusDiffere, 800);
        File fl = fichierLu;
        fichierLu = null;
        // Fin (ou coupure) d'une relecture : hote-1 tenait la lecture auto
        // (rejouer.sh), il laisse maintenant 8 s aux boutons (relufini.sh).
        if (fl != null && fl.equals(relu)) {
            relu = null;
            Bulle.commande(this, "relufini");
        }
        ranger(fl);
        finLecture();
    }

    // ------------------------------------------------------------- stop

    /** Le bouton stop de la notification, ou la bulle touchee pendant la voix. */
    private void taire() {
        int s = sorte;
        Log.i("pixelgarde", "voix : taire (" + s + ")");
        // Un envoi attend la fin de cette voix : couper la voix l'annule,
        // comme le fait deja un appui sur la bulle pendant la lecture.
        if (envoiArme) { annulerEnvoi(); return; }
        if (suiteDe != null || attenteSuite || suiteNom != null) {
            // Taire pendant la 1re phrase, ou entre elle et la complete.
            hEnvoi.removeCallbacks(suitePerdue);
            boolean entre = attenteSuite;
            if (suiteNom != null) {
                ranger(new File(new File(getExternalFilesDir(null), "voix"), suiteNom));
                suiteNom = null;
            } else if (suiteDe != null) {
                debutCoupe = true;
            }
            attenteSuite = false;
            suiteChoix = null;
            if (entre && vivant) {
                vibrer(20);
                pret = true;
                Bulle.commande(this, "voixpret");
                return;
            }
        }
        if (s == RIEN || lecteur == null) {
            // Rien ne joue : appui tardif sur une notification perimee.
            if (!actif) { try { stopForeground(true); } catch (Throwable t) { } stopSelf(); }
            return;
        }
        libererLecteur();
        rapportFin("rapportcoupe");
        vibrer(20);
        if (s == SEUL) {
            stopForeground(true);
            stopSelf();
        } else if (s == REPONSE_LUE && vivant) {
            // Meme fin qu'une lecture complete : la conversation reste
            // ouverte, le micro attend un appui.
            pret = true;
            Bulle.commande(this, "voixpret");
        }
        // ACCUSE : le QG travaille encore, son etat ne change pas.
    }

    /**
     * Une lecture commence : la notification devient un lecteur media.
     *
     * MediaSession et pas une simple notification a bouton : sur Android 13
     * et plus, seul un lecteur media monte en tete du panneau, au-dessus des
     * autres notifications, et sur l'ecran verrouille. Bonus : le bouton
     * pause d'un casque ou de la voiture fait taire la voix aussi.
     */
    private void enLecture(int quoi, String titre, int dureeMs) {
        // Une seule voix a la fois : un texte lu (presse-papier, ecran) s'arrete.
        if (Lecteur.actif()) {
            try { startService(new Intent(this, Lecteur.class).setAction(Lecteur.STOP)); }
            catch (Throwable ignore) { }
        }
        sorte = quoi;
        parle = true;
        enPause = false;
        pauseVue = false;
        titreLecture = titre;
        pauseMicro = false;
        respecterMicro = true;
        afficherLecteur();
        // Guetter le micro pendant la voix : USER peut se mettre a dicter.
        hEnvoi.removeCallbacks(guetMicro);
        hEnvoi.postDelayed(guetMicro, MICRO_GUET_MS);
    }

    /** Toucher de la bulle ou bouton pause : met en pause, ou relance. */
    private void basculer() {
        // Voix prete mais retenue par une dictee : le toucher la lance tout
        // de suite. USER a choisi d'ecouter, on ne le fait pas attendre.
        if (departDiffere != null) {
            Runnable r = departDiffere;
            departDiffere = null;
            retenue = false;
            r.run();
            respecterMicro = false;
            return;
        }
        if (lecteur == null || sorte == RIEN) { taire(); return; }
        // Relance a la main pendant une dictee : USER a choisi, on le laisse.
        if (enPause) { if (pauseMicro) { pauseMicro = false; respecterMicro = false; } reprendre(); }
        else pause();
    }

    /**
     * Le curseur de la notification. USER, 2026-10-02 : « avancer ou reculer
     * la ou j'ai le curseur ». L'anneau de la bulle saute au meme point.
     */
    private void avancerA(long pos) {
        if (lecteur == null || sorte == RIEN || departDiffere != null) return;
        try {
            int d = lecteur.getDuration();
            final int p = (int) Math.max(0, Math.min(pos, Math.max(0, d - 300)));
            lecteur.setOnSeekCompleteListener(new MediaPlayer.OnSeekCompleteListener() {
                public void onSeekComplete(MediaPlayer mp) { afficherLecteur(); }
            });
            lecteur.seekTo(p);
            Bulle.lectureA(p);
        } catch (Throwable t) { Log.i("pixelgarde", "voix : curseur : " + t); }
    }

    /**
     * Rapport precedent (-1) ou suivant (+1) parmi les voix rangees. USER,
     * 2026-10-02 : « basculer entre les differents rapports comme une
     * musique ». Une voix fraiche n'est pas encore rangee : elle compte
     * comme la plus recente, et rejoint voix/lus en la quittant.
     */
    private void sauter(int sens) {
        if (lecteur == null || (sorte != SEUL && sorte != REPONSE_LUE)) return;
        File[] tous = lusAudibles();
        int i = tous.length;
        for (int k = 0; k < tous.length; k++) if (tous[k].equals(fichierLu)) { i = k; break; }
        int j = i + sens;
        if (j < 0 || j >= tous.length) {
            Toast.makeText(this, Langue.t(this, sens < 0 ? R.string.voix_pas_plus_ancien
                    : R.string.voix_dernier_rapport), Toast.LENGTH_SHORT).show();
            return;
        }
        String nom = "lus/" + tous[j].getName();
        prendreRapport(null);
        Log.i("pixelgarde", "voix : piste " + (sens < 0 ? "precedente " : "suivante ") + nom);
        vibrer(15);
        if (sorte == SEUL) direSeul(nom); else jouer(nom, false);
    }

    /** « Rapport 3/10, ecoute a 19h24 » pour une voix rangee, sinon le titre donne. */
    private String titreDe(File f, String defaut) {
        try {
            if (f == null || !"lus".equals(f.getParentFile().getName())) return defaut;
            File[] tous = lusAudibles();
            int rang = java.util.Arrays.asList(tous).indexOf(f) + 1;
            String n = f.getName();
            long ms = Long.parseLong(n.substring(0, n.indexOf('-')));
            String h = new java.text.SimpleDateFormat(Langue.t(this, R.string.voix_format_heure), Langue.locale(this))
                    .format(new java.util.Date(ms));
            return Langue.t(this, R.string.voix_titre_relu, rang, tous.length, h);
        } catch (Throwable t) { return defaut; }
    }

    // ------------------------------------------------------------- reecoute

    private File dossierLus() {
        File d = new File(new File(getExternalFilesDir(null), "voix"), "lus");
        if (!d.isDirectory() && !d.mkdirs()) Log.i("pixelgarde", "voix : lus/ impossible");
        return d;
    }

    /**
     * Une voix jouee (ou coupee) se range dans voix/lus au lieu d'etre
     * effacee. Prefixe horaire : le garde reutilise parfois un nom
     * (qg-pre-<id>.mp3), et l'ordre de rangement est l'ordre d'ecoute.
     */
    private void ranger(File f) {
        if (f == null || !f.exists()) return;
        try {
            File d = dossierLus();
            if (!d.equals(f.getParentFile())) {
                File cible = new File(d, System.currentTimeMillis() + "-" + f.getName());
                if (!f.renameTo(cible) && !f.delete()) { /* le menage l'emportera */ }
            }
            File[] tous = d.listFiles();
            if (tous == null || tous.length <= VOIX_GARDEES) return;
            java.util.Arrays.sort(tous);
            for (int i = 0; i < tous.length - VOIX_GARDEES; i++) {
                if (!tous[i].delete()) { /* tant pis, au prochain */ }
            }
        } catch (Throwable t) { Log.i("pixelgarde", "voix : ranger : " + t); }
    }

    /** La derniere voix rangee : noms prefixes par l'heure, le plus grand gagne. */
    private File dernierLu() {
        File[] tous = lusAudibles();
        return tous.length == 0 ? null : tous[tous.length - 1];
    }

    /**
     * Les voix rangees qu'on peut reecouter, de la plus ancienne a la plus
     * recente. Un bouton touche (Oui, Detail) range un silence de 0,2 s
     * (~500 octets) : « Reecouter le dernier » jouait ce silence, puis rendait
     * la main aussitot (bug du 2026-10-03). Sous 4 ko, ce n'est pas une voix.
     */
    private File[] lusAudibles() {
        File[] tous = dossierLus().listFiles();
        if (tous == null) return new File[0];
        java.util.List<File> ok = new java.util.ArrayList<File>();
        for (File f : tous) if (f.length() >= 4096) ok.add(f);
        File[] r = ok.toArray(new File[0]);
        java.util.Arrays.sort(r);
        return r;
    }

    // ------------------------------------------------------------- micro

    /** Vrai si une AUTRE appli enregistre : dictee du clavier, appel. */
    private boolean microAilleurs() {
        try {
            AudioManager a = getSystemService(AudioManager.class);
            if (a == null) return false;
            for (AudioRecordingConfiguration c : a.getActiveRecordingConfigurations()) {
                if (c.getClientAudioSessionId() == sessionMicro) continue;
                if (Build.VERSION.SDK_INT >= 29 && c.isClientSilenced()) continue;
                return true;
            }
        } catch (Throwable ignore) { }
        return false;
    }

    /** Lance la voix tout de suite, ou apres la dictee de USER. */
    private void quandMicroLibre(Runnable depart) {
        if (!microAilleurs()) { depart.run(); return; }
        Log.i("pixelgarde", "voix : micro pris ailleurs, lecture retenue");
        departDiffere = depart;
        retenue = true;
        microLibreDepuis = 0;
        hEnvoi.removeCallbacks(guetMicro);
        hEnvoi.postDelayed(guetMicro, MICRO_GUET_MS);
    }

    /** Toutes les 500 ms, tant qu'une voix attend ou joue. */
    private void guetter() {
        boolean pris = microAilleurs();
        long t = SystemClock.elapsedRealtime();
        if (pris) { microLibreDepuis = 0; if (microPrisDepuis == 0) microPrisDepuis = t; }
        else { microPrisDepuis = 0; if (microLibreDepuis == 0) microLibreDepuis = t; }
        boolean tenu = pris && t - microPrisDepuis >= MICRO_TENU_MS;
        boolean calme = !pris && t - microLibreDepuis >= MICRO_CALME_MS;
        if (departDiffere != null) {
            if (calme) {
                Runnable r = departDiffere;
                departDiffere = null;
                retenue = false;
                Log.i("pixelgarde", "voix : micro libre, lecture lancee");
                r.run();
            }
        } else if (lecteur != null && sorte != RIEN) {
            if (tenu && !enPause && respecterMicro) {
                Log.i("pixelgarde", "voix : dictee, pause");
                pause();
                pauseMicro = true;
            } else if (calme && enPause && pauseMicro) {
                Log.i("pixelgarde", "voix : dictee finie, reprise");
                pauseMicro = false;
                reprendre();
            }
        } else {
            return;
        }
        hEnvoi.removeCallbacks(guetMicro);
        hEnvoi.postDelayed(guetMicro, MICRO_GUET_MS);
    }

    private void pause() {
        if (lecteur == null || enPause) return;
        try { lecteur.pause(); } catch (Throwable t) { taire(); return; }
        lacherFocus();
        enPause = true;
        pauseVue = true;
        Bulle.lecturePause(true);
        hEnvoi.removeCallbacks(pausePerimee);
        hEnvoi.postDelayed(pausePerimee, PAUSE_MAX_MS);
        vibrer(15);
        afficherLecteur();
    }

    private void reprendre() {
        if (lecteur == null || !enPause) return;
        hEnvoi.removeCallbacks(pausePerimee);
        prendreFocus();
        try { lecteur.start(); } catch (Throwable t) { taire(); return; }
        enPause = false;
        pauseVue = false;
        Bulle.lecturePause(false);
        vibrer(15);
        afficherLecteur();
    }

    /** Session et notification suivent l'etat reel : lecture ou pause. */
    private void afficherLecteur() {
        String titre = titreLecture;
        int dureeMs = 0;
        long pos = 0;
        try { dureeMs = lecteur.getDuration(); pos = lecteur.getCurrentPosition(); }
        catch (Throwable ignore) { }
        // L'accuse d'attente n'est pas une piste : pas de suivant ni precedent.
        boolean pistes = sorte == SEUL || sorte == REPONSE_LUE;
        try {
            if (session == null) {
                session = new MediaSession(this, "pixelgarde-voix");
                session.setCallback(new MediaSession.Callback() {
                    @Override public void onPause() { pause(); }
                    @Override public void onPlay() { reprendre(); }
                    @Override public void onStop() { taire(); }
                    @Override public void onCustomAction(String a, android.os.Bundle e) { taire(); }
                    @Override public void onSeekTo(long pos) { avancerA(pos); }
                    @Override public void onSkipToNext() { sauter(1); }
                    @Override public void onSkipToPrevious() { sauter(-1); }
                });
            }
            session.setMetadata(new MediaMetadata.Builder()
                    .putString(MediaMetadata.METADATA_KEY_TITLE, titre)
                    .putString(MediaMetadata.METADATA_KEY_ARTIST, "Creeper")
                    .putLong(MediaMetadata.METADATA_KEY_DURATION, Math.max(0, dureeMs))
                    .build());
            session.setPlaybackState(new PlaybackState.Builder()
                    .setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
                            | PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_STOP
                            | PlaybackState.ACTION_SEEK_TO
                            | (pistes ? PlaybackState.ACTION_SKIP_TO_PREVIOUS
                                    | PlaybackState.ACTION_SKIP_TO_NEXT : 0))
                    .addCustomAction(new PlaybackState.CustomAction.Builder(
                            "taire", Langue.t(this, R.string.voix_btn_arreter), R.drawable.arreter).build())
                    .setState(enPause ? PlaybackState.STATE_PAUSED : PlaybackState.STATE_PLAYING,
                            pos, enPause ? 0f : 1f)
                    .build());
            session.setActive(true);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                NotificationChannel c = new NotificationChannel(
                        CANAL_LECTURE, Langue.t(this, R.string.voix_canal_lecture), NotificationManager.IMPORTANCE_LOW);
                c.setSound(null, null);
                nm.createNotificationChannel(c);
                Notification n = new Notification.Builder(this, CANAL_LECTURE)
                        .setSmallIcon(android.R.drawable.ic_lock_silent_mode_off)
                        .setColor(Charte.VERT)
                        .setContentTitle(enPause ? Langue.t(this, R.string.voix_titre_pause, titre) : titre)
                        .setContentText(Langue.t(this, enPause ? R.string.voix_touche_reprendre
                                : R.string.voix_touche_pause))
                        .setOngoing(true)
                        .setOnlyAlertOnce(true)
                        .setVisibility(Notification.VISIBILITY_PUBLIC)
                        // Avant Android 13, et sur certaines surcouches, les
                        // boutons viennent des actions ; apres, du PlaybackState.
                        .addAction(bouton(android.R.drawable.ic_media_previous,
                                Langue.t(this, R.string.voix_btn_precedent), PRECEDENT, 9))
                        .addAction(bouton(enPause ? R.drawable.jouer : android.R.drawable.ic_media_pause,
                                Langue.t(this, enPause ? R.string.voix_btn_reprendre : R.string.voix_btn_pause), BASCULE, 8))
                        .addAction(bouton(android.R.drawable.ic_media_next,
                                Langue.t(this, R.string.voix_btn_suivant), SUIVANT, 10))
                        .addAction(bouton(R.drawable.arreter, Langue.t(this, R.string.voix_btn_arreter), TAIRE, 7))
                        .setStyle(new Notification.MediaStyle()
                                .setMediaSession(session.getSessionToken())
                                .setShowActionsInCompactView(0, 1, 2))
                        .build();
                // Meme numero que la notification du service : elle la
                // remplace pendant la voix, au lieu d'en empiler une seconde.
                nm.notify(NOTIF, n);
            }
        } catch (Throwable t) { Log.i("pixelgarde", "voix : lecteur notif : " + t); }
    }

    private Notification.Action bouton(int icone, String libelle, String act, int req) {
        PendingIntent pi = PendingIntent.getService(this, req,
                new Intent(this, Voix.class).setAction(act),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Action.Builder(
                android.graphics.drawable.Icon.createWithResource(this, icone), libelle, pi).build();
    }

    /** Fin de voix : le lecteur disparait, la notification discrete revient. */
    private void finLecture() {
        boolean etait = parle;
        sorte = RIEN;
        parle = false;
        enPause = false;
        pauseVue = false;
        if (etait) finParole = SystemClock.elapsedRealtime();
        hEnvoi.removeCallbacks(pausePerimee);
        if (!etait) return;
        try {
            if (session != null) {
                session.setPlaybackState(new PlaybackState.Builder()
                        .setState(PlaybackState.STATE_STOPPED, 0, 0f).build());
                session.setActive(false);
            }
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null && actif) nm.notify(NOTIF, notifConversation());
        } catch (Throwable t) { Log.i("pixelgarde", "voix : fin lecteur : " + t); }
    }

    // -------------------------------------------------------------- sortie

    private void echec(String raison) {
        Log.i("pixelgarde", "voix : " + raison);
        couper();
    }

    private void couper() {
        if (!actif && !vivant) {
            // Peut arriver par start-foreground-service sans conversation
            // ouverte (appli relancee) : passer au premier plan avant de
            // s'eteindre, sinon Android tue l'appli. try : lance par un simple
            // startService en arriere-plan, startForeground leverait.
            try { premierPlan(); stopForeground(true); } catch (Throwable t) { }
            stopSelf();
            return;
        }
        vivant = false;
        actif = false;
        pret = false;
        desarmerEnvoi();
        libererLecteur();
        rapportFin("rapportcoupe");
        vibrer(60);
        Bulle.commande(this, "voixfin");
        stopForeground(true);
        stopSelf();
    }

    @Override public void onDestroy() {
        lacherFocus();
        hEnvoi.removeCallbacks(guetMicro);
        desarmerEnvoi();
        vivant = false;
        actif = false;
        pret = false;
        libererLecteur();
        rapportFin("rapportcoupe");
        if (session != null) { try { session.release(); } catch (Throwable t) { } session = null; }
        super.onDestroy();
    }

    private void vibrer(int ms) {
        try {
            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null) v.vibrate(VibrationEffect.createOneShot(
                    ms, VibrationEffect.DEFAULT_AMPLITUDE));
        } catch (Throwable ignore) { }
    }

    /**
     * La notification obligatoire du service de premier plan.
     *
     * IMPORTANCE_MIN, et l'histoire vaut d'etre dite. Les notifications de
     * l'appli etaient coupees en bloc (appops POST_NOTIFICATION ignore), donc
     * celle-ci ne s'affichait pas et personne ne s'en souciait. Le 2026-08-30
     * USER a demande un avis cliquable pour ses rapports : il a fallu rendre la
     * permission, et cette notification-ci est redevenue visible du meme coup.
     * MIN la garde au dernier rang du panneau, sans icone de barre d'etat ni
     * bruit. Le systeme l'exige pour accorder le micro, on ne peut pas s'en
     * passer, seulement l'effacer.
     */
    private Notification notifConversation() {
        return new Notification.Builder(this, CANAL)
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setContentTitle(Langue.t(this, R.string.voix_conversation))
                .setColor(Charte.VERT)
                .setOngoing(true)
                .build();
    }

    private void premierPlan() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) {
            nm.createNotificationChannel(new NotificationChannel(
                    CANAL, Langue.t(this, R.string.voix_canal_conversation), NotificationManager.IMPORTANCE_MIN));
        }
        Notification n = notifConversation();
        // Le type est OBLIGATOIRE depuis l'API 34 pour un service qui declare
        // foregroundServiceType : sans lui, le systeme refuse et leve
        // MissingForegroundServiceTypeException au premier tour. Il n'existe
        // qu'a partir de l'API 29, d'ou la branche : minSdk vaut 26.
        if (Build.VERSION.SDK_INT >= 29) {
            // Lance par le relais reseau et non plus par ADB, le service part
            // de l'appli en arriere-plan : Android peut alors refuser le type
            // micro (regle « pendant l'utilisation ») et leverait ici, ce qui
            // tuerait l'appli. Une simple lecture n'a pas besoin du micro : on
            // retombe sur le type lecture, declare aussi dans le manifeste.
            try {
                startForeground(NOTIF, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
            } catch (RuntimeException e) {
                Log.w("pixelgarde", "voix : micro refuse au premier plan, lecture seule " + e);
                startForeground(NOTIF, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
            }
        } else {
            startForeground(NOTIF, n);
        }
    }
}
