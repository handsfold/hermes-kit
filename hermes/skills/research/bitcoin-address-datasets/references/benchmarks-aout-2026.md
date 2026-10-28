# Benchmarks scan: août 2026

Machine : hote-1 (24 coeurs, 31 GB RAM)

## Python (PBKDF2-bound, Coldcard scan)

| Workers | Plage | Vitesse (pads/s) | Hashmap RAM | Méthode |
|---|---|---|---|---|
| 1 | 1 000 | 245 | n/a | Série, profilage |
| 4 | 50 000 | 737 | 1.4×4 GB (pickle) | Pool standard |
| 4 | 50 000 | 828 | 1.4 GB (COW) | Fork COW |
| 20 | 250 000 | **2 808** | 1.4 GB (COW) | Fork COW |

Goulets Python : `mnemonic_to_seed` (PBKDF2) : 0.63 ms = 80% du total.

## Rust (no PBKDF2, bx seed -> raw key -> hash160)

| Méthode | Vitesse (addr/s) | 2^32 |
|---|---|---|
| Chunked `into_par_iter` (4096/chunk) | **643K** | 111 min |
| `par_bridge` | 247K | 289 min |
| Full scan: 35.8M hash160s (P2PKH+P2SH+BECH32 merged) | 643K | 111 min |

Recette : 8× MT19937 → 32-byte privkey, pas de mnemonic, binary search `Vec<[u8; 20]>`.

## Décodage des formats d'adresse Bitcoin

CLÉ : **P2PKH, P2SH-P2WPKH, et BECH32 partagent le même hash160** pour une même clé.
Les trois formats ne sont que des wrappers autour de `ripemd160(sha256(pubkey))`.

### BECH32 → hash160
```python
import bech32
hrp, data = bech32.bech32_decode(addr)
converted = bech32.convertbits(data[1:], 5, 8, False)  # 20 bytes
```

### P2PKH / P2SH (base58check) → hash160
```python
import base58
raw = base58.b58decode(addr)  # 25 bytes = version + hash160(20) + checksum(4)
hash160 = raw[1:21]
```
P2PKH version = `0x00`, P2SH = `0x05`.

## Comptes datasets Pymmdrza (13 août 2026)

| Format | Adresses | Hash160 uniques |
|---|---|---|
| BECH32 | 19.9M | 17.6M |
| P2PKH | 13.3M | 18.1M nouveaux (vs bech32) |
| P2SH | 4.9M | 18.1M nouveaux (vs bech32) |
| **Total unique** | - | **35.8M** |

Les ~18.1M hash160s supplémentaires viennent de clés non-compressées et de vrais P2SH multisig.