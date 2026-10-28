---
name: recherche-thai
description: "Web thaïlandais en thaï : prix, normes, douane, lois. Cherche sur le web thaïlandais, en thaï, pour obtenir les vrais chiffres au lieu des pages pour expatriés. Fournit le lexique thaï, les sites qui font autorité et les pièges (ère bouddhiste, unités). La recherche passe ensuite par agent-reach-hermes. À charger dès qu'une question sur la Thaïlande touche un prix, un taux, une loi, une douane, une banque, un terrain, une société ou une démarche, même posée en français."
when_to_use: "USER demande « combien ça coûte en Thaïlande », « la douane thaïe prend combien », « le taux de prêt », « le prix du terrain », « c'est légal en Thaïlande ? », « comment ouvrir une société thaïe », « quel visa », « le FDA thaï ». Pas pour la douane des États-Unis (voir tarifs-douane-usa)."
version: 1.0.0
metadata:
  hermes:
    tags: [recherche, thailande, thai, langue, sources, prix, banque]
---

# Recherche en thaï

## La règle en une phrase

Une requête en anglais sur un sujet thaïlandais renvoie des sites pour
expatriés. La même requête en thaï renvoie la source primaire.

Exemple mesuré le 16/09/2026 :

| Requête | Ce que ça donne |
|---|---|
| `Thailand car loan LTV` | blogs d'expats, chiffres de 2019, aucune grille |
| `สินเชื่อรถยนต์ LTV ราคาประเมิน` | grilles Kasikorn et Krungsri, plafonds d'âge |

## Comment procéder

**D'abord `enquete "<question>"`** (2026-09-27) : il écrit lui-même les requêtes
en thaï, cible Pantip et les sites `.go.th`, et classe correctement les pages thaïes.
Les étapes ci-dessous servent à creuser ce qu'il n'a pas trouvé.

1. **Traduire la question en 3 à 6 mots-clés thaïs.** Voir `references/lexique.md`.
2. **Lancer agent-reach** avec la requête thaï. C'est le moteur, ce skill est le vocabulaire.
3. **Ajouter le site** quand la source primaire est connue : `site:bot.or.th ...`.
4. **Croiser avec une requête anglaise** pour le contexte, jamais pour le chiffre.

```bash
agent-reach search "สินเชื่อบ้าน LTV ธปท 2569"
agent-reach read "https://www.bot.or.th/th/news-and-media/news/news-20260514.html"
```

## Les 4 pièges qui font rater une recherche

**1 · L'année bouddhiste.** พ.ศ. = ère bouddhiste = année grégorienne + 543.
2026 s'écrit **2569**. Un document officiel thaï n'écrit jamais 2026.
Chercher « 2026 » sur un site .go.th ne renvoie presque rien.

**2 · Les unités de nombres.** Le thaï compte par paliers, pas par milliers.

| Thaï | Valeur | Exemple d'annonce |
|---|---|---|
| พัน | 1 000 | |
| หมื่น | 10 000 | |
| แสน | 100 000 | `9 แสน` = 900 000 |
| ล้าน | 1 000 000 | `5.5 ล้าน` = 5 500 000 THB |

`5.5 ล้าน` n'est PAS 5,5 millions de dollars. Toujours THB sauf mention.

**3 · La translittération est instable.** Un même mot s'écrit de 3 façons en
alphabet latin : `Srisawad`, `Sri Sawad`, `ศรีสวัสดิ์`. Toujours préférer
l'écriture thaïe pour une recherche, la latine seulement pour un nom de domaine.

**4 · Les chiffres thaïs.** ๐๑๒๓๔๕๖๗๘๙ apparaissent encore dans les documents
officiels scannés et les journaux officiels. Les convertir avant de citer.

## Vérification d'un chiffre

Un chiffre trouvé sur un blog thaï vaut autant qu'un chiffre trouvé sur un blog
anglais : rien. La hiérarchie des sources est dans `references/sites.md`.

Ordre de confiance :
1. Site gouvernemental `.go.th` ou `.or.th` (BOT, DBD, cadastre, douanes)
2. Page produit officielle de la banque ou de l'entreprise
3. Presse économique thaïe (Thansettakij, Prachachat, Bangkokbiznews)
4. Agrégateur ou comparateur
5. Blog, Pantip, Facebook : indice seulement, jamais une citation

## Quand ne pas utiliser ce skill

- Sujet non thaïlandais.
- La réponse est publiée en anglais par la source primaire elle-même
  (rapport annuel d'une banque, communiqué du BOI). Aller au document.
- Besoin d'une traduction ou d'une rédaction en thaï : ce skill ne couvre que la
  recherche.

## Références

- `references/lexique.md` : le vocabulaire par domaine, prêt à copier
- `references/sites.md` : les sources qui font autorité, par sujet
