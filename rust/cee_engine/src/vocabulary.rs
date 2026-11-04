//! Slovní zásoba kódů na začátku běhu (zrcadlo `Simulation._seed_vocabulary`).
//!
//! Každý kód dostane jako dominantní slovo pojmu to, které je dominantní v jeho
//! rozdělení lexikální proměnné; do slovní zásoby vstoupí slovo i jeho tvary buněk.

use crate::ids::{GroupId, MorphemeId};
use crate::model::lexicon::unit_name;
use crate::model::repertoire::{Payload, VariableKind};
use crate::world::World;

/// Tvary slova (citační tvar a buňky paradigmatu), které svět už zná.
///
/// Lexém vzniklý až za běhu a výpůjčky dostávají tvary buněk podle produktivních koncovek
/// kódu (`morphology.units_of`); to přináší R1c.
pub fn units_of(world: &World, root: MorphemeId) -> Vec<MorphemeId> {
    let class = world.morphemes.word_class[root.index()];
    let paradigm = if class.is_none() {
        None
    } else {
        world.paradigms.get(class.index()).and_then(Option::as_ref)
    };
    let Some(paradigm) = paradigm else {
        return vec![root];
    };
    let root_name = world.registry.morphemes.name(root.0);
    let citation = world.registry.cells.name(paradigm.citation().0);
    let mut units = vec![root];
    for &cell in &paradigm.cells[1..] {
        let name = unit_name(root_name, world.registry.cells.name(cell.0), citation);
        if let Some(found) = world.registry.morphemes.get(&name) {
            if world.morphemes.contains(MorphemeId(found)) {
                units.push(MorphemeId(found));
            }
        }
    }
    units
}

/// Tvary slova (citační tvar a buňky paradigmatu) pro kód skupiny; chybějící tvary lexému vzniklého
/// za běhu a výpůjčky se založí podle produktivních koncovek kódu (`morphology.units_of`).
/// Volá je přenos slovní zásoby (R1b) při vstupu nového slova do kódu.
pub fn units_in(world: &mut World, group: GroupId, root: MorphemeId) -> Vec<MorphemeId> {
    crate::morphology::units_of(world, group, root)
}

/// Doplní slovní zásobu jedné skupiny, pokud ji nemá.
pub fn seed_vocabulary(world: &mut World, group: GroupId) -> Result<(), String> {
    if !world
        .groups
        .main_code(group)
        .phonology
        .vocabulary
        .is_empty()
    {
        return Ok(());
    }
    let mut found = Vec::new();
    for number in world.registry.variables.sorted() {
        let variable = crate::ids::VariableId(number);
        if variable.index() >= world.variables.len()
            || world.variables.kind[variable.index()] != VariableKind::Lexical
        {
            continue;
        }
        let Some((dominant, _)) = world.dominant(group, variable) else {
            continue;
        };
        if let Payload::Lexical { morpheme, .. } = &world.variants.payload[dominant.index()] {
            if !morpheme.is_none() {
                found.push((world.variables.concept[variable.index()], *morpheme));
            }
        }
    }
    for (concept, morpheme) in found {
        let units = units_of(world, morpheme);
        crate::views::set_dominant(world, group, concept, morpheme);
        let state = &mut world.groups.main_code_mut(group).phonology;
        state.adjust_uses(morpheme, 1, 0);
        for &unit in &units {
            state.enter_vocabulary(unit);
        }
        state.version += 1;
        state.lexicon_version += 1;
        crate::views::refresh(world, group, &units);
        crate::views::vocabulary_changed(world, group, &units);
    }
    Ok(())
}

/// Doplní slovní zásobu všech skupin světa.
pub fn seed_vocabulary_all(world: &mut World) -> Result<(), String> {
    for group in world.group_ids() {
        seed_vocabulary(world, group)?;
    }
    Ok(())
}

// --- slovník světa: velikost a vlastní pojmy (zrcadlo `cee.v2.vocabulary`) -------------------------
//
// Výchozí slovník (149 pojmů `DEFAULT_CONCEPTS`) se rozšiřuje o pojmy katalogu WOLD v pořadí
// `ConceptData::catalog_order` (slovník o `n` pojmech je vždy začátkem slovníku o `n + 1`) a o vlastní
// pojmy autora světa. **Pořadí pojmů** je deterministické: výchozí pojmy, zdroje gramatikalizace,
// pojmy katalogu, nakonec vlastní pojmy podle ID. Co autor vlastnímu pojmu nezadá, doplní engine
// (doména `core`, půjčitelnost a frekvence jako průměr katalogu, podstatné jméno). Graf pojmů
// pro větší slovník staví `v2_core_semantics.json`, `v2_catalog_semantics.json` (DatSemShift a
// CLICS⁴, CC BY 4.0) a vztahy zadané autorem, které mají u dané dvojice přednost.

use std::collections::{BTreeMap, HashMap, HashSet};

use serde::Deserialize;

use crate::concepts::{CatalogItem, ConceptData, ConceptGraph, Defaults, Relation, DOMAINS};
use crate::grammar::GRAMMATICAL_SOURCES;

/// Velikost výchozího slovníku (`DEFAULT_CONCEPTS`).
pub const DEFAULT_SIZE: usize = 149;
const WORD_CLASSES: [&str; 3] = ["noun", "verb", "uninflected"];
const RELATION_KINDS: [&str; 3] = ["polysemy", "derivation", "colexification"];
const RELATION_DIRECTIONS: [&str; 3] = ["to", "from", "both"];

fn default_direction(kind: &str) -> &'static str {
    match kind {
        "derivation" => "from",
        _ => "both",
    }
}

/// Váha vztahu bez zadání ve stejných jednotkách jako data.
fn default_weight(kind: &str) -> i64 {
    match kind {
        "colexification" => 9,
        _ => 2,
    }
}

fn default_kind() -> String {
    "polysemy".into()
}

/// Příbuzný pojem vlastního pojmu: druh vztahu, směr a váha.
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Related {
    pub concept: String,
    #[serde(default = "default_kind")]
    pub kind: String,
    #[serde(default)]
    pub direction: Option<String>,
    #[serde(default)]
    pub weight: Option<i64>,
}

/// Vlastní pojem autora světa.
#[derive(Clone, Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CustomConcept {
    pub id: String,
    #[serde(default)]
    pub gloss: Option<String>,
    #[serde(default)]
    pub wold: Option<String>,
    #[serde(default)]
    pub concepticon: Option<i64>,
    #[serde(default)]
    pub domain: Option<String>,
    #[serde(default)]
    pub frequency: Option<f64>,
    #[serde(default)]
    pub word_class: Option<String>,
    #[serde(default)]
    pub borrowed: Option<f64>,
    #[serde(default)]
    pub related: Vec<Related>,
}

/// Odkud pojem pochází.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Source {
    Default,
    Engine,
    Catalog,
    Custom,
}

/// Pojem světa s tím, co o něm engine ví.
#[derive(Clone, Debug)]
pub struct Concept {
    pub id: String,
    pub source: Source,
    pub domain: String,
    pub borrowed: f64,
    /// Frekvence na stupnici enginu; `None` = vygeneruje protojazyk (zdroje bez dat).
    pub frequency: Option<f64>,
    pub word_class: String,
    pub concepticon_id: Option<i64>,
}

/// Slovník světa: pojmy v pořadí simulace a vlastní pojmy; staví ho [`resolve`].
#[derive(Clone, Debug)]
pub struct Vocabulary {
    pub size: usize,
    pub concepts: Vec<Concept>,
    pub custom: Vec<CustomConcept>,
}

/// Největší slovník: výchozí pojmy a všechny pojmy katalogu.
pub fn max_size() -> usize {
    DEFAULT_SIZE + ConceptData::shared().catalog_order().len()
}

/// Pojmy bez vlastních v pořadí simulace: výchozí, zdroje gramatikalizace, pojmy katalogu.
fn base(size: usize) -> Vec<(String, Source)> {
    let defaults = &Defaults::shared().default_concepts;
    let mut found: Vec<(String, Source)> = defaults
        .iter()
        .map(|c| (c.clone(), Source::Default))
        .collect();
    for source in GRAMMATICAL_SOURCES {
        if !defaults.iter().any(|c| c == source) {
            found.push((source.to_owned(), Source::Engine));
        }
    }
    let order = ConceptData::shared().catalog_order();
    found.extend(
        order
            .into_iter()
            .take(size.saturating_sub(DEFAULT_SIZE))
            .map(|c| (c, Source::Catalog)),
    );
    found
}

fn valid_id(id: &str) -> bool {
    let mut chars = id.chars();
    chars
        .next()
        .is_some_and(|c| c.is_alphanumeric() || c == '_')
        && chars.all(|c| c.is_alphanumeric() || matches!(c, '_' | '.' | '-'))
}

/// Význam katalogu, na který je vlastní pojem navázán (WOLD, Concepticon, glos, nebo ID katalogu).
fn link(item: &CustomConcept) -> Option<CatalogItem> {
    let data = ConceptData::shared();
    if let Some(wold) = &item.wold {
        return data.find(Some(wold), None, None).cloned();
    }
    if let Some(id) = item.concepticon {
        return data.find(None, Some(id), None).cloned();
    }
    if let Some(gloss) = &item.gloss {
        if let Some(found) = data.find(None, None, Some(gloss)) {
            return Some(found.clone());
        }
    }
    data.catalog_item(&item.id).cloned()
}

/// Chyby slovníku (varování se nevracejí); cesta uvnitř popisu a zpráva.
pub fn validate(size: usize, custom: &[CustomConcept]) -> Vec<String> {
    let mut problems = Vec::new();
    let top = max_size();
    let mut size = size;
    if !(DEFAULT_SIZE..=top).contains(&size) {
        problems.push(format!(
            "vocabulary: velikost slovníku musí být {DEFAULT_SIZE} až {top} pojmů"
        ));
        size = size.clamp(DEFAULT_SIZE, top);
    }
    let present: HashSet<String> = base(size).into_iter().map(|b| b.0).collect();
    let mut seen: HashMap<&str, usize> = HashMap::new();
    for (index, item) in custom.iter().enumerate() {
        if !valid_id(&item.id) {
            problems.push(format!(
                "concepts.{index}.id: ID smí obsahovat jen písmena, číslice, _ . - a začít písmenem nebo číslicí"
            ));
        } else if seen.contains_key(item.id.as_str()) {
            problems.push(format!(
                "concepts.{index}.id: pojem '{}' je v seznamu vícekrát",
                item.id
            ));
        } else if present.contains(&item.id) {
            problems.push(format!(
                "concepts.{index}.id: pojem '{}' už ve slovníku je; zvol jiné ID",
                item.id
            ));
        }
        seen.entry(item.id.as_str()).or_insert(index);
    }
    let data = ConceptData::shared();
    let catalog_ids: HashSet<&str> = data.catalog_ids().map(|c| c.0).collect();
    for (index, item) in custom.iter().enumerate() {
        let at = format!("concepts.{index}");
        if item.wold.is_some() && item.concepticon.is_some() {
            problems.push(format!(
                "{at}: zadej jen jednu vazbu na data: wold, nebo concepticon"
            ));
        } else if let Some(wold) = &item.wold {
            if data.find(Some(wold), None, None).is_none() {
                problems.push(format!("{at}.wold: neznámý význam WOLD '{wold}'"));
            }
        } else if let Some(id) = item.concepticon {
            if data.find(None, Some(id), None).is_none() {
                problems.push(format!(
                    "{at}.concepticon: Concepticon {id} nemá v katalogu žádný význam"
                ));
            }
        }
        if let Some(domain) = &item.domain {
            if !DOMAINS.contains(&domain.as_str()) {
                problems.push(format!("{at}.domain: neznámá doména '{domain}'"));
            }
        }
        let (low, high) = crate::concepts::FREQUENCY_RANGE;
        if item.frequency.is_some_and(|f| !(low..=high).contains(&f)) {
            problems.push(format!(
                "{at}.frequency: frekvence musí být {low} až {high}"
            ));
        }
        if item.borrowed.is_some_and(|b| !(0.0..=1.0).contains(&b)) {
            problems.push(format!("{at}.borrowed: půjčitelnost musí být 0 až 1"));
        }
        if let Some(class) = &item.word_class {
            if !WORD_CLASSES.contains(&class.as_str()) {
                problems.push(format!("{at}.word_class: neznámý slovní druh '{class}'"));
            }
        }
        let mut pairs: HashSet<(String, String, String)> = HashSet::new();
        for (position, related) in item.related.iter().enumerate() {
            let path = format!("{at}.related.{position}");
            if related.concept == item.id {
                problems.push(format!(
                    "{path}.concept: pojem nemůže být příbuzný sám sobě"
                ));
            } else if !present.contains(&related.concept)
                && !seen.contains_key(related.concept.as_str())
            {
                let hint = if catalog_ids.contains(related.concept.as_str()) {
                    " (pojem katalogu je ve větším slovníku)"
                } else {
                    ""
                };
                problems.push(format!(
                    "{path}.concept: neznámý pojem '{}' (není ve slovníku){hint}",
                    related.concept
                ));
            }
            if !RELATION_KINDS.contains(&related.kind.as_str()) {
                problems.push(format!(
                    "{path}.kind: neznámý druh vztahu '{}'",
                    related.kind
                ));
            }
            if related
                .direction
                .as_deref()
                .is_some_and(|d| !RELATION_DIRECTIONS.contains(&d))
            {
                problems.push(format!("{path}.direction: neznámý směr"));
            }
            if related.weight.is_some_and(|w| w < 1) {
                problems.push(format!("{path}.weight: váha musí být aspoň 1"));
            }
            let key = (
                related.concept.clone(),
                related.kind.clone(),
                related
                    .direction
                    .clone()
                    .unwrap_or_else(|| default_direction(&related.kind).to_owned()),
            );
            if !pairs.insert(key) {
                problems.push(format!(
                    "{path}: vztah k '{}' je zadaný vícekrát",
                    related.concept
                ));
            }
        }
    }
    problems
}

/// ID pojmů slovníku o `size` pojmech bez vlastních pojmů (v pořadí simulace).
pub fn base_ids(size: usize) -> Vec<String> {
    base(size.clamp(DEFAULT_SIZE, max_size()))
        .into_iter()
        .map(|b| b.0)
        .collect()
}

/// Varování slovníku (cesta, zpráva): jiný slovník dá jiné výsledky než výchozí svět,
/// vlastní pojem může zdvojit význam WOLD.
pub fn warnings(size: usize, custom: &[CustomConcept]) -> Vec<(String, String)> {
    let size = size.clamp(DEFAULT_SIZE, max_size());
    let mut found = Vec::new();
    if size != DEFAULT_SIZE {
        found.push((
            "vocabulary".to_owned(),
            format!(
                "slovník o {size} pojmech dá jiné výsledky než výchozí svět ({DEFAULT_SIZE} pojmů): slova \
                 nových pojmů soutěží se stávajícími a kalibrace bran platí jen pro výchozí slovník"
            ),
        ));
    }
    if !custom.is_empty() {
        found.push((
            "concepts".to_owned(),
            "vlastní pojmy dají jiné výsledky než výchozí svět: jejich slova soutěží se stávajícími \
             a kalibrace bran platí jen pro výchozí slovník"
                .to_owned(),
        ));
    }
    let data = ConceptData::shared();
    let mut meanings: HashMap<String, String> = HashMap::new();
    for (concept, _) in base(size) {
        let entry = data
            .engine_item(&concept)
            .or_else(|| data.catalog_item(&concept).cloned());
        if let Some(item) = entry {
            meanings.insert(item.wold_id, concept);
        }
    }
    for (index, item) in custom.iter().enumerate() {
        if let Some(linked) = link(item) {
            if let Some(other) = meanings.get(&linked.wold_id) {
                if other != &item.id {
                    found.push((
                        format!("concepts.{index}"),
                        format!(
                            "stejný význam WOLD ('{}') už má pojem '{other}'; slova obou pojmů budou soutěžit",
                            linked.name
                        ),
                    ));
                }
            }
        }
    }
    found
}

/// Slovní druh pojmu z kategorie WOLD: jména a slovesa se ohýbají, ostatní ne.
fn data_class(item: &CatalogItem) -> &'static str {
    match item.category.as_str() {
        "Noun" => "noun",
        "Verb" => "verb",
        _ => "uninflected",
    }
}

fn base_concept(id: &str, source: Source) -> Concept {
    let data = ConceptData::shared();
    let entry = data
        .engine_item(id)
        .or_else(|| data.catalog_item(id).cloned());
    let listed = Defaults::shared().word_class(id).map(str::to_owned);
    let class = match (&entry, source) {
        (None, _) | (_, Source::Default) => listed.unwrap_or_else(|| "uninflected".into()),
        (Some(item), _) => data_class(item).to_owned(),
    };
    match entry {
        None => Concept {
            id: id.to_owned(),
            source,
            domain: "core".into(),
            borrowed: data.mean_borrowed(),
            frequency: None,
            word_class: class,
            concepticon_id: None,
        },
        Some(item) => Concept {
            id: id.to_owned(),
            source,
            domain: item.domain.clone(),
            borrowed: data.borrowed(id),
            frequency: data.frequency(id),
            word_class: class,
            concepticon_id: item.concepticon_id,
        },
    }
}

fn custom_concept(item: &CustomConcept) -> Concept {
    let data = ConceptData::shared();
    let linked = link(item);
    let domain = item
        .domain
        .clone()
        .unwrap_or_else(|| linked.as_ref().map_or("core".into(), |l| l.domain.clone()));
    let scope = item
        .domain
        .as_deref()
        .or_else(|| linked.as_ref().map(|l| l.domain.as_str()));
    let borrowed = item
        .borrowed
        .or_else(|| linked.as_ref().and_then(|l| l.borrowed))
        .unwrap_or_else(|| data.mean_borrowed_in(scope));
    let frequency = item.frequency.unwrap_or_else(|| {
        linked
            .as_ref()
            .and_then(|l| data.item_frequency(l))
            .unwrap_or_else(|| data.mean_frequency(scope))
    });
    let word_class = item
        .word_class
        .clone()
        .unwrap_or_else(|| linked.as_ref().map_or("noun", data_class).to_owned());
    Concept {
        id: item.id.clone(),
        source: Source::Custom,
        domain,
        borrowed,
        frequency: Some(frequency),
        word_class,
        concepticon_id: linked.and_then(|l| l.concepticon_id),
    }
}

/// Slovník o `size` pojmech a s vlastními pojmy; chybný vstup vrátí chybu.
pub fn resolve(size: usize, custom: &[CustomConcept]) -> Result<Vocabulary, String> {
    let errors = validate(size, custom);
    if !errors.is_empty() {
        return Err(errors.join("; "));
    }
    let mut concepts: Vec<Concept> = base(size)
        .into_iter()
        .map(|(id, source)| base_concept(&id, source))
        .collect();
    let mut ordered = custom.to_vec();
    ordered.sort_by(|a, b| a.id.cmp(&b.id));
    concepts.extend(ordered.iter().map(custom_concept));
    Ok(Vocabulary {
        size,
        concepts,
        custom: ordered,
    })
}

impl Vocabulary {
    /// Pojmy světa v pořadí simulace.
    pub fn ids(&self) -> Vec<String> {
        self.concepts.iter().map(|c| c.id.clone()).collect()
    }

    /// Výchozí slovník: bez rozšíření a bez vlastních pojmů (výsledky jako dřív).
    pub fn is_default(&self) -> bool {
        self.size == DEFAULT_SIZE && self.custom.is_empty()
    }

    /// Pojem → třída slova světa (jen ohebné pojmy).
    pub fn word_classes(&self) -> HashMap<String, String> {
        self.concepts
            .iter()
            .filter(|c| c.word_class != "uninflected")
            .map(|c| (c.id.clone(), c.word_class.clone()))
            .collect()
    }

    /// Frekvence, které protojazyk nemá brát z dat podle ID: vlastní pojmy.
    pub fn known_frequencies(&self) -> HashMap<String, f64> {
        self.concepts
            .iter()
            .filter(|c| c.source == Source::Custom)
            .filter_map(|c| c.frequency.map(|f| (c.id.clone(), f)))
            .collect()
    }

    /// Doména a půjčitelnost vlastních pojmů se zapíšou do sloupců pojmů světa (data je neznají).
    pub fn apply_traits(&self, world: &mut World) {
        world.grow_concepts();
        for concept in self.concepts.iter().filter(|c| c.source == Source::Custom) {
            let Some(id) = world.registry.concepts.get(&concept.id) else {
                continue;
            };
            let at = id as usize;
            if let Some(domain) = DOMAINS.iter().position(|d| *d == concept.domain) {
                world.concepts.domain[at] = domain as u8;
            }
            world.concepts.borrowed[at] = concept.borrowed;
        }
    }

    /// Graf pojmů pro posun významu, odvozování a skládání (viz hlavička oddílu).
    pub fn graph(&self, world: &mut World) -> Result<ConceptGraph, String> {
        let defaults = Defaults::shared();
        let core = ConceptGraph::core(
            &mut world.registry,
            crate::data::CORE_SEMANTICS_JSON,
            defaults,
        )?;
        if self.is_default() {
            return Ok(core);
        }
        let ids: HashSet<String> = self.ids().into_iter().collect();
        let default_ids: HashSet<&str> = defaults
            .default_concepts
            .iter()
            .map(String::as_str)
            .collect();
        type Values = BTreeMap<(String, String), BTreeMap<&'static str, i64>>;
        let mut values: Values = BTreeMap::new();
        let names = &world.registry.concepts;
        for relation in &core.relations {
            let (source, target) = (
                names.name(relation.source.0).to_owned(),
                names.name(relation.target.0).to_owned(),
            );
            if ids.contains(&source) && ids.contains(&target) {
                let item = values.entry((source, target)).or_default();
                item.insert("polysemy", i64::from(relation.polysemy));
                item.insert("derivation", i64::from(relation.derivation));
                item.insert("colexification", i64::from(relation.colexification));
            }
        }
        // Pojem enginu má i druhé ID Concepticonu z výřezu (`aliases`).
        let semantics: serde_json::Value =
            serde_json::from_str(crate::data::CATALOG_SEMANTICS_JSON)
                .map_err(|e| format!("v2_catalog_semantics.json: {e}"))?;
        let mut owners: HashMap<i64, Vec<&str>> = HashMap::new();
        for concept in &self.concepts {
            let mut found: Vec<i64> = concept.concepticon_id.into_iter().collect();
            if let Some(alias) = semantics["aliases"][concept.id.as_str()].as_i64() {
                found.push(alias);
            }
            for id in found {
                owners.entry(id).or_default().push(&concept.id);
            }
        }
        for row in semantics["relations"].as_array().ok_or("chybí relations")? {
            let number = |at: usize| row[at].as_i64().unwrap_or(0);
            let (Some(firsts), Some(seconds)) = (owners.get(&number(0)), owners.get(&number(1)))
            else {
                continue;
            };
            for first in firsts {
                for second in seconds {
                    if first == second
                        || (default_ids.contains(first) && default_ids.contains(second))
                    {
                        continue;
                    }
                    let item = values
                        .entry(((*first).to_owned(), (*second).to_owned()))
                        .or_default();
                    for (kind, value) in [
                        ("polysemy", number(2)),
                        ("derivation", number(3)),
                        ("colexification", number(4)),
                    ] {
                        let held = item.entry(kind).or_insert(0);
                        *held = (*held).max(value);
                    }
                }
            }
        }
        for own in &self.custom {
            for related in &own.related {
                let weight = related
                    .weight
                    .unwrap_or_else(|| default_weight(&related.kind));
                let chosen = related
                    .direction
                    .as_deref()
                    .unwrap_or_else(|| default_direction(&related.kind));
                let directions: &[&str] = if chosen == "both" || related.kind == "colexification" {
                    &["to", "from"]
                } else if chosen == "to" {
                    &["to"]
                } else {
                    &["from"]
                };
                let kind: &'static str = RELATION_KINDS
                    .iter()
                    .find(|k| **k == related.kind)
                    .copied()
                    .ok_or("neznámý druh vztahu")?;
                for direction in directions {
                    let pair = if *direction == "to" {
                        (own.id.clone(), related.concept.clone())
                    } else {
                        (related.concept.clone(), own.id.clone())
                    };
                    values.entry(pair).or_default().insert(kind, weight);
                }
            }
        }
        let mut relations = Vec::new();
        for ((source, target), item) in values {
            if item.values().all(|v| *v == 0) {
                continue;
            }
            let get = |k: &str| item.get(k).copied().unwrap_or(0) as u32;
            relations.push(Relation {
                source: world.registry.concept(&source),
                target: world.registry.concept(&target),
                polysemy: get("polysemy"),
                derivation: get("derivation"),
                colexification: get("colexification"),
            });
        }
        Ok(ConceptGraph::with_relations(
            &mut world.registry,
            relations,
            defaults,
        ))
    }
}
