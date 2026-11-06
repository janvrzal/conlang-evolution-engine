//! Hláskové tvary protojazyka (dok. 25).
//!
//! Generátor skládá slova z inventáře jazyka podle dat o skutečných jazycích
//! (`v2_protoform.json`, sestavuje `scripts/build_v2_protoform.py`):
//!
//! - **četnost hlásek** podle pozice ve slově (začátek, vnitřek, konec) z ASJP: třída hlásky
//!   ASJP a její podíl ve slovech jazyků, které ji mají; každý jazyk má navíc vlastní
//!   „příchuť“ (náhodný násobek váhy hlásky, jazyky se v četnostech liší);
//! - **slabičná stavba** WALS 12A (jednoduchá / středně složitá / složitá, Maddieson 2013),
//!   zadaná ve spec nebo vylosovaná podle podílů ve WALS; počet slabik, podíl slov na
//!   samohlásku, slov na souhlásku a skupin souhlásek změřený na slovech ASJP téhož typu;
//! - **fonotaktika kód**: implikační hierarchie nosovky ⊂ sonory ⊂ všechny souhlásky
//!   (jazyk, který připouští na konci slabiky ražené, připouští i sonory);
//! - **Zipfův zákon zkracování**: časté pojmy mají víc krátkých slov (cíl ze shody délky
//!   a frekvence v ASJP);
//! - **dětská slova** pro matku a otce (Murdock 1959, Jakobson 1962): nosovka + *a* pro
//!   matku, retná nebo zubná ražená + *a* pro otce;
//! - **zvuková symbolika** (Blasi a kol. 2016): slabá preference hlásek u vybraných pojmů.
//!
//! Slova zadaná autorem (`fixed`) mají vždy přednost. Stejné semínko dá stejný jazyk;
//! slovo pojmu má vlastní proud náhody, takže přidaný pojem nezmění slova ostatních
//! (kromě vzácné kolize stejných tvarů).

use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;

use serde_json::Value;

use cee_core::assess::pairwise_sum;

use crate::concepts::ConceptData;
use crate::rng::{Part, Stream};
use crate::segments::SegmentTable;

/// Zipfovské váhy (první v seznamu nejčastější): `1 / k^0.7`, normalizované. Generátor je
/// už používá jen pro tóny.
pub fn zipf(count: usize) -> Vec<f64> {
    let weights: Vec<f64> = (1..=count).map(|k| 1.0 / (k as f64).powf(0.7)).collect();
    let total = pairwise_sum(&weights);
    weights.iter().map(|w| w / total).collect()
}

/// Slabičná stavba jazyka (WALS 12A).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum SyllableType {
    /// (C)V: bez kód a bez skupin souhlásek.
    Simple,
    /// (C)(C)V(C): jedna souhláska na konci slabiky, na začátku nejvýš ražená + sonora.
    Moderate,
    /// Skupiny souhlásek na začátku i na konci slabiky.
    Complex,
}

impl SyllableType {
    pub const ALL: [SyllableType; 3] = [Self::Simple, Self::Moderate, Self::Complex];

    pub fn parse(name: &str) -> Option<SyllableType> {
        match name {
            "simple" => Some(Self::Simple),
            "moderate" => Some(Self::Moderate),
            "complex" => Some(Self::Complex),
            _ => None,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::Simple => "simple",
            Self::Moderate => "moderate",
            Self::Complex => "complex",
        }
    }

    fn index(self) -> usize {
        self as usize
    }
}

/// Podíl jazyků, jejichž slovo pro matku (otce) je dětské slovo typu *mama* (*papa*, *tata*):
/// Murdock 1959 našel slabiku typu *ma* ve slově „matka“ u 52 % jazyků a *pa*/*ta* ve slově
/// „otec“ u 55 %; WOLD (41 jazyků) dává nosovku ve slově „matka“ u 71 % (dok. 25).
pub const NURSERY_SHARE: f64 = 0.55;
/// Směrodatná odchylka log násobku váhy hlásky v jazyce („příchuť“ jazyka). ASJP dává mezi
/// jazyky 0,72 včetně šumu krátkých seznamů (40–100 slov); bereme menší část.
pub const LANGUAGE_SPREAD: f64 = 0.5;
/// Násobek váhy souhlásky, která by zopakovala předchozí souhlásku slova (OCP: Frisch,
/// Pierrehumbert a Broe 2004 — sousední stejné souhlásky jsou v lexikonech vzácné).
pub const OCP_REPEAT: f64 = 0.3;
/// Síla Zipfova zkracování: `P(k slabik) ∝ P_typ(k) · exp(−β · z · k)`, z = standardizovaný
/// logaritmus frekvence pojmu. Kalibrováno na Spearmanovo ρ(frekvence, délka) z ASJP.
pub const ABBREVIATION_BETA: f64 = 0.2;
/// Váha hlásky u pojmu se zvukovou symbolikou se násobí `RR^γ` (RR z Blasi a kol. 2016).
/// Kalibrováno tak, aby generované RR bylo v řádu publikovaného.
pub const SYMBOLISM_EXPONENT: f64 = 1.0;
/// Podíl skupin s + ražená mezi začátky slova se skupinou u složité slabiky (*st-*, *sk-*).
const S_CLUSTER_SHARE: f64 = 0.3;

const INITIAL: usize = 0;
const MEDIAL: usize = 1;
const FINAL: usize = 2;
const POSITIONS: [&str; 3] = ["initial", "medial", "final"];

/// Statistiky slabičného typu z ASJP × WALS 12A.
#[derive(Clone, Debug)]
pub struct TypeProfile {
    /// Podíl slov s 1, 2, 3 a 4+ slabikami.
    pub syllables: [f64; 4],
    pub vowel_initial: f64,
    pub consonant_final: f64,
    pub initial_cluster: f64,
    pub medial_cluster: f64,
    pub final_cluster: f64,
    /// Počet jazyků typu ve WALS (podíl pro losování typu).
    pub wals_languages: f64,
}

/// Data generátoru (`v2_protoform.json`).
pub struct ProtoformData {
    ipa_to_asjp: HashMap<String, char>,
    /// `[souhlásky | samohlásky][pozice]`: třída ASJP → podíl.
    weights: [[HashMap<char, f64>; 3]; 2],
    types: [TypeProfile; 3],
    /// Pojem → (třída ASJP, poměr rizik).
    symbolism: HashMap<String, Vec<(char, f64)>>,
}

fn number(value: &Value, key: &str) -> Result<f64, String> {
    value[key]
        .as_f64()
        .ok_or_else(|| format!("v2_protoform.json: chybí číslo '{key}'"))
}

fn class_char(key: &str) -> Result<char, String> {
    let mut chars = key.chars();
    match (chars.next(), chars.next()) {
        (Some(c), None) => Ok(c),
        _ => Err(format!(
            "v2_protoform.json: třída ASJP '{key}' není jeden znak"
        )),
    }
}

impl ProtoformData {
    pub fn from_json(text: &str) -> Result<ProtoformData, String> {
        let root: Value =
            serde_json::from_str(text).map_err(|e| format!("v2_protoform.json: {e}"))?;
        let mut ipa_to_asjp = HashMap::new();
        for (ipa, class) in root["ipa_to_asjp"].as_object().into_iter().flatten() {
            ipa_to_asjp.insert(ipa.clone(), class_char(class.as_str().unwrap_or_default())?);
        }
        let table = |kind: &str, position: &str| -> Result<HashMap<char, f64>, String> {
            let mut out = HashMap::new();
            for (class, share) in root["segment_weights"][kind][position]
                .as_object()
                .into_iter()
                .flatten()
            {
                let share = share
                    .as_f64()
                    .filter(|s| *s > 0.0 && s.is_finite())
                    .ok_or_else(|| format!("v2_protoform.json: váha {kind}.{position}.{class}"))?;
                out.insert(class_char(class)?, share);
            }
            if out.is_empty() {
                return Err(format!("v2_protoform.json: prázdné váhy {kind}.{position}"));
            }
            Ok(out)
        };
        let mut weights: [[HashMap<char, f64>; 3]; 2] = Default::default();
        for (k, kind) in ["consonants", "vowels"].iter().enumerate() {
            for (p, position) in POSITIONS.iter().enumerate() {
                weights[k][p] = table(kind, position)?;
            }
        }
        let profile = |name: &str| -> Result<TypeProfile, String> {
            let entry = &root["syllable_types"][name];
            Ok(TypeProfile {
                syllables: [
                    number(entry, "syllables_1")?,
                    number(entry, "syllables_2")?,
                    number(entry, "syllables_3")?,
                    number(entry, "syllables_4")?,
                ],
                vowel_initial: number(entry, "vowel_initial")?,
                consonant_final: number(entry, "consonant_final")?,
                initial_cluster: number(entry, "initial_cluster")?,
                medial_cluster: number(entry, "medial_cluster")?,
                final_cluster: number(entry, "final_cluster")?,
                wals_languages: number(entry, "wals_languages")?,
            })
        };
        let types = [
            profile("simple")?,
            profile("moderate")?,
            profile("complex")?,
        ];
        let mut symbolism: HashMap<String, Vec<(char, f64)>> = HashMap::new();
        for entry in root["symbolism"].as_array().into_iter().flatten() {
            let concept = entry["concept"].as_str().unwrap_or_default().to_owned();
            let class = class_char(entry["symbol"].as_str().unwrap_or_default())?;
            symbolism
                .entry(concept)
                .or_default()
                .push((class, number(entry, "risk_ratio")?));
        }
        Ok(ProtoformData {
            ipa_to_asjp,
            weights,
            types,
            symbolism,
        })
    }

    pub fn shared() -> &'static ProtoformData {
        static DATA: OnceLock<ProtoformData> = OnceLock::new();
        DATA.get_or_init(|| {
            ProtoformData::from_json(crate::data::PROTOFORM_JSON).expect("v2_protoform.json")
        })
    }

    pub fn profile(&self, kind: SyllableType) -> &TypeProfile {
        &self.types[kind.index()]
    }

    /// Poměry rizik zvukové symboliky pojmu (třída ASJP, RR).
    pub fn symbolism(&self, concept: &str) -> &[(char, f64)] {
        self.symbolism.get(concept).map_or(&[], Vec::as_slice)
    }

    /// Třída ASJP hlásky v IPA (bez diakritiky a sekundární artikulace), `None` u neznámé.
    pub fn asjp_class(&self, ipa: &str) -> Option<char> {
        let core: Vec<char> = ipa.chars().filter(|c| !is_modifier(*c)).collect();
        if core.len() >= 2 {
            let two: String = core[..2].iter().collect();
            if let Some(class) = self.ipa_to_asjp.get(&two) {
                return Some(*class);
            }
        }
        core.first()
            .and_then(|c| self.ipa_to_asjp.get(&c.to_string()))
            .copied()
    }
}

fn is_modifier(c: char) -> bool {
    matches!(
        c,
        'ʰ' | 'ʷ'
            | 'ʲ'
            | 'ː'
            | 'ˑ'
            | 'ˀ'
            | 'ʼ'
            | 'ˠ'
            | 'ˤ'
            | 'ⁿ'
            | 'ᵐ'
            | 'ᵑ'
            | '͡'
            | '͜'
            | '˥'..='˩'
    ) || ('\u{0300}'..='\u{036F}').contains(&c)
}

/// Způsob tvoření pro fonotaktiku (z třídy ASJP, jinak z rysů tabulky hlásek).
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum Manner {
    Nasal,
    Liquid,
    Glide,
    Obstruent,
}

#[derive(Clone, Debug)]
struct Segment {
    ipa: String,
    class: Option<char>,
    manner: Manner,
}

fn manner_of(ipa: &str, class: Option<char>) -> Manner {
    match class {
        Some('m' | 'n' | 'N' | '5' | '4') => Manner::Nasal,
        Some('r' | 'l' | 'L') => Manner::Liquid,
        Some('w' | 'y') => Manner::Glide,
        Some(_) => Manner::Obstruent,
        None => {
            let table = SegmentTable::default_table();
            match table.id_of(ipa) {
                Ok(id) if table.feature(id, "nas") == 1 => Manner::Nasal,
                Ok(id) if table.feature(id, "son") == 1 && table.feature(id, "cons") == 1 => {
                    Manner::Liquid
                }
                Ok(id) if table.feature(id, "son") == 1 => Manner::Glide,
                _ => Manner::Obstruent,
            }
        }
    }
}

/// Neznělá ražená (druhý člen skupiny *sp-*, *st-*, *sk-*).
fn is_voiceless_stop(class: Option<char>) -> bool {
    matches!(class, Some('p' | 't' | 'k' | 'q' | 'T'))
}

/// Hrtanová souhláska (*h*, *ʔ*): ve skupinách souhlásek ji generátor nepoužívá.
fn is_laryngeal(class: Option<char>) -> bool {
    matches!(class, Some('h' | '7'))
}

/// Znělá ražená nebo třená (na konci slova ve skupině souhlásek ji generátor nedává:
/// koncové skupiny jsou typicky *-nt*, *-rk*, *-ls*).
fn is_voiced_obstruent(class: Option<char>) -> bool {
    matches!(class, Some('b' | 'd' | 'g' | 'G' | 'v' | 'z' | 'Z' | 'j'))
}

/// Ražená nebo třená souhláska, která smí stát ve skupině souhlásek.
fn cluster_obstruent(segment: &Segment) -> bool {
    segment.manner == Manner::Obstruent && !is_laryngeal(segment.class)
}

fn is_sibilant(class: Option<char>) -> bool {
    matches!(class, Some('s' | 'S'))
}

/// Vstupy generátoru protojazyka.
pub struct ProtoSpec<'a> {
    pub concepts: &'a [String],
    pub seed: u64,
    pub consonants: &'a [String],
    pub vowels: &'a [String],
    /// Slova zadaná autorem (pojem → IPA).
    pub fixed: &'a HashMap<String, String>,
    pub tones: &'a [String],
    pub known_frequencies: Option<&'a HashMap<String, f64>>,
    /// Slabičná stavba; `None` = vylosuje se podle podílů typů ve WALS 12A.
    pub syllables: Option<SyllableType>,
}

/// Tvary (pojem → IPA) a frekvence (pojem → hodnota) protojazyka.
pub type ProtoWords = (HashMap<String, String>, HashMap<String, f64>);

/// Slabičná stavba jazyka: zadaná, nebo vylosovaná ze semínka (podíly typů ve WALS 12A).
pub fn syllable_type(spec: &ProtoSpec<'_>) -> SyllableType {
    if let Some(given) = spec.syllables {
        return given;
    }
    let data = ProtoformData::shared();
    let weights: Vec<f64> = SyllableType::ALL
        .iter()
        .map(|t| data.profile(*t).wals_languages)
        .collect();
    let mut rng = Stream::new(
        spec.seed,
        &[Part::Str("protolanguage"), Part::Str("syllables")],
    );
    SyllableType::ALL[rng.choice(&weights).unwrap_or(1)]
}

/// Fonologie jednoho jazyka: hlásky s vahami podle pozice a pravděpodobnosti stavby slova.
struct Phonology<'d> {
    data: &'d ProtoformData,
    kind: SyllableType,
    consonants: Vec<Segment>,
    vowels: Vec<Segment>,
    /// `[pozice][hláska]`
    consonant_weights: [Vec<f64>; 3],
    vowel_weights: [Vec<f64>; 3],
    /// Smí souhláska stát na konci slabiky?
    coda: Vec<bool>,
    tones: Vec<String>,
    tone_weights: Vec<f64>,
    vowel_initial: f64,
    final_coda: f64,
    medial_coda: f64,
    initial_cluster: f64,
    final_cluster: f64,
}

/// Pravděpodobnost kódy vnitřní slabiky `p` taková, že podíl slov se skupinou souhlásek
/// uvnitř (`E_k[1 − (1 − p)^(k−1)]`) je `target` (půlením intervalu).
fn medial_coda_probability(syllables: &[f64; 4], target: f64) -> f64 {
    let share = |p: f64| -> f64 {
        let total: f64 = syllables.iter().sum();
        syllables
            .iter()
            .enumerate()
            .map(|(i, w)| w / total * (1.0 - (1.0 - p).powi(i as i32)))
            .sum()
    };
    let (mut low, mut high) = (0.0_f64, 1.0_f64);
    if share(high) <= target {
        return 1.0;
    }
    for _ in 0..50 {
        let mid = 0.5 * (low + high);
        if share(mid) < target {
            low = mid;
        } else {
            high = mid;
        }
    }
    0.5 * (low + high)
}

impl<'d> Phonology<'d> {
    fn new(spec: &ProtoSpec<'_>, data: &'d ProtoformData) -> Phonology<'d> {
        let kind = syllable_type(spec);
        let mut rng = Stream::new(
            spec.seed,
            &[Part::Str("protolanguage"), Part::Str("phonology")],
        );
        let segments = |list: &[String]| -> Vec<Segment> {
            list.iter()
                .map(|ipa| {
                    let class = data.asjp_class(ipa);
                    Segment {
                        ipa: ipa.clone(),
                        class,
                        manner: manner_of(ipa, class),
                    }
                })
                .collect()
        };
        let consonants = segments(spec.consonants);
        let vowels = segments(spec.vowels);
        let flavour = |rng: &mut Stream, count: usize| -> Vec<f64> {
            (0..count)
                .map(|_| rng.normal(0.0, LANGUAGE_SPREAD).exp())
                .collect()
        };
        let consonant_flavour = flavour(&mut rng, consonants.len());
        let vowel_flavour = flavour(&mut rng, vowels.len());
        let weights = |list: &[Segment], kind: usize, flavour: &[f64]| -> [Vec<f64>; 3] {
            let mut out: [Vec<f64>; 3] = Default::default();
            for (p, slot) in out.iter_mut().enumerate() {
                let table = &data.weights[kind][p];
                let fallback = table.values().sum::<f64>() / table.len() as f64;
                *slot = list
                    .iter()
                    .zip(flavour)
                    .map(|(segment, f)| {
                        let base = segment
                            .class
                            .and_then(|c| table.get(&c).copied())
                            .unwrap_or(fallback);
                        let sharing = match segment.class {
                            Some(c) => list.iter().filter(|s| s.class == Some(c)).count(),
                            None => 1,
                        };
                        base / sharing as f64 * f
                    })
                    .collect();
            }
            out
        };
        let consonant_weights = weights(&consonants, 0, &consonant_flavour);
        let vowel_weights = weights(&vowels, 1, &vowel_flavour);
        // Fonotaktika kód: nosovky ⊂ sonory ⊂ všechny souhlásky.
        let mut level = match kind {
            SyllableType::Simple => 0,
            SyllableType::Moderate => 1 + rng.integers(3) as usize,
            SyllableType::Complex => 3,
        };
        let allowed = |level: usize, segment: &Segment| match level {
            0 => false,
            1 => segment.manner == Manner::Nasal,
            2 => segment.manner != Manner::Obstruent,
            _ => true,
        };
        while level > 0 && level < 3 && !consonants.iter().any(|s| allowed(level, s)) {
            level += 1;
        }
        let coda: Vec<bool> = consonants.iter().map(|s| allowed(level, s)).collect();
        let profile = data.profile(kind);
        let consonant_start = (1.0 - profile.vowel_initial).max(1e-9);
        let (initial_cluster, medial_coda, final_cluster, final_coda) = match kind {
            SyllableType::Simple => (0.0, 0.0, 0.0, 0.0),
            SyllableType::Moderate => (
                profile.initial_cluster / consonant_start,
                medial_coda_probability(&profile.syllables, profile.medial_cluster),
                0.0,
                profile.consonant_final,
            ),
            SyllableType::Complex => (
                profile.initial_cluster / consonant_start,
                medial_coda_probability(&profile.syllables, profile.medial_cluster),
                profile.final_cluster / profile.consonant_final.max(1e-9),
                profile.consonant_final,
            ),
        };
        let tone_weights = if spec.tones.is_empty() {
            Vec::new()
        } else {
            zipf(spec.tones.len())
        };
        Phonology {
            data,
            kind,
            consonants,
            vowels,
            consonant_weights,
            vowel_weights,
            coda,
            tones: spec.tones.to_vec(),
            tone_weights,
            vowel_initial: profile.vowel_initial,
            final_coda,
            medial_coda,
            initial_cluster,
            final_cluster,
        }
    }

    /// Násobky vah hlásek pro pojem se zvukovou symbolikou (souhlásky, samohlásky).
    fn boosts(&self, concept: &str) -> (Vec<f64>, Vec<f64>) {
        let associations = self.data.symbolism(concept);
        let boost = |list: &[Segment]| -> Vec<f64> {
            list.iter()
                .map(|s| {
                    associations
                        .iter()
                        .filter(|(class, _)| s.class == Some(*class))
                        .map(|(_, rr)| rr.powf(SYMBOLISM_EXPONENT))
                        .product()
                })
                .collect()
        };
        (boost(&self.consonants), boost(&self.vowels))
    }

    /// Souhláska z pozice; `filter` vybírá dovolené, `previous` je předchozí souhláska slova.
    fn consonant(
        &self,
        rng: &mut Stream,
        position: usize,
        boost: &[f64],
        previous: Option<usize>,
        filter: impl Fn(usize, &Segment) -> bool,
    ) -> Option<usize> {
        let weights: Vec<f64> = self
            .consonants
            .iter()
            .enumerate()
            .map(|(i, s)| {
                if !filter(i, s) {
                    return 0.0;
                }
                let repeat = if previous == Some(i) { OCP_REPEAT } else { 1.0 };
                self.consonant_weights[position][i] * boost[i] * repeat
            })
            .collect();
        if weights.iter().sum::<f64>() <= 0.0 {
            return None;
        }
        rng.choice(&weights).ok()
    }

    fn vowel(&self, rng: &mut Stream, position: usize, boost: &[f64]) -> usize {
        let weights: Vec<f64> = self.vowel_weights[position]
            .iter()
            .zip(boost)
            .map(|(w, b)| w * b)
            .collect();
        rng.choice(&weights).unwrap_or(0)
    }

    fn tone(&self, rng: &mut Stream, word: &mut String) {
        if !self.tones.is_empty() {
            word.push_str(&self.tones[rng.choice(&self.tone_weights).unwrap_or(0)]);
        }
    }

    /// Počet slabik: rozdělení typu posunuté Zipfovým zkracováním (`z` = standardizovaný
    /// logaritmus frekvence pojmu).
    fn syllable_count(&self, rng: &mut Stream, z: f64) -> usize {
        let base = &self.data.profile(self.kind).syllables;
        let weights: Vec<f64> = base
            .iter()
            .enumerate()
            .map(|(i, w)| w * (-ABBREVIATION_BETA * z * (i + 1) as f64).exp())
            .collect();
        1 + rng.choice(&weights).unwrap_or(1)
    }

    /// Jedno slovo (bez kontroly jedinečnosti).
    fn word(&self, rng: &mut Stream, z: f64, boosts: &(Vec<f64>, Vec<f64>)) -> String {
        let (consonant_boost, vowel_boost) = boosts;
        let count = self.syllable_count(rng, z);
        let mut word = String::new();
        let mut previous: Option<usize> = None;
        for syllable in 0..count {
            let first = syllable == 0;
            let last = syllable + 1 == count;
            let onset = !(first && rng.random() < self.vowel_initial);
            let mut begins_with_vowel = first && !onset;
            if onset {
                let position = if first { INITIAL } else { MEDIAL };
                if first && rng.random() < self.initial_cluster {
                    if let Some((a, b)) = self.onset_cluster(rng, consonant_boost) {
                        word.push_str(&self.consonants[a].ipa);
                        word.push_str(&self.consonants[b].ipa);
                        previous = Some(b);
                    }
                }
                if word.is_empty() || !first {
                    match self.consonant(rng, position, consonant_boost, previous, |_, _| true) {
                        Some(c) => {
                            word.push_str(&self.consonants[c].ipa);
                            previous = Some(c);
                        }
                        None => begins_with_vowel = first,
                    }
                }
            }
            let coda = if last {
                rng.random() < self.final_coda
            } else {
                rng.random() < self.medial_coda
            };
            let position = if begins_with_vowel {
                INITIAL
            } else if last && !coda {
                FINAL
            } else {
                MEDIAL
            };
            word.push_str(&self.vowels[self.vowel(rng, position, vowel_boost)].ipa);
            self.tone(rng, &mut word);
            if coda {
                let position = if last { FINAL } else { MEDIAL };
                let cluster = last && rng.random() < self.final_cluster;
                let allowed = |i: usize, s: &Segment| {
                    self.coda[i] && (!cluster || matches!(s.manner, Manner::Nasal | Manner::Liquid))
                };
                if let Some(c) = self.consonant(rng, position, consonant_boost, previous, allowed) {
                    word.push_str(&self.consonants[c].ipa);
                    previous = Some(c);
                    if cluster {
                        let obstruent = |_: usize, s: &Segment| {
                            cluster_obstruent(s) && !is_voiced_obstruent(s.class)
                        };
                        if let Some(d) =
                            self.consonant(rng, FINAL, consonant_boost, previous, obstruent)
                        {
                            word.push_str(&self.consonants[d].ipa);
                            previous = Some(d);
                        }
                    }
                }
            }
        }
        word
    }

    /// Skupina souhlásek na začátku slova: ražená nebo třená + sonora (*pr-*, *kw-*, *fl-*),
    /// u složité slabiky i sykavka + neznělá ražená (*st-*); bez *h* a *ʔ*.
    fn onset_cluster(&self, rng: &mut Stream, boost: &[f64]) -> Option<(usize, usize)> {
        if self.kind == SyllableType::Complex && rng.random() < S_CLUSTER_SHARE {
            let s = self.consonant(rng, INITIAL, boost, None, |_, s| is_sibilant(s.class));
            if let Some(s) = s {
                if let Some(t) = self.consonant(rng, MEDIAL, boost, Some(s), |_, x| {
                    is_voiceless_stop(x.class)
                }) {
                    return Some((s, t));
                }
            }
        }
        let first = self.consonant(rng, INITIAL, boost, None, |_, s| {
            cluster_obstruent(s) && !is_sibilant(s.class)
        })?;
        let second = self.consonant(rng, MEDIAL, boost, Some(first), |_, s| {
            matches!(s.manner, Manner::Liquid | Manner::Glide)
        })?;
        Some((first, second))
    }

    /// Dětské slovo pro matku (nosovka) nebo otce (retná či zubná ražená) s nejotevřenější
    /// samohláskou: *mama*, *ma*, *ama*; *papa*, *tata*, *aba*. `None`, když jazyk hlásky nemá.
    fn nursery(&self, rng: &mut Stream, concept: &str) -> Option<String> {
        let preferred: &[(char, f64)] = match concept {
            "mother" => &[('m', 3.0), ('n', 2.0), ('5', 1.0), ('N', 0.5)],
            "father" => &[('p', 2.0), ('b', 2.0), ('t', 2.0), ('d', 1.0)],
            _ => return None,
        };
        let weights: Vec<f64> = self
            .consonants
            .iter()
            .map(|s| {
                preferred
                    .iter()
                    .find(|(c, _)| s.class == Some(*c))
                    .map_or(0.0, |(_, w)| *w)
            })
            .collect();
        if weights.iter().sum::<f64>() <= 0.0 {
            return None;
        }
        let consonant = &self.consonants[rng.choice(&weights).ok()?].ipa;
        let vowel = ['a', 'E', 'o', '3']
            .iter()
            .find_map(|c| self.vowels.iter().find(|v| v.class == Some(*c)))
            .unwrap_or(&self.vowels[0]);
        let mut syllable = format!("{consonant}{}", vowel.ipa);
        let mut bare = vowel.ipa.clone();
        if !self.tones.is_empty() {
            syllable.push_str(&self.tones[0]);
            bare.push_str(&self.tones[0]);
        }
        // Tvary podle WOLD: zdvojené (mama, baba) asi polovina, CV a VCV po čtvrtině.
        Some(match rng.choice(&[0.5, 0.25, 0.25]).ok()? {
            0 => format!("{syllable}{syllable}"),
            1 => syllable,
            _ => format!("{bare}{syllable}"),
        })
    }
}

/// Standardizovaný logaritmus frekvence každého pojmu (průměr 0, rozptyl 1).
fn standardized(frequencies: &HashMap<String, f64>, order: &[&String]) -> HashMap<String, f64> {
    let logs: Vec<f64> = order.iter().map(|c| frequencies[*c].ln()).collect();
    let n = logs.len().max(1) as f64;
    let mean = logs.iter().sum::<f64>() / n;
    let sd = (logs.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / n).sqrt();
    order
        .iter()
        .zip(&logs)
        .map(|(c, x)| {
            let z = if sd > 0.0 { (x - mean) / sd } else { 0.0 };
            ((*c).clone(), z)
        })
        .collect()
}

/// Tvary (IPA) a frekvence pojmů; stejné semínko dá stejný protojazyk.
pub fn protolanguage(spec: &ProtoSpec<'_>, data: &ConceptData) -> Result<ProtoWords, String> {
    if spec.consonants.is_empty() || spec.vowels.is_empty() {
        return Err("protojazyk potřebuje aspoň jednu souhlásku a jednu samohlásku".into());
    }
    let mut order: Vec<&String> = Vec::new();
    let mut seen = HashSet::new();
    for concept in spec.concepts {
        if seen.insert(concept) {
            order.push(concept);
        }
    }
    // Generované frekvence se losují vždy (vlastní proud), aby na nich tvary nezávisely.
    let mut rng = Stream::new(
        spec.seed,
        &[Part::Str("protolanguage"), Part::Str("frequency")],
    );
    let (low, high) = (0.05_f64.ln(), 0.8_f64.ln());
    let mut frequencies = HashMap::new();
    for (index, concept) in order.iter().enumerate() {
        let generated = if index < 20 {
            0.9
        } else {
            (low + (high - low) * rng.random()).exp()
        };
        let known = spec
            .known_frequencies
            .and_then(|given| given.get(*concept).copied())
            .or_else(|| data.frequency(concept));
        frequencies.insert((*concept).clone(), known.unwrap_or(generated));
    }
    let z = standardized(&frequencies, &order);
    let phonology = Phonology::new(spec, ProtoformData::shared());
    let mut used: HashSet<String> = spec.fixed.values().cloned().collect();
    let mut forms = HashMap::new();
    // Dětská slova pro rodiče se vybírají první, aby jim krátký tvar nevzalo jiné slovo.
    let nursery_first = |c: &&String| !matches!(c.as_str(), "mother" | "father");
    let mut ordered = order.clone();
    ordered.sort_by_key(nursery_first);
    for concept in &ordered {
        if let Some(given) = spec.fixed.get(*concept) {
            forms.insert((*concept).clone(), given.clone());
            continue;
        }
        let mut rng = Stream::new(
            spec.seed,
            &[
                Part::Str("protolanguage"),
                Part::Str("word"),
                Part::Str(concept),
            ],
        );
        let mut word = None;
        if rng.random() < NURSERY_SHARE {
            word = phonology
                .nursery(&mut rng, concept)
                .filter(|w| !used.contains(w));
        }
        let word = match word {
            Some(found) => found,
            None => {
                let boosts = phonology.boosts(concept);
                let mut found = String::new();
                for _ in 0..100 {
                    found = phonology.word(&mut rng, z[*concept], &boosts);
                    if found.chars().count() >= 2 && !used.contains(&found) {
                        break;
                    }
                }
                found
            }
        };
        used.insert(word.clone());
        forms.insert((*concept).clone(), word);
    }
    Ok((forms, frequencies))
}
