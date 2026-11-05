//! Brána M1 (`test_v2_m1_gate.py`): dialektové kontinuum S1, metriky 7 a 8, velká souhrnná
//! skupina a stavba nepropojených oblastí.

use std::collections::BTreeSet;
use std::sync::Arc;

use serde_json::{json, Value};

use super::metrics::{
    establishment_fraction, group_named, isolation_by_distance, logistic_r2, maximum, mean, median,
};
use super::{Batch, Cmp, Report, Runner};
use crate::events::{PendingEvent, WorldEvent};
use crate::ids::{GroupId, VariantId};
use crate::model::code::Code;
use crate::model::group::GroupInit;
use crate::model::links::LinkKind;
use crate::model::repertoire::{Distribution, Origin, Payload, Repertoire, VariableKind};
use crate::model::territory::{Territory, TerritoryLevel};
use crate::parameters::Parameters;
use crate::scenarios::{
    default_concepts, seed_language, village_grid_default, village_grid_landscape, Landscape,
    SeedOptions,
};
use crate::world::{Endings, World};
use crate::{Simulation, SimulationConfig};

/// S1: řada 20 vesnic v nepravidelné krajině ([`Landscape::rural`]), 3 000 let, s dráhami pro
/// metriku 7.
pub fn run_continuum(seed: i64) -> Result<Simulation, String> {
    let world = village_grid_landscape(
        20,
        1,
        seed,
        &SeedOptions::default(),
        &default_concepts(),
        10.0,
        500,
        25.0,
        0.1,
        2.0,
        Parameters::default(),
        &Landscape::rural(),
    )?;
    let config = SimulationConfig {
        record_trajectories: true,
        keep_distances: true,
        ..SimulationConfig::default()
    };
    let mut simulation = Simulation::new(world, config, Vec::new())?;
    simulation.run(3000.0)?;
    Ok(simulation)
}

/// S1 s hranicí státu mezi 10. a 11. vesnicí od roku 1000.
pub fn run_bordered(seed: i64) -> Result<Simulation, String> {
    let world = village_grid_default(20, 1, seed, &SeedOptions::default())?;
    let names: Vec<String> = world
        .group_ids()
        .iter()
        .map(|&g| world.group_name(g).to_owned())
        .collect();
    let event: Box<dyn WorldEvent> = Box::new(PendingEvent::new(
        1000.0,
        "border",
        json!({"side_a": &names[..10], "side_b": &names[10..], "factor": 0.05}),
    ));
    let config = SimulationConfig {
        keep_distances: true,
        ..SimulationConfig::default()
    };
    let mut simulation = Simulation::new(world, config, vec![event])?;
    simulation.run(3000.0)?;
    Ok(simulation)
}

/// Vzdálenosti sousedních vesnic (`distances[i, i + 1]`), počet skupin a matice snímku.
fn neighbours(simulation: &Simulation) -> Option<(Vec<f64>, usize, &[f64])> {
    let snapshot = simulation.history.snapshots.last()?;
    let flat = snapshot.distances.as_deref()?;
    let n = snapshot.group_ids.len();
    if n < 2 || flat.len() != n * n {
        return None;
    }
    Some(((0..n - 1).map(|i| flat[i * n + i + 1]).collect(), n, flat))
}

pub fn check_s1_kontinuum(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let Some((near, n, flat)) = neighbours(simulation) else {
        report.missing("snímek se vzdálenostmi (keep_distances)");
        return report;
    };
    let snapshot = simulation.history.snapshots.last().expect("snímek");
    report.check(
        "největší vzdálenost sousedů / (3 × medián)",
        maximum(&near) / (3.0 * median(&near)),
        Cmp::Lt,
        1.0,
    );
    report.check(
        "vzdálenost krajních vesnic / (3 × průměr sousedů)",
        flat[n - 1] / (3.0 * mean(&near)),
        Cmp::Gt,
        1.0,
    );
    report.check("počet nářečí", snapshot.dialects.len() as f64, Cmp::Gt, 1.0);
    let world = &simulation.world;
    let positions: Option<Vec<(f64, f64)>> = snapshot
        .group_ids
        .iter()
        .map(|name| group_named(world, name).and_then(|g| world.position_of(g)))
        .collect();
    match positions {
        Some(positions) => {
            let fit = isolation_by_distance(flat, &positions);
            report.check(
                "korelace vzdálenosti jazyka a polohy",
                fit.correlation,
                Cmp::Gt,
                0.8,
            );
            report.check(
                "korelace vzdálenosti jazyka a logaritmu polohy",
                fit.correlation_log,
                Cmp::Gt,
                0.5,
            );
        }
        None => report.missing("poloha skupin snímku"),
    }
    report
}

pub fn check_s1_hranice(bordered: &Simulation) -> Report {
    let mut report = Report::new();
    let Some((near, _, _)) = neighbours(bordered) else {
        report.missing("snímek se vzdálenostmi (keep_distances)");
        return report;
    };
    if near.len() < 11 {
        report.missing("20 vesnic ve snímku");
        return report;
    }
    let others: Vec<f64> = near[..9].iter().chain(near[10..].iter()).copied().collect();
    report.check(
        "vzdálenost přes hranici / (2 × největší ostatní)",
        near[9] / (2.0 * maximum(&others)),
        Cmp::Gt,
        1.0,
    );
    report
}

pub fn check_metrika_7(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let fits: Vec<f64> = simulation
        .history
        .trajectories
        .values()
        .filter(|path| path.last().is_some_and(|p| p.1 == 1.0))
        .filter_map(|path| {
            let points: Vec<(f64, f64)> = path.iter().map(|&(t, v)| (f64::from(t), v)).collect();
            logistic_r2(&points)
        })
        .collect();
    report.check(
        "počet ustálených drah s proložením",
        fits.len() as f64,
        Cmp::Gt,
        50.0,
    );
    report.check("medián R² logistické křivky", median(&fits), Cmp::Gt, 0.9);
    report
}

pub fn check_metrika_8(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let history = &simulation.history;
    let fraction = establishment_fraction(history);
    report.check("podíl ustálených inovací (dolní)", fraction, Cmp::Gt, 0.0);
    report.check("podíl ustálených inovací (horní)", fraction, Cmp::Lt, 0.2);
    let (extinct, innovations) = (
        history.of_kind("extinct").count() as f64,
        history.of_kind("innovation").count() as f64,
    );
    report.check(
        "zaniklé / (inovace / 2)",
        extinct / (innovations / 2.0),
        Cmp::Gt,
        1.0,
    );
    report
}

/// Drift neutrálních variant 50 : 50 bez inovací a tlaků: střední odchylka od 0,5.
fn drift(population: u32, seed: i64) -> Result<f64, String> {
    let mut world = World::new(seed, Parameters::default());
    world.add_territory("world", None, Territory::new(TerritoryLevel::World))?;
    let place =
        world.add_territory("place", Some("world"), Territory::new(TerritoryLevel::Area))?;
    let mut repertoire = Repertoire::new();
    let mut pairs = Vec::new();
    for index in 0..200 {
        let variable =
            world.store_variable(VariableKind::Lexical, &format!("c{index}"), VariantId::NONE);
        let name = world.registry.variables.name(variable.0).to_owned();
        let origin = Origin {
            change: Some("test".into()),
            tick: 0,
            year: 0.0,
            group: GroupId::NONE,
            parent: VariantId::NONE,
        };
        let a = world.store_variant(
            &format!("{name}/a"),
            variable,
            Payload::Other(Value::Null),
            origin.clone(),
        );
        let b = world.store_variant(
            &format!("{name}/b"),
            variable,
            Payload::Other(Value::Null),
            origin,
        );
        repertoire.set(
            variable,
            Distribution::from_pairs(vec![(a, 0.5), (b, 0.5)], &world.registry.variants),
        );
        pairs.push((variable, a));
    }
    let language = world.language("proto");
    let mut init = GroupInit::new(
        "place",
        place,
        population,
        vec![Code::new("main", repertoire, language)],
    );
    init.aggregate = population > 10_000;
    let group = world.add_group(init)?;
    let mut simulation =
        Simulation::with_changes(world, SimulationConfig::default(), Vec::new(), Vec::new())?;
    simulation.run(1000.0)?;
    let deviations: Vec<f64> = pairs
        .iter()
        .filter_map(|&(variable, a)| {
            simulation
                .world
                .distribution(group, variable)
                .map(|d| (d.frequency(a) - 0.5).abs())
        })
        .collect();
    Ok(mean(&deviations))
}

/// Drift velké souhrnné skupiny a malé vesnice: (velká, malá).
pub fn run_drift_pair(seed: i64) -> Result<(f64, f64), String> {
    Ok((drift(1_000_000, seed)?, drift(200, seed)?))
}

pub fn check_velka_souhrnna_skupina(large: f64, small: f64) -> Report {
    let mut report = Report::new();
    report.check("drift velké skupiny (1 000 000)", large, Cmp::Lt, 0.01);
    report.check("drift malé vesnice (200)", small, Cmp::Gt, 0.01);
    report
}

/// Svět se dvěma oblastmi (západ buď jedna souhrnná skupina, nebo dvě vesnice, východ tři
/// vesnice) pro zkoušku, že zjemnění jedné oblasti nepohne s nepropojenou druhou.
///
/// `concepts` je počet pojmů `c0`, `c1`, …; s `phonology` mají slova hláskové tvary (M2).
pub fn two_regions(refine_west: bool, concepts: usize, phonology: bool) -> Result<World, String> {
    let mut world = World::new(9, Parameters::default());
    world.add_territory("world", None, Territory::new(TerritoryLevel::World))?;
    let names: Vec<String> = (0..concepts).map(|index| format!("c{index}")).collect();
    let options = SeedOptions {
        phonology,
        ..SeedOptions::default()
    };
    let base: Arc<Repertoire> = if phonology {
        seed_language(&mut world, 9, &names, &options)?
    } else {
        world.seed_lexicon(&names, None, None, None, &Endings::new(), "proto", None)?
    };
    let language = world.language("proto");
    let region = |world: &mut World, name: &str, x: f64| {
        let mut territory = Territory::new(TerritoryLevel::Region);
        territory.position = Some((x, 0.0));
        world.add_territory(name, Some("world"), territory)
    };
    let west = region(&mut world, "west", 0.0)?;
    let east = region(&mut world, "east", 100.0)?;
    let code = |base: &Arc<Repertoire>| Code::new("main", Repertoire::over(base.clone()), language);
    let settle = |world: &mut World, name: &str, parent: &str, x: f64| {
        let mut territory = Territory::new(TerritoryLevel::Settlement);
        territory.position = Some((x, 0.0));
        world.add_territory(name, Some(parent), territory)
    };
    if refine_west {
        let mut ids = Vec::new();
        for index in 0..2 {
            let village = format!("west-{index}");
            let territory = settle(&mut world, &village, "west", index as f64 * 10.0)?;
            let init = GroupInit::new(&village, territory, 1_500, vec![code(&base)]);
            ids.push(world.add_group(init)?);
        }
        world.connect(ids[0], ids[1], 0.8, LinkKind::Strong)?;
    } else {
        let mut init = GroupInit::new("west", west, 3_000, vec![code(&base)]);
        init.aggregate = true;
        world.add_group(init)?;
    }
    let _ = east;
    let mut villages = Vec::new();
    for index in 0..3 {
        let village = format!("east-{index}");
        let territory = settle(&mut world, &village, "east", 100.0 + index as f64 * 10.0)?;
        let init = GroupInit::new(&village, territory, 500, vec![code(&base)]);
        villages.push(world.add_group(init)?);
    }
    world.connect(villages[0], villages[1], 0.6, LinkKind::Weak)?;
    world.connect(villages[1], villages[2], 0.6, LinkKind::Weak)?;
    Ok(world)
}

/// Událost historie patří východní oblasti (skupina východu, nebo zánik varianty ze skupiny východu).
pub fn east_events(
    simulation: &Simulation,
    skip_emerged: bool,
) -> Vec<serde_json::Map<String, Value>> {
    let world = &simulation.world;
    let east: BTreeSet<&str> = ["east-0", "east-1", "east-2"].into_iter().collect();
    simulation
        .history
        .events
        .iter()
        .filter(|event| {
            let kind = event.get("kind").and_then(Value::as_str).unwrap_or("");
            if skip_emerged && kind == "language_emerged" {
                return false;
            }
            let group = event.get("group").and_then(Value::as_str).unwrap_or("");
            if east.contains(group) {
                return true;
            }
            kind == "extinct" && !skip_emerged && {
                let variant = event.get("variant").and_then(Value::as_str).unwrap_or("");
                super::metrics::variant_named(world, variant).is_some_and(|v| {
                    let origin = world.variants.origin[v.index()].group;
                    !origin.is_none() && east.contains(world.group_name(origin))
                })
            }
        })
        .collect()
}

pub fn batches() -> Vec<Batch> {
    fn continuum(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let simulation = run_continuum(seed)?;
        Ok(vec![
            ("m1::s1_kontinuum", check_s1_kontinuum(&simulation)),
            ("m1::metrika_7", check_metrika_7(&simulation)),
            ("m1::metrika_8", check_metrika_8(&simulation)),
        ])
    }
    fn bordered(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![(
            "m1::s1_hranice",
            check_s1_hranice(&run_bordered(seed)?),
        )])
    }
    fn drift_pair(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let (large, small) = run_drift_pair(seed)?;
        Ok(vec![(
            "m1::velka_skupina_drift",
            check_velka_souhrnna_skupina(large, small),
        )])
    }
    vec![
        Batch {
            id: "m1_continuum",
            gates: &["m1::s1_kontinuum", "m1::metrika_7", "m1::metrika_8"],
            run: Runner::Single(continuum),
        },
        Batch {
            id: "m1_bordered",
            gates: &["m1::s1_hranice"],
            run: Runner::Single(bordered),
        },
        Batch {
            id: "m1_drift",
            gates: &["m1::velka_skupina_drift"],
            run: Runner::Single(drift_pair),
        },
    ]
}
