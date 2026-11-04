//! Pojmy: data o významech (WOLD, frekvence) a graf pojmů pro posun významu.
//!
//! Zrcadlo `cee.v2.concept_data`, `cee.v2.semantics` a výchozího slovníku
//! (`scenarios.DEFAULT_CONCEPTS`). Statická data (domény, půjčitelnost, frekvence
//! z korpusů) se čtou z vložených JSON; svět si z nich udělá sloupce podle čísla
//! pojmu ([`ConceptColumns`]), takže horké cesty nehledají podle řetězců.
//!
//! **Hotové v R0:** výchozí slovník (149 pojmů + zdroje gramatikalizace) a graf
//! pojmů z `v2_core_semantics.json` s recepty složenin. **Patří dál (R1c/R2):**
//! větší slovník z katalogu WOLD a vlastní pojmy autora (`cee.v2.vocabulary`),
//! včetně `v2_catalog_semantics.json` (`data::CATALOG_SEMANTICS_JSON`).

use std::collections::HashMap;
use std::sync::OnceLock;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::ids::{ConceptId, Registry};

/// Převod frekvence z dat na stupnici enginu: kotvy `log10` výskytů na milion.
const LOG_FREQUENCY_ANCHORS: (f64, f64) = (0.5, 3.5);
/// Rozpětí frekvence na stupnici enginu.
pub const FREQUENCY_RANGE: (f64, f64) = (0.05, 0.9);
/// Frekvence pojmu, který nikdo nenastavil (`World.concept_frequency`).
pub const DEFAULT_FREQUENCY: f64 = 0.3;

/// Půjčitelnost pod touto hodnotou se bere jako tato hodnota (slovo, které WOLD nikde nenašla přejaté).
pub const BORROWED_FLOOR: f64 = 0.01;

/// Domény enginu (mechanismy, které na slova působí nejvíc).
pub const DOMAINS: [&str; 5] = ["core", "learned", "culture", "religion", "power"];

/// Vložená data o pojmech (zrcadlo `concept_data`).
pub struct ConceptData {
    concepts: Value,
    catalog: Vec<Value>,
    frequencies: Value,
    mean_borrowed: f64,
}

fn scaled(value: f64) -> f64 {
    let (low, high) = LOG_FREQUENCY_ANCHORS;
    let position = ((value - low) / (high - low)).clamp(0.0, 1.0);
    let (least, most) = FREQUENCY_RANGE;
    least * (most / least).powf(position)
}

impl ConceptData {
    pub fn from_json(concepts: &str, frequencies: &str) -> Result<ConceptData, String> {
        let root: Value =
            serde_json::from_str(concepts).map_err(|e| format!("v2_concepts.json: {e}"))?;
        let frequencies: Value = serde_json::from_str(frequencies)
            .map_err(|e| format!("v2_concept_frequencies.json: {e}"))?;
        let catalog = root["catalog"].as_array().cloned().unwrap_or_default();
        let scores: Vec<f64> = catalog
            .iter()
            .filter_map(|item| item["borrowed"].as_f64())
            .collect();
        let mean_borrowed = scores.iter().sum::<f64>() / scores.len().max(1) as f64;
        Ok(ConceptData {
            concepts: root["concepts"].clone(),
            catalog,
            frequencies,
            mean_borrowed,
        })
    }

    /// Sdílená data vložená do binárky.
    pub fn shared() -> &'static ConceptData {
        static DATA: OnceLock<ConceptData> = OnceLock::new();
        DATA.get_or_init(|| {
            ConceptData::from_json(
                crate::data::CONCEPTS_JSON,
                crate::data::CONCEPT_FREQUENCIES_JSON,
            )
            .expect("vložená data o pojmech")
        })
    }

    /// Doména enginu pojmu (`core` u pojmu mimo data).
    pub fn domain(&self, concept: &str) -> &str {
        self.concepts[concept]["domain"].as_str().unwrap_or("core")
    }

    /// Půjčitelnost pojmu (průměr WOLD u pojmu mimo data nebo bez skóre).
    pub fn borrowed(&self, concept: &str) -> f64 {
        self.concepts[concept]["borrowed"]
            .as_f64()
            .unwrap_or(self.mean_borrowed)
    }

    /// Průměrná půjčitelnost významů katalogu WOLD.
    pub fn mean_borrowed(&self) -> f64 {
        self.mean_borrowed
    }

    /// Frekvence pojmu na stupnici enginu, nebo `None` u pojmu mimo data.
    pub fn frequency(&self, concept: &str) -> Option<f64> {
        self.frequencies["concepts"][concept]["log_frequency"]
            .as_f64()
            .map(scaled)
    }

    /// Průměrná půjčitelnost výchozích pojmů z dat (kotva `borrowability_strength`; `contact.reference`).
    pub fn reference_borrowed(&self) -> f64 {
        let scores: Vec<f64> = self
            .concepts
            .as_object()
            .map(|m| m.values().filter_map(|e| e["borrowed"].as_f64()).collect())
            .unwrap_or_default();
        scores.iter().sum::<f64>() / scores.len().max(1) as f64
    }

    /// Normalizace váhy přenositelnosti pojmu: průměr váhy přes výchozí pojmy vůči průměru
    /// `1 − frekvence` (průměrná míra výpůjček se s `strength` nemění; `contact._normalizer`).
    pub fn borrowing_normalizer(&self, strength: f64) -> f64 {
        let mean = self.reference_borrowed();
        let Some(all) = self.concepts.as_object() else {
            return 1.0;
        };
        let mut rarity = 0.0;
        let mut values = 0.0;
        let mut counted = 0.0_f64;
        for (name, entry) in all {
            let rare = 1.0 - self.frequency(name).unwrap_or(0.0);
            rarity += rare;
            if let Some(borrowed) = entry["borrowed"].as_f64() {
                values += rare.powf((1.0 - strength).max(0.0))
                    * (borrowed.max(BORROWED_FLOOR) / mean).powf(strength);
                counted += 1.0;
            }
        }
        (values / counted.max(1.0)) / (rarity / all.len().max(1) as f64)
    }

    /// Počet významů katalogu mimo pojmy enginu (kolik pojmů lze přidat k výchozímu slovníku).
    pub fn catalog_len(&self) -> usize {
        self.catalog.len()
    }
}

/// Výchozí pojmy a konstanty scénářů (`v2_defaults.json`).
#[derive(Clone, Debug, Deserialize)]
pub struct Defaults {
    pub default_concepts: Vec<String>,
    pub grammatical_sources: Vec<String>,
    pub verbs: Vec<String>,
    pub uninflected: Vec<String>,
    pub default_consonants: Vec<String>,
    pub default_vowels: Vec<String>,
    pub compounds: HashMap<String, Vec<[String; 2]>>,
}

impl Defaults {
    pub fn shared() -> &'static Defaults {
        static DEFAULTS: OnceLock<Defaults> = OnceLock::new();
        DEFAULTS.get_or_init(|| {
            serde_json::from_str(crate::data::DEFAULTS_JSON).expect("vložené výchozí pojmy")
        })
    }

    /// Třída slova pojmu výchozího slovníku (`scenarios.word_class`): `None` = neohebné.
    pub fn word_class(&self, concept: &str) -> Option<&'static str> {
        if concept.starts_with("concept-") || self.uninflected.iter().any(|c| c == concept) {
            return None;
        }
        Some(if self.verbs.iter().any(|c| c == concept) {
            "verb"
        } else {
            "noun"
        })
    }
}

/// Vztah v grafu pojmů: doklady o posunu, odvození a kolexifikaci.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Relation {
    pub source: ConceptId,
    pub target: ConceptId,
    pub polysemy: u32,
    pub derivation: u32,
    pub colexification: u32,
}

impl Relation {
    /// Síla dokladu pro posun významu A → B (kolexifikace váží méně).
    pub fn shift_weight(&self) -> f64 {
        f64::from(self.polysemy).ln_1p() + f64::from(self.colexification).ln_1p() / 3.0
    }

    pub fn derivation_weight(&self) -> f64 {
        f64::from(self.derivation).ln_1p()
    }
}

/// Graf pojmů pro lexikální změny; po stavbě neměnný a sdílený (`Arc`).
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct ConceptGraph {
    pub relations: Vec<Relation>,
    /// Vztahy vedoucí do pojmu (CSR podle čísla cílového pojmu), seřazené podle jména zdroje.
    incoming_start: Vec<u32>,
    incoming: Vec<u32>,
    /// Recepty složenin: pojem → (hlava, určení), CSR podle čísla pojmu.
    compound_start: Vec<u32>,
    compounds: Vec<(ConceptId, ConceptId)>,
}

impl ConceptGraph {
    /// Graf z `v2_core_semantics.json` a receptů složenin; pojmy se zapíšou do registru.
    pub fn core(
        registry: &mut Registry,
        core_semantics: &str,
        defaults: &Defaults,
    ) -> Result<ConceptGraph, String> {
        let root: Value = serde_json::from_str(core_semantics)
            .map_err(|e| format!("v2_core_semantics.json: {e}"))?;
        let mut relations = Vec::new();
        for item in root["relations"].as_array().ok_or("chybí relations")? {
            let count = |key: &str| item[key].as_u64().unwrap_or(0) as u32;
            relations.push(Relation {
                source: registry.concept(item["source"].as_str().ok_or("source")?),
                target: registry.concept(item["target"].as_str().ok_or("target")?),
                polysemy: count("polysemy"),
                derivation: count("derivation"),
                colexification: count("colexification"),
            });
        }
        let mut recipes: Vec<(ConceptId, Vec<(ConceptId, ConceptId)>)> = Vec::new();
        let mut names: Vec<&String> = defaults.compounds.keys().collect();
        names.sort();
        for target in names {
            let options = defaults.compounds[target]
                .iter()
                .map(|[head, modifier]| (registry.concept(head), registry.concept(modifier)))
                .collect();
            recipes.push((registry.concept(target), options));
        }
        Ok(ConceptGraph::build(registry, relations, recipes))
    }

    fn build(
        registry: &Registry,
        relations: Vec<Relation>,
        recipes: Vec<(ConceptId, Vec<(ConceptId, ConceptId)>)>,
    ) -> ConceptGraph {
        let size = registry.concepts.len();
        let mut incoming: Vec<Vec<u32>> = vec![Vec::new(); size];
        for (index, relation) in relations.iter().enumerate() {
            incoming[relation.target.index()].push(index as u32);
        }
        for list in incoming.iter_mut() {
            list.sort_by(|&a, &b| {
                let (a, b) = (&relations[a as usize], &relations[b as usize]);
                registry
                    .concepts
                    .name(a.source.0)
                    .cmp(registry.concepts.name(b.source.0))
            });
        }
        let mut incoming_start = vec![0_u32];
        let mut flat = Vec::new();
        for list in &incoming {
            flat.extend_from_slice(list);
            incoming_start.push(flat.len() as u32);
        }
        let mut by_target: Vec<Vec<(ConceptId, ConceptId)>> = vec![Vec::new(); size];
        for (target, options) in recipes {
            by_target[target.index()] = options;
        }
        let mut compound_start = vec![0_u32];
        let mut compounds = Vec::new();
        for list in &by_target {
            compounds.extend_from_slice(list);
            compound_start.push(compounds.len() as u32);
        }
        ConceptGraph {
            relations,
            incoming_start,
            incoming: flat,
            compound_start,
            compounds,
        }
    }

    /// Vztahy, které vedou do pojmu `target`, seřazené podle jména zdroje.
    pub fn into(&self, target: ConceptId) -> impl Iterator<Item = &Relation> {
        let (low, high) = match self.incoming_start.get(target.index()..=target.index() + 1) {
            Some(range) => (range[0] as usize, range[1] as usize),
            None => (0, 0),
        };
        self.incoming[low..high]
            .iter()
            .map(|&i| &self.relations[i as usize])
    }

    /// Recepty složenin pojmu: (hlava, určení).
    pub fn compounds_of(&self, concept: ConceptId) -> &[(ConceptId, ConceptId)] {
        match self
            .compound_start
            .get(concept.index()..=concept.index() + 1)
        {
            Some(range) => &self.compounds[range[0] as usize..range[1] as usize],
            None => &[],
        }
    }

    /// Jsou pojmy doloženě příbuzné (v jakémkoli směru)?
    pub fn related(&self, first: ConceptId, second: ConceptId) -> bool {
        self.into(second).any(|r| r.source == first) || self.into(first).any(|r| r.source == second)
    }
}

/// Sloupce vlastností pojmů podle čísla pojmu (frekvence, třída slova, doména, půjčitelnost).
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct ConceptColumns {
    /// Jak často se o pojmu mluví (0 až 1); `NaN` = nenastaveno (platí [`DEFAULT_FREQUENCY`]).
    pub frequency: Vec<f64>,
    /// Roste s každou změnou frekvence; podle ní si fáze zneplatňují keše (`FrequencyMap.version`).
    pub version: u64,
    /// Pojmy se změněnou frekvencí v pořadí změn (`FrequencyMap.log`).
    pub log: Vec<ConceptId>,
    /// Třída slova pojmu (`WordClassId::NONE` = neohebné) a zda už byla určena.
    pub word_class: Vec<crate::ids::WordClassId>,
    pub word_class_set: Vec<bool>,
    /// Doména enginu (index do [`DOMAINS`]) a půjčitelnost.
    pub domain: Vec<u8>,
    pub borrowed: Vec<f64>,
}

impl ConceptColumns {
    /// Zvětší sloupce na `size` pojmů; nové pojmy dostanou domény a půjčitelnost z dat.
    pub fn grow(&mut self, registry: &Registry, data: &ConceptData) {
        let size = registry.concepts.len();
        while self.frequency.len() < size {
            let name = registry.concepts.name(self.frequency.len() as u32);
            let domain = DOMAINS
                .iter()
                .position(|d| *d == data.domain(name))
                .unwrap_or(0) as u8;
            self.frequency.push(f64::NAN);
            self.word_class.push(crate::ids::WordClassId::NONE);
            self.word_class_set.push(false);
            self.domain.push(domain);
            self.borrowed.push(data.borrowed(name));
        }
    }

    pub fn frequency_of(&self, concept: ConceptId) -> f64 {
        match self.frequency.get(concept.index()) {
            Some(value) if !value.is_nan() => *value,
            _ => DEFAULT_FREQUENCY,
        }
    }

    /// Nastaví frekvenci a zapíše změnu do deníku (jen když se hodnota opravdu změnila).
    pub fn set_frequency(&mut self, concept: ConceptId, value: f64) {
        let old = self.frequency[concept.index()];
        self.frequency[concept.index()] = value;
        if old.is_nan() || old != value {
            self.version += 1;
            self.log.push(concept);
        }
    }

    /// `setdefault`: nastaví frekvenci jen když není nastavená; vrací platnou hodnotu.
    pub fn default_frequency(&mut self, concept: ConceptId, value: f64) -> f64 {
        if self.frequency[concept.index()].is_nan() {
            self.set_frequency(concept, value);
        }
        self.frequency[concept.index()]
    }
}
