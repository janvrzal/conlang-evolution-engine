//! Brána M6b (`test_v2_m6b_gate.py`): společnost. Metrika 9 (Séguyho zákon) v plném modelu
//! na mapě, superstrát po přechodu elity, stabilní dvojjazyčnost, loajalita, podíl L2 mluvčích
//! z migrace, Fergusonova diglosie a učená slova z liturgického jazyka.

use std::collections::{BTreeMap, BTreeSet};

use super::metrics::{
    distinctive_variants, dominant_roots, group_named, isolation_by_distance, mean, mean_frequency,
    morphological_complexity, roots_of_language, spearman, text, total_distance, trace_shares,
};
use super::{Batch, Cmp, Report, Runner};
use crate::contact;
use crate::events::WorldEvent;
use crate::ids::{GroupId, VariableId, VariantId};
use crate::model::group::Domain;
use crate::model::repertoire::VariableKind;
use crate::scenarios::{
    conquest, conversion, diglossia, language_shift, market_town, migration_region,
    village_grid_default, SeedOptions,
};
use crate::world::World;
use crate::{Simulation, SimulationConfig};

// --- metrika 9 ------------------------------------------------------------------------------

/// Séguyho zákon: na mapě (2D) roste vzdálenost nářečí jako logaritmus.
pub fn run_metrika_9(seed: i64) -> Result<Simulation, String> {
    let options = SeedOptions {
        morphology: true,
        semantics: true,
        ..SeedOptions::default()
    };
    let world = village_grid_default(5, 5, seed, &options)?;
    let config = SimulationConfig {
        keep_distances: true,
        ..SimulationConfig::default()
    };
    let mut simulation = Simulation::new(world, config, Vec::new())?;
    simulation.run(2500.0)?;
    Ok(simulation)
}

pub fn check_metrika_9(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let Some(snapshot) = simulation.history.snapshots.last() else {
        report.missing("snímek");
        return report;
    };
    let Some(distances) = snapshot.distances.as_deref() else {
        report.missing("matice vzdáleností (keep_distances)");
        return report;
    };
    let positions: Option<Vec<(f64, f64)>> = snapshot
        .group_ids
        .iter()
        .map(|name| group_named(world, name).and_then(|g| world.position_of(g)))
        .collect();
    let Some(positions) = positions else {
        report.missing("poloha skupin snímku");
        return report;
    };
    let fit = isolation_by_distance(distances, &positions);
    report.check(
        "korelace vzdálenosti jazyka a polohy",
        fit.correlation,
        Cmp::Gt,
        0.7,
    );
    report.check(
        "R² logaritmického − R² lineárního proložení",
        fit.r2_log - fit.r2_linear,
        Cmp::Ge,
        0.0,
    );
    report
}

// --- superstrát -----------------------------------------------------------------------------

/// Dobytí: běh po 3 100 letech a proměnné, ve kterých se skupina `l0+e0` v roce 1100 liší od `l3`.
pub struct Conquered {
    pub simulation: Simulation,
    pub elite: BTreeMap<VariableId, (VariableKind, VariantId)>,
    pub elite_known: bool,
}

pub fn run_conquered(seed: i64) -> Result<Conquered, String> {
    let (world, events) = conquest(seed, 1000.0)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    simulation.run(1100.0)?;
    let world = &simulation.world;
    let known = group_named(world, "l0+e0").zip(group_named(world, "l3"));
    let elite = known.map_or_else(BTreeMap::new, |(a, b)| distinctive_variants(world, a, b));
    simulation.run(2000.0)?;
    Ok(Conquered {
        simulation,
        elite,
        elite_known: known.is_some(),
    })
}

/// Elita v menšině přejde na jazyk poddaných.
pub fn check_elita_prejde(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let shifts: Vec<_> = simulation.history.of_kind("language_shift").collect();
    report.flag(
        "přešla právě skupina l0+e0",
        shifts.len() == 1 && text(shifts[0], "group") == "l0+e0",
    );
    if let Some(first) = shifts.first() {
        let delay = first
            .get("year")
            .and_then(|y| y.as_f64())
            .unwrap_or(f64::NAN)
            - 1100.0;
        report.between("doba do přechodu elity (roky)", delay, 150.0, 500.0);
    } else {
        report.missing("přechod elity");
    }
    let language = world.registry.languages.get("l");
    let foreign = world
        .group_ids()
        .into_iter()
        .filter(|g| {
            world
                .registry
                .territories
                .name(world.groups.territory[g.index()].0)
                != "e0"
        })
        .filter(|&g| Some(world.groups.main_code(g).language.0) != language)
        .count();
    report.check(
        "skupiny mimo domovinu dobyvatelů s cizím jazykem",
        foreign as f64,
        Cmp::Eq,
        0.0,
    );
    report
}

/// Superstrát je hlavně slovní.
pub fn check_superstrat(run: &Conquered) -> Report {
    let mut report = Report::new();
    let world = &run.simulation.world;
    report.flag("skupiny l0+e0 a l3 existovaly v roce 1100", run.elite_known);
    for name in ["l0", "l1", "l2", "l3"] {
        let Some(group) = group_named(world, name) else {
            report.missing(&format!("skupina {name}"));
            continue;
        };
        report.check(
            &format!("{name}: slova z jazyka dobyvatelů"),
            roots_of_language(world, group, "e") as f64,
            Cmp::Ge,
            2.0,
        );
        let build = trace_shares(world, group, &run.elite)
            .get(&VariableKind::Construction)
            .copied()
            .unwrap_or(f64::NAN);
        report.check(&format!("{name}: stavba elity"), build, Cmp::Lt, 0.1);
    }
    report
}

// --- stabilní dvojjazyčnost a loajalita -----------------------------------------------------

pub fn run_market_town(seed: i64) -> Result<Simulation, String> {
    let (world, events) = market_town(seed, 500.0)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    simulation.run(2000.0)?;
    Ok(simulation)
}

pub fn check_jazyk_trhu(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    report.check(
        "přechody jazyka",
        simulation.history.of_kind("language_shift").count() as f64,
        Cmp::Eq,
        0.0,
    );
    let (Some(home), Some(bilingual)) = (group_named(world, "a1"), group_named(world, "a1>b"))
    else {
        report.missing("skupiny a1 a a1>b");
        return report;
    };
    report.flag(
        "a1 se dál předává a má 500 mluvčích",
        world.groups.transmitted[home.index()] && world.groups.population[home.index()] == 500,
    );
    report.flag(
        "a1>b je veřejná skupina",
        world.groups.domain[bilingual.index()] == Domain::Public,
    );
    report.check(
        "podíl L2 ve skupině a1>b",
        world.groups.main_code(bilingual).l2_share,
        Cmp::Eq,
        1.0,
    );
    let roots = dominant_roots(world, home);
    report.check(
        "podíl vlastních slov v a1",
        roots_of_language(world, home, "a") as f64 / roots.len() as f64,
        Cmp::Gt,
        0.8,
    );
    report.check(
        "výpůjčky z jazyka b v a1",
        roots_of_language(world, home, "b") as f64,
        Cmp::Gt,
        0.0,
    );
    report
}

/// Roky přechodu jazyka podle skupin při loajalitě `loyalty` skupin x0 až x2.
fn shifted_years(seed: i64, loyalty: f64) -> Result<BTreeMap<String, f64>, String> {
    let (mut world, events) = language_shift(seed, 1500.0)?;
    for name in ["x0", "x1", "x2"] {
        if let Some(group) = group_named(&world, name) {
            world.groups.loyalty[group.index()] = loyalty;
        }
    }
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    simulation.run(2500.0)?;
    Ok(simulation
        .history
        .of_kind("language_shift")
        .map(|event| {
            (
                text(event, "group").to_owned(),
                event
                    .get("year")
                    .and_then(|y| y.as_f64())
                    .unwrap_or(f64::NAN),
            )
        })
        .collect())
}

/// Bez loajality, s loajalitou 0,6 a 0,9.
pub type Loyalty = (
    BTreeMap<String, f64>,
    BTreeMap<String, f64>,
    BTreeMap<String, f64>,
);

pub fn run_loyalty(seed: i64) -> Result<Loyalty, String> {
    Ok((
        shifted_years(seed, 0.0)?,
        shifted_years(seed, 0.6)?,
        shifted_years(seed, 0.9)?,
    ))
}

pub fn check_loajalita(run: &Loyalty) -> Report {
    let (free, loyal, steadfast) = run;
    let mut report = Report::new();
    let expected: BTreeSet<&str> = ["x0", "x1", "x2"].into_iter().collect();
    fn keys(map: &BTreeMap<String, f64>) -> BTreeSet<&str> {
        map.keys().map(String::as_str).collect()
    }
    report.flag("bez loajality přešly x0, x1 a x2", keys(free) == expected);
    report.flag(
        "s loajalitou 0,6 přešly x0, x1 a x2",
        keys(loyal) == expected,
    );
    let later = free
        .iter()
        .filter(|(group, year)| loyal.get(*group).is_none_or(|l| l <= year))
        .count();
    report.check(
        "skupiny, které s loajalitou nepřešly později",
        later as f64,
        Cmp::Eq,
        0.0,
    );
    let held = ["x0", "x1"]
        .iter()
        .filter(|name| steadfast.contains_key(**name))
        .count();
    report.check(
        "skupiny x0 a x1, které přešly i s loajalitou 0,9",
        held as f64,
        Cmp::Eq,
        0.0,
    );
    report
}

// --- migrace --------------------------------------------------------------------------------

pub fn run_migration(seed: i64) -> Result<Simulation, String> {
    let world = migration_region(seed, 0.1)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    simulation.run(1500.0)?;
    Ok(simulation)
}

pub fn check_migrace(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let groups = world.group_ids();
    let populations: Vec<f64> = groups
        .iter()
        .map(|g| f64::from(world.groups.population[g.index()]))
        .collect();
    let shares: Vec<f64> = groups
        .iter()
        .map(|&g| world.groups.main_code(g).l2_share)
        .collect();
    let complexity: Vec<f64> = groups
        .iter()
        .map(|&g| morphological_complexity(world, g))
        .collect();
    report.check(
        "korelace populace a podílu L2",
        spearman(&populations, &shares),
        Cmp::Gt,
        0.6,
    );
    match group_named(world, "city") {
        Some(city) => report.check(
            "podíl L2 ve městě − největší podíl L2",
            world.groups.main_code(city).l2_share - shares.iter().copied().fold(f64::MIN, f64::max),
            Cmp::Ge,
            0.0,
        ),
        None => {
            report.missing("skupina city");
            false
        }
    };
    report.check(
        "korelace populace a složitosti",
        spearman(&populations, &complexity),
        Cmp::Lt,
        0.0,
    );
    report.check(
        "korelace podílu L2 a složitosti",
        spearman(&shares, &complexity),
        Cmp::Lt,
        0.0,
    );
    report
}

// --- Fergusonova diglosie a náboženská změna ------------------------------------------------

/// Diglosie s vysokou varietou: běh a rozdíl lidové řeči od psané v roce 1475.
pub struct Ferguson {
    pub simulation: Simulation,
    pub before: f64,
}

pub fn run_ferguson(seed: i64) -> Result<Ferguson, String> {
    let (world, events) = diglossia(seed, 500.0, Some(1500.0), true, 0.05, true)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    simulation.run(1475.0)?;
    let world = &simulation.world;
    let before = match group_named(world, super::m6a::WRITTEN) {
        Some(written) => {
            let values: Vec<f64> = world
                .group_ids()
                .into_iter()
                .filter(|&g| g != written)
                .map(|g| total_distance(world, g, written))
                .collect();
            mean(&values)
        }
        None => f64::NAN,
    };
    simulation.run(3000.0)?;
    Ok(Ferguson { simulation, before })
}

pub fn check_ferguson(run: &Ferguson) -> Report {
    let mut report = Report::new();
    let world = &run.simulation.world;
    let Some(written) = group_named(world, super::m6a::WRITTEN) else {
        report.missing(&format!("skupina {}", super::m6a::WRITTEN));
        return report;
    };
    let vernacular: Vec<GroupId> = world
        .group_ids()
        .into_iter()
        .filter(|g| {
            !world.groups.written[g.index()] && world.groups.domain[g.index()] == Domain::Home
        })
        .collect();
    let high: Vec<Option<GroupId>> = vernacular
        .iter()
        .map(|&g| group_named(world, &format!("{}>H", world.group_name(g))))
        .collect();
    report.check(
        "lidové skupiny bez veřejné vysoké variety",
        high.iter()
            .filter(|h| h.is_none_or(|h| world.groups.domain[h.index()] != Domain::Public))
            .count() as f64,
        Cmp::Eq,
        0.0,
    );
    let high: Vec<GroupId> = high.into_iter().flatten().collect();
    let gap = |groups: &[GroupId]| {
        let values: Vec<f64> = groups
            .iter()
            .map(|&g| total_distance(world, g, written))
            .collect();
        mean(&values)
    };
    let (low_gap, high_gap) = (gap(&vernacular), gap(&high));
    report.check(
        "rozdíl lidové řeči od psané − rozdíl v roce 1475",
        low_gap - run.before,
        Cmp::Ge,
        0.0,
    );
    report.check(
        "rozdíl vysoké variety / (rozdíl lidové řeči / 2)",
        high_gap / (low_gap / 2.0),
        Cmp::Lt,
        1.0,
    );
    let split: Vec<f64> = vernacular
        .iter()
        .filter_map(|&g| {
            group_named(world, &format!("{}>H", world.group_name(g)))
                .map(|h| total_distance(world, g, h))
        })
        .collect();
    report.check(
        "vzdálenost lidové řeči od vlastní vysoké variety",
        mean(&split),
        Cmp::Gt,
        0.05,
    );
    let observed: BTreeSet<&str> = run
        .simulation
        .history
        .snapshots
        .last()
        .map(|s| s.dialects.iter().flatten().map(String::as_str).collect())
        .unwrap_or_default();
    let expected: BTreeSet<&str> = vernacular.iter().map(|&g| world.group_name(g)).collect();
    report.flag(
        "vysoká varieta se do nářečí a jazyků nepočítá",
        observed == expected,
    );
    report
}

/// Náboženská změna: běh s ní a kontrola bez ní; počty výpůjček z jazyka r ve vesnicích v0 až v3.
pub struct Converted {
    pub simulation: Simulation,
    pub converted: Vec<usize>,
    pub control: Vec<usize>,
}

fn conversion_run(seed: i64, with_conversion: bool) -> Result<(Simulation, Vec<usize>), String> {
    let (world, events) = conversion(seed, 500.0, 0.3)?;
    let events: Vec<Box<dyn WorldEvent>> = events
        .into_iter()
        .filter(|event| with_conversion || event.kind() != "religious_change")
        .collect();
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    simulation.run(2000.0)?;
    let counts = ["v0", "v1", "v2", "v3"]
        .iter()
        .map(|name| {
            group_named(&simulation.world, name)
                .map_or(0, |g| roots_of_language(&simulation.world, g, "r"))
        })
        .collect();
    Ok((simulation, counts))
}

pub fn run_conversion_pair(seed: i64) -> Result<Converted, String> {
    let (simulation, converted) = conversion_run(seed, true)?;
    let (_, control) = conversion_run(seed, false)?;
    Ok(Converted {
        simulation,
        converted,
        control,
    })
}

pub fn check_nabozenstvi(run: &Converted) -> Report {
    let mut report = Report::new();
    let world: &World = &run.simulation.world;
    report.check(
        "nejméně výpůjček z jazyka r ve vesnici",
        run.converted.iter().copied().min().unwrap_or(0) as f64,
        Cmp::Ge,
        1.0,
    );
    report.check(
        "výpůjčky z jazyka r celkem",
        run.converted.iter().sum::<usize>() as f64,
        Cmp::Ge,
        6.0,
    );
    report.check(
        "výpůjčky v kontrole bez náboženské změny",
        run.control.iter().sum::<usize>() as f64,
        Cmp::Eq,
        0.0,
    );
    let language = world.registry.languages.get("r");
    let (mut learned, mut foreign) = (Vec::new(), 0);
    for name in ["v0", "v1", "v2", "v3"] {
        let Some(group) = group_named(world, name) else {
            report.missing(&format!("skupina {name}"));
            continue;
        };
        let inventory = contact::inventory(world, group);
        for (concept, root) in dominant_roots(world, group) {
            if Some(world.morphemes.language[root.index()].0) != language {
                continue;
            }
            learned.push(world.concept_frequency(concept));
            foreign += world
                .form_of(group, root)
                .iter()
                .any(|s| inventory.binary_search(s).is_err()) as usize;
        }
    }
    report.check(
        "průměrná frekvence učených slov / (0,7 × průměr všech)",
        mean(&learned) / (0.7 * mean_frequency(world)),
        Cmp::Lt,
        1.0,
    );
    report.check(
        "učená slova s hláskou mimo inventář příjemce",
        foreign as f64,
        Cmp::Eq,
        0.0,
    );
    report
}

pub fn batches() -> Vec<Batch> {
    fn metric_9(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![(
            "m6b::metrika_9",
            check_metrika_9(&run_metrika_9(seed)?),
        )])
    }
    fn conquered(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let run = run_conquered(seed)?;
        Ok(vec![
            ("m6b::elita_prejde", check_elita_prejde(&run.simulation)),
            ("m6b::superstrat", check_superstrat(&run)),
        ])
    }
    fn market(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![(
            "m6b::jazyk_trhu",
            check_jazyk_trhu(&run_market_town(seed)?),
        )])
    }
    fn loyalty(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![(
            "m6b::loajalita",
            check_loajalita(&run_loyalty(seed)?),
        )])
    }
    fn migration(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![("m6b::migrace", check_migrace(&run_migration(seed)?))])
    }
    fn ferguson(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![(
            "m6b::ferguson",
            check_ferguson(&run_ferguson(seed)?),
        )])
    }
    fn religion(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![(
            "m6b::nabozenstvi",
            check_nabozenstvi(&run_conversion_pair(seed)?),
        )])
    }
    vec![
        Batch {
            id: "m6b_metrika_9",
            gates: &["m6b::metrika_9"],
            run: Runner::Single(metric_9),
        },
        Batch {
            id: "m6b_conquered",
            gates: &["m6b::elita_prejde", "m6b::superstrat"],
            run: Runner::Single(conquered),
        },
        Batch {
            id: "m6b_market_town",
            gates: &["m6b::jazyk_trhu"],
            run: Runner::Single(market),
        },
        Batch {
            id: "m6b_loyalty",
            gates: &["m6b::loajalita"],
            run: Runner::Single(loyalty),
        },
        Batch {
            id: "m6b_migration",
            gates: &["m6b::migrace"],
            run: Runner::Single(migration),
        },
        Batch {
            id: "m6b_ferguson",
            gates: &["m6b::ferguson"],
            run: Runner::Single(ferguson),
        },
        Batch {
            id: "m6b_conversion",
            gates: &["m6b::nabozenstvi"],
            run: Runner::Single(religion),
        },
    ]
}
