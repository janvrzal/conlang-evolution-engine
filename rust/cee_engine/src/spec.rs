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
use serde_json::{json, Map, Value};

use crate::events::{PendingEvent, WorldEvent};
use crate::grammar::profile;
use crate::history::History;
use crate::model::code::{StressRule, StressStrength};
use crate::parameters::Parameters;
use crate::protoform::SyllableType;
use crate::scenarios::{region_world, ProtoLanguage, Region, SeedOptions};
use crate::segments::SegmentTable;
use crate::vocabulary::{resolve, CustomConcept, DEFAULT_SIZE};
use crate::world::World;
use crate::{Simulation, SimulationConfig};

pub const FORMAT: &str = "cee-v2-world/1";

/// Druhy událostí popisu světa.
pub const EVENT_KINDS: [&str; 16] = [
    "sound_shift",
    "settlement",
    "elite",
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
    /// Přepisy konstrukcí profilu podle funkce (`{"FUTURE": {"kind": "synthetic"}}`); funkce,
    /// kterou profil nemá, se přidá.
    #[serde(default)]
    pub constructions: std::collections::BTreeMap<String, ConstructionSpec>,
    /// Vlastní koncovky podle `třída:buňka` (`{"noun:OBJ": [["m", 1.0]]}`): možnosti s vahami;
    /// buňky, které tu nejsou, mají výchozí koncovky.
    #[serde(default)]
    pub endings: std::collections::BTreeMap<String, Vec<(String, f64)>>,
    /// Zvukové změny rozběhnuté už na startu: jazyk v historickém okamžiku má změny napůl
    /// provedené (lat. -m vyslovované jen jako nosovost samohlásky).
    #[serde(default)]
    pub processes: Vec<InitialProcess>,
    /// Odvozovací přípony (IPA); prázdné = engine je vylosuje z inventáře hlásek jazyka.
    #[serde(default)]
    pub suffixes: Vec<String>,
    /// Slabičná stavba generovaných slov (WALS 12A): `simple`, `moderate`, `complex`;
    /// `None` = vylosuje se podle podílů typů ve WALS.
    #[serde(default)]
    pub syllables: Option<String>,
}

/// Zvuková změna rozběhnutá na startu: rodina, popis kandidáta (`m → ∅ /V_#`) a podíl
/// mluvčích, kteří ji už mají.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InitialProcess {
    pub family: String,
    pub label: String,
    pub share: f64,
}

/// Konstrukce gramatické funkce v popisu jazyka (`Construction` bez stavu vývoje).
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ConstructionSpec {
    pub kind: String,
    #[serde(default)]
    pub source: Option<String>,
    #[serde(default)]
    pub stage: Option<String>,
    #[serde(default)]
    pub order: Option<String>,
    #[serde(default)]
    pub reinforcer: Option<String>,
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
    /// Velikost města regionu (násobek vesnice); chybí = `city_size`, 0 = bez města (dok. 27).
    #[serde(default)]
    pub city: Option<f64>,
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
    // Jazyky z popisu světa (aplikace, scénáře Evropa a Romania) dostanou vlastní morfémy.
    language.generated_morphemes = true;
    // Bez zadaného inventáře (ani souhlásek, ani samohlásek) se inventář vygeneruje (PHOIBLE).
    language.generated_inventory = spec.consonants.is_none() && spec.vowels.is_none();
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
    for suffix in &spec.suffixes {
        table
            .parse(suffix)
            .map_err(|e| format!("languages.{}.suffixes: {e}", spec.id))?;
    }
    language.suffixes = spec.suffixes.clone();
    if let Some(name) = &spec.syllables {
        language.syllables = Some(SyllableType::parse(name).ok_or_else(|| {
            format!(
                "languages.{}.syllables: neznámá slabičná stavba '{name}' (simple, moderate, complex)",
                spec.id
            )
        })?);
    }
    language.endonym = spec.endonym.clone();
    language.tones = spec.tones.clone();
    for (function, given) in &spec.constructions {
        let name = crate::grammar::FUNCTIONS
            .iter()
            .copied()
            .find(|f| f == function)
            .ok_or_else(|| {
                format!(
                    "languages.{}.constructions: neznámá funkce '{function}'",
                    spec.id
                )
            })?;
        const KINDS: [&str; 7] = [
            "synthetic",
            "periphrastic",
            "zero",
            "pre",
            "post",
            "embraced",
            "fixed",
        ];
        if !KINDS.contains(&given.kind.as_str()) && given.kind != "free" {
            return Err(format!(
                "languages.{}.constructions.{function}: neznámý druh '{}'",
                spec.id, given.kind
            ));
        }
        let mut construction = crate::grammar::Construction::new(name, &given.kind);
        construction.source = given.source.clone();
        construction.stage = given.stage.clone();
        construction.order = given.order.clone();
        construction.reinforcer = given.reinforcer.clone();
        match language.grammar.iter_mut().find(|(f, _)| *f == name) {
            Some(slot) => slot.1 = construction,
            None => language.grammar.push((name, construction)),
        }
    }
    if !spec.endings.is_empty() {
        let mut endings = crate::scenarios::syntax_endings();
        for (key, options) in &spec.endings {
            let (class, cell) = key.split_once(':').ok_or_else(|| {
                format!(
                    "languages.{}.endings.{key}: klíč má tvar třída:buňka",
                    spec.id
                )
            })?;
            if !matches!(class, "noun" | "verb") || options.is_empty() {
                return Err(format!(
                    "languages.{}.endings.{key}: třída noun nebo verb a aspoň jedna koncovka",
                    spec.id
                ));
            }
            for (form, weight) in options {
                table
                    .parse(form)
                    .map_err(|e| format!("languages.{}.endings.{key}: {e}", spec.id))?;
                if !weight.is_finite() || *weight <= 0.0 {
                    return Err(format!(
                        "languages.{}.endings.{key}: váha musí být kladná",
                        spec.id
                    ));
                }
            }
            endings.insert((class.to_owned(), cell.to_owned()), options.clone());
        }
        language.endings = Some(endings);
    }
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
            city: r.city,
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
    for language in &spec.languages {
        for item in &language.processes {
            if !(item.share > 0.0 && item.share < 1.0) {
                return Err(format!(
                    "languages.{}.processes: podíl musí být mezi 0 a 1",
                    language.id
                ));
            }
            if !cee_core::candidates::FAMILIES.contains(&item.family.as_str()) {
                return Err(format!(
                    "languages.{}.processes: neznámá rodina '{}'",
                    language.id, item.family
                ));
            }
            let mut inventory: Vec<u32> = Vec::new();
            let (consonants, vowels) = proto_language(language, &table)?
                .inventory(crate::scenarios::language_seed(spec.seed, &language.id));
            for segment in consonants.iter().chain(vowels.iter()) {
                inventory.extend(table.parse(segment)?.into_iter().map(|s| s as u32));
            }
            inventory.sort_unstable();
            inventory.dedup();
            world
                .initial_processes
                .push(crate::world::InitialProcessSeed {
                    language: language.id.clone(),
                    family: item.family.clone(),
                    label: item.label.clone(),
                    share: item.share,
                    inventory,
                });
        }
    }
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
        match item.kind.as_str() {
            "settlement" | "elite" => {
                for (kind, params) in region_event(spec, item).map_err(|(field, message)| {
                    format!("events.{index}.{field} ({}): {message}", item.kind)
                })? {
                    events.push(crate::events::from_pending(PendingEvent::new(
                        item.year, kind, params,
                    )));
                }
            }
            _ => events.push(crate::events::from_pending(PendingEvent::new(
                item.year,
                &item.kind,
                Value::Object(item.params.clone()),
            ))),
        }
    }
    events.extend(background_events(spec, &params_for_background)?);
    Ok((world, events))
}

/// Vesnice regionu popisu světa (jména `region-v0` …, jak je zakládá `region_world`).
fn villages_of(spec: &WorldSpec, region: &str) -> Result<Vec<String>, String> {
    let found = spec
        .regions
        .iter()
        .find(|r| r.id == region)
        .ok_or_else(|| format!("neznámý region '{region}'"))?;
    Ok((0..found.villages)
        .map(|i| format!("{region}-v{i}"))
        .collect())
}

/// Chyba pole události po regionech: jméno pole (`from`, `subjects.1` …) a zpráva.
type FieldError = (String, String);

/// Události po regionech přeložené na události skupin enginu (dok. 23, M8):
///
/// - `settlement` (`from`, `to`, `share`, volitelně `settlements` a `prestige`): podíl `share`
///   obyvatel vesnic regionu `from` se usadí v regionu `to` v nových osadách (`to+from-0` …);
///   osady patří do regionu `to` a jejich lidé mluví jazykem odkud přišli (migrace).
/// - `elite` (`from`, `seat`, `subjects`, volitelně `language`, `population`, `prestige`,
///   `strength`, `homeland`): elita z největší vesnice regionu `from` (s `language` z největší
///   skupiny toho jazyka) se usadí v regionu `seat` s vazbami na vesnice regionů `subjects`
///   (dobytí, superstrát).
///
/// Stavba běhu (`build`) i ověření (`check`) jdou přes tuto funkci, takže obě ověří pole
/// stejně: regiony musí existovat, jazyk elity musí být jazyk popisu, čísla v mezích schématu.
fn region_event(
    spec: &WorldSpec,
    item: &EventSpec,
) -> Result<Vec<(&'static str, Value)>, FieldError> {
    let p = &item.params;
    let fail = |field: &str, message: String| (field.to_owned(), message);
    let text = |key: &str| -> Result<String, FieldError> {
        match p.get(key) {
            None | Some(Value::Null) => Err(fail(key, format!("chybí pole '{key}'"))),
            Some(Value::String(s)) if !s.is_empty() => Ok(s.clone()),
            Some(_) => Err(fail(key, format!("pole '{key}' musí být neprázdný text"))),
        }
    };
    let number = |key: &str, default: f64| -> Result<f64, FieldError> {
        match p.get(key) {
            None | Some(Value::Null) => Ok(default),
            Some(value) => value
                .as_f64()
                .ok_or_else(|| fail(key, format!("pole '{key}' musí být číslo"))),
        }
    };
    let region = |key: &str| -> Result<String, FieldError> {
        let id = text(key)?;
        villages_of(spec, &id).map_err(|e| fail(key, e))?;
        Ok(id)
    };
    match item.kind.as_str() {
        "settlement" => {
            let (from, to) = (region("from")?, region("to")?);
            let share = number("share", 0.2)?;
            if !(share > 0.0 && share < 1.0) {
                return Err(fail("share", "share musí být mezi 0 a 1".into()));
            }
            let count = number("settlements", 1.0)?;
            if count < 1.0 || count.fract() != 0.0 {
                return Err(fail(
                    "settlements",
                    "počet osad musí být celé číslo alespoň 1".into(),
                ));
            }
            let count = count as usize;
            let prestige = match p.get("prestige") {
                None | Some(Value::Null) => None,
                Some(_) => Some(number("prestige", 0.0)?),
            };
            let target = spec
                .regions
                .iter()
                .find(|r| r.id == to)
                .expect("region `to` ověřen výše");
            let sources = villages_of(spec, &from).map_err(|e| fail("from", e))?;
            let mut out = Vec::new();
            for n in 0..count {
                let angle = std::f64::consts::TAU * (n as f64 + 0.5) / count as f64;
                let position = [
                    target.position.0 + spec.village_spacing * 0.5 * angle.cos(),
                    target.position.1 + spec.village_spacing * 0.5 * angle.sin(),
                ];
                let mut params = Map::new();
                params.insert(
                    "sources".into(),
                    Value::Array(
                        sources
                            .iter()
                            .map(|s| json!([s, share / count as f64]))
                            .collect(),
                    ),
                );
                params.insert("target".into(), json!(format!("{to}+{from}-{n}")));
                params.insert("position".into(), json!(position));
                params.insert("region".into(), json!(to));
                params.insert("reach".into(), json!(spec.village_spacing * 2.5));
                if let Some(prestige) = prestige {
                    params.insert("prestige".into(), json!(prestige));
                }
                out.push(("migration", Value::Object(params)));
            }
            Ok(out)
        }
        "elite" => {
            let (from, seat) = (region("from")?, region("seat")?);
            // S jazykem (`language`) se elita vybere až v roce události podle jazyka.
            let conqueror = match p.get("language") {
                None | Some(Value::Null) => format!("{from}-v0"),
                Some(_) => {
                    let language = text("language")?;
                    if !spec.languages.iter().any(|l| l.id == language) {
                        return Err(fail(
                            "language",
                            format!(
                                "neznámý jazyk elity '{language}'; možnosti: {}",
                                spec.languages
                                    .iter()
                                    .map(|l| l.id.as_str())
                                    .collect::<Vec<_>>()
                                    .join(", ")
                            ),
                        ));
                    }
                    format!("{from}:{language}")
                }
            };
            // Poddané regiony se dohledají až v roce události (`@region`).
            let subjects: Vec<String> = match p.get("subjects") {
                None | Some(Value::Null) => vec![format!("@{seat}")],
                Some(Value::Array(items)) => items
                    .iter()
                    .enumerate()
                    .map(|(n, value)| {
                        let field = format!("subjects.{n}");
                        let id = value
                            .as_str()
                            .ok_or_else(|| fail(&field, "poddaný region musí být text".into()))?;
                        villages_of(spec, id).map_err(|e| fail(&field, e))?;
                        Ok(format!("@{id}"))
                    })
                    .collect::<Result<Vec<_>, FieldError>>()?,
                Some(_) => {
                    return Err(fail(
                        "subjects",
                        "pole 'subjects' musí být seznam regionů".into(),
                    ))
                }
            };
            let population = number("population", 100.0)?;
            if population <= 0.0 {
                return Err(fail("population", "počet elity musí být kladný".into()));
            }
            let strength = number("strength", 0.5)?;
            if strength <= 0.0 {
                return Err(fail("strength", "síla vazeb elity musí být kladná".into()));
            }
            let mut params = Map::new();
            params.insert("conqueror".into(), json!(conqueror));
            params.insert("territory".into(), json!(seat));
            params.insert("subjects".into(), json!(subjects));
            params.insert("population".into(), json!(population));
            params.insert("prestige".into(), json!(number("prestige", 2.0)?));
            params.insert("strength".into(), json!(strength));
            if let Some(Value::Number(_)) = p.get("homeland") {
                let homeland = number("homeland", 0.0)?;
                if homeland < 0.0 {
                    return Err(fail(
                        "homeland",
                        "vazba k domovině nesmí být záporná".into(),
                    ));
                }
                params.insert("homeland".into(), json!(homeland));
            } else if !matches!(p.get("homeland"), None | Some(Value::Null)) {
                return Err(fail("homeland", "pole 'homeland' musí být číslo".into()));
            }
            Ok(vec![("conquest", Value::Object(params))])
        }
        _ => Ok(Vec::new()),
    }
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
        if let Some(name) = &language.syllables {
            if SyllableType::parse(name).is_none() {
                issues.push(Issue::error(
                    format!("languages.{index}.syllables"),
                    format!(
                        "neznámá slabičná stavba '{name}'; možnosti: simple, moderate, complex"
                    ),
                ));
            }
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
                // Události po regionech se zkouší přeložené stejně jako při stavbě běhu.
                let translated: Vec<(String, Value)> = match item.kind.as_str() {
                    "settlement" | "elite" => match region_event(spec, item) {
                        Ok(found) => found
                            .into_iter()
                            .map(|(kind, params)| (kind.to_owned(), params))
                            .collect(),
                        Err((field, message)) => {
                            issues.push(Issue::error(format!("events.{index}.{field}"), message));
                            continue;
                        }
                    },
                    _ => vec![(item.kind.clone(), Value::Object(item.params.clone()))],
                };
                for (kind, params) in translated {
                    // Elita podle jazyka se vybírá až v roce události; jazyk se do regionu může
                    // dostat během běhu (posun, osídlení), proto jen varování.
                    if let Some((region, language)) = params
                        .get("conqueror")
                        .and_then(Value::as_str)
                        .and_then(|c| c.split_once(':'))
                    {
                        if crate::events::largest_speaking(&trial.world, region, language).is_err()
                        {
                            found.push(Issue::warning(
                                format!("events.{index}.language"),
                                format!(
                                    "v regionu '{region}' zatím nikdo nemluví jazykem '{language}'; \
                                     pokud tomu tak bude i v roce události, běh skončí chybou"
                                ),
                            ));
                            continue;
                        }
                    }
                    let event =
                        crate::events::from_pending(PendingEvent::new(item.year, &kind, params));
                    if let Err(message) = event.apply(&mut trial.world, &mut history, 0) {
                        issues.push(Issue::error(format!("events.{index}"), message));
                    }
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
