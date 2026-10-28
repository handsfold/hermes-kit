# Rust Bitcoin Scan : leçons terrain (août 2026)

Sommaire :
- Contourner BIP39 pour x54 de débit
- bitcoin 0.32 crate : pieges
- rayon + iterateur sur u32
- Hash160 binary search > bloom filter > HashSet string
- Le collapse multi-format : un seul hash160 pour tout
- Téléchargement rapide : aria2c
- Trust Wallet BTC : a scanné
- Ill Bloom (CryptoJS MWC) : pas une cible viable non plus

## Contourner BIP39 pour x54 de débit

PBKDF2 plafonne a 12K derivations/s. Solution : traiter la sortie MT19937 comme cle privee brute
(`bx seed` -> raw key -> ECDSA -> address), sans mnemonic, sans BIP32.

| Methode | Debit | 2^32 |
|---|---|---|
| BIP39 (mnemonic -> seed -> BIP84) | 12 K/s | 4 jours |
| Raw key (seed -> bytes -> ECDSA) | 650 K/s | 110 min |

**Code** : 8 appels MT19937 -> 32 bytes -> `SecretKey::from_slice` -> `public_key` -> `Address::p2wpkh`.

## bitcoin 0.32 crate : pieges

- `CompressedPublicKey` n'implémente **ni `From<PublicKey>` ni `TryFrom<PublicKey>`**.
  Utiliser `CompressedPublicKey::from_slice(&pk.serialize())` : c'est la seule voie.
- `Address::p2wpkh(&CompressedPublicKey, network)` : passe un `Network` directement,
  `KnownHrp` dérive de `Network` via `From`.
- `Address::p2pkh(&bitcoin::PublicKey, network)` : le wrapper `bitcoin::PublicKey`
  fonctionne, `secp256k1::PublicKey` non.

## rayon + iterateur sur u32

`(0..(batch as u32)).into_par_iter()` OK.
`(0u32..).take(batch).into_par_iter()` : **refusé par rayon** (exige range borné).

Pour 2^32 complet : `(0u32..=u32::MAX).into_par_iter()` : compile et fonctionne.

### `par_bridge` détruit le débit, utiliser le chunking

Mesure sur le même scanner (bx seed -> hash160, 35.7M entrées binaires) :

| Méthode | Débit |
|---|---|
| `(0u32..=u32::MAX).par_bridge()` | **247K addr/s** |
| chunking + `into_par_iter` sur indices de chunks | **643K addr/s** |

`par_bridge` ajoute un surcoût par élément qui mange ~60% du débit. **Fix : chunking.**

```rust
let chunk_size: u64 = 4096;
let n_chunks: u64 = (total + chunk_size - 1) / chunk_size;
(0u64..n_chunks).into_par_iter().for_each(|chunk| {
    let base = chunk * chunk_size;
    let end = (base + chunk_size).min(total);
    for seed_u64 in base..end {
        // boucle sequentielle serree ici, pas de surcoût rayon par element
    }
});
```

**Ne jamais materialiser 2^32 seeds dans un `Vec`.** `(0u32..).take(4_294_967_296).collect::<Vec<u32>>()`
= 16 GB. Chunker, ou iterer par plage.

## Hash160 binary search > bloom filter > HashSet string

Chaque approche ajoute du coût. Pour 20M entrées :

| Approche | addr/s (8 threads) | RAM |
|---|---|---|
| Binary search `[u8; 20]` | **650K** | ~400 MB |
| Bloom filter (8 hash) | 480K | ~29 MB |
| HashSet string 19.9M | 400K | many GB |

**Conversion bech32 -> hash160** : `bech32.bech32_decode(addr)` -> `convertbits(data[1:], 5, 8, False)` -> 20 bytes.
Charger en `Vec<[u8; 20]>`, trier avec `.sort_unstable()`, chercher avec `.binary_search()`.

**Conversion P2PKH/P2SH (base58check) -> hash160** : `base58.b58decode(addr)` donne 25 bytes =
`version_byte(1) + hash160(20) + checksum(4)`. Prendre `raw[1:21]`. P2PKH = version `0x00`, P2SH = version `0x05`.

```python
import base58
raw = base58.b58decode(addr)  # 25 bytes
assert len(raw) == 25
hash160 = raw[1:21]           # 20 bytes, identique à bech32 pour la même clé
```

## Le collapse multi-format : un seul hash160 pour tout

Une même clé privée (`bx ec-new`) donne **plusieurs adresses selon le format**, mais elles
partagent **le même hash160** :

- P2PKH (`1...`) : version `0x00` + hash160
- P2SH-P2WPKH (`3...`) : version `0x05` + hash160
- P2WPKH (`bc1...`) : version `0x00` + hash160 en bech32

**Conséquence critique pour les scans** : si un scan couvre le hash160 bech32 et trouve 0 match,
il a déjà couvert P2PKH ET P2SH pour les clés compressées (même hash160). Les datasets séparés
P2PKH/P2SH n'ajoutent que les clés *non-compressées* et les vrais P2SH multisig (qui ne sont pas
`bx ec-new`). Ne pas re-scanner P2PKH/P2SH en pensant couvrir un nouvel espace.

**Même logique pour les forks** : BCH, LTC, DOGE partagent le hash160 de BTC. Un scan BTC à 0 match
implique 0 match sur ces forks pour le même chemin de dérivation. Scanner les forks séparément est
inutile, sauf pour les chemins de dérivation spécifiques au fork (ex: BCH CashAddr n'est qu'un
encodage du même hash160).

## Téléchargement rapide : aria2c

Quand wget est lent sur un gros fichier :
```bash
sudo apt-get install -y aria2
aria2c -x16 -s16 -o output.gz "URL"
```

## Trust Wallet BTC : a scanné

Ledger Donjon a scanné ETH des seeds Trust Wallet (CVE-2023-31290).
Le BTC du même espace de seed n'a **jamais été scanné publiquement**.
Le code vulnérable est dans le WASM de l'extension navigateur : MT19937 seedé par std::random_device (déterministe en WASM) -> 16 low-bytes -> mnémo 12 mots -> BIP84.

## Ill Bloom (CryptoJS MWC) : pas une cible viable non plus

MWC -> `WordArray.random(16)` -> 128-bit entropy -> BIP39 -> PBKDF2. Même goulet que Trust Wallet,
pire : 8 décisions de signe (Math.random() > 0.5) multiplient l'espace par 2^8 = **2^40 total**.
Plus le fait que Coinspect a déjà énuméré l'espace et que l'attaquant a drainé les wallets visibles
(2 vagues, $5.7M). Seul angle théorique : wallets dormants invisibles à BigQuery. Coût/retour défavorable.
