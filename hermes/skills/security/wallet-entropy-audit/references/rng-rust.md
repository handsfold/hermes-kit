# Implémentation Rust du RNG Coldcard exact

Dual Yasmarang: `rng_get()` (MicroPython) XOR `my_yasmarang()` (libngu).
Init: pad=UID^SysTick, n=RTC->TR, d=RTC->SSR, dat=0.
Seed = SHA256d(bytes32).

```rust
const M32: u32 = 0xFFFFFFFF;

#[derive(Clone)]
struct Yasmarang {
    pad: u32,
    n: u32,
    d: u32,
    dat: u8,
}

impl Yasmarang {
    fn new(pad: u32, n: u32, d: u32) -> Self {
        Self { pad: pad & M32, n, d, dat: 0 }
    }

    fn next(&mut self) -> u8 {
        self.pad = self.pad.wrapping_add(
            self.pad.wrapping_mul(self.n).wrapping_add(self.d)
        );
        self.dat = ((self.pad >> 24) ^ self.pad) as u8;
        self.dat
    }

    fn next_u32(&mut self) -> u32 {
        let b0 = self.next() as u32;
        let b1 = self.next() as u32;
        let b2 = self.next() as u32;
        let b3 = self.next() as u32;
        (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
    }
}

fn gen_seed(uid: u32, rtc_tr: u32, rtc_ssr: u32) -> [u8; 32] {
    // rng_get() : MicroPython Yasmarang
    let mut rng = Yasmarang::new(uid, rtc_tr, rtc_ssr);
    
    // Initial seeding: comme MicroPython urandom
    for _ in 0..64 {
        rng.next();
    }
    
    // my_yasmarang() : libngu, seed = rng_get()^Time
    let mut ngu = Yasmarang::new(
        rng.next_u32() ^ rtc_tr,
        rng.next_u32() as u32,
        rng.next_u32() as u32,
    );
    
    // 32 bytes from XOR of both generators
    let mut bytes = [0u8; 32];
    for i in 0..32 {
        bytes[i] = rng.next() ^ ngu.next();
    }
    
    // SHA256d(bytes) : identical to shared/seed.py
    use bitcoin::hashes::{sha256, Hash};
    let hash1 = sha256::Hash::hash(&bytes);
    let hash2 = sha256::Hash::hash(&hash1[..]);
    let mut seed = [0u8; 32];
    seed.copy_from_slice(&hash2[..]);
    seed
}
```

## Notes

- Le seed initial (32 bytes) passe par SHA256d avant d'être utilisé comme seed BIP39
- Le touchscreen sur Specter ajoute de l'entropie via `urandom.seed(touch_data)`
  après l'appel à `gen_seed()` : à prendre en compte si on audite Specter
- RTC=0 au cold boot sur certains modèles Mk3 : réduit drastiquement l'espace de recherche
