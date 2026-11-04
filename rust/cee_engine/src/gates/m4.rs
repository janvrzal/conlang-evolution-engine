//! Brána M4 (`test_v2_m4_gate.py`): syntax a gramatikalizace. Přirozená eroze konkrétní
//! koncovky je v simulaci vzácná, proto se odpověď syntaxe ověřuje kontrolovanými pokusy:
//! na začátku se koncovka nebo záporka oslabí a sleduje se, co jazyk udělá.

use std::collections::{BTreeMap, BTreeSet};

use super::metrics::{lexicon_profile, maximum, mean, minimum, text, variant_named};
use super::{Batch, Cmp, Report, Runner};
use crate::grammar::Catalog;
use crate::ids::{CellId, MorphemeId};
use crate::model::forms::UnitForm;
use crate::scenarios::{village_grid_default, SeedOptions};
use crate::syntax;
use crate::world::World;
use crate::{Simulation, SimulationConfig};

/// Pokus s oslabenou koncovkou buňky `cell` nebo záporkou `particle` (pojem) ve všech skupinách.
fn experiment(seed: i64, cell: Option<&str>, particle: Option<&str>) -> Result<Simulation, String> {
    let options = SeedOptions {
        syntax: true,
        semantics: true,
        ..SeedOptions::default()
    };
    let world = village_grid_default(6, 1, seed, &options)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    let world = &mut simulation.world;
    let cell_id = cell
        .and_then(|name| world.registry.cells.get(name))
        .map(CellId);
    let concept = particle.and_then(|name| world.registry.concepts.get(name));
    for group in world.group_ids() {
        if let Some(cell_id) = cell_id {
            let units: Vec<MorphemeId> = world
                .groups
                .main_code(group)
                .phonology
                .vocabulary
                .iter()
                .filter(|unit| world.morphemes.cell[unit.index()] == cell_id)
                .collect();
            for unit in units {
                let lexeme = world.morphemes.lexeme_id(unit);
                let citation = world.form_of(group, lexeme).to_vec();
                let exponent = world.unit_of(group, unit).exponent;
                let form = world.bank.id_of(&citation);
                crate::views::set_form(
                    world,
                    group,
                    unit,
                    UnitForm {
                        form,
                        boundary: citation.len() as i32,
                        exponent,
                    },
                );
            }
        }
        if let Some(concept) = concept {
            // Záporka obroušená na samotnou samohlásku.
            let root = world
                .groups
                .main_code(group)
                .phonology
                .dominant_of(crate::ids::ConceptId(concept));
            if !root.is_none() {
                let table = world.table.clone().ok_or("svět nemá tabulku hlásek")?;
                let vowel = world
                    .form_of(group, root)
                    .iter()
                    .copied()
                    .find(|&s| table.is_vowel(s));
                if let Some(vowel) = vowel {
                    let form = world.bank.id_of(&[vowel]);
                    crate::views::set_form(
                        world,
                        group,
                        root,
                        UnitForm {
                            form,
                            boundary: -1,
                            exponent: MorphemeId::NONE,
                        },
                    );
                }
            }
        }
        world.groups.main_code_mut(group).phonology.version += 1;
    }
    Ok(simulation)
}

/// Kolik skupin má dominantní konstrukci funkce daného druhu.
pub fn kinds(world: &World, function: &str) -> BTreeMap<String, usize> {
    let mut counts = BTreeMap::new();
    for group in world.group_ids() {
        if let Some(construction) = syntax::dominant(world, group, function) {
            *counts.entry(construction.kind).or_insert(0) += 1;
        }
    }
    counts
}

pub fn kind_count(world: &World, function: &str, kind: &str) -> f64 {
    kinds(world, function).get(kind).copied().unwrap_or(0) as f64
}

pub fn run_control(seed: i64) -> Result<Simulation, String> {
    let mut simulation = experiment(seed, None, None)?;
    simulation.run(1500.0)?;
    Ok(simulation)
}

pub fn run_obj_eroded(seed: i64) -> Result<Simulation, String> {
    let mut simulation = experiment(seed, Some("OBJ"), None)?;
    simulation.run(1500.0)?;
    Ok(simulation)
}

/// Velký cyklus: běh po 2 500 letech a druhy konstrukcí minulého času po 500 letech.
pub struct BigCycle {
    pub simulation: Simulation,
    pub kinds_500: BTreeMap<String, usize>,
}

pub fn run_velky_cyklus(seed: i64) -> Result<BigCycle, String> {
    let mut simulation = experiment(seed, Some("PAST"), None)?;
    simulation.run(500.0)?;
    let kinds_500 = kinds(&simulation.world, "PAST");
    simulation.run(2500.0)?;
    Ok(BigCycle {
        simulation,
        kinds_500,
    })
}

pub fn run_jespersen(seed: i64) -> Result<Simulation, String> {
    let mut simulation = experiment(seed, None, Some("not"))?;
    simulation.run(3000.0)?;
    Ok(simulation)
}

/// Po erozi pádu se ustálí slovosled (a bez eroze zůstane volný).
pub fn check_analytizace(eroded: &Simulation, control: &Simulation) -> Report {
    let mut report = Report::new();
    report.check(
        "skupiny s pevným slovosledem po erozi pádu",
        kind_count(&eroded.world, "ORDER", "fixed"),
        Cmp::Ge,
        5.0,
    );
    report.check(
        "skupiny s volným slovosledem v kontrole",
        kind_count(&control.world, "ORDER", "free"),
        Cmp::Ge,
        5.0,
    );
    report
}

/// Eroze, opis, přiklonka, nová koncovka minulého času.
pub fn check_velky_cyklus(run: &BigCycle) -> Report {
    let mut report = Report::new();
    let (world, history) = (&run.simulation.world, &run.simulation.history);
    report.check(
        "skupiny s opisem po 500 letech",
        run.kinds_500.get("periphrastic").copied().unwrap_or(0) as f64,
        Cmp::Ge,
        4.0,
    );
    let events: Vec<_> = history.of_kind("grammaticalized").collect();
    let groups: BTreeSet<&str> = events.iter().map(|e| text(e, "group")).collect();
    report.check(
        "skupiny, kde opis srostl v koncovku",
        groups.len() as f64,
        Cmp::Ge,
        4.0,
    );
    let sources: Vec<String> = Catalog::shared()
        .get("PAST")
        .map(|f| f.sources.clone())
        .unwrap_or_default();
    let foreign = events
        .iter()
        .filter(|e| !sources.iter().any(|s| s == text(e, "source")))
        .count();
    report.check(
        "gramatikalizace z cizího zdroje",
        foreign as f64,
        Cmp::Eq,
        0.0,
    );
    let weakness: Vec<f64> = world
        .group_ids()
        .into_iter()
        .map(|group| syntax::weakness(world, group, "PAST"))
        .collect();
    report.check(
        "průměrná slabost koncovky minulého času",
        mean(&weakness),
        Cmp::Lt,
        0.4,
    );
    report
}

/// Jespersenův cyklus: *ne*, *ne … pas*, *pas*.
pub fn check_jespersenuv_cyklus(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let established: Vec<String> = simulation
        .history
        .of_kind("established")
        .filter(|event| text(event, "variable") == "construction:NEG")
        .filter_map(|event| {
            let variant = variant_named(world, text(&event, "variant"))?;
            syntax::construction_of(world, variant).map(|c| c.kind.clone())
        })
        .collect();
    let first = |kind: &str| established.iter().position(|k| k == kind);
    report.flag(
        "ustálila se zdvojená záporka (embraced)",
        first("embraced").is_some(),
    );
    report.flag(
        "ustálila se koncová záporka (post)",
        first("post").is_some(),
    );
    report.flag(
        "embraced se ustálila dřív než post",
        matches!((first("embraced"), first("post")), (Some(a), Some(b)) if a < b),
    );
    report.check(
        "skupiny s koncovou záporkou",
        kind_count(world, "NEG", "post"),
        Cmp::Ge,
        4.0,
    );
    report
}

/// Bez eroze syntax zůstává a zvukové metriky drží.
pub fn check_bez_eroze(control: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &control.world;
    report.check(
        "skupiny se syntetickým minulým časem",
        kind_count(world, "PAST", "synthetic"),
        Cmp::Ge,
        5.0,
    );
    report.check(
        "skupiny se záporkou před slovesem",
        kind_count(world, "NEG", "pre"),
        Cmp::Ge,
        5.0,
    );
    let profiles: Vec<_> = world
        .group_ids()
        .into_iter()
        .map(|group| lexicon_profile(world, group))
        .collect();
    let lengths: Vec<f64> = profiles.iter().map(|p| p.mean_length).collect();
    let homophony: Vec<f64> = profiles.iter().map(|p| p.homophony).collect();
    report.check(
        "nejkratší průměrná délka slova",
        minimum(&lengths),
        Cmp::Ge,
        3.0,
    );
    report.check(
        "nejdelší průměrná délka slova",
        maximum(&lengths),
        Cmp::Le,
        8.0,
    );
    report.check("nejvyšší homofonie", maximum(&homophony), Cmp::Lt, 0.05);
    report
}

/// Otisk historie téhož běhu (zkouška determinismu se syntaxí).
pub fn determinism_digest() -> Result<String, String> {
    let options = SeedOptions {
        syntax: true,
        semantics: true,
        ..SeedOptions::default()
    };
    let world = village_grid_default(3, 1, 4, &options)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    simulation.run(1000.0)?;
    Ok(simulation.history.digest())
}

pub fn batches() -> Vec<Batch> {
    fn control_eroded(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let control = run_control(seed)?;
        let eroded = run_obj_eroded(seed)?;
        Ok(vec![
            ("m4::analytizace", check_analytizace(&eroded, &control)),
            ("m4::bez_eroze", check_bez_eroze(&control)),
        ])
    }
    fn big_cycle(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![(
            "m4::velky_cyklus",
            check_velky_cyklus(&run_velky_cyklus(seed)?),
        )])
    }
    fn jespersen(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![(
            "m4::jespersen",
            check_jespersenuv_cyklus(&run_jespersen(seed)?),
        )])
    }
    vec![
        Batch {
            id: "m4_control_eroded",
            gates: &["m4::analytizace", "m4::bez_eroze"],
            run: Runner::Single(control_eroded),
        },
        Batch {
            id: "m4_velky_cyklus",
            gates: &["m4::velky_cyklus"],
            run: Runner::Single(big_cycle),
        },
        Batch {
            id: "m4_jespersen",
            gates: &["m4::jespersen"],
            run: Runner::Single(jespersen),
        },
    ]
}
