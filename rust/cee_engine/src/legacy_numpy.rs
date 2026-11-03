//! Zrcadlo generátoru `numpy.random.Generator` (PCG64 se `SeedSequence`).
//!
//! Python staví svět (hláskové tvary protojazyka, `scenarios.py`) přes numpy
//! generátor `rng.generator(seed, ...)`. Aby šla stavba světa v Rustu porovnat
//! s Pythonem v ticku 0, je tu jen to, co stavba světa potřebuje: semínko,
//! `random`, `uniform`, `integers(low, high)` a `choice(n, p=...)`. Simulace
//! samotná tento generátor nepoužívá (běží na [`crate::rng::Stream`]).
//! Vektory z numpy: `tests/fixtures/rng.json`.

use crate::rng::{stable_int, Part};

const INIT_A: u32 = 0x43b0_d7e5;
const MULT_A: u32 = 0x931e_8875;
const INIT_B: u32 = 0x8b51_f9dd;
const MULT_B: u32 = 0x58f3_8ded;
const MIX_MULT_L: u32 = 0xca01_f9dd;
const MIX_MULT_R: u32 = 0x4973_f715;
const XSHIFT: u32 = 16;
const POOL_SIZE: usize = 4;
const PCG_MULT: u128 = 0x2360_ED05_1FC6_5DA4_4385_DF64_9FCC_F645;

fn hashmix(value: u32, hash_const: &mut u32) -> u32 {
    let mut value = value ^ *hash_const;
    *hash_const = hash_const.wrapping_mul(MULT_A);
    value = value.wrapping_mul(*hash_const);
    value ^ (value >> XSHIFT)
}

fn mix(x: u32, y: u32) -> u32 {
    let result = MIX_MULT_L.wrapping_mul(x).wrapping_sub(MIX_MULT_R.wrapping_mul(y));
    result ^ (result >> XSHIFT)
}

/// Slova `uint32` celého čísla (nejnižší první; nula je jedno slovo).
fn words(mut value: u64) -> Vec<u32> {
    let mut out = Vec::new();
    while value > 0 {
        out.push((value & 0xFFFF_FFFF) as u32);
        value >>= 32;
    }
    if out.is_empty() {
        out.push(0);
    }
    out
}

/// `SeedSequence(entropy).generate_state(4, uint64)` pro seznam 64bitových čísel.
fn seed_sequence_state(entropy: &[u64]) -> [u64; 4] {
    let entropy: Vec<u32> = entropy.iter().flat_map(|&x| words(x)).collect();
    let mut pool = [0_u32; POOL_SIZE];
    let mut hash_const = INIT_A;
    for (i, slot) in pool.iter_mut().enumerate() {
        *slot = hashmix(entropy.get(i).copied().unwrap_or(0), &mut hash_const);
    }
    for i_src in 0..POOL_SIZE {
        for i_dst in 0..POOL_SIZE {
            if i_src != i_dst {
                let mixed = hashmix(pool[i_src], &mut hash_const);
                pool[i_dst] = mix(pool[i_dst], mixed);
            }
        }
    }
    for &extra in entropy.iter().skip(POOL_SIZE) {
        for slot in pool.iter_mut() {
            let mixed = hashmix(extra, &mut hash_const);
            *slot = mix(*slot, mixed);
        }
    }
    let mut hash_const = INIT_B;
    let mut state = [0_u32; 8];
    for (i, out) in state.iter_mut().enumerate() {
        let mut value = pool[i % POOL_SIZE] ^ hash_const;
        hash_const = hash_const.wrapping_mul(MULT_B);
        value = value.wrapping_mul(hash_const);
        *out = value ^ (value >> XSHIFT);
    }
    let mut out = [0_u64; 4];
    for (i, item) in out.iter_mut().enumerate() {
        *item = u64::from(state[2 * i]) | (u64::from(state[2 * i + 1]) << 32);
    }
    out
}

/// PCG64 (XSL-RR 128/64) s polovičním bufferem pro 32bitové tahy jako numpy.
#[derive(Clone, Debug)]
pub struct Pcg64 {
    state: u128,
    inc: u128,
    has_uint32: bool,
    uinteger: u32,
}

impl Pcg64 {
    /// Generátor jako `np.random.Generator(PCG64(SeedSequence([entropy...])))`.
    pub fn from_entropy(entropy: &[u64]) -> Pcg64 {
        let val = seed_sequence_state(entropy);
        let initstate = (u128::from(val[0]) << 64) | u128::from(val[1]);
        let initseq = (u128::from(val[2]) << 64) | u128::from(val[3]);
        let mut rng = Pcg64 { state: 0, inc: (initseq << 1) | 1, has_uint32: false, uinteger: 0 };
        rng.step();
        rng.state = rng.state.wrapping_add(initstate);
        rng.step();
        rng
    }

    /// `rng.generator(seed, *parts)`: `SeedSequence([seed & MASK64, stable_int(*parts)])`.
    pub fn for_parts(seed: u64, parts: &[Part<'_>]) -> Pcg64 {
        Pcg64::from_entropy(&[seed, stable_int(parts)])
    }

    fn step(&mut self) {
        self.state = self.state.wrapping_mul(PCG_MULT).wrapping_add(self.inc);
    }

    pub fn next_u64(&mut self) -> u64 {
        self.step();
        let rotate = (self.state >> 122) as u32;
        let xored = ((self.state >> 64) as u64) ^ (self.state as u64);
        xored.rotate_right(rotate)
    }

    fn next_u32(&mut self) -> u32 {
        if self.has_uint32 {
            self.has_uint32 = false;
            return self.uinteger;
        }
        let next = self.next_u64();
        self.has_uint32 = true;
        self.uinteger = (next >> 32) as u32;
        (next & 0xFFFF_FFFF) as u32
    }

    /// `rng.random()`: `[0, 1)` s 53 bity.
    pub fn random(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / 9_007_199_254_740_992.0)
    }

    /// `rng.uniform(low, high)`.
    pub fn uniform(&mut self, low: f64, high: f64) -> f64 {
        low + (high - low) * self.random()
    }

    /// `rng.integers(low, high)` (horní mez mimo) pro rozsah do 2^32.
    pub fn integers(&mut self, low: i64, high: i64) -> i64 {
        let range = (high - 1 - low) as u64;
        assert!(range <= 0xFFFF_FFFF, "integers: rozsah nad 2^32 se nepoužívá");
        if range == 0 {
            return low;
        }
        if range == 0xFFFF_FFFF {
            return low + i64::from(self.next_u32());
        }
        let exclusive = range + 1;
        let mut m = u64::from(self.next_u32()) * exclusive;
        let mut leftover = m & 0xFFFF_FFFF;
        if leftover < exclusive {
            let threshold = (0xFFFF_FFFF_u64 - range) % exclusive;
            while leftover < threshold {
                m = u64::from(self.next_u32()) * exclusive;
                leftover = m & 0xFFFF_FFFF;
            }
        }
        low + (m >> 32) as i64
    }

    /// `rng.choice(len(p), p=p)`: normalizované kumulativní součty a `searchsorted(side="right")`.
    pub fn choice(&mut self, probabilities: &[f64]) -> usize {
        let mut cdf = Vec::with_capacity(probabilities.len());
        let mut total = 0.0;
        for &p in probabilities {
            total += p;
            cdf.push(total);
        }
        let last = *cdf.last().expect("neprázdné váhy");
        for item in cdf.iter_mut() {
            *item /= last;
        }
        let u = self.random();
        cdf.partition_point(|&c| c <= u)
    }
}
