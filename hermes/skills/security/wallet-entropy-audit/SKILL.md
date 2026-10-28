---
name: wallet-entropy-audit
description: Auditer l'entropie des hardware wallets Bitcoin.
---

# Wallet Entropy Audit

## Classe de bug

Le pattern Coldcard : un fallback RNG logiciel déterministe (Yasmarang MicroPython) qui
remplace silencieusement le TRNG hardware à cause d'une erreur de build (`#ifndef` au
lieu de `#if`).

Mécanisme exact :
- `MICROPY_HW_ENABLE_RNG` défini à 0, pas absent
- `#ifndef` teste l'existence, pas la valeur → libngu croit le TRNG présent
- Seed générée par Yasmarang (déterministe, seedé par UID + RTC)
- 40 bits d'entropie effective au lieu de 128 sur Mk2/Mk3
- 72 bits sur Mk4/Mk5/Q (4 bytes du secure element ajoutés)

## Méthodologie d'audit

Pour chaque wallet, vérifier dans l'ordre :

1. **Code partagé avec Coldcard** : fork ? mêmes librairies ? même archi STM32+MicroPython ?
2. **Source d'entropie documentée** : TRNG hardware ? accumulateur ? multi-source ?
3. **Fallback path** : que fait le code si le TRNG échoue ? fail-closed ou fallback ?
4. **Flags de build** : présence de `MICROPY_HW_ENABLE_RNG` ou équivalent ?
5. **Seed finale** : XOR device+host ? hash d'accumulateur ? raw TRNG ?

## RNG Coldcard exact (implémentation Rust validée)

```rust
// Dual Yasmarang: rng_get() XOR my_yasmarang() (libngu)
// Init: pad=UID^SysTick, n=RTC->TR, d=RTC->SSR, dat=0
// Seed = SHA256d(bytes32) du XOR des deux Yasmarang
```

Voir `references/rng-rust.md` pour le code complet, `references/wallet-tiers.md`
pour la classification complète, et `references/cryptojs-mwc.md` pour l'analyse
Ill Bloom (CryptoJS MWC PRNG).

## Pièges connus

- **DK27ss/ColdCard-38M-PoC** : repo signalé malveillant. Le `go_poc` vole des
  credentials. `victims_wave1.json` est un leurre : 65 536 UIDs × 200 indices scannés, 0 hit.
  **Bannir tout ce qui vient de DK27ss.** Coût gaspillé : ~$180 Modal, ~6h CPU.
- Ne jamais faire confiance aux datasets sans vérification indépendante.
- Un wallet peut documenter un TRNG sans que le binaire compilé l'appelle.
- **Ill Bloom (CryptoJS)** : même classe de bug (RNG faible) mais tout a déjà été drainé
  par des attaquants avec des mois d'avance (2 vagues, $5.7M). Coinspect a énuméré
  l'espace complet. Scanner cet espace aujourd'hui = chercher des miettes.
  Détail : `references/cryptojs-mwc.md`.

## Résultats d'audit confirmés

### Non vulnérables à la classe Coldcard

| Wallet | Raison |
|---|---|
| **Specter DIY** | `os.urandom()` via TRNG hardware STM32. Pas de libngu, pas de Yasmarang.
| **Foundation Passport** | Forké Coldcard **avant** le bug (mars 2021). 4 sources : Avalanche TRNG + MCU RNG + SE + ALS. `MICROPY_HW_ENABLE_RNG=1`. Pas de libngu.
| **Trezor** | Device TRNG XOR host entropy. Fail-closed (`RuntimeError` si TRNG échoue).
| **Ledger** | BOLOS OS, Secure Element CC EAL5+, TRNG certifié.
| **SeedSigner** | `/dev/random` noyau Linux + caméra + dés.

Voir `references/wallet-tiers.md` pour la liste complète avec justifications.

## Classification des wallets

Voir `references/wallet-tiers.md` pour la liste complète avec justifications.
