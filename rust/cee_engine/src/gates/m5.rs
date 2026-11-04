//! Brána M5 (`test_v2_m5_gate.py`): kontakt jazyků. S2 (ostrov a obchodní město), S3 (přechod
//! regionu na prestižní jazyk), výpůjčky mezi jazyky v trvalém kontaktu a metrika 11
//! (morfologická složitost klesá s podílem L2 mluvčích a s velikostí populace).

use std::collections::{BTreeMap, BTreeSet};

use serde_json::json;

use super::metrics::{
    concepts_by_frequency, distinctive_variants, dominant_roots, group_named, loans, mean,
    mean_frequency, morphological_complexity, morphology_profile, spearman, trace_shares,
};
use super::{Batch, Cmp, Report, Runner};
use crate::contact;
use crate::events::{PendingEvent, WorldEvent};
use crate::ids::{GroupId, VariableId, VariantId};
use crate::model::repertoire::VariableKind;
use crate::parameters::Parameters;
use crate::scenarios::{contact_world, island_and_city, language_shift, Language, Place};
use crate::syntax;
use crate::world::World;
use crate::{Simulation, SimulationConfig};

fn run_world(
    world: World,
    until: f64,
    events: Vec<Box<dyn WorldEvent>>,
) -> Result<Simulation, String> {
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    simulation.run(until)?;
    Ok(simulation)
}

/// Skupina podle jména; chybějící skupina se zapíše do reportu jako neúspěch.
fn need(report: &mut Report, world: &World, name: &str) -> Option<GroupId> {
    let found = group_named(world, name);
    if found.is_none() {
        report.missing(&format!("skupina {name}"));
    }
    found
}

// --- S2: ostrov a město ---------------------------------------------------------------------

pub fn run_s2_city(seed: i64) -> Result<Simulation, String> {
    run_world(island_and_city(seed, 0.3)?, 2000.0, Vec::new())
}

pub fn check_s2_mesto(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let (Some(island), Some(city)) = (
        need(&mut report, world, "island"),
        need(&mut report, world, "city"),
    ) else {
        return report;
    };
    let (island, city) = (
        morphology_profile(world, island),
        morphology_profile(world, city),
    );
    report.check(
        "nepravidelnost vzácných slov: město / (ostrov / 2)",
        city.irregular_rare / (island.irregular_rare / 2.0),
        Cmp::Lt,
        1.0,
    );
    report.check(
        "produktivní podíl: město − ostrov",
        city.productive_share - island.productive_share,
        Cmp::Gt,
        0.1,
    );
    report.check(
        "ve městě: nepravidelnost častých − vzácných",
        city.irregular_frequent - city.irregular_rare,
        Cmp::Gt,
        0.0,
    );
    report
}

/// Kontrolovaný pokus: totéž město bez přistěhovalců a s nimi.
pub fn run_s2_l2_pair(seed: i64) -> Result<(Simulation, Simulation), String> {
    Ok((
        run_world(island_and_city(seed, 0.0)?, 2000.0, Vec::new())?,
        run_world(island_and_city(seed, 0.6)?, 2000.0, Vec::new())?,
    ))
}

pub fn check_s2_l2(native: &Simulation, mixed: &Simulation) -> Report {
    let mut report = Report::new();
    let (Some(a), Some(b)) = (
        need(&mut report, &native.world, "city"),
        need(&mut report, &mixed.world, "city"),
    ) else {
        return report;
    };
    report.check(
        "složitost města s přistěhovalci / (složitost bez nich / 2)",
        morphological_complexity(&mixed.world, b)
            / (morphological_complexity(&native.world, a) / 2.0),
        Cmp::Lt,
        1.0,
    );
    report
}

// --- S3: přechod na jiný jazyk -------------------------------------------------------------

/// Běh S3 a proměnné, ve kterých se skupina x1 po 1 500 letech liší od y2 (substrát).
pub struct Shifted {
    pub simulation: Simulation,
    pub substrate: BTreeMap<VariableId, (VariableKind, VariantId)>,
}

pub fn run_shifted(seed: i64) -> Result<Shifted, String> {
    let (world, events) = language_shift(seed, 1500.0)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    simulation.run(1500.0)?;
    let world = &simulation.world;
    let substrate = match (group_named(world, "x1"), group_named(world, "y2")) {
        (Some(x1), Some(y2)) => distinctive_variants(world, x1, y2),
        _ => BTreeMap::new(),
    };
    simulation.run(2500.0)?;
    Ok(Shifted {
        simulation,
        substrate,
    })
}

pub fn check_s3_prechod(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let shifted: BTreeSet<String> = simulation
        .history
        .of_kind("language_shift")
        .map(|event| super::metrics::text(&event, "group").to_owned())
        .collect();
    report.flag(
        "přešly právě x0, x1 a x2",
        shifted == ["x0", "x1", "x2"].map(String::from).into_iter().collect(),
    );
    let target = world.registry.languages.get("y");
    let others = world
        .group_ids()
        .into_iter()
        .filter(|&g| Some(world.groups.main_code(g).language.0) != target)
        .count();
    report.check(
        "skupiny, které nemluví jazykem y",
        others as f64,
        Cmp::Eq,
        0.0,
    );
    report
}

/// V novém jazyce zůstane stavba a výslovnost, ale málo slov (substrát).
pub fn check_s3_substrat(run: &Shifted) -> Report {
    let mut report = Report::new();
    let (world, substrate) = (&run.simulation.world, &run.substrate);
    let share = |group: GroupId, kind: VariableKind| {
        trace_shares(world, group, substrate)
            .get(&kind)
            .copied()
            .unwrap_or(f64::NAN)
    };
    let (Some(x0), Some(x1), Some(x2), Some(y2)) = (
        need(&mut report, world, "x0>y"),
        need(&mut report, world, "x1>y"),
        need(&mut report, world, "x2>y"),
        need(&mut report, world, "y2"),
    ) else {
        return report;
    };
    let construction = VariableKind::Construction;
    let (c0, c1, c2, cy) = (
        share(x0, construction),
        share(x1, construction),
        share(x2, construction),
        share(y2, construction),
    );
    report.check(
        "stavba substrátu v x0>y a x1>y (menší z nich)",
        c0.min(c1),
        Cmp::Gt,
        0.4,
    );
    report.check("stavba: x1>y − x2>y", c1 - c2, Cmp::Gt, 0.0);
    report.check("stavba: x2>y − y2", c2 - cy, Cmp::Gt, 0.0);
    let processes: Vec<VariableId> = substrate
        .iter()
        .filter(|(_, (kind, _))| *kind == VariableKind::Process)
        .map(|(&variable, _)| variable)
        .collect();
    for (label, group) in [("x0>y", x0), ("x1>y", x1), ("x2>y", x2)] {
        let lexical = share(group, VariableKind::Lexical);
        let build = share(group, construction);
        report.check(&format!("{label}: slovní stopa"), lexical, Cmp::Lt, 0.05);
        report.check(
            &format!("{label}: stavba − 10 × slovní stopa"),
            build - 10.0 * lexical,
            Cmp::Gt,
            0.0,
        );
        let code = world.groups.main_code(group);
        let written = processes
            .iter()
            .filter(|&&variable| {
                let process = world.variables.process[variable.index()];
                code.phonology
                    .sound
                    .queues
                    .state
                    .procs
                    .iter()
                    .any(|proc| proc.number == process.index() && proc.done.contains(&1))
            })
            .count();
        report.check(
            &format!("{label}: zapsané zvukové změny − 0,8 × změny substrátu"),
            written as f64 - 0.8 * processes.len() as f64,
            Cmp::Ge,
            0.0,
        );
        let roots = dominant_roots(world, group);
        let language_x = world.registry.languages.get("x");
        let native: Vec<f64> = roots
            .iter()
            .filter(|(_, root)| Some(world.morphemes.language[root.index()].0) == language_x)
            .map(|(concept, _)| world.concept_frequency(*concept))
            .collect();
        report.check(
            &format!("{label}: podíl slov jazyka x"),
            native.len() as f64 / roots.len() as f64,
            Cmp::Lt,
            0.08,
        );
        if !native.is_empty() {
            report.check(
                &format!("{label}: průměrná frekvence slov jazyka x / průměr všech"),
                mean(&native) / mean_frequency(world),
                Cmp::Lt,
                1.0,
            );
        }
    }
    report.flag(
        "y2 drží záporku před slovesem",
        syntax::dominant(world, y2, "NEG").is_some_and(|c| c.kind == "pre"),
    );
    report.check("stavba substrátu v jádru y2", cy, Cmp::Lt, 0.1);
    report
}

// --- výpůjčky -------------------------------------------------------------------------------

pub fn run_borrowing(seed: i64) -> Result<Simulation, String> {
    let a = Language::new(
        "a",
        (0..3)
            .map(|i| Place::new(&format!("a{i}"), (i as f64 * 10.0, 0.0)))
            .collect(),
    );
    let mut b = Language::new(
        "b",
        (0..3)
            .map(|i| Place::new(&format!("b{i}"), (40.0 + i as f64 * 10.0, 0.0)))
            .collect(),
    );
    b.proto = b.proto.with_consonants(&[
        "t", "k", "s", "n", "m", "l", "ʃ", "f", "x", "v", "r", "j", "ts",
    ]);
    let world = contact_world(&[a, b], seed, true, 25.0, Parameters::default())?;
    let event: Box<dyn WorldEvent> = Box::new(PendingEvent::new(
        500.0,
        "contact",
        json!({"pairs": [["a2", "b0"]], "strength": 0.5}),
    ));
    run_world(world, 2000.0, vec![event])
}

/// Výpůjčky jsou vzácné pojmy adaptované hláskami příjemce.
pub fn check_vypujcky(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    for name in ["a2", "b0"] {
        let Some(group) = need(&mut report, world, name) else {
            continue;
        };
        let found = loans(world, group);
        report.between(
            &format!("{name}: počet výpůjček"),
            found.len() as f64,
            3.0,
            40.0,
        );
        let inventory = contact::inventory(world, group);
        let foreign = found
            .iter()
            .filter(|(_, root)| {
                world
                    .form_of(group, *root)
                    .iter()
                    .any(|s| inventory.binary_search(s).is_err())
            })
            .count();
        report.check(
            &format!("{name}: výpůjčky s hláskou mimo inventář příjemce"),
            foreign as f64,
            Cmp::Eq,
            0.0,
        );
    }
    let ordered = concepts_by_frequency(world);
    let rank: BTreeMap<u32, f64> = ordered
        .iter()
        .enumerate()
        .map(|(index, concept)| (concept.0, index as f64 / (ordered.len() as f64 - 1.0)))
        .collect();
    let ranks: Vec<f64> = world
        .group_ids()
        .into_iter()
        .flat_map(|group| loans(world, group))
        .filter_map(|(concept, _)| rank.get(&concept.0).copied())
        .collect();
    report.check(
        "průměrné pořadí přejatých pojmů podle frekvence",
        mean(&ranks),
        Cmp::Lt,
        0.5,
    );
    report
}

/// Bez dvojjazyčnosti se stavba nepůjčuje.
pub fn check_bez_dvojjazycnosti(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let language_a = world.registry.languages.get("a");
    let mut foreign = 0;
    for name in ["a0", "a1", "a2"] {
        let Some(group) = need(&mut report, world, name) else {
            continue;
        };
        for function in ["PAST", "PL", "OBJ"] {
            let exponent = syntax::dominant(world, group, function).and_then(|c| c.exponent);
            if let Some(exponent) = exponent {
                let language = world
                    .registry
                    .morphemes
                    .get(&exponent)
                    .map(|m| world.morphemes.language[m as usize].0);
                foreign += usize::from(language != language_a);
            }
        }
    }
    report.check("koncovky převzaté z jazyka b", foreign as f64, Cmp::Eq, 0.0);
    report
}

// --- metrika 11 -----------------------------------------------------------------------------

pub const POPULATIONS: [u32; 5] = [100, 300, 1000, 3000, 10000];
pub const L2_SHARES: [f64; 4] = [0.0, 0.15, 0.3, 0.45];

/// Místa pokusu: jméno, populace a podíl L2 (přistěhovalců).
pub type Places = Vec<(String, u32, f64)>;

pub fn run_metrika_11(seed: i64) -> Result<(Simulation, Places), String> {
    let mut places = Vec::new();
    let mut spec = Vec::new();
    for (column, &population) in POPULATIONS.iter().enumerate() {
        for (row, &share) in L2_SHARES.iter().enumerate() {
            let name = format!("g{population}-{}", (share * 100.0) as i64);
            spec.push(Place {
                population,
                immigration: share,
                ..Place::new(&name, (column as f64 * 1000.0, row as f64 * 1000.0))
            });
            places.push((name, population, share));
        }
    }
    let world = contact_world(
        &[Language::new("proto", spec)],
        seed,
        true,
        25.0,
        Parameters::default(),
    )?;
    Ok((run_world(world, 1500.0, Vec::new())?, places))
}

pub fn check_metrika_11(simulation: &Simulation, places: &Places) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let complexity: Vec<f64> = places
        .iter()
        .map(|(name, _, _)| {
            group_named(world, name).map_or(f64::NAN, |g| morphological_complexity(world, g))
        })
        .collect();
    let attribute = |index: usize, place: &(String, u32, f64)| {
        if index == 0 {
            f64::from(place.1)
        } else {
            place.2
        }
    };
    // Průměrná korelace s `varied` při pevné hodnotě `fixed` (0 = populace, 1 = podíl L2).
    let within = |fixed: usize, varied: usize| {
        let mut levels: Vec<f64> = places.iter().map(|p| attribute(fixed, p)).collect();
        levels.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        levels.dedup();
        let values: Vec<f64> = levels
            .iter()
            .map(|&level| {
                let chosen: Vec<usize> = (0..places.len())
                    .filter(|&i| attribute(fixed, &places[i]) == level)
                    .collect();
                let x: Vec<f64> = chosen
                    .iter()
                    .map(|&i| attribute(varied, &places[i]))
                    .collect();
                let y: Vec<f64> = chosen.iter().map(|&i| complexity[i]).collect();
                spearman(&x, &y)
            })
            .collect();
        mean(&values)
    };
    report.check(
        "korelace složitosti s podílem L2 při pevné populaci",
        within(0, 1),
        Cmp::Lt,
        -0.6,
    );
    report.check(
        "korelace složitosti s populací při pevném podílu L2",
        within(1, 0),
        Cmp::Lt,
        -0.6,
    );
    report
}

pub fn batches() -> Vec<Batch> {
    fn city(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![("m5::s2_mesto", check_s2_mesto(&run_s2_city(seed)?))])
    }
    fn pair(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let (native, mixed) = run_s2_l2_pair(seed)?;
        Ok(vec![("m5::s2_l2", check_s2_l2(&native, &mixed))])
    }
    fn shifted(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let run = run_shifted(seed)?;
        Ok(vec![
            ("m5::s3_prechod", check_s3_prechod(&run.simulation)),
            ("m5::s3_substrat", check_s3_substrat(&run)),
        ])
    }
    fn borrowing(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let simulation = run_borrowing(seed)?;
        Ok(vec![
            ("m5::vypujcky", check_vypujcky(&simulation)),
            (
                "m5::bez_dvojjazycnosti",
                check_bez_dvojjazycnosti(&simulation),
            ),
        ])
    }
    fn metric_11(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let (simulation, places) = run_metrika_11(seed)?;
        Ok(vec![(
            "m5::metrika_11",
            check_metrika_11(&simulation, &places),
        )])
    }
    vec![
        Batch {
            id: "m5_s2_city",
            gates: &["m5::s2_mesto"],
            run: Runner::Single(city),
        },
        Batch {
            id: "m5_s2_l2",
            gates: &["m5::s2_l2"],
            run: Runner::Single(pair),
        },
        Batch {
            id: "m5_shifted",
            gates: &["m5::s3_prechod", "m5::s3_substrat"],
            run: Runner::Single(shifted),
        },
        Batch {
            id: "m5_borrowing",
            gates: &["m5::vypujcky", "m5::bez_dvojjazycnosti"],
            run: Runner::Single(borrowing),
        },
        Batch {
            id: "m5_metrika_11",
            gates: &["m5::metrika_11"],
            run: Runner::Single(metric_11),
        },
    ]
}
