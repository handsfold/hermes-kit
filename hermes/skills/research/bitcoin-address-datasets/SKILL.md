---
name: bitcoin-address-datasets
description: Dumps Bitcoin (LoyceV) pour scan local sans réseau.
disable-model-invocation: true
---

Sommaire :
- Sources de données
- Structure du dump
- Compter d'abord, dimensionner ensuite
- Bloom filter vs hashmap
- Fork COW pour partager la hashmap
- Profilage du goulet
- Extrapolation

**Fichiers liés** : `references/benchmarks-aout-2026.md` (perfs hote-1), `references/hash160-binary-search.md` (technique de scan optimale), `templates/build_hashmap.py` (script de construction réutilisable), `scripts/convert_bech32_to_hash160.py` (conversion bech32 → hash160 trié).

## Sources de données

| Source | Vitesse | Format | Gratuit | Fraîcheur |
|---|---|---|---|---|
| **Pymmdrza GitHub Releases** | ~50 Mbit/s | `.txt.gz` (une adresse/ligne) | Oui | Mensuel |
| Blockchair `gz.blockchair.com` | 10 kB/s | `.tsv.gz` (balance incluse) | Oui | Quotidien |
| Blockchair API |, | JSON/SQL | **Payant (402)** | Live |
| **LoyceV** (`addresses.loyce.club`) | **MORT** | `.tsv.gz` |, |, |
| BigQuery `crypto_bitcoin` | ~5 $/TB | SQL | 1er TB gratuit | Live |

**LoyceV est hors ligne depuis août 2026.** Tous les snapshots (`LATEST`, `20260802`, `20260701`, etc.) renvoient 404.
Priorité : Pymmdrza GitHub Releases en premier (gratuit, ~50 Mbit/s, pas de clé API). Blockchair direct = trop lent pour les scans (10 kB/s pour 1.7 GB = heures).

### Datasets Pymmdrza

```bash
wget "https://github.com/Pymmdrza/Rich-Address-Wallet/releases/download/Bitcoin/Latest_Rich_Bitcoin_BECH32.txt.gz"
wget "https://github.com/Pymmdrza/Rich-Address-Wallet/releases/download/Bitcoin/Latest_Rich_Bitcoin_P2PKH.txt.gz"
wget "https://github.com/Pymmdrza/Rich-Address-Wallet/releases/download/Bitcoin/Latest_Rich_Bitcoin_P2SH.txt.gz"
```

| Fichier | Taille | Format | Août 2026 |
|---|---|---|---|
| `Latest_Rich_Bitcoin_BECH32.txt.gz` | ~538 MB | une bc1/ligne | ~19.9M adresses |
| `Latest_Rich_Bitcoin_P2PKH.txt.gz` | ~700 MB | une 1xxx/ligne | ~23M |
| `Latest_Rich_Bitcoin_P2SH.txt.gz` | ~100 MB | une 3xxx/ligne | ~6M |

## Structure du dump

- ~59M lignes, ~29M bc1, ~23M P2PKH (1xxx), ~5.8M P2SH (3xxx)
- Header : `address\tbalance`
- Trié par balance décroissante (satoshis)

### Téléchargement

```bash
curl -o addresses.tsv.gz -L "http://addresses.loyce.club/blockchair_bitcoin_addresses_and_balance_LATEST.tsv.gz"
```

~1.7 GB compressé, ~3-4 minutes à 250 Mbit/s. Toujours vérifier avec `gunzip -t`.

## Compter d'abord, dimensionner ensuite

**Piège** : estimer la capacité sans compter → bloom filter plein → erreur après 30 minutes.

Toujours compter la population cible avant de dimensionner :
```bash
zcat addresses.tsv.gz | grep -c "^bc1"    # retourne le vrai compte
```

Dimensions typiques (août 2026) :
- bc1 : 29.3M → bloom 30M items, fpr=0.001% → ~86 MB
- Hashmap pickle : 1.4 GB pour 29.3M adresses

## Bloom filter vs hashmap

| Approche | RAM | Faux positifs | Lookup |
|---|---|---|---|
| **Hashmap `set()` pickle** | 1.4 GB | 0 | O(1) |
| Bloom filter (pybloom_live) | 86 MB | 0.001% | O(1) |

**Règle** : si RAM dispo > 2× taille hashmap → hashmap. Sinon bloom + vérification secondaire.

Construction hashmap :
```python
import gzip, pickle
funded = set()
with gzip.open("addresses.tsv.gz", "rt") as f:
    f.readline()  # skip header
    for line in f:
        addr = line.split("\t")[0]
        if addr.startswith("bc1"):
            funded.add(addr)
with open("hashmap_bc1.pkl", "wb") as f:
    pickle.dump(funded, f, protocol=pickle.HIGHEST_PROTOCOL)
```

## Fork COW pour partager la hashmap

Problème : `Pool` avec `initializer` + pickle → chaque worker a sa copie → N × 1.4 GB.

Solution : charger dans le parent, `fork`, partager via COW (Linux seulement).

```python
import multiprocessing as mp
mp.set_start_method("fork", force=True)

# Charger dans le parent
with open("hashmap_bc1.pkl", "rb") as f:
    hashmap = pickle.load(f)

def worker_init(h):
    global _hashmap
    _hashmap = h

with mp.Pool(workers, initializer=worker_init, initargs=(hashmap,)) as pool:
    for result in pool.imap_unordered(process_chunk, chunks):
        ...
```

**Piège** : ne pas utiliser `apply_async` avec une `Queue` passée en argument → `RuntimeError: Queue objects should only be shared between processes through inheritance`. Utiliser `imap_unordered` avec un générateur de chunks.

## Profilage du goulet

Pour un scanner de dérivation d'adresses Bitcoin, le goulet est quasi-systématiquement :

```
entropy_to_mnemonic:  ~0.002 ms  (négligeable)
mnemonic_to_seed:     ~0.630 ms  (PBKDF2 2048 rounds, 80% du temps)
first_address_bip84:  ~0.172 ms  (secp256k1 + hash160)
```

Toute optimisation doit cibler `mnemonic_to_seed` en premier (PBKDF2 → GPU, ou pré-calcul).

## Extrapolation

Règle de calcul pour estimer la durée d'un scan complet :

```
durée_jours = (2^32) / (pads_par_seconde × 86400)
```

Exemple : 2 808 pads/s → 2^32 / (2808 × 86400) = 17.7 jours (24 CPU cores).