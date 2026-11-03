//! Deterministická náhoda enginu: zrcadlo `cee.v2.rng`.
//!
//! Každý náhodný tah závisí jen na semínku světa a na stabilních ID toho, čeho
//! se týká (tik, skupina, změna, varianta), nikdy na pořadí ani na počtu
//! ostatních objektů. Port je bit po bitu: [`stable_int`] je BLAKE2b s
//! 8bajtovým výstupem nad textovou podobou částí, [`Stream`] je SplitMix64
//! s Lemirovým výběrem bez zkreslení. Vektory z Pythonu jsou v
//! `tests/fixtures/rng.json` a testy je ověřují.
//!
//! Fáze si proud náhody tvoří sama z klíče (`Stream::new(seed, &[...])`), takže
//! souběžné (rayon) zpracování skupin dává stejný výsledek při libovolném počtu
//! vláken: žádný sdílený stav generátoru neexistuje.

use blake2::digest::{Update, VariableOutput};
use blake2::Blake2bVar;

pub use cee_core::transmission::{hash_normal, splitmix64};

const GOLDEN: u64 = 0x9E37_79B9_7F4A_7C15;
const MIX_1: u64 = 0xBF58_476D_1CE4_E5B9;
const MIX_2: u64 = 0x94D0_49BB_1331_11EB;
const FLOAT53: f64 = (1_u64 << 53) as f64;
/// Nejvyšší střední hodnota jednoho kusu Poissonova tahu.
const POISSON_CHUNK: f64 = 30.0;
/// Pojistka inverze Poissonova rozdělení.
const POISSON_MAX: u32 = 120;

/// Část klíče náhody. Textová podoba (`str(part)` v Pythonu) určuje hash.
#[derive(Clone, Copy, Debug)]
pub enum Part<'a> {
    Str(&'a str),
    Int(i64),
    Uint(u64),
    /// Desetinné číslo se píše jako `repr(float)` v Pythonu.
    Float(f64),
}

impl<'a> From<&'a str> for Part<'a> {
    fn from(value: &'a str) -> Self {
        Part::Str(value)
    }
}
impl<'a> From<&'a String> for Part<'a> {
    fn from(value: &'a String) -> Self {
        Part::Str(value)
    }
}
impl From<i64> for Part<'_> {
    fn from(value: i64) -> Self {
        Part::Int(value)
    }
}
impl From<u64> for Part<'_> {
    fn from(value: u64) -> Self {
        Part::Uint(value)
    }
}
impl From<u32> for Part<'_> {
    fn from(value: u32) -> Self {
        Part::Uint(u64::from(value))
    }
}
impl From<usize> for Part<'_> {
    fn from(value: usize) -> Self {
        Part::Uint(value as u64)
    }
}
impl From<f64> for Part<'_> {
    fn from(value: f64) -> Self {
        Part::Float(value)
    }
}

/// Textová podoba čísla jako `repr(float)` v Pythonu (nejkratší zápis, který se čte zpět).
pub fn py_float_repr(value: f64) -> String {
    if value.is_nan() {
        return "nan".into();
    }
    if value.is_infinite() {
        return if value > 0.0 { "inf" } else { "-inf" }.into();
    }
    if value == 0.0 {
        return if value.is_sign_negative() { "-0.0" } else { "0.0" }.into();
    }
    // `{:e}` dá nejkratší číslice: „d.ddde±x“.
    let text = format!("{:e}", value.abs());
    let (mantissa, exponent) = text.split_once('e').expect("exponent");
    let digits: String = mantissa.chars().filter(|c| *c != '.').collect();
    let decpt: i32 = exponent.parse::<i32>().expect("exponent") + 1;
    let length = digits.len() as i32;
    let sign = if value < 0.0 { "-" } else { "" };
    let body = if -4 < decpt && decpt <= 16 {
        if decpt <= 0 {
            format!("0.{}{}", "0".repeat((-decpt) as usize), digits)
        } else if decpt >= length {
            format!("{}{}.0", digits, "0".repeat((decpt - length) as usize))
        } else {
            format!("{}.{}", &digits[..decpt as usize], &digits[decpt as usize..])
        }
    } else {
        let mantissa = if length > 1 { format!("{}.{}", &digits[..1], &digits[1..]) } else { digits.clone() };
        let power = decpt - 1;
        format!("{}e{}{:02}", mantissa, if power < 0 { "-" } else { "+" }, power.abs())
    };
    format!("{sign}{body}")
}

/// 64bitový otisk částí; `("ab", "c")` a `("a", "bc")` se liší.
pub fn stable_int(parts: &[Part<'_>]) -> u64 {
    let mut hasher = Blake2bVar::new(8).expect("délka výstupu");
    for part in parts {
        hasher.update(b"\x1f");
        match part {
            Part::Str(text) => hasher.update(text.as_bytes()),
            Part::Int(number) => hasher.update(number.to_string().as_bytes()),
            Part::Uint(number) => hasher.update(number.to_string().as_bytes()),
            Part::Float(number) => hasher.update(py_float_repr(*number).as_bytes()),
        }
    }
    let mut out = [0_u8; 8];
    hasher.finalize_variable(&mut out).expect("výstup");
    u64::from_be_bytes(out)
}

/// Čitelný a stabilní identifikátor odvozený z původu objektu: `prefix:hash16`.
pub fn stable_id(prefix: &str, parts: &[Part<'_>]) -> String {
    let mut all = Vec::with_capacity(parts.len() + 1);
    all.push(Part::Str(prefix));
    all.extend_from_slice(parts);
    format!("{prefix}:{:016x}", stable_int(&all))
}

/// Kumulativní součty vah počítané postupně v pořadí indexů.
///
/// Váhy musí být nezáporné a konečné se součtem kladným, jinak chyba.
pub fn cumulative(weights: &[f64]) -> Result<Vec<f64>, String> {
    if weights.is_empty() {
        return Err("choice: prázdné váhy.".into());
    }
    let mut total = 0.0;
    let mut out = Vec::with_capacity(weights.len());
    for &weight in weights {
        total += weight;
        out.push(total);
    }
    if !(total > 0.0 && total.is_finite()) || weights.iter().any(|&w| w < 0.0) {
        return Err("choice: váhy musí být nezáporné a konečné se součtem kladným.".into());
    }
    Ok(out)
}

/// Index podle předpočtených kumulativních vah a `u` z `[0, 1)` (`Stream.pick`).
pub fn pick(cumulated: &[f64], u: f64) -> usize {
    let total = *cumulated.last().expect("neprázdné váhy");
    let target = u * total;
    // bisect_right: první index s c[i] > target
    let index = cumulated.partition_point(|&c| c <= target);
    if index >= cumulated.len() {
        // bisect_left(total): první i s c[i] >= total
        return cumulated.partition_point(|&c| c < total);
    }
    index
}

/// Poissonův tah inverzí CDF pro `0 < lam <= 30` a `u` z `[0, 1)`.
pub fn poisson_inversion(lam: f64, u: f64) -> u32 {
    let mut p = (-lam).exp();
    let mut cdf = p;
    let mut count = 0_u32;
    while u > cdf && count < POISSON_MAX {
        count += 1;
        p *= lam / f64::from(count);
        cdf += p;
    }
    count
}

/// Přenositelný proud náhody pro jednu kombinaci (semínko, části).
///
/// Jediný stav je `state`; viz popis algoritmů v `cee.v2.rng.Stream`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Stream {
    pub state: u64,
}

impl Stream {
    /// `key = stable_int("stream", seed & (2**64 - 1), *parts)`.
    pub fn new(seed: u64, parts: &[Part<'_>]) -> Stream {
        let mut all = Vec::with_capacity(parts.len() + 2);
        all.push(Part::Str("stream"));
        all.push(Part::Uint(seed));
        all.extend_from_slice(parts);
        Stream { state: stable_int(&all) }
    }

    /// Proud s daným 64bitovým klíčem (počáteční stav).
    pub fn from_key(key: u64) -> Stream {
        Stream { state: key }
    }

    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(GOLDEN);
        let mut z = (self.state ^ (self.state >> 30)).wrapping_mul(MIX_1);
        z = (z ^ (z >> 27)).wrapping_mul(MIX_2);
        z ^ (z >> 31)
    }

    /// Rovnoměrně na `[0, 1)` s 53 bity.
    pub fn random(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / FLOAT53
    }

    /// Celé číslo `0 <= i < n` bez zkreslení (Lemirova metoda); `n >= 1`.
    pub fn integers(&mut self, n: u64) -> u64 {
        assert!(n >= 1, "integers: n musí být aspoň 1.");
        let mut m = u128::from(self.next_u64()) * u128::from(n);
        let mut low = m as u64;
        if low < n {
            let threshold = n.wrapping_neg() % n;
            while low < threshold {
                m = u128::from(self.next_u64()) * u128::from(n);
                low = m as u64;
            }
        }
        (m >> 64) as u64
    }

    /// Index podle vah (`choice(n, p)`); jedno `random()`.
    pub fn choice(&mut self, weights: &[f64]) -> Result<usize, String> {
        let cumulated = cumulative(weights)?;
        let u = self.random();
        Ok(pick(&cumulated, u))
    }

    /// Normální rozdělení N(mean, sd²), Box–Muller (dva tahy).
    pub fn normal(&mut self, mean: f64, sd: f64) -> f64 {
        let u1 = ((self.next_u64() >> 11) as f64 + 0.5) / FLOAT53;
        let u2 = ((self.next_u64() >> 11) as f64 + 0.5) / FLOAT53;
        mean + sd * ((-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos())
    }

    /// Poissonův tah se střední hodnotou `lam` (součet kusů po nejvýš 30).
    pub fn poisson(&mut self, lam: f64) -> u64 {
        if lam <= 0.0 {
            return 0;
        }
        let chunks = ((lam / POISSON_CHUNK).ceil() as u64).max(1);
        let part = lam / chunks as f64;
        (0..chunks).map(|_| u64::from(poisson_inversion(part, self.random()))).sum()
    }
}

/// Klíč tahu inovací skupiny a kódu v kroku: `stable_int(seed, "innovation", tick, skupina, kód)`.
pub fn innovation_group_key(seed: i64, tick: u64, group: &str, code: &str) -> u64 {
    stable_int(&[Part::Int(seed), Part::Str("innovation"), Part::Uint(tick), Part::Str(group), Part::Str(code)])
}

/// Poissonův tah závislý jen na klíčích řádku a sloupce (`rng.hash_poisson` po prvcích).
pub fn hash_poisson(row_key: u64, column_key: u64, expected: f64) -> u64 {
    if !(expected.is_finite() && expected >= 0.0) {
        panic!("Střední hodnoty Poissonova rozdělení musí být nezáporná konečná čísla.");
    }
    if expected <= 0.0 {
        return 0;
    }
    let first = splitmix64(row_key ^ splitmix64(column_key));
    if expected <= 30.0 {
        let u = ((first >> 11) as f64 + 0.5) / FLOAT53;
        let mut p = (-expected).exp();
        let mut cdf = p;
        let mut count = 0_u64;
        for k in 1..=120_u32 {
            let more = (cdf + p > cdf) || f64::from(k) <= expected;
            if !(u > cdf && more) {
                break;
            }
            count = u64::from(k);
            p *= expected / f64::from(k);
            cdf += p;
        }
        count
    } else {
        Stream::from_key(splitmix64(first)).poisson(expected)
    }
}
