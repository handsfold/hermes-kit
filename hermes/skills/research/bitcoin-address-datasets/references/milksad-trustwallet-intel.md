## Milk Sad & Trust Wallet : Threat Intelligence (août 2026)

### CVE-2023-39910 (Milk Sad / bx seed)

- **Source** : `bx seed` de libbitcoin-explorer (2017 → 2023)
- **PRNG** : MT19937 seedé par l'horloge système → **2^32 graines**
- **Victimes** : 2668 wallets BTC trouvés, 112+ BTC drainés (juillet 2023)
- **Chemins scannés par Milk Sad** : BIP44/49/84 (m/xx'/0'/0'), index 0 uniquement
- **Chemins JAMAIS scannés** : raw keys directes (`bx seed` → clé brute sans BIP32), index 1+, chemins Electrum/MultiBit/Breadwallet
- **Débit de référence** : 70 min pour 2^32 sur Ryzen 7950X3D (Milk Sad team)

### CVE-2023-31290 (Trust Wallet Browser Extension)

- **Source** : extension navigateur Trust Wallet, `wallet-core` compilé en WASM
- **PRNG** : MT19937 seedé par `std::random_device` (déterministe en WASM)
- **Mécanisme** : 16 appels MT19937 → bits [7:0] → 128-bit entropy → mnémo 12 mots BIP39
- **Différence vs bx seed** : espace de seeds distinct, MT19937 seedé différemment
- **Scan ETH** : Ledger Donjon a scanné et publié (juillet 2023)
- **Scan BTC** : **JAMAIS PUBLIÉ.** Milk Sad a confirmé enquête en cours, jamais publié les résultats
- **Chemin cible** : BIP84 (m/84'/0'/0'/0) : bech32, correspond au dataset Pymmdrza

### Angles morts non explorés

1. **Raw keys bx seed** : 2^32 seeds → clé privée brute → P2WPKH. Jamais scanné.
2. **Trust Wallet BTC BIP84** : même faille que l'extension ETH, mais versant Bitcoin non scanné.
3. **Index/comptes > 0** : Coinspect (Ill Bloom) n'a scanné que l'index 0 du compte 0.
4. **Forks BTC** : BCH, LTC, DOGE utilisent les mêmes clés, jamais scannés.
5. **Chemins non-BIP** : Electrum, MultiBit HD, Breadwallet, tous compatibles avec les seeds faibles.

### Sources

- https://milksad.info/disclosure.html
- https://milksad.info/posts/research-update-1
- Ledger Donjon blog (Trust Wallet disclosure)
- Coinspect Ill Bloom report