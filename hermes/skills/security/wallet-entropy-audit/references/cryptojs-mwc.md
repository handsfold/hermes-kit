# CryptoJS MWC PRNG : Ill Bloom

## Code source (CryptoJS 3.1.2-4, commit ff1f003)

```js
random: function (nBytes) {
    var words = [];
    var r = (function (m_w) {
        var m_w = m_w;
        var m_z = 0x3ade68b1;         // ← CONSTANTE FIXE, jamais changée
        var mask = 0xffffffff;
        return function () {
            m_z = (0x9069 * (m_z & 0xFFFF) + (m_z >> 0x10)) & mask;
            m_w = (0x4650 * (m_w & 0xFFFF) + (m_w >> 0x10)) & mask;
            var result = ((m_z << 0x10) + m_w) & mask;
            result /= 0x100000000;
            result += 0.5;
            return result * (Math.random() > .5 ? 1 : -1);
        }
    });

    for (var i = 0, rcache; i < nBytes; i += 4) {
        var _r = r((rcache || Math.random()) * 0x100000000);
        rcache = _r() * 0x3ade67b7;
        words.push((_r() * 0x100000000) | 0);
    }
    return new WordArray.init(words, nBytes);
}
```

## Analyse

- `m_z` = **0x3ade68b1** : constante codée en dur
- `m_w` seedé depuis `Math.random()` : **unique variable d'état**
- `Math.random()` fournit ~53 bits (double précision, 1<<53 entropie pratique V8)
- Espace effectif : **2^39 (12 mots) / 2^47 (24 mots)**, confirmé par Coinspect
- Résultat final signé par `Math.random() > .5` à chaque appel, ajoute du bruit mais pas d'entropie réelle
- Le `rcache` initial est le vrai seed → `rcache = _r() * 0x3ade67b7` → `m_w` pour le mot suivant

## Modèle de seed

```
seed = Math.random()        # 53 bits effectifs (double V8)
rcache = seed * 0x100000000
m_w = rcache * 0x3ade67b7   # déterministe à partir du seed
m_z = 0x3ade68b1            # constant
```

## Wallets affectés

| Wallet | Statut | Fix |
|---|---|---|
| RRWallet | Discontinué | Aucun |
| Bexo Wallet | Fixé en 20.1.0 | Builds non uploadées |
| NanChat | <1.3.0 affecté | Fixé en 1.3.0 |
| Bitcoin Libre | Fixé en v4 (juillet 2024) | OK |
| Milo | Discontinué | Aucun |

## Pertes confirmées

- Vague 1 (27 mai 2026) : 431 adresses, $3.14M
- Vague 2 (mai-juillet 2026) : 2 114 adresses actives
- Total estimé : $5.69M (borne inférieure)
- Chaînes : BTC, ETH, TRX, SOL, BNB, Polygon, Monad, Arbitrum, Gnosis, Optimism, Base, Avax, Linea, HyperEVM

## Pourquoi ne pas scanner aujourd'hui

- Coinspect a déjà énuméré tout l'espace (mois d'avance)
- Les attaquants ont drainé les adresses trouvées
- Les adresses restantes non publiées sont inconnues
- Sans le dataset Coinspect (non public), impossible de cibler

## Références

- GitHub Advisory: GHSA-rg76-677x-56q9
- Coinspect Ill Bloom: https://illbloom.org/
- Commit ff1f003 : https://github.com/brix/crypto-js/commit/ff1f003
- ferrumnet/bip39 fork (React Native) : https://github.com/ferrumnet/bip39