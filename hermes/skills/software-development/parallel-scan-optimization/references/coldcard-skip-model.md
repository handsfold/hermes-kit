# Modele de skip Coldcard (firmware RE par DK27ss)

## Source

Reverse-engineering du firmware Coldcard Mk2/Mk3 v4.0.x-4.1.9, commit vulnerable `b18723dd`.

## Origine du skip

Sur le **premier boot** d'un device, `nvstore` (`shared/nvstore.py`) trouve 32 slots vides et en remplit 3 avec du garbage :

```
shuffle(32 slots) → 31 appels uniform (chip+mixer, + retries)
3 slots × 16 × random.bytes(256) = 3072 mots (1:1 chip+mixer)
```

## Skips exacts

- **chip_skip = 3072 + 31 = 3103** (deterministe)
- **mixer_skip ≈ 3103 + E[shuffle retries] ≈ 3161 ± 8** (geometrique)

## Deux generateurs, deux skips

`external/libngu/ngu/random.c` precise :

- `my_random_bytes()` et `random_uint32()` : **chip + mixer 1:1**
- `_rand_below()` : premier essai = chip+mixer, retries = **mixer seulement**

Donc `chip_skip` et `mixer_skip` sont **independants**.

## Pipeline complet

```
pad = UID32 ^ SysTick->VAL
  → MicroPython fallback PRNG (seed: pad, n=0, d=0, RTC=0)
  → chip.rng_get() × 3103, mixer.next() × 3161
  → 8 × (rng_get() ⊕ yasmarang) = random.bytes(32)
  → sha256s (un seul SHA-256) = BIP39 entropy
  → 24 mots → PBKDF2-HMAC-SHA512 × 2048
  → BIP32 m/84'/0'/0'/0/0 → bech32
```

## Validation

- 3 implementations cross-validatees bit-for-bit : Python (`vuln_rng.py`), Go (`go_poc/`), CUDA (`gpu_poc/`)
- Test vectors publies couvrant raw32, entropy, mnemonic, seed64, privkey, hash160, address
- `make_victim.py` / `recover.py` : demo de bout en bout (ancien modele lockstep, skip=0 uniquement)

## Status live

Au 12 aout 2026, les scans GPU (2× RTX PRO 6000) avec skip=3103, mixer∈[3135,3195) n'ont pas trouve de victime reelle. Le skip derive du firmware peut ne pas correspondre a l'historique de boot reel des victimes.

## Universel

L'espace est **universel** : `pad = UID32 ^ SysTick->VAL` fait 2^32. Un seul scan retrouve TOUS les wallets Mk2/Mk3 vulnerables.