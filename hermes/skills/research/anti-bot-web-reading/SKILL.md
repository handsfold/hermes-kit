---
name: anti-bot-web-reading
description: Lire un site anti-bot (eBay, Amazon) via Chrome CDP.
version: 1.0.0
metadata:
  hermes:
    tags: [anti-bot, scraping, chrome, cdp, ebay, extraction, veille]
---

# Lire un site anti-bot

Quand un site bloque l'accès automatisé, le signal est net et répétitif :
`web_extract` renvoie une page anti-bot (~800 car.), `curl` avec un User-Agent
Chrome renvoie une sortie **vide** avec exit 0, `web_search` ne remonte aucun
prix/donnée sur les identifiants d'item. Tous ces symptômes pointent vers le
même verrou, et la seule porte fiable est un **vrai Chrome avec un vrai profil**.

## Échelle d'escalade

**Règle de Vin (août 2026) : utiliser `agent-reach` en premier, toujours.** C'est
le chemin par défaut, pas Chrome CDP. Chrome CDP ne sert que de repli pour les
pages qu'`agent-reach` ne lit pas.

1. **Exa** (`mcporter call 'exa.web_search_exa(query: "...", numResults: N)'`) :
   trouve les annonces/URL. **Couverture : Swappa oui, eBay non** (résultats
   vides sur les requêtes `site:ebay.com`). Sortie = JSON structuré, pas du
   texte : les URL sont sous `"results"[].url`, à parser avec `json.loads`, pas
   un regex `URL: ...`.
2. **Jina Reader** (`curl -s https://r.jina.ai/URL`) : lit une page en markdown.
   **Couverture : Swappa oui, eBay non** (403 Forbidden). Détecte « SOLD » en
   majuscules dans le markdown : à vérifier avant de conclure qu'une annonce est
   achetable.
3. **Chrome réel piloté par CDP** : le seul repli fiable pour eBay. Mais le
   contournement ne tient **que** dans une session interactive (`browser_navigate`).
   Un script autonome qui ouvre un onglet via `/json/new` se fait re-détecter
   (`Runtime.evaluate` renvoie `[]`) : ne pas compter dessus pour un cron `no_agent`.
4. **`curl` + User-Agent Chrome** : marche pour les pages simples, échoue sur
   anti-bot (sortie vide, exit 0 = ne pas conclure « OK »).

## Diagnostic des backends `agent-reach`

```bash
agent-reach doctor --json
```

Donne, par plateforme, `status`, `backends` et `active_backend`. Clés utiles ici :
`web` (backend `Jina Reader`) et `exa_search` (backend Exa). Avant d'écrire un
script, vérifier quel backend est actif et le tester sur la cible : la couverture
varie fortement selon la plateforme (Swappa passe, eBay non).

## Le repli qui marche : Chrome réel + CDP

```bash
google-chrome --remote-debugging-port=9222 &
```

Ensuite utiliser les outils navigateur Hermes (`browser_navigate`,
`browser_snapshot`, `browser_console`, `browser_click`). Hermes se connecte au
port de debug local : le site voit un vrai navigateur avec un vrai profil et
sert la page complète au lieu de l'interstitiel anti-bot.

Vérifié sur eBay (août 2026) : titre, prix, stock et statut « VENDU » deviennent
tous lisibles, là où `web_extract`/`curl`/`web_search` ne rendaient rien pendant
20+ tentatives.

## Pièges spécifiques eBay

- Un lien `/itm/<id>` expiré ou vendu **redirige** vers la fiche catalogue
  `/p/<ePID>` (prix neuf officiel, souvent hors budget) au lieu de l'annonce
  d'origine. Le numéro d'item dans l'URL ne garantit pas que tu lis la bonne
  annonce : vérifier le titre et le vendeur dans le snapshot.
- Un item vendu peut être **relisté** sous un nouveau `/itm/<id>` : cliquer
  « relisted this item » mène vers une annonce qui est *elle aussi* SOLD, mais
  avec le même prix. Ne pas déclencher d'alerte sur le prix avant d'avoir lu le
  statut « SOLD » dans la page de destination.
- Sur eBay, « SOLD » est détectable via `document.body.innerText` (`/\bSOLD\b/`)
  dans un `Runtime.evaluate`. C'est le seul signal fiable pour écarter un faux
  positif de prix.
- Pour lister les annonces plutôt qu'ouvrir chaque `/itm/` un par un, passer par
  la recherche triée prix :
  `https://www.ebay.com/sch/i.html?_nkw=...&_sop=15&LH_BIN=1&_ipg=120&LH_PrefLoc=2&LH_ItemCondition=...`
  (`_sop=15` = prix croissant, `_ipg=120` = 120 résultats/page,
  `LH_PrefLoc=2` = monde entier).
- Snapshot tronqué au-delà de ~15 000 car. ? `browser_console` avec un
  `querySelectorAll(...)` ciblé (`.s-item`, `.s-item__price`,
  `.s-item__link`) bat le scroll pour extraire une liste proprement, en JSON.
- « 0 results for ... » suivi de « N items found from international sellers »
  = les vendeurs qui livrent hors US. Filtrer par `LH_PrefLoc=2` pour les voir
  dans la liste principale.
- `-verizon -at&t -t-mobile` dans `_nkw` pour écarter les modèles opérateur
  (bootloader verrouillé).

## Règle de fond

Ne jamais présenter des données non confirmées comme des prix vérifiés. Si
l'extraction échoue, escalader jusqu'au Chrome CDP avant de dire « prix
inconnu ». Et ne jamais conclure « le site est mort » : c'est l'anti-bot.