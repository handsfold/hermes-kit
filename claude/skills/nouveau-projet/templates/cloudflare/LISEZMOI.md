# Site statique sur Cloudflare Workers : ce qui se pose en plus du socle

Lecons de ProjetA, MARQUE-E, Vynn et realvoxai. Ordre a suivre :

1. **DNS d'abord** (apex et www, A 192.0.2.1 et AAAA 100:: proxifies). Aucune
   requete sur le nom avant : le cache negatif du routeur dure 30 min, et USER voit un site mort.
2. **Zone** : `durcir-zone.sh <domaine>` (cache navigateur 0, https force, TLS 1.2,
   SSL full, SPF `-all` et DMARC `p=reject` si le domaine n'envoie pas de mail,
   www en 301 vers l'apex). Relancable sans risque. `--mail` si le domaine envoie.
3. **Deploiement** : copier `deployer.sh` dans `scripts/`, remplir DOMAINE et ZONE,
   mettre `<div class="version">version <!--VERSION-->-<!--/VERSION--></div>` dans la page.
   Il fait : filet, version tamponnee, envoi, purge, preuve en ligne, retour arriere.
   Seule la preuve en ligne fait foi : un jeton sans droit sur les routes envoie la version puis echoue.
   Tester le retour arriere une fois : `VP_ECHEC=1 scripts/deployer.sh`.
4. **SEO de base** : canonical, favicon svg, apple-touch-icon, og:image 1200x630,
   robots.txt, sitemap.xml, 404.html. Assets avec `?v=`.
5. **Formulaire** : honeypot, delai mini 2 s, limite par IP, doublon, KV ; alerte
   Telegram par `ctx.waitUntil` avec sa trace dans la fiche. L'API reste compatible avec l'ancienne page.
6. **Preuve visuelle** : `VERIF_UI_CACHE=ignore ~/Bureau/Projets/contexte/bin/verif-ui.sh https://<domaine>`.

Plus tard, selon le besoin : une seule regle `http_ratelimit` par zone ; compteur
de visites maison (D1) car le jeton n'a pas le droit Web Analytics ; pages privacy
et terms avant toute pub ou collecte large.
