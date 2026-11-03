//! Export běhu pro UI: stejné schéma jako `cee.v2.export` (`cee-v2/1`).
//!
//! Jeden JSON popisuje svět tak, jak ho UI potřebuje: území, skupiny a vazby (mapa),
//! snímky dialektů a jazyků (časová osa), strom linií, dnešní slova každé skupiny
//! s původem, gramatiku skupin. Server (`runner.py`) a UI proto fungují beze změny.
//! Pořadí a jména polí se shodují s Pythonem; seřazení podle jmen (ne podle čísel).
//!
//! **Hotové v R0:** území, skupiny, vazby, snímky, slovník, gramatika, události a
//! `frame`. **Zjednodušené (R1d):** `states`, `borders`, `census` regionů, `dialect_facts`,
//! `lineages` (strom jazyků vznikne až z pozorování R1d) a `endonym` v rámu.

use serde_json::{json, Map, Value};

use crate::grammar::Catalog;
use crate::ids::GroupId;
use crate::model::repertoire::Payload;
use crate::simulation::Simulation;
use crate::world::World;

pub const FORMAT: &str = "cee-v2/1";

/// Události pro časovou osu UI; ostatní (inovace, milníky šíření…) jsou šum.
pub const TIMELINE: [&str; 43] = [
    "border", "contact", "migration", "conquest", "war", "epidemic", "state_collapse", "religious_change", "codification", "printing", "schooling", "bilingualism", "transmission_stopped", "language_shift", "language_emerged", "language_split", "language_ended", "grammaticalized", "exapted", "refinement", "state", "language_policy", "annexation", "secession", "collapse", "border_policy", "lingua_franca", "standard", "schools", "nativization", "revival_movement", "revival", "transmission_resumed", "preserve", "identity", "immigration", "plague", "recovery", "resettlement", "trade", "prestige", "foreign_elite", "elite_assimilation",
];

fn position(value: Option<(f64, f64)>) -> Value {
    value.map_or(Value::Null, |(x, y)| json!([x, y]))
}

fn observed_languages(simulation: &Simulation) -> std::collections::BTreeMap<String, String> {
    let mut found = std::collections::BTreeMap::new();
    if let Some(last) = simulation.history.snapshots.last() {
        for (lineage, groups) in &last.languages {
            for group in groups {
                found.insert(group.clone(), lineage.clone());
            }
        }
    }
    found
}

fn group_view(world: &World, group: GroupId, lineage: Option<&String>) -> Value {
    let at = group.index();
    let g = &world.groups;
    let code = g.main_code(group);
    let name = |id: GroupId| -> Value { if id.is_none() { Value::Null } else { world.group_name(id).into() } };
    let community = if g.community[at].is_none() { world.group_name(group).into() } else { name(g.community[at]) };
    json!({
        "id": world.group_name(group), "territory": world.registry.territories.name(g.territory[at].0),
        "position": position(world.position_of(group)),
        "population": g.population[at], "prestige": g.prestige[at], "openness": g.openness[at],
        "generation_years": g.generation_years[at], "community": community,
        "domain": g.domain[at].name(), "written": g.written[at], "aggregate": g.aggregate[at],
        "code_language": world.registry.languages.name(code.language.0), "observed_language": lineage,
        "l2_share": code.l2_share, "literacy": g.literacy[at], "schooling": g.schooling[at],
        "standard": name(g.standard[at]), "liturgy": name(g.liturgy[at]),
        "loyalty": g.loyalty[at], "home_pull": g.home_pull[at], "preserved": g.preserved[at],
        "revival": g.revival[at],
    })
}

/// Dnešní slova skupiny: tvar (IPA), lexém a jeho původ.
pub fn lexicon(world: &World, group: GroupId) -> Map<String, Value> {
    let mut result = Map::new();
    let Some(table) = world.segments() else { return result };
    let code = world.groups.main_code(group);
    let mut concepts: Vec<(String, usize)> = code
        .phonology
        .dominant
        .iter()
        .enumerate()
        .filter(|(_, root)| !root.is_none())
        .map(|(concept, _)| (world.registry.concepts.name(concept as u32).to_owned(), concept))
        .collect();
    concepts.sort();
    for (concept, number) in concepts {
        let root = code.phonology.dominant[number];
        let at = root.index();
        let meta = &world.morphemes.meta[at];
        let language = world.morphemes.language[at];
        let loan = language != code.language;
        let origin_group = world.morphemes.origin_group[at];
        let origin = meta.etymology.clone().unwrap_or_else(|| {
            if origin_group.is_none() { "inherited".into() } else { "coinage".into() }
        });
        result.insert(
            concept,
            json!({
                "form": table.render(world.form_of(group, root)),
                "root": world.registry.morphemes.name(root.0),
                "language": world.registry.languages.name(language.0),
                "loan": loan,
                "origin": origin,
                "sources": meta.sources,
                "base": meta.base.map(|b| world.registry.morphemes.name(b.0)),
                "since": if origin_group.is_none() { Value::Null } else { world.morphemes.origin_tick[at].into() },
            }),
        );
    }
    result
}

/// Převládající konstrukce každé gramatické funkce skupiny.
pub fn grammar(world: &World, group: GroupId) -> Map<String, Value> {
    let mut result = Map::new();
    let Ok(catalog) = Catalog::shared().with_overrides(&world.params) else { return result };
    let mut functions: Vec<&crate::grammar::GrammaticalFunction> = catalog.functions.iter().collect();
    functions.sort_by(|a, b| a.id.cmp(&b.id));
    for entry in functions {
        let name = format!("construction:{}", entry.id);
        let Some(variable) = world.registry.variables.get(&name) else { continue };
        let variable = crate::ids::VariableId(variable);
        if variable.index() >= world.variables.len() {
            continue;
        }
        let Some((variant, _)) = world.dominant(group, variable) else { continue };
        let Payload::Construction(construction) = &world.variants.payload[variant.index()] else { continue };
        let exponent = match (&construction.exponent, world.segments()) {
            (Some(id), Some(table)) => world
                .registry
                .morphemes
                .get(id)
                .map(|m| table.render(world.bank.form(world.morphemes.form[m as usize]))),
            _ => None,
        };
        result.insert(
            entry.id.clone(),
            json!({
                "kind": construction.kind, "source": construction.source, "stage": construction.stage,
                "order": construction.order, "reinforcer": construction.reinforcer,
                "donor": construction.donor, "exponent": exponent,
            }),
        );
    }
    result
}

fn census(world: &World) -> Value {
    let mut by_region: std::collections::BTreeMap<String, (Map<String, Value>, Map<String, Value>, f64)> = Default::default();
    let mut people: std::collections::BTreeMap<String, f64> = Default::default();
    let mut tally: std::collections::BTreeMap<String, (std::collections::BTreeMap<String, f64>, std::collections::BTreeMap<String, f64>)> =
        Default::default();
    for group in world.group_ids() {
        let at = group.index();
        if world.groups.written[at] {
            continue;
        }
        // Region = předek území na úrovni `region`.
        let mut territory = world.groups.territory[at];
        let region = loop {
            if territory.is_none() {
                break None;
            }
            let node = &world.territories[territory.index()];
            if node.level == crate::model::territory::TerritoryLevel::Region {
                break Some(world.registry.territories.name(territory.0).to_owned());
            }
            territory = node.parent;
        };
        let Some(region) = region else { continue };
        let language = world.registry.languages.name(world.groups.main_code(group).language.0).to_owned();
        let population = f64::from(world.groups.population[at]);
        let entry = tally.entry(region.clone()).or_default();
        if world.groups.domain[at] == crate::model::group::Domain::Home {
            *entry.0.entry(language).or_insert(0.0) += population;
            *people.entry(region).or_insert(0.0) += population;
        } else {
            *entry.1.entry(language).or_insert(0.0) += population;
        }
    }
    let _ = &mut by_region;
    let mut out = Map::new();
    for (region, (home, public)) in tally {
        let total = people.get(&region).copied().filter(|&p| p != 0.0).unwrap_or(1.0);
        let share = |counts: std::collections::BTreeMap<String, f64>| -> Value {
            Value::Object(counts.into_iter().map(|(l, c)| (l, json!(c / total))).collect())
        };
        out.insert(region, json!({"home": share(home), "public": share(public), "state": Value::Null}));
    }
    Value::Object(out)
}

/// Stav a historie běhu jako JSON slovník (`export.export`).
pub fn export(simulation: &Simulation, only_timeline: bool) -> Value {
    let world = &simulation.world;
    let history = &simulation.history;
    let observed = observed_languages(simulation);
    let mut territories: Vec<(&str, usize)> =
        (0..world.territories.len()).map(|i| (world.registry.territories.name(i as u32), i)).collect();
    territories.sort();
    let territories: Vec<Value> = territories
        .into_iter()
        .map(|(name, i)| {
            let node = &world.territories[i];
            json!({
                "id": name, "level": node.level.name(),
                "parent": if node.parent.is_none() { Value::Null } else { world.registry.territories.name(node.parent.0).into() },
                "position": position(node.position), "terrain": node.terrain,
                "native_language": if node.native_language.is_none() { Value::Null } else { world.registry.languages.name(node.native_language.0).into() },
            })
        })
        .collect();
    let ids = world.group_ids();
    let mut links: Vec<(&str, &str, Value)> = world
        .links
        .iter()
        .map(|(&(source, target), link)| {
            let (s, t) = (world.group_name(source), world.group_name(target));
            (s, t, json!({"source": s, "target": t, "strength": link.strength, "kind": link.kind.name()}))
        })
        .collect();
    links.sort_by(|a, b| (a.0, a.1).cmp(&(b.0, b.1)));
    let mut standards = Map::new();
    for (key, group) in &world.society.standards {
        standards.insert(key.clone(), world.group_name(*group).into());
    }
    let timeline: Vec<&str> = TIMELINE.to_vec();
    let events: Vec<Value> = history
        .events
        .iter()
        .filter(|e| !only_timeline || e.get("kind").and_then(Value::as_str).is_some_and(|k| timeline.contains(&k)))
        .map(|e| Value::Object(e.clone()))
        .collect();
    json!({
        "format": FORMAT, "seed": world.seed, "start_year": world.start_year, "year": simulation.year(),
        "tick": simulation.tick,
        "territories": territories,
        "groups": ids.iter().map(|&g| group_view(world, g, observed.get(world.group_name(g)))).collect::<Vec<_>>(),
        "links": links.into_iter().map(|l| l.2).collect::<Vec<_>>(),
        "snapshots": history.snapshots.iter().map(|s| json!({
            "tick": s.tick, "year": s.year, "dialects": s.dialects, "languages": s.languages,
        })).collect::<Vec<_>>(),
        "lineages": Vec::<Value>::new(),
        "lexicon": Value::Object(ids.iter().map(|&g| (world.group_name(g).to_owned(), Value::Object(lexicon(world, g)))).collect()),
        "grammar": Value::Object(ids.iter().map(|&g| (world.group_name(g).to_owned(), Value::Object(grammar(world, g)))).collect()),
        "states": Vec::<Value>::new(),
        "borders": Vec::<Value>::new(),
        "standards": Value::Object(standards),
        "dialect_facts": Vec::<Value>::new(),
        "census": census(world),
        "events": events,
    })
}

/// Lehký snímek pro průběžné kreslení během běhu (`export.frame`).
pub fn frame(simulation: &Simulation) -> Value {
    let world = &simulation.world;
    let snapshot = simulation.history.snapshots.last();
    let observed = observed_languages(simulation);
    json!({
        "year": simulation.year(), "tick": simulation.tick,
        "groups": world.group_ids().iter().map(|&g| json!({
            "id": world.group_name(g), "population": world.groups.population[g.index()],
            "l2_share": world.groups.main_code(g).l2_share,
            "observed_language": observed.get(world.group_name(g)),
        })).collect::<Vec<_>>(),
        "dialects": snapshot.map_or(Vec::new(), |s| s.dialects.clone()),
        "languages": snapshot.map_or(Default::default(), |s| s.languages.clone()),
        "census": census(world),
        "states": Vec::<Value>::new(),
        "endonyms": Value::Object(Map::new()),
        "dialect_facts": Vec::<Value>::new(),
    })
}
