//! Export běhu pro UI: stejné schéma jako `cee.v2.export` (`cee-v2/1`).
//!
//! Jeden JSON popisuje svět tak, jak ho UI potřebuje: území, skupiny a vazby (mapa),
//! snímky dialektů a jazyků (časová osa), strom linií, dnešní slova každé skupiny
//! s původem, gramatiku skupin. Server (`runner.py`) a UI proto fungují beze změny.
//! Pořadí a jména polí se shodují s Pythonem; seřazení podle jmen (ne podle čísel).
//!
//! `states`, `borders`, `census` počítá `polity`; `lineages`, `dialect_facts` a `endonym`
//! vycházejí z pozorování (`observe`) a podkladů jmen (`naming`).

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

use crate::grammar::Catalog;
use crate::ids::GroupId;
use crate::model::repertoire::Payload;
use crate::naming;
use crate::polity;
use crate::simulation::Simulation;
use crate::world::World;

pub const FORMAT: &str = "cee-v2/1";

/// Události pro časovou osu UI; ostatní (inovace, milníky šíření…) jsou šum.
pub const TIMELINE: [&str; 44] = [
    "study_case",
    "border",
    "contact",
    "migration",
    "conquest",
    "war",
    "epidemic",
    "state_collapse",
    "religious_change",
    "codification",
    "printing",
    "schooling",
    "bilingualism",
    "transmission_stopped",
    "language_shift",
    "language_emerged",
    "language_split",
    "language_ended",
    "grammaticalized",
    "exapted",
    "refinement",
    "state",
    "language_policy",
    "annexation",
    "secession",
    "collapse",
    "border_policy",
    "lingua_franca",
    "standard",
    "schools",
    "nativization",
    "revival_movement",
    "revival",
    "transmission_resumed",
    "preserve",
    "identity",
    "immigration",
    "plague",
    "recovery",
    "resettlement",
    "trade",
    "prestige",
    "foreign_elite",
    "elite_assimilation",
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
    let name = |id: GroupId| -> Value {
        if id.is_none() {
            Value::Null
        } else {
            world.group_name(id).into()
        }
    };
    let community = if g.community[at].is_none() {
        world.group_name(group).into()
    } else {
        name(g.community[at])
    };
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
        "root_retention": root_retention(world, group),
    })
}

/// Podíl pojmů skupiny vyjádřených zděděným kořenem (zahrnuje obnovu zdrobnělinou a zkrácení).
pub fn root_retention(world: &World, group: GroupId) -> f64 {
    crate::gates::metrics::root_retention(world, group)
}

/// Dnešní slova skupiny: tvar (IPA), lexém a jeho původ.
pub fn lexicon(world: &World, group: GroupId) -> Map<String, Value> {
    let mut result = Map::new();
    let Some(table) = world.segments() else {
        return result;
    };
    let code = world.groups.main_code(group);
    let total_concepts = world
        .registry
        .concepts
        .len()
        .max(code.phonology.dominant.len());
    let mut concepts: Vec<(String, crate::ids::MorphemeId)> = (0..total_concepts)
        .filter_map(|concept| {
            let root = world.dominant_or_plural_root(group, crate::ids::ConceptId::new(concept));
            (!root.is_none()).then(|| {
                (
                    world.registry.concepts.name(concept as u32).to_owned(),
                    root,
                )
            })
        })
        .collect();
    concepts.sort_by(|a, b| a.0.cmp(&b.0));
    for (concept, root) in concepts {
        let at = root.index();
        let meta = &world.morphemes.meta[at];
        let language = world.morphemes.language[at];
        let loan = language != code.language;
        let origin_group = world.morphemes.origin_group[at];
        let origin = meta.etymology.clone().unwrap_or_else(|| {
            if origin_group.is_none() {
                "inherited".into()
            } else {
                "coinage".into()
            }
        });
        let form = world.adapted_form_of(group, root);
        result.insert(
            concept,
            json!({
                "form": table.render(&form),
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

/// Slovník jazyka v jednom okamžiku: skupina, podle které se tvary berou, a tvar (IPA) pojmů.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct LanguageLexicon {
    pub group: String,
    pub forms: BTreeMap<String, String>,
}

/// Tvary pojmů skupiny (IPA) bez původu; lehčí verze [`lexicon`] pro snímky a protojazyk.
pub fn forms(world: &World, group: GroupId) -> BTreeMap<String, String> {
    let mut result = BTreeMap::new();
    let Some(table) = world.segments() else {
        return result;
    };
    let code = world.groups.main_code(group);
    let total = world
        .registry
        .concepts
        .len()
        .max(code.phonology.dominant.len());
    for concept in 0..total {
        let root = world.dominant_or_plural_root(group, crate::ids::ConceptId::new(concept));
        if root.is_none() {
            continue;
        }
        result.insert(
            world.registry.concepts.name(concept as u32).to_owned(),
            table.render(&world.adapted_form_of(group, root)),
        );
    }
    result
}

/// Mluvčí skupina, podle které se ukazuje slovník jazyka: největší domácí skupina (ne souhrnná),
/// jinak největší ze všech; při shodě abecedně první.
fn representative(world: &World, groups: &[GroupId]) -> Option<GroupId> {
    let g = &world.groups;
    let key = |&id: &GroupId| {
        let at = id.index();
        let home = g.domain[at] == crate::model::group::Domain::Home && !g.aggregate[at];
        (home, g.population[at])
    };
    groups.iter().copied().max_by(|a, b| {
        let (ka, kb) = (key(a), key(b));
        ka.0.cmp(&kb.0)
            .then(ka.1.partial_cmp(&kb.1).unwrap_or(std::cmp::Ordering::Equal))
            .then(world.group_name(*b).cmp(world.group_name(*a)))
    })
}

/// Slovník každého jazyka podle skupin, které ho mluví (jazyk → skupiny).
fn lexicons_of(
    world: &World,
    members: BTreeMap<String, Vec<GroupId>>,
) -> BTreeMap<String, LanguageLexicon> {
    members
        .into_iter()
        .filter_map(|(language, groups)| {
            let group = representative(world, &groups)?;
            Some((
                language,
                LanguageLexicon {
                    group: world.group_name(group).to_owned(),
                    forms: forms(world, group),
                },
            ))
        })
        .collect()
}

/// Slovník podle jazyka kódu skupin (na startu: protojazyky popisu světa).
pub fn code_language_lexicons(world: &World) -> BTreeMap<String, LanguageLexicon> {
    let mut members: BTreeMap<String, Vec<GroupId>> = BTreeMap::new();
    for g in world.group_ids() {
        let language = world.groups.main_code(g).language;
        members
            .entry(world.registry.languages.name(language.0).to_owned())
            .or_default()
            .push(g);
    }
    lexicons_of(world, members)
}

/// Slovník každého pozorovaného jazyka (linie posledního snímku); bez snímku podle jazyka kódu.
pub fn language_lexicons(simulation: &Simulation) -> BTreeMap<String, LanguageLexicon> {
    let world = &simulation.world;
    let Some(last) = simulation.history.snapshots.last() else {
        return code_language_lexicons(world);
    };
    let members: BTreeMap<String, Vec<GroupId>> = last
        .languages
        .iter()
        .map(|(language, groups)| {
            let ids = groups
                .iter()
                .filter_map(|name| world.registry.groups.get(name).map(GroupId))
                .filter(|&id| world.groups.contains(id))
                .collect();
            (language.clone(), ids)
        })
        .collect();
    lexicons_of(world, members)
}

/// Části klíče zvukové změny (`rodina|cíl|operace|rysy|hláska|vlevo|vpravo|přízvuk|…`).
fn sound_parts(variable: &str) -> Value {
    let key = variable.strip_prefix("process:").unwrap_or(variable);
    let parts: Vec<&str> = key.split('|').collect();
    let part = |i: usize| {
        parts
            .get(i)
            .filter(|p| !p.is_empty())
            .map_or(Value::Null, |p| json!(p))
    };
    json!({
        "family": part(0), "target": part(1), "operation": part(2), "features": part(3),
        "segment": part(4), "left": part(5), "right": part(6), "stress": part(7),
        "medial": parts.get(8).is_some_and(|p| *p == "medial"),
    })
}

/// Zvukové změny a analogie po jazycích (dok. 36): které vesnice změnu přijaly a kdy.
///
/// Zvuková změna = procesní proměnná, která se ve skupině ustálila (`established`); u každé
/// skupiny rok ustálení, případně rok uzavření procesu (`process_closed`) s počtem reliktů.
/// Analogie = vyrovnání tvaru (`analogy`) s pojmem a buňkou paradigmatu. Jazyk skupiny je
/// linie posledního snímku; skupiny, které už nežijí, jsou pod `null`.
pub fn change_history(simulation: &Simulation) -> Vec<Value> {
    let history = &simulation.history;
    let observed = observed_languages(simulation);
    // (proměnná, skupina) → (rok ustálení, rok uzavření, relikty)
    type Adopted = (f64, Option<f64>, f64);
    let mut sound: BTreeMap<String, BTreeMap<String, Adopted>> = BTreeMap::new();
    let text =
        |e: &Map<String, Value>, k: &str| e.get(k).and_then(Value::as_str).map(str::to_owned);
    let year = |e: &Map<String, Value>| e.get("year").and_then(Value::as_f64).unwrap_or(0.0);
    for event in history.of_kind("established") {
        let (Some(variable), Some(group)) = (text(&event, "variable"), text(&event, "group"))
        else {
            continue;
        };
        if !variable.starts_with("process:") {
            continue;
        }
        sound
            .entry(variable)
            .or_default()
            .entry(group)
            .or_insert((year(&event), None, 0.0));
    }
    for event in history.of_kind("process_closed") {
        let (Some(variable), Some(group)) = (text(&event, "variable"), text(&event, "group"))
        else {
            continue;
        };
        let relics = event.get("relics").and_then(Value::as_f64).unwrap_or(0.0);
        let entry =
            sound
                .entry(variable)
                .or_default()
                .entry(group)
                .or_insert((year(&event), None, 0.0));
        entry.1.get_or_insert(year(&event));
        entry.2 += relics;
    }
    // (proměnná, operace, pojem, buňka) → skupina → rok
    let mut analogy: BTreeMap<(String, String, String, String), BTreeMap<String, f64>> =
        BTreeMap::new();
    for event in history.of_kind("analogy") {
        let (Some(variable), Some(group)) = (text(&event, "variable"), text(&event, "group"))
        else {
            continue;
        };
        let key = (
            variable,
            text(&event, "operation").unwrap_or_default(),
            text(&event, "concept").unwrap_or_default(),
            text(&event, "cell").unwrap_or_default(),
        );
        analogy
            .entry(key)
            .or_default()
            .entry(group)
            .or_insert(year(&event));
    }
    let mut by_language: BTreeMap<Option<String>, Vec<Value>> = BTreeMap::new();
    let language_of = |group: &str| observed.get(group).cloned();
    for (variable, groups) in sound {
        let mut split: BTreeMap<Option<String>, Vec<Value>> = BTreeMap::new();
        for (group, (since, closed, relics)) in groups {
            split.entry(language_of(&group)).or_default().push(json!({
                "group": group, "year": since, "closed": closed, "relics": relics,
            }));
        }
        for (language, list) in split {
            let first = list
                .iter()
                .filter_map(|g| g["year"].as_f64())
                .fold(f64::INFINITY, f64::min);
            let mut item =
                json!({ "kind": "sound", "variable": variable, "year": first, "groups": list });
            if let (Some(o), Value::Object(parts)) = (item.as_object_mut(), sound_parts(&variable))
            {
                o.extend(parts);
            }
            by_language.entry(language).or_default().push(item);
        }
    }
    for ((variable, operation, concept, cell), groups) in analogy {
        let mut split: BTreeMap<Option<String>, Vec<Value>> = BTreeMap::new();
        for (group, since) in groups {
            split
                .entry(language_of(&group))
                .or_default()
                .push(json!({ "group": group, "year": since }));
        }
        for (language, list) in split {
            let first = list
                .iter()
                .filter_map(|g| g["year"].as_f64())
                .fold(f64::INFINITY, f64::min);
            by_language.entry(language).or_default().push(json!({
                "kind": "analogy", "variable": variable, "operation": operation,
                "concept": if concept.is_empty() { Value::Null } else { json!(concept) },
                "cell": if cell.is_empty() { Value::Null } else { json!(cell) },
                "year": first, "groups": list,
            }));
        }
    }
    let speakers: BTreeMap<String, usize> = simulation
        .history
        .snapshots
        .last()
        .map(|s| {
            s.languages
                .iter()
                .map(|(l, g)| (l.clone(), g.len()))
                .collect()
        })
        .unwrap_or_default();
    by_language
        .into_iter()
        .map(|(language, mut changes)| {
            changes.sort_by(|a, b| {
                let y = |v: &Value| v["year"].as_f64().unwrap_or(0.0);
                y(a).partial_cmp(&y(b)).unwrap_or(std::cmp::Ordering::Equal)
            });
            let groups = language
                .as_ref()
                .and_then(|l| speakers.get(l))
                .copied()
                .unwrap_or(0);
            json!({ "language": language, "groups": groups, "changes": changes })
        })
        .collect()
}

/// Převládající konstrukce každé gramatické funkce skupiny.
pub fn grammar(world: &World, group: GroupId) -> Map<String, Value> {
    let mut result = Map::new();
    let Ok(catalog) = Catalog::shared().with_overrides(&world.params) else {
        return result;
    };
    let mut functions: Vec<&crate::grammar::GrammaticalFunction> =
        catalog.functions.iter().collect();
    functions.sort_by(|a, b| a.id.cmp(&b.id));
    for entry in functions {
        let name = format!("construction:{}", entry.id);
        let Some(variable) = world.registry.variables.get(&name) else {
            continue;
        };
        let variable = crate::ids::VariableId(variable);
        if variable.index() >= world.variables.len() {
            continue;
        }
        let Some((variant, _)) = world.dominant(group, variable) else {
            continue;
        };
        let Payload::Construction(construction) = &world.variants.payload[variant.index()] else {
            continue;
        };
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

/// Strom jazyků: linie, jejich rodiče a doba trvání (z událostí pozorování).
pub fn lineages(simulation: &Simulation) -> Vec<Value> {
    let world = &simulation.world;
    let mut found: std::collections::BTreeMap<String, Map<String, Value>> = Default::default();
    for event in simulation.history.events.iter() {
        match event.get("kind").and_then(Value::as_str) {
            Some("language_emerged" | "language_split") => {
                let Some(id) = event.get("lineage").and_then(Value::as_str) else {
                    continue;
                };
                let mut item = Map::new();
                item.insert("id".into(), id.into());
                item.insert(
                    "parent".into(),
                    event.get("parent").cloned().unwrap_or(Value::Null),
                );
                item.insert(
                    "start_year".into(),
                    event.get("year").cloned().unwrap_or(Value::Null),
                );
                item.insert("end_year".into(), Value::Null);
                item.insert(
                    "groups_at_start".into(),
                    event.get("groups").cloned().unwrap_or_else(|| json!([])),
                );
                found.insert(id.to_owned(), item);
            }
            Some("language_ended") => {
                if let Some(item) = event
                    .get("lineage")
                    .and_then(Value::as_str)
                    .and_then(|id| found.get_mut(id))
                {
                    item.insert(
                        "end_year".into(),
                        event.get("year").cloned().unwrap_or(Value::Null),
                    );
                }
            }
            _ => {}
        }
    }
    let last = simulation.history.snapshots.last();
    let mut out: Vec<Map<String, Value>> = found.into_values().collect();
    for item in &mut out {
        let id = item["id"].as_str().unwrap_or_default().to_owned();
        let groups: Vec<String> = last
            .and_then(|s| s.languages.get(&id))
            .cloned()
            .unwrap_or_default();
        let at_start: Vec<String> = item["groups_at_start"]
            .as_array()
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(str::to_owned))
                    .collect()
            })
            .unwrap_or_default();
        item.insert(
            "endonym".into(),
            if groups.is_empty() {
                Value::Null
            } else {
                naming::endonym(world, &groups).map_or(Value::Null, Value::from)
            },
        );
        item.insert(
            "origin_region".into(),
            naming::origin_region(world, &at_start).map_or(Value::Null, Value::from),
        );
        item.insert("groups".into(), json!(groups));
    }
    out.sort_by(|a, b| {
        let year = |m: &Map<String, Value>| m["start_year"].as_f64().unwrap_or(0.0);
        year(a)
            .partial_cmp(&year(b))
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a["id"].as_str().cmp(&b["id"].as_str()))
    });
    out.into_iter().map(Value::Object).collect()
}

/// Nářečí posledního pozorování s fakty pro jméno (`naming::dialects`).
pub fn dialect_facts(simulation: &Simulation) -> Vec<Value> {
    let Some(snapshot) = simulation.history.snapshots.last() else {
        return Vec::new();
    };
    let world = &simulation.world;
    let lineage_of: std::collections::BTreeMap<String, String> = snapshot
        .languages
        .iter()
        .flat_map(|(l, groups)| groups.iter().map(move |g| (g.clone(), l.clone())))
        .collect();
    let alive = |name: &String| {
        world
            .registry
            .groups
            .get(name)
            .is_some_and(|g| world.groups.contains(crate::ids::GroupId(g)))
    };
    let clusters: Vec<Vec<String>> = snapshot
        .dialects
        .iter()
        .map(|c| c.iter().filter(|g| alive(g)).cloned().collect::<Vec<_>>())
        .filter(|c| !c.is_empty())
        .collect();
    naming::dialects(world, &clusters, &lineage_of)
}

/// Stav a historie běhu jako JSON slovník (`export.export`).
pub fn export(simulation: &Simulation, only_timeline: bool) -> Value {
    let world = &simulation.world;
    let history = &simulation.history;
    let observed = observed_languages(simulation);
    let onomastics = crate::onomastics::export_world_onomastics(world);
    let mut territories: Vec<(&str, usize)> = (0..world.territories.len())
        .map(|i| (world.registry.territories.name(i as u32), i))
        .collect();
    territories.sort();
    let territories: Vec<Value> = territories
        .into_iter()
        .map(|(name, i)| {
            let node = &world.territories[i];
            let top = onomastics
                .get("toponyms")
                .and_then(|t| t.get(name))
                .cloned()
                .unwrap_or(Value::Null);
            let place_name = top.get("name").cloned().unwrap_or(Value::Null);
            json!({
                "id": name, "name": place_name, "level": node.level.name(),
                "parent": if node.parent.is_none() { Value::Null } else { world.registry.territories.name(node.parent.0).into() },
                "position": position(node.position), "terrain": node.terrain,
                "native_language": if node.native_language.is_none() { Value::Null } else { world.registry.languages.name(node.native_language.0).into() },
                "toponym": top,
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
        .filter(|e| {
            !only_timeline
                || e.get("kind")
                    .and_then(Value::as_str)
                    .is_some_and(|k| timeline.contains(&k))
        })
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
        "lineages": lineages(simulation),
        "lexicon": Value::Object(ids.iter().map(|&g| (world.group_name(g).to_owned(), Value::Object(lexicon(world, g)))).collect()),
        "grammar": Value::Object(ids.iter().map(|&g| (world.group_name(g).to_owned(), Value::Object(grammar(world, g)))).collect()),
        "states": polity::states(world),
        "borders": polity::borders(world),
        "standards": Value::Object(standards),
        "dialect_facts": dialect_facts(simulation),
        "onomastics": onomastics,
        "census": polity::language_census(world),
        "events": events,
        "proto_lexicon": history.proto,
        "lexicon_by_language": language_lexicons(simulation),
        "change_history": change_history(simulation),
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
        "census": polity::language_census(world),
        "states": polity::states(world).into_iter().map(|s| json!({
            "id": s["id"], "name": s["name"], "regions": s["regions"],
        })).collect::<Vec<_>>(),
        "endonyms": Value::Object(
            snapshot.map_or_else(Default::default, |s| s.languages.iter()
                .map(|(l, groups)| (l.clone(), naming::endonym(world, groups).map_or(Value::Null, Value::from)))
                .collect())
        ),
        "dialect_facts": dialect_facts(simulation),
    })
}
