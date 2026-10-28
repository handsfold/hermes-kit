# Classification des wallets : du plus au moins vulnérable (août 2026)

Sommaire :
- Tier 1 : Lien direct avec Coldcard
- Tier 2 : MicroPython, hardware différent
- Tier 3 : Accumulateur, source unique
- Tier 4 : Double source device + host
- Tier 5 : Secure Element certifié
- Tier 6 : Pas de firmware embarqué
- Bonus : CryptoJS/Ill Bloom (classe différente, aucun lien avec Coldcard)

Critères : partage de code Coldcard, utilisation MicroPython, sources d'entropie,
architecture de build.

---

## Tier 1, Lien direct avec Coldcard

### 1. Foundation Passport
- Fork du codebase Coldcard **avant** le bug de mars 2021
- Même duo STM32 + MicroPython
- Utilise un TRNG hardware open-source (avalanche noise), pas libngu
- Le CEO admet que le bug Coldcard est apparu dans un commit de 120 fichiers GPL→propriétaire
- **Audité 2026-08-12 : NON vulnérable.** `MICROPY_HW_ENABLE_RNG=1`.
  4 sources d'entropie validées : Avalanche TRNG + MCU RNG + SE + ALS.
  Pas de libngu, pas de Yasmarang.
- Difficulté : non applicable

### 2. Specter DIY
- STM32 + MicroPython + embit
- `os.urandom()` via TRNG hardware STM32
- **Audité 2026-08-12 : NON vulnérable.** `rng.py` appelle `os.urandom()` : pas
  de libngu, pas de Yasmarang, pas de `#ifdef` piège. Zéro code partagé avec
  la chaîne RNG foireuse de Coldcard.
- Difficulté : non applicable

---

## Tier 2, MicroPython, hardware différent

### 3. Krux
- MicroPython sur Kendryte K210 (pas STM32)
- Seed par caméra (hash des bytes bruts) : 900x l'entropie nécessaire
- Le hardware RNG du K210 n'est pas le point critique
- Risque : qualité d'image. Mur blanc = entropie faible
- Difficulté : difficile

---

## Tier 3, Accumulateur, source unique

### 4. Blockstream Jade
- ESP32, pas MicroPython. Accumulateur SHA512 style Bitcoin Core
- Sources : TRNG hardware + bruit radio + timers
- Code: `random.c` sur GitHub
- Risque : `bootloader_random_enable()` silencieux fail
- Difficulté : élevée

### 5. Keystone 3 Pro
- 3 Secure Elements (Microchip + Maxim ×2), TRNG dédiés, dés physiques
- Firmware partiellement open source
- Risque : 3 constructeurs différents, très improbable
- Difficulté : très élevée

---

## Tier 4, Double source device + host

### 6. Trezor (Model One, T, Safe 3/5)
- Device TRNG XOR host entropy (Trezor Suite)
- Fail-closed : `RuntimeError` si TRNG échoue
- Confirmé non affecté par Block et Trezor
- Risque : compromettre simultanément device ET OS hôte
- Difficulté : extrême

---

## Tier 5, Secure Element certifié

### 7. Ledger (Nano, Stax, Flex)
- BOLOS OS, SE CC EAL5+, TRNG certifié dans le SE
- Firmware partiellement closed-source
- Difficulté : extrême

### 8. BitBox02
- Double puce STM32 + ATECC608
- TRNG du SE combiné open source
- Difficulté : très élevée

### 9. Tangem
- Carte à puce, SE Samsung, 100% closed source
- Difficulté : extrême (boîte noire)

---

## Tier 6, Pas de firmware embarqué

### 10. SeedSigner
- Software sur Raspberry Pi, `/dev/random` Linux + caméra + dés
- Risque : `/dev/random` est un des RNG les plus audités
- Difficulté : quasi impossible sans casser le noyau Linux

---

## Bonus, CryptoJS/Ill Bloom (classe différente, aucun lien avec Coldcard)

- RRWallet, Bexo, NanChat, Bitcoin Libre, Milo Wallet
- Bug : MWC PRNG seedé depuis `Math.random()` : espace 2^39/2^47
- **Tout a déjà été drainé.** Coinspect a énuméré l'espace complet avant nous.
  Les attaquants ont vidé $5.7M+ en 2 vagues (mai-juillet 2026).
- Détail technique complet : `references/cryptojs-mwc.md`
