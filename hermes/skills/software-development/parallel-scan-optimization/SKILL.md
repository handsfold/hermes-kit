---
name: parallel-scan-optimization
description: Scans paralleles massifs avec large dataset partage.
disable-model-invocation: true
---

Sommaire :
- Quand charger
- Pattern principal : Fork COW
- Calibration avant scan complet
- Tradeoffs hashmap vs bloom
- GPU obligatoire pour les scans PBKDF2-bound
- Pitfalls Rust pour les scans
- References
- Extraction de donnees on-chain (Blockstream)

## Quand charger

Toute tache de scan/recherche ou on doit tester des millions/milliards de candidats contre un grand ensemble de reference immutable (hashmap, set, bloom filter) en Python multiprocessing.

## Pattern principal : Fork COW

Quand chaque worker a besoin d'acceder a une structure de donnees volumineuse et read-only, **la charger dans le parent avant le fork** pour que Linux la partage via copy-on-write.

```python
# BON : charge AVANT le Pool, les workers heritent via fork COW
def init_worker(data_path, counter, lock):
    global _data, _counter, _counter_lock
    with open(data_path, 'rb') as f:
        _data = pickle.load(f)  # chaque worker a sa reference, pages partagees
    _counter = counter
    _counter_lock = lock

if __name__ == '__main__':
    # build hashmap (1x), save to pickle
    pickle.dump(hashmap, open('hashmap.pkl', 'wb'))

    counter = Value('Q', 0)
    lock = Lock()
    with Pool(processes=N, initializer=init_worker,
              initargs=('hashmap.pkl', counter, lock)) as pool:
        for result in pool.imap_unordered(scan_worker, pad_ranges()):
            if result:
                handle_hit(result)
```

**Pourquoi ca marche :** sous Linux, `fork()` + COW = les pages memoire du parent sont partagees avec chaque enfant tant qu'elles ne sont pas modifiees. Une hashmap/set utilisee en lecture seule = pages partagees = 1x la RAM au lieu de Nx.

**Piege :** Python multiprocessing copie les arguments dans chaque worker via pickle. Ne JAMAIS passer la hashmap en argument (`imap_unordered(func, [data] * N)` = N copies). Utiliser `initializer` + `initargs` pour passer le chemin du fichier pickle.

**Piege :** `apply_async` avec des objets non picklables (Queue, Lock passes dans args) = blocage silencieux. Preferer `Pool(initializer=...)` + `imap_unordered`.

## Calibration avant scan complet

Avant de lancer un scan 2^32, valider que les parametres sont corrects avec un ensemble de cibles connues :

1. **Collecter des cibles averees** (ex: adresses victimes connues sur la blockchain)
2. **Scanner un petit espace** avec toutes les hypotheses de parametres
3. **Arreter des qu'un match est trouve** = parametres confirmes
4. **Lancer le scan complet** avec les parametres calibres

```python
# Hypotheses a tester
skips = [
    (0, 0), (1, 1), (2, 2),  # lockstep
    (3103, 3161),             # split principal
    (3103, 3135),             # split range
    # ...
]
for pad in range(0, 10_000_000):
    for cs, ms in skips:
        addr = derive(pad, cs, ms)
        if addr in known_victims:
            return pad, cs, ms  # calibre!
```

## Tradeoffs hashmap vs bloom

| Approche | RAM | Faux positifs | Verification |
|---|---|---|---|
| **set/hashmap** (pickle) | elevee (~50-100 bytes/entree) | **zero** | aucune |
| **Bloom filter** (pybloom) | faible (~12 bits/entree) | ~0.001% | necessaire (seconde passe) |

**Regle :** si la hashmap tient en RAM (meme proche de la limite grace a COW), preferer la hashmap. Les faux positifs du bloom obligent a une verification secondaire qui coute du temps.

Pour ~30M d'entrees : hashmap = ~1.5 GB pickle, bloom = ~45 MB. Avec 16 GB+ RAM, hashmap COW = viable.

## GPU obligatoire pour les scans PBKDF2-bound

**Regle :** si le goulet est PBKDF2-HMAC-SHA512 (2048 rounds), le CPU est inutile. Le langage ne change rien : Python `hashlib.pbkdf2_hmac` ≈ Rust `ring::pbkdf2` ≈ 300-600 derivations/s par coeur. Les 2048 rounds HMAC sont le cout dominant, pas l'overhead du langage.

| Implementation | Derivations/s (1 coeur) | pour 2^32 pads |
|---|---|---|
| Python (hashlib) | ~600 | ~83 jours |
| Rust (ring) | ~300 | ~166 jours |
| CUDA (PoC, non optimise) | ~140 000 | ~8.5 heures |
| CUDA (optimise, theorique) | ~500 000+ | ~2.4 heures |

**Conclusion :** tout scan ou PBKDF2 apparait dans la boucle interne, passer directement au GPU. Ne pas perdre de temps a optimiser le CPU ou a changer de langage.

## Pitfalls Rust pour les scans

- **`ring::pbkdf2::derive` n'est pas plus rapide** que Python `hashlib` : le PBKDF2 est le bottleneck, pas le langage. Ne pas migrer Python→Rust en esperant un gain sur cette partie.
- **`rayon::ThreadPoolBuilder::build_global()` ne peut etre appele qu'une fois.** Si le binaire est lance dans un contexte ou rayon est deja initialise, utiliser `.ok()` ou laisser rayon decider du nombre de threads.
- **Compilation avec beaucoup de dependances :** `CARGO_BUILD_JOBS=2` evite les OOM sur les machines avec beaucoup de CPU mais RAM limitee. Le parallelisme de `cargo` consomme ~1-2 GB par job de compilation.
- **Binaire renomme :** `cargo init --name calibrate` cree `target/release/calibrate`, pas `target/release/scanner`. Verifier le nom reel du binaire avant de l'appeler.

## References

- `references/coldcard-skip-model.md` : Modele de skip Coldcard Mk2/Mk3
- `references/rust-bitcoin-scan-lessons.md` : Rust + bitcoin crate : pieges, contournement BIP39, hash160 binary search, Trust Wallet

## Extraction de donnees on-chain (Blockstream)

```python
import json, urllib.request

def get_txs(address: str, last_txid: str = None) -> list:
    url = f"https://blockstream.info/api/address/{address}/txs"
    if last_txid:
        url += f"/chain/{last_txid}"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)
```

Pour extraire les adresses entrantes d'une adresse de consolidation : iterer sur les pages de 25 txs, collecter `vin[].prevout.scriptpubkey_address`.
