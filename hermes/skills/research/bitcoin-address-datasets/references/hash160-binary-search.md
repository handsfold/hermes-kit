## hash160 Binary Search : Scanner Pattern (août 2026)

Approche optimale pour scanner 2^32 seeds contre 20M+ adresses financées :
pas de bloom filter, pas de hashset string : conversion bech32 → hash160 trié → binary search.

### Pourquoi c'est plus rapide

| Approche | Mémoire | Lookup | Débit (hote-1) |
|---|---|---|---|
| HashSet string | ~2 GB | O(1) mais hash lent sur strings | 400K/s |
| Bloom filter 8-hash | 29 MB | 8 hash par lookup | 480K/s |
| **hash160 binary search** | **352 MB** | **O(log n), 0 allocation hot path** | **650K/s** |

Le gain vient de : pas de string dans la boucle chaude, pas de hashing, pas d'allocation.
Binary search sur `[u8; 20]` trié = ~24 comparaisons par lookup, tout en cache L3.

### Pipeline

1. **Télécharger** le dataset bech32 : `Pymmdrza/Rich-Address-Wallet` → `Latest_Rich_Bitcoin_BECH32.txt.gz` (~538 MB)
2. **Convertir** en hash160 trié : `scripts/convert_bech32_to_hash160.py`
3. **Scanner** en Rust : charger `hash160s.bin`, `(0u32..=u32::MAX).into_par_iter()`, binary search

### Conversion (Python, ~7 minutes pour 20M)

```python
import bech32, gzip

hash160s = []
with gzip.open('bech32_funded.txt.gz', 'rt') as f:
    for line in f:
        addr = line.strip()
        hrp, data = bech32.bech32_decode(addr)
        if hrp == 'bc' and data and data[0] == 0:
            decoded = bech32.convertbits(data[1:], 5, 8, False)
            if decoded and len(decoded) == 20:
                hash160s.append(bytes(decoded))

hash160s.sort()
# dedup
unique = [h for i, h in enumerate(hash160s) if i == 0 or h != hash160s[i-1]]

with open('hash160s.bin', 'wb') as f:
    for h in unique:
        f.write(h)
```

Librairie : `pip install bech32` (bech32-1.2.0, pas `bitcoin`).

### Scanner Rust (boucle chaude)

```rust
// Chargement
fn load_hash160s(path: &str) -> Vec<[u8; 20]> {
    let buf = fs::read(path).unwrap();
    buf.chunks_exact(20).map(|c| {
        let mut h = [0u8; 20];
        h.copy_from_slice(c);
        h
    }).collect()
}

// Boucle chaude : pas de string, pas d'alloc
(0u32..=u32::MAX).into_par_iter().for_each(|seed| {
    let sk = seed_to_secret_key(seed);
    let pk = sk.public_key(&secp);
    let h160 = ripemd160::Hash::hash(&sha256::Hash::hash(&pk.serialize())[..]);
    if dataset.binary_search(&h160.to_byte_array()).is_ok() {
        // MATCH
    }
});
```

### Pièges

- `bech32` doit être dans le venv Hermes, pas le Python système
- `hash160s.bin` = `nombre_entrées × 20` octets, pas de header
- Le dataset doit être trié AVANT la déduplication
- SecretKey::from_slice échoue sur ~10% des seeds (clé > ordre de la courbe) : normal