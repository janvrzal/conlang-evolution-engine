//! Popis světa pro UI: JSON, ze kterého engine postaví svět a události (`cee.v2.spec`).
//!
//! Validaci (meze polí, české zprávy, zkušební provedení událostí) dál dělá Python
//! (pydantic); Rust přijme **stejný JSON** přes `serde` a postaví z něj svět a události.
//! Formát má verzi [`FORMAT`]; mění se jen přidáváním polí.
//!
//! **Hotové v R0:** `WorldSpec` se stejnými poli, stavba světa pro výchozí slovník.
//! **Patří dál:** větší slovník a vlastní pojmy (`vocabulary`, `concepts`; R1c/R2); takový
//! popis `build` odmítne chybou, místo aby tiše dal jiný svět. Pozadí dějin (`background`)
//! generuje `crate::background` (R1d).

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::concepts::{ConceptData, Defaults};
use crate::events::{PendingEvent, WorldEvent};
use crate::grammar::profile;
use crate::model::code::{StressRule, StressStrength};
use crate::parameters::Parameters;
use crate::scenarios::{region_world, ProtoLanguage, Region, SeedOptions};
use crate::segments::SegmentTable;
use crate::world::World;

pub const FORMAT: &str = "cee-v2-world/1";

/// Druhy událostí popisu světa.
pub const EVENT_KINDS: [&str; 13] = [
    "state",
    "language_policy",
    "annexation",
    "secession",
    "collapse",
    "border_policy",
    "lingua_franca",
    "standard",
    "schools",
    "revival",
    "preserve",
    "identity",
    "immigration",
];

fn default_format() -> String {
    FORMAT.into()
}
fn default_seed() -> i64 {
    1
}
fn default_grammar() -> String {
    "default".into()
}
fn default_stress() -> String {
    "penult".into()
}
fn default_weak() -> String {
    "weak".into()
}
fn default_density() -> f64 {
    1.0
}
fn default_villages() -> usize {
    4
}
fn default_prestige() -> f64 {
    0.5
}
fn default_plain() -> String {
    "plain".into()
}
fn default_shared() -> String {
    "shared".into()
}
fn default_vocabulary() -> usize {
    149
}
fn default_true() -> bool {
    true
}
fn default_spacing() -> f64 {
    10.0
}
fn default_generation() -> f64 {
    25.0
}
fn default_background() -> String {
    "none".into()
}

/// Protojazyk jedné linie.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LanguageSpec {
    pub id: String,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub consonants: Option<Vec<String>>,
    #[serde(default)]
    pub vowels: Option<Vec<String>>,
    #[serde(default = "default_grammar")]
    pub grammar: String,
    #[serde(default = "default_stress")]
    pub stress: String,
    #[serde(default = "default_weak")]
    pub stress_strength: String,
    #[serde(default)]
    pub words: HashMap<String, String>,
    #[serde(default)]
    pub endonym: Vec<String>,
    #[serde(default)]
    pub tones: Vec<String>,
}

/// Region jako síť vesnic.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RegionSpec {
    pub id: String,
    #[serde(default)]
    pub name: Option<String>,
    pub position: (f64, f64),
    #[serde(default = "default_density")]
    pub density: f64,
    #[serde(default)]
    pub neighbours: Vec<String>,
    #[serde(default = "default_villages")]
    pub villages: usize,
    #[serde(default = "default_prestige")]
    pub prestige: f64,
    #[serde(default)]
    pub language: Option<String>,
    #[serde(default = "default_plain")]
    pub terrain: String,
    #[serde(default = "default_shared")]
    pub identity: String,
    #[serde(default)]
    pub preserve: bool,
    #[serde(default)]
    pub immigration: f64,
}

/// Událost popisu světa: rok, druh a zbylá pole podle druhu (viz pydantic modely v `spec.py`).
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct EventSpec {
    pub year: f64,
    pub kind: String,
    #[serde(flatten)]
    pub params: Map<String, Value>,
}

/// Celý svět: protojazyky, regiony, časová osa a přepisy parametrů.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorldSpec {
    #[serde(default = "default_format")]
    pub format: String,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default = "default_seed")]
    pub seed: i64,
    #[serde(default)]
    pub start_year: f64,
    pub end_year: f64,
    pub languages: Vec<LanguageSpec>,
    pub regions: Vec<RegionSpec>,
    #[serde(default)]
    pub events: Vec<EventSpec>,
    #[serde(default = "default_vocabulary")]
    pub vocabulary: usize,
    #[serde(default)]
    pub concepts: Vec<Value>,
    #[serde(default = "default_true")]
    pub semantics: bool,
    #[serde(default = "default_spacing")]
    pub village_spacing: f64,
    #[serde(default = "default_generation")]
    pub generation_years: f64,
    #[serde(default)]
    pub parameters: Map<String, Value>,
    #[serde(default = "default_background")]
    pub background: String,
}

impl WorldSpec {
    pub fn from_json(text: &str) -> Result<WorldSpec, String> {
        let spec: WorldSpec =
            serde_json::from_str(text).map_err(|e| format!("popis světa: {e}"))?;
        if spec.format != FORMAT {
            return Err(format!("popis světa: neznámý formát '{}'", spec.format));
        }
        if spec.end_year <= spec.start_year {
            return Err("end_year musí být později než start_year".into());
        }
        Ok(spec)
    }
}

fn proto_language(spec: &LanguageSpec, table: &SegmentTable) -> Result<ProtoLanguage, String> {
    let mut language = ProtoLanguage::new(&spec.id);
    language.grammar = profile::by_name(&spec.grammar).ok_or_else(|| {
        format!(
            "languages.{}: neznámá gramatika '{}'",
            spec.id, spec.grammar
        )
    })?;
    if let Some(consonants) = &spec.consonants {
        language.consonants = consonants.clone();
    }
    if let Some(vowels) = &spec.vowels {
        language.vowels = vowels.clone();
    }
    language.stress_rule = StressRule::parse(&spec.stress)
        .ok_or_else(|| format!("neznámý přízvuk '{}'", spec.stress))?;
    language.stress_strength = StressStrength::parse(&spec.stress_strength)
        .ok_or_else(|| format!("neznámá síla přízvuku '{}'", spec.stress_strength))?;
    for (concept, form) in &spec.words {
        table
            .parse(form)
            .map_err(|e| format!("languages.{}.words.{concept}: {e}", spec.id))?;
    }
    language.words = spec.words.clone();
    language.endonym = spec.endonym.clone();
    language.tones = spec.tones.clone();
    Ok(language)
}

/// Svět a události z popisu (`spec.build`); varování se nevrací, chyba zastaví stavbu.
pub fn build(spec: &WorldSpec) -> Result<(World, Vec<Box<dyn WorldEvent>>), String> {
    let params = Parameters::from_overrides(&spec.parameters)?;
    if spec.vocabulary != Defaults::shared().default_concepts.len() || !spec.concepts.is_empty() {
        return Err(format!(
            "Větší slovník ({} pojmů z {} možných) a vlastní pojmy zatím nejsou v Rustu (patří R1c/R2).",
            spec.vocabulary,
            Defaults::shared().default_concepts.len() + ConceptData::shared().catalog_len()
        ));
    }
    if !params.background_levels.contains_key(&spec.background) {
        return Err(format!("neznámá míra pozadí dějin '{}'", spec.background));
    }
    let params_for_background = params.clone();
    let table = SegmentTable::default_table();
    let languages = spec
        .languages
        .iter()
        .map(|l| proto_language(l, &table))
        .collect::<Result<Vec<_>, _>>()?;
    let regions: Vec<Region> = spec
        .regions
        .iter()
        .map(|r| Region {
            id: r.id.clone(),
            position: r.position,
            density: r.density,
            neighbours: r.neighbours.clone(),
            villages: r.villages,
            prestige: r.prestige,
            openness: None,
            immigration: r.immigration,
            language: r.language.clone(),
            terrain: r.terrain.clone(),
            identity: r.identity.clone(),
            preserve: r.preserve,
        })
        .collect();
    let options = SeedOptions {
        semantics: spec.semantics,
        ..SeedOptions::default()
    };
    let mut world = region_world(
        &regions,
        spec.seed,
        &options,
        spec.village_spacing,
        spec.generation_years,
        2.0,
        params,
        &languages,
    )?;
    world.start_year = spec.start_year;
    let mut order: Vec<usize> = (0..spec.events.len()).collect();
    order.sort_by(|&a, &b| {
        spec.events[a]
            .year
            .partial_cmp(&spec.events[b].year)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a.cmp(&b))
    });
    let mut events: Vec<Box<dyn WorldEvent>> = Vec::new();
    for index in order {
        let item = &spec.events[index];
        if !EVENT_KINDS.contains(&item.kind.as_str()) {
            return Err(format!(
                "events.{index}: neznámý druh události '{}'",
                item.kind
            ));
        }
        events.push(crate::events::from_pending(PendingEvent::new(
            item.year,
            &item.kind,
            Value::Object(item.params.clone()),
        )));
    }
    events.extend(background_events(spec, &params_for_background)?);
    Ok((world, events))
}

/// Události pozadí dějin pro popis světa (po událostech autora ve stejném roce).
fn background_events(
    spec: &WorldSpec,
    params: &Parameters,
) -> Result<Vec<Box<dyn WorldEvent>>, String> {
    let first = spec.languages[0].id.clone();
    let mut near: std::collections::BTreeMap<&str, std::collections::BTreeSet<&str>> = spec
        .regions
        .iter()
        .map(|r| (r.id.as_str(), Default::default()))
        .collect();
    for region in &spec.regions {
        for other in &region.neighbours {
            if near.contains_key(other.as_str()) && other != &region.id {
                near.get_mut(region.id.as_str()).map(|s| s.insert(other));
                near.get_mut(other.as_str()).map(|s| s.insert(&region.id));
            }
        }
    }
    let regions: Vec<crate::background::BackgroundRegion> = spec
        .regions
        .iter()
        .map(|r| crate::background::BackgroundRegion {
            id: r.id.clone(),
            neighbours: near[r.id.as_str()]
                .iter()
                .map(|s| (*s).to_owned())
                .collect(),
            language: r.language.clone().unwrap_or_else(|| first.clone()),
        })
        .collect();
    crate::background::generate(
        &regions,
        spec.start_year,
        spec.end_year,
        &spec.background,
        spec.seed,
        params,
    )
}
