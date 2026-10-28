# Session eBay du 13 août 2026 : anti-bot par CDP

## Symptômes de blocage confirmés

5 tentatives sur ~20, toutes échoué avant Chrome CDP :

| Méthode | Résultat |
|---|---|
| `web_extract` | Page anti-bot ~800 car., même sur 3 items groupés (char_limit 3000, total 788 car.) |
| `browser_navigate` (Hermes natif) | 799 car., page anti-bot identique (2 tentatives) |
| `curl` + User-Agent Chrome | Sortie **vide**, exit_code 0 : trompeur |
| `web_search` sur numéros d'item | Aucun prix dans les résultats indexés |
| `web_search` sur fourchettes `$610 OR $549 OR $489` | Rien |

## La solution : Chrome réel

```bash
google-chrome --remote-debugging-port=9222 &
```

Hermes se connecte au port CDP → eBay voit un vrai navigateur → prix, stock,
statut « VENDU » tous lisibles. Vérifié sur `327106346279`, `327181527900`,
`227415473806`.

## Annonces disparues entre la dernière session et aujourd'hui

| Item | Titre | Prix | Statut |
|---|---|---|---|
| `327106346279` | Moonstone 256GB G4QUR XFINITY, Excellent | $539.95 | **VENDU** 27 juillet |
| `327181527900` | Moonstone 256GB G4QUR XFINITY, Very Good | Inconnu | **SOLD OUT** |
| `227415473806` | Obsidian 256GB G4QUR | MACROMART $1,749 | Redirigé vers fiche catalogue |

## Ce qui restait en stock (13 août)

- Pro **XL** 256GB Obsidian Open Box : $850 (+ $72 livraison TH)
- 128/256/512GB HK `didamobile` : $912 (livraison gratuite)
- GrapheneOS `privacyportal` UK : $1,085+
- Aucun G4QUR ~$500

## Paramètres de recherche eBay qui marchent

```
_nkw="pixel 10 pro" 256GB unlocked -XL -fold -verizon -at&t -t-mobile
_sop=15           (prix croissant)
LH_BIN=1          (Buy It Now uniquement)
_ipg=120          (120 résultats/page)
LH_PrefLoc=2      (monde entier)
LH_ItemCondition=3000|1500|2500  (Used | Refurbished | New: other)
```

Sans `LH_PrefLoc=2` : « 0 results » suivi de « N items from international sellers ».