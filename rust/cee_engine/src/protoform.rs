//! Hláskové tvary protojazyka: zrcadlo `cee.v2.language.protoforms.protolanguage`.
//!
//! Protojazyk se generuje ze slabičné šablony a inventáře. Stavba světa v Pythonu
//! běží na numpy generátoru; aby šla porovnat v ticku 0, běží i tady na jeho
//! zrcadle ([`crate::legacy_numpy::Pcg64`]). Simulace samotná používá `rng::Stream`.

use std::collections::{HashMap, HashSet};

use cee_core::assess::pairwise_sum;

use crate::concepts::ConceptData;
use crate::legacy_numpy::Pcg64;
use crate::rng::Part;

/// Zipfovské váhy hlásek (první v seznamu nejčastější): `1 / k^0.7`, normalizované.
pub fn zipf(count: usize) -> Vec<f64> {
    let weights: Vec<f64> = (1..=count).map(|k| 1.0 / (k as f64).powf(0.7)).collect();
    let total = pairwise_sum(&weights);
    weights.iter().map(|w| w / total).collect()
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
}

/// Tvary (IPA) a frekvence pojmů; stejné semínko dá stejný protojazyk.
pub fn protolanguage(spec: &ProtoSpec<'_>, data: &ConceptData) -> Result<(HashMap<String, String>, HashMap<String, f64>), String> {
    let (min_syllables, max_syllables, coda_share) = (1_i64, 3_i64, 0.25);
    let mut rng = Pcg64::for_parts(spec.seed, &[Part::Str("protolanguage")]);
    let consonant_weights = zipf(spec.consonants.len());
    let vowel_weights = zipf(spec.vowels.len());
    let tone_weights = if spec.tones.is_empty() { Vec::new() } else { zipf(spec.tones.len()) };
    let mut used: HashSet<String> = spec.fixed.values().cloned().collect();
    let mut forms = HashMap::new();
    let mut order: Vec<&String> = Vec::new();
    let mut seen = HashSet::new();
    for concept in spec.concepts {
        if !seen.insert(concept) {
            continue;
        }
        order.push(concept);
        let mut word = String::new();
        for _ in 0..100 {
            let count = rng.integers(min_syllables, max_syllables + 1);
            word.clear();
            for position in 0..count {
                if position == 0 && rng.random() < 0.15 {
                    // slovo začínající samohláskou
                } else {
                    word.push_str(&spec.consonants[rng.choice(&consonant_weights)]);
                }
                word.push_str(&spec.vowels[rng.choice(&vowel_weights)]);
                if !spec.tones.is_empty() {
                    word.push_str(&spec.tones[rng.choice(&tone_weights)]);
                }
            }
            if rng.random() < coda_share {
                word.push_str(&spec.consonants[rng.choice(&consonant_weights)]);
            }
            if word.chars().count() >= 2 && !used.contains(&word) {
                break;
            }
        }
        let word = spec.fixed.get(concept).cloned().unwrap_or_else(|| word.clone());
        used.insert(word.clone());
        forms.insert(concept.clone(), word);
    }
    // Generované frekvence se losují vždy, aby tvary na zdroji frekvencí nezávisely.
    let (low, high) = (0.05_f64.ln(), 0.8_f64.ln());
    let mut frequencies = HashMap::new();
    for (index, concept) in order.iter().enumerate() {
        let generated = if index < 20 { 0.9 } else { rng.uniform(low, high).exp() };
        let known = spec
            .known_frequencies
            .and_then(|given| given.get(*concept).copied())
            .or_else(|| data.frequency(concept));
        frequencies.insert((*concept).clone(), known.unwrap_or(generated));
    }
    Ok((forms, frequencies))
}
