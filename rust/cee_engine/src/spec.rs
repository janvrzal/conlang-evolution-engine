//! Popis světa pro UI: JSON, ze kterého engine postaví svět a události (`cee.v2.spec`).
//!
//! Validaci (meze polí, české zprávy, zkušební provedení událostí) dál dělá Python
//! (pydantic); Rust přijme **stejný JSON** přes `serde` a postaví z něj svět a události.
//! Formát má verzi [`FORMAT`]; mění se jen přidáváním polí.
//!
//! **Hotové:** `WorldSpec` se stejnými poli, stavba světa včetně většího slovníku a vlastních
//! pojmů (`vocabulary`, `concepts`; R1c, `vocabulary::resolve`) a pozadí dějin (`background`,
//! generuje `crate::background`; R1d).

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::events::{PendingEvent, WorldEvent};
use crate::grammar::profile;
use crate::history::History;
use crate::model::code::{StressRule, StressStrength};
use crate::parameters::Parameters;
use crate::scenarios::{region_world, ProtoLanguage, Region, SeedOptions};
use crate::segments::SegmentTable;
use crate::vocabulary::{resolve, CustomConcept, DEFAULT_SIZE};
use crate::world::World;
use crate::{Simulation, SimulationConfig};

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

fn custom_concepts(spec: &WorldSpec) -> Result<Vec<CustomConcept>, (usize, String)> {
    spec.concepts
        .iter()
        .enumerate()
        .map(|(index, item)| {
            serde_json::from_value::<CustomConcept>(item.clone())
                .map_err(|e| (index, e.to_string()))
        })
        .collect()
}

/// Svět z popisu bez událostí; chyba je text se zprávou enginu.
fn make_world(spec: &WorldSpec, params: Parameters) -> Result<World, String> {
    let vocabulary = if spec.vocabulary == DEFAULT_SIZE && spec.concepts.is_empty() {
        None
    } else {
        let custom =
            custom_concepts(spec).map_err(|(index, e)| format!("concepts.{index}: {e}"))?;
        Some(Arc::new(resolve(spec.vocabulary, &custom)?))
    };
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
        vocabulary,
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
    Ok(world)
}

/// Svět a události z popisu (`spec.build`); varování se nevrací, chyba zastaví stavbu.
pub fn build(spec: &WorldSpec) -> Result<(World, Vec<Box<dyn WorldEvent>>), String> {
    let params = Parameters::from_overrides(&spec.parameters)?;
    if !params.background_levels.contains_key(&spec.background) {
        return Err(format!("neznámá míra pozadí dějin '{}'", spec.background));
    }
    let params_for_background = params.clone();
    let world = make_world(spec, params)?;
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

/// Chyba nebo varování popisu světa: cesta k poli (`events.2.capital`), zpráva a závažnost.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Issue {
    pub path: String,
    pub message: String,
    /// `error` svět nepustí, `warning` jen upozorní.
    pub severity: &'static str,
}

impl Issue {
    pub fn error(path: impl Into<String>, message: impl Into<String>) -> Issue {
        Issue {
            path: path.into(),
            message: message.into(),
            severity: "error",
        }
    }

    pub fn warning(path: impl Into<String>, message: impl Into<String>) -> Issue {
        Issue {
            severity: "warning",
            ..Issue::error(path, message)
        }
    }
}

/// Zpráva ve tvaru `cesta: text` rozdělená na cestu a text; bez cesty platí `fallback`.
fn with_path(text: &str, fallback: &str) -> (String, String) {
    if let Some((head, rest)) = text.split_once(": ") {
        let path_like = !head.is_empty()
            && head
                .chars()
                .all(|c| c.is_alphanumeric() || matches!(c, '_' | '.' | '-'));
        if path_like {
            return (head.to_owned(), rest.to_owned());
        }
    }
    (fallback.to_owned(), text.to_owned())
}

/// Slova, tóny a vlastní jména jazyků zadaná autorem: známý pojem a hlásky, které engine umí.
fn word_issues(spec: &WorldSpec, known: &HashSet<String>) -> Vec<Issue> {
    let table = SegmentTable::default_table();
    let tones = table.tone_symbols();
    let mut issues = Vec::new();
    for (index, language) in spec.languages.iter().enumerate() {
        for (position, tone) in language.tones.iter().enumerate() {
            if !tones.contains(tone) {
                issues.push(Issue::error(
                    format!("languages.{index}.tones.{position}"),
                    format!(
                        "neznámý tón '{tone}'; tón se píše tónovými značkami ˥ ˦ ˧ ˨ ˩ (např. ˥, ˧˥)"
                    ),
                ));
            }
        }
        let distinct: HashSet<&String> = language.tones.iter().collect();
        if distinct.len() != language.tones.len() {
            issues.push(Issue::error(
                format!("languages.{index}.tones"),
                "tóny se opakují",
            ));
        }
        for (position, concept) in language.endonym.iter().enumerate() {
            if !known.contains(concept) {
                issues.push(Issue::error(
                    format!("languages.{index}.endonym.{position}"),
                    format!("neznámý pojem '{concept}'"),
                ));
            }
        }
        let mut words: Vec<(&String, &String)> = language.words.iter().collect();
        words.sort();
        for (concept, form) in words {
            let path = format!("languages.{index}.words.{concept}");
            if !known.contains(concept) {
                issues.push(Issue::error(path, format!("neznámý pojem '{concept}'")));
            } else if form.trim().is_empty() {
                issues.push(Issue::error(path, "slovo nesmí být prázdné"));
            } else {
                match table.lossless(form) {
                    Err(_) => issues.push(Issue::error(
                        path,
                        format!("engine nezná některou hlásku ve slově '{form}'"),
                    )),
                    Ok(Some(rendered)) => issues.push(Issue::error(
                        path,
                        format!("slovo '{form}' by se zapsalo jako '{rendered}'"),
                    )),
                    Ok(None) => {}
                }
            }
        }
    }
    issues
}

/// Chyby a varování popisu světa (`spec.check` bez schématu, které ověřuje pydantic).
///
/// Bez chyb se svět dá postavit a spustit. Chyby jdou před varováními. Události se
/// ověří zkušebním provedením na vlastním světě v pořadí roků: odhalí odkazy na
/// neexistující státy a regiony, neznámé úrovně i špatné pořadí (zánik před vznikem).
pub fn check(spec: &WorldSpec) -> Vec<Issue> {
    let params = match Parameters::from_overrides(&spec.parameters) {
        Ok(params) => params,
        Err(message) => {
            let (path, text) = with_path(&message, "parameters");
            return vec![Issue::error(path, text)];
        }
    };
    let custom = match custom_concepts(spec) {
        Ok(custom) => custom,
        Err((index, message)) => return vec![Issue::error(format!("concepts.{index}"), message)],
    };
    let mut found: Vec<Issue> = Vec::new();
    for problem in crate::vocabulary::validate(spec.vocabulary, &custom) {
        let (path, text) = with_path(&problem, "vocabulary");
        found.push(Issue::error(path, text));
    }
    let failed = !found.is_empty();
    for (path, text) in crate::vocabulary::warnings(spec.vocabulary, &custom) {
        found.push(Issue::warning(path, text));
    }
    if failed {
        return found;
    }
    let mut known: HashSet<String> = crate::vocabulary::base_ids(spec.vocabulary)
        .into_iter()
        .collect();
    known.extend(custom.iter().map(|c| c.id.clone()));
    let mut issues = word_issues(spec, &known);
    if !issues.is_empty() {
        issues.extend(found);
        return issues;
    }
    let world = match make_world(spec, params.clone()) {
        Ok(world) => world,
        Err(message) => {
            let (path, text) = with_path(&message, "regions");
            let path = if path == "regions" || path.starts_with("languages.") {
                path
            } else {
                "regions".to_owned()
            };
            let mut all = vec![Issue::error(path, text)];
            all.extend(found);
            return all;
        }
    };
    if !params.background_levels.contains_key(&spec.background) {
        issues.push(Issue::error(
            "background",
            format!(
                "neznámá míra pozadí dějin '{}'; možnosti: {}",
                spec.background,
                params
                    .background_levels
                    .keys()
                    .cloned()
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
        ));
    }
    for (index, item) in spec.events.iter().enumerate() {
        if !(spec.start_year <= item.year && item.year <= spec.end_year) {
            issues.push(Issue::error(
                format!("events.{index}.year"),
                "událost leží mimo start_year až end_year",
            ));
        }
    }
    // Zkušební svět má stejný stav jako na začátku běhu; události se provedou v pořadí roků.
    match Simulation::new(world, SimulationConfig::default(), Vec::new()) {
        Err(message) => issues.push(Issue::error("(svět)", message)),
        Ok(mut trial) => {
            let mut history = History::default();
            let mut order: Vec<usize> = (0..spec.events.len()).collect();
            order.sort_by(|&a, &b| {
                spec.events[a]
                    .year
                    .partial_cmp(&spec.events[b].year)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then(a.cmp(&b))
            });
            for index in order {
                let item = &spec.events[index];
                if !EVENT_KINDS.contains(&item.kind.as_str()) {
                    issues.push(Issue::error(
                        format!("events.{index}"),
                        format!("neznámý druh události '{}'", item.kind),
                    ));
                    continue;
                }
                let event = crate::events::from_pending(PendingEvent::new(
                    item.year,
                    &item.kind,
                    Value::Object(item.params.clone()),
                ));
                if let Err(message) = event.apply(&mut trial.world, &mut history, 0) {
                    issues.push(Issue::error(format!("events.{index}"), message));
                }
            }
        }
    }
    if !spec.semantics && custom_related(&custom) {
        found.push(Issue::warning(
            "semantics",
            "příbuzné pojmy vlastních pojmů se bez sémantiky (semantics: false) nepoužijí",
        ));
    }
    issues.extend(found);
    issues
}

fn custom_related(custom: &[CustomConcept]) -> bool {
    custom.iter().any(|c| !c.related.is_empty())
}
