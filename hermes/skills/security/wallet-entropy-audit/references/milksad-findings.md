# Milk Sad : Résumé complet des découvertes

Dernière mise à jour : 13 août 2026 (scan brut `bx seed` → hash160 sur 35.8M adresses)

## CVE-2023-39910 : `bx seed` (libbitcoin-explorer 3.x)

**Mécanisme** : `bx seed` utilise `std::mt19937` (Mersenne Twister 32-bit) seedé par
`get_clock_seed()` → timestamp + `time(nullptr)` + `clock()`. Seulement 32 bits
d'entropie effective. Espace : 2^32 seeds (~4.3 milliards).

## Résultats du scan Milk Sad : BIP39 (mt19937 → BIP39 → adresses BTC)

**2668 wallets** trouvés au total sur BTC mainnet (paths standards examinés) :

| Entropie BIP39 | 128-bit (12 mots) | 160-bit (15 mots) | 192-bit (18 mots) | 224-bit (21 mots) | 256-bit (24 mots) |
|---|---|---|---|---|---|
| m/44' P2PKH comp. | 8 | 0 | 2 | 0 | 14 |
| m/44' P2PKH uncomp. | 0 | - | 0 | - | 1 |
| m/49' P2SH | 1 | 0 | 1 | 0 | 2634 |
| m/84' Bech32 | 0 | 0 | 1 | 0 | 9 |
| Total unique wallets | 9 | 0 | 4 | 0 | 2655 |

## Résultats du scan Milk Sad : `bx ec-new` (mt19937 → raw privkey BIP32)

**81 wallets** trouvés, 112.86 BTC volume cumulé. Performance : **70 minutes** pour 2^32 seeds.

## SCAN INDÉPENDANT confirmé (13 août 2026) : `bx seed` → raw key → hash160

Scan exhaustif 2^32 réalisé en local (Rust, 643K addr/s, 111 min) contre **35.8M hash160s**
fusionnés (P2PKH 13.3M + P2SH 4.9M + BECH32 17.6M uniques). **Résultat : 0 match.**

**Conclusion définitive** : le chemin `bx seed` → clé privée brute → adresse (sans BIP39,
sans BIP32) est ÉPUISÉ. Aucun wallet financé restant sur ce vecteur. Les victimes passaient
par `bx mnemonic-new` (BIP39 → BIP84), déjà drainé par Milk Sad en juillet 2023.

## Attaquant principal

- 2023-07-12 : vol massif BTC + ETH dans les heures qui suivent
- A drainé bx + Trust Wallet en même temps (même attaquant)

## Ce qui a été scanné par Milk Sad (EXHAUSTIVEMENT)

- Tous les paths BIP44/49/84 standards, index 0, pour les 2^32 seeds
- `bx ec-new` pour les 2^32 seeds
- ETH via les mêmes seeds (partiellement)

## Ce qui N'A PAS été scanné : et pourquoi c'est en fait une impasse

- **BCH / LTC / DOGE** : ~~jamais scanné~~ → **IMPASSE**. Ces forks partagent le même
  hash160 que BTC. Le scan BTC à 0 match implique 0 match sur ces forks pour le même
  chemin de dérivation. Scanner les forks séparément est inutile (sauf chemins de
  dérivation spécifiques au fork, qui n'existent pas pour `bx ec-new`).
- **Trust Wallet BTC (CVE-2023-31290)** : distinct de bx (espace de seed séparé), mais
  **impasse pratique** : nécessite BIP39/PBKDF2 → 15K addr/s → 80h sur CPU. Sans GPU,
  hors budget. Le code compile et tourne, le goulet est PBKDF2.
- **BIP84 index 1-100** des 2668 seeds Milk Sad : la liste des seeds n'est pas publique.
  Sans elle, il faudrait un scan BIP39 complet (80h+).
- **Ill Bloom (CryptoJS MWC)** : même goulet PBKDF2 + espace 2^40 (8 sign bits).
  Déjà énuméré par Coinspect. Pas viable.

## Trust Wallet (CVE-2023-31290)

Extension navigateur Trust Wallet. Même classe de bug (MT19937), implémentation séparée de bx.
Entropie : MT19937 seedé `std::random_device` 32-bit (déterministe en WASM) → 16 low-bytes
→ BIP39 128-bit → mnémo 12 mots → BIP84. Ledger Donjon a scanné ETH, jamais BTC.
Mais le versant BTC est **PBKDF2-bound** : injouable sur CPU.

## Conclusion opérationnelle (définitive au 13 août 2026)

- **BTC via bx/BIP39** : épuisé, drainé.
- **BTC via bx ec-new (raw key)** : épuisé : scan local 2^32 confirmé, 0 match.
- **BCH/LTC/DOGE** : impasse (même hash160 que BTC).
- **Trust Wallet BTC** : impasse pratique (PBKDF2, 80h CPU).
- **BIP84 index>0** : impasse (liste de seeds non publique).

Aucun vecteur restant exploitable avec le matériel actuel. La classe de bug est documentée
et l'espace est couvert par Milk Sad + ce scan local.