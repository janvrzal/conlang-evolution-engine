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
    /// Významy katalogu v pořadí ID WOLD.
    items: Vec<CatalogItem>,
    /// ID pojmu katalogu (mimo pojmy enginu) → číslo významu v `items`, v pořadí ID WOLD.
    ids: Vec<(String, usize)>,
}

/// Význam katalogu WOLD (zrcadlo záznamu `v2_concepts.json`, část `catalog`).
#[derive(Clone, Debug)]
pub struct CatalogItem {
    pub wold_id: String,
    pub name: String,
    pub concepticon_id: Option<i64>,
    pub concepticon_gloss: Option<String>,
    pub category: String,
    pub domain: String,
    pub borrowed: Option<f64>,
    pub languages: i64,
}

/// Číselný klíč ID významu WOLD (`10-47` jako `[10, 47]`), aby `2-9` přišlo před `2-10`.
pub fn wold_key(wold_id: &str) -> Vec<u32> {
    wold_id.split('-').filter_map(|p| p.parse().ok()).collect()
}

/// ID pojmu z názvu významu WOLD: `the mountain or hill` dá `mountain-or-hill`.
pub fn slug(name: &str) -> String {
    let mut text = name.trim().to_lowercase();
    for prefix in ["the ", "to ", "a ", "an "] {
        if let Some(rest) = text.strip_prefix(prefix) {
            text = rest.to_owned();
            break;
        }
    }
    if let Some(body) = text.strip_suffix(')') {
        if let Some(open) = body.rfind('(') {
            let digits = &body[open + 1..];
            if !digits.is_empty() && digits.chars().all(|c| c.is_ascii_digit()) {
                text = format!("{}-{digits}", &body[..open]);
            }
        }
    }
    let mut out = String::new();
    let mut dash = false;
    for c in text.chars() {
        if c.is_ascii_lowercase() || c.is_ascii_digit() {
            if dash && !out.is_empty() {
                out.push('-');
            }
            dash = false;
            out.push(c);
        } else {
            dash = true;
        }
    }
    out
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
        let items: Vec<CatalogItem> = {
            let mut found: Vec<CatalogItem> = catalog
                .iter()
                .map(|item| CatalogItem {
                    wold_id: item["wold_id"].as_str().unwrap_or_default().to_owned(),
                    name: item["name"].as_str().unwrap_or_default().to_owned(),
                    concepticon_id: item["concepticon_id"].as_i64(),
                    concepticon_gloss: item["concepticon_gloss"].as_str().map(str::to_owned),
                    category: item["category"].as_str().unwrap_or_default().to_owned(),
                    domain: item["domain"].as_str().unwrap_or("core").to_owned(),
                    borrowed: item["borrowed"].as_f64(),
                    languages: item["languages"].as_i64().unwrap_or(0),
                })
                .collect();
            found.sort_by_key(|i| wold_key(&i.wold_id));
            found
        };
        let engine = root["concepts"].as_object().cloned().unwrap_or_default();
        let known: std::collections::HashSet<&str> = engine
            .values()
            .filter_map(|e| e["wold_id"].as_str())
            .collect();
        let mut taken: std::collections::HashSet<String> = engine.keys().cloned().collect();
        taken.extend(
            crate::grammar::GRAMMATICAL_SOURCES
                .iter()
                .map(|s| (*s).to_owned()),
        );
        let mut ids = Vec::new();
        for (at, item) in items.iter().enumerate() {
            if known.contains(item.wold_id.as_str()) {
                continue;
            }
            let base = slug(&item.name);
            if crate::grammar::GRAMMATICAL_SOURCES.contains(&base.as_str()) {
                continue;
            }
            let concept = if taken.contains(&base) {
                format!("{base}-{}", item.wold_id)
            } else {
                base
            };
            taken.insert(concept.clone());
            ids.push((concept, at));
        }
        Ok(ConceptData {
            concepts: root["concepts"].clone(),
            catalog,
            frequencies,
            mean_borrowed,
            items,
            ids,
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
        match self.concepts[concept]["domain"].as_str() {
            Some(found) => found,
            None => self
                .catalog_item(concept)
                .map_or("core", |i| i.domain.as_str()),
        }
    }

    /// Půjčitelnost pojmu (průměr WOLD u pojmu mimo data nebo bez skóre).
    pub fn borrowed(&self, concept: &str) -> f64 {
        self.concepts[concept]["borrowed"]
            .as_f64()
            .or_else(|| self.catalog_item(concept).and_then(|i| i.borrowed))
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
            .or_else(|| {
                let item = self.catalog_item(concept)?;
                self.frequencies["catalog"][item.wold_id.as_str()][0].as_f64()
            })
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

    /// Význam katalogu podle ID pojmu (jen pojmy mimo engine; `catalog_ids`).
    pub fn catalog_item(&self, concept: &str) -> Option<&CatalogItem> {
        let at = self.ids.iter().find(|(id, _)| id == concept)?.1;
        Some(&self.items[at])
    }

    /// Významy katalogu mimo pojmy enginu podle ID pojmu v pořadí ID WOLD.
    pub fn catalog_ids(&self) -> impl Iterator<Item = (&str, &CatalogItem)> {
        self.ids
            .iter()
            .map(|(id, at)| (id.as_str(), &self.items[*at]))
    }

    /// Pořadí, ve kterém se slovník rozšiřuje o pojmy katalogu: nejdřív významy Swadeshova
    /// seznamu (Calude a Pagel 2011), pak ostatní; uvnitř skupiny sestupně podle frekvence,
    /// při shodě podle ID WOLD (`concept_data.catalog_order`).
    pub fn catalog_order(&self) -> Vec<String> {
        let table = &self.frequencies["catalog"];
        let mut keyed: Vec<(bool, f64, Vec<u32>, &str)> = self
            .ids
            .iter()
            .map(|(id, at)| {
                let item = &self.items[*at];
                let row = &table[item.wold_id.as_str()];
                (
                    row[1].as_str() != Some("calude2011"),
                    -row[0].as_f64().unwrap_or(0.0),
                    wold_key(&item.wold_id),
                    id.as_str(),
                )
            })
            .collect();
        keyed.sort_by(|a, b| {
            a.0.cmp(&b.0)
                .then(a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))
                .then(a.2.cmp(&b.2))
        });
        keyed.into_iter().map(|k| k.3.to_owned()).collect()
    }

    /// Záznam pojmu enginu (`concepts`): ID WOLD, název, Concepticon, kategorie a doména.
    pub fn engine_item(&self, concept: &str) -> Option<CatalogItem> {
        let e = self.concepts.get(concept)?;
        Some(CatalogItem {
            wold_id: e["wold_id"].as_str()?.to_owned(),
            name: e["name"].as_str().unwrap_or_default().to_owned(),
            concepticon_id: e["concepticon_id"].as_i64(),
            concepticon_gloss: e["concepticon_gloss"].as_str().map(str::to_owned),
            category: e["category"].as_str().unwrap_or_default().to_owned(),
            domain: e["domain"].as_str().unwrap_or("core").to_owned(),
            borrowed: e["borrowed"].as_f64(),
            languages: e["languages"].as_i64().unwrap_or(0),
        })
    }

    /// Význam katalogu podle ID WOLD, ID Concepticonu nebo glosu (`concept_data.find`).
    pub fn find(
        &self,
        wold: Option<&str>,
        concepticon: Option<i64>,
        gloss: Option<&str>,
    ) -> Option<&CatalogItem> {
        if let Some(wold) = wold {
            return self.items.iter().find(|i| i.wold_id == wold);
        }
        let matches: Vec<&CatalogItem> = if let Some(id) = concepticon {
            self.items
                .iter()
                .filter(|i| i.concepticon_id == Some(id))
                .collect()
        } else {
            let wanted = gloss?.trim().to_lowercase();
            let by_gloss: Vec<&CatalogItem> = self
                .items
                .iter()
                .filter(|i| i.concepticon_gloss.as_deref().unwrap_or("").to_lowercase() == wanted)
                .collect();
            if by_gloss.is_empty() {
                let strip = |name: &str| {
                    let lower = name.to_lowercase();
                    for prefix in ["the ", "to ", "a ", "an "] {
                        if let Some(rest) = lower.strip_prefix(prefix) {
                            return rest.to_owned();
                        }
                    }
                    lower
                };
                self.items
                    .iter()
                    .filter(|i| strip(&i.name) == wanted)
                    .collect()
            } else {
                by_gloss
            }
        };
        // Víc shod: vyhraje význam doložený ve víc jazycích, pak nižší ID WOLD.
        matches.into_iter().min_by(|a, b| {
            b.languages
                .cmp(&a.languages)
                .then(wold_key(&a.wold_id).cmp(&wold_key(&b.wold_id)))
        })
    }

    /// Průměrná půjčitelnost významů katalogu (jen domény `domain`, je-li zadaná).
    pub fn mean_borrowed_in(&self, domain: Option<&str>) -> f64 {
        let scores: Vec<f64> = self
            .items
            .iter()
            .filter(|i| domain.is_none_or(|d| i.domain == d))
            .filter_map(|i| i.borrowed)
            .collect();
        scores.iter().sum::<f64>() / scores.len().max(1) as f64
    }

    /// Průměrná frekvence (stupnice enginu) významů katalogu (jen domény `domain`, je-li zadaná).
    pub fn mean_frequency(&self, domain: Option<&str>) -> f64 {
        let values: Vec<f64> = self
            .items
            .iter()
            .filter(|i| domain.is_none_or(|d| i.domain == d))
            .filter_map(|i| self.item_frequency(i))
            .collect();
        values.iter().sum::<f64>() / values.len().max(1) as f64
    }

    /// Frekvence významu katalogu na stupnici enginu (`None`, když ji data nemají).
    pub fn item_frequency(&self, item: &CatalogItem) -> Option<f64> {
        self.frequencies["catalog"][item.wold_id.as_str()][0]
            .as_f64()
            .map(scaled)
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
        Ok(ConceptGraph::with_relations(registry, relations, defaults))
    }

    /// Graf z daných vztahů a receptů složenin výchozích pojmů (vztahy jiného slovníku).
    pub fn with_relations(
        registry: &mut Registry,
        relations: Vec<Relation>,
        defaults: &Defaults,
    ) -> ConceptGraph {
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
        ConceptGraph::build(registry, relations, recipes)
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
