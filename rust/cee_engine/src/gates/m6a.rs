//! Brána M6a (`test_v2_m6a_gate.py`): instituce a diglosie. Scénář S4: písmo v roce 500,
//! škola a tisk v roce 1500. Rozdíl mluvené a psané řeči roste do zavedení školy, pak se zmenšuje.

use serde_json::json;

use super::metrics::{group_named, mean, total_distance};
use super::{Batch, Cmp, Report, Runner};
use crate::events::{PendingEvent, WorldEvent};
use crate::ids::{GroupId, VariableId, VariantId};
use crate::scenarios::{diglossia, village_grid_default, SeedOptions};
use crate::world::World;
use crate::{Simulation, SimulationConfig};

/// Psaný kód v S4 (norma elity v. 3. vesnici).
pub const WRITTEN: &str = "written:v00-02";
/// Roky, ve kterých se měří rozdíl a nářečí.
pub const YEARS: [f64; 4] = [1000.0, 1475.0, 2000.0, 2500.0];

fn spoken(world: &World) -> Vec<GroupId> {
    world
        .group_ids()
        .into_iter()
        .filter(|g| !world.groups.written[g.index()])
        .collect()
}

/// Průměrná vzdálenost mluvené řeči vesnic od psaného kódu.
fn gap(world: &World, written: &str) -> f64 {
    let Some(written) = group_named(world, written) else {
        return f64::NAN;
    };
    let values: Vec<f64> = spoken(world)
        .into_iter()
        .map(|g| total_distance(world, g, written))
        .collect();
    mean(&values)
}

/// Průměrná vzdálenost mezi mluvenými skupinami (nářečí).
fn dialects(world: &World) -> f64 {
    let groups = spoken(world);
    let mut values = Vec::new();
    for (index, &first) in groups.iter().enumerate() {
        for &second in &groups[index + 1..] {
            values.push(total_distance(world, first, second));
        }
    }
    mean(&values)
}

/// Průběh jednoho scénáře: (rozdíl, nářečí) v letech [`YEARS`] a počet ustálení po roce 1750.
pub struct Course {
    pub course: Vec<(f64, f64)>,
    pub changes: usize,
}

fn course(seed: i64, school: Option<f64>, printing: bool) -> Result<Course, String> {
    let (world, events) = diglossia(seed, 500.0, school, printing, 0.05, false)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    let mut course = Vec::new();
    for year in YEARS {
        simulation.run(year)?;
        course.push((gap(&simulation.world, WRITTEN), dialects(&simulation.world)));
    }
    let changes = simulation
        .history
        .of_kind("established")
        .filter(|event| event.get("year").and_then(|y| y.as_f64()).unwrap_or(0.0) > 1750.0)
        .count();
    Ok(Course { course, changes })
}

/// Se školou, bez školy a se školou bez tisku (zmrazená norma).
pub struct Courses {
    pub school: Course,
    pub none: Course,
    pub frozen: Course,
}

pub fn run_diglossia_courses(seed: i64) -> Result<Courses, String> {
    Ok(Courses {
        school: course(seed, Some(1500.0), true)?,
        none: course(seed, None, true)?,
        frozen: course(seed, Some(1500.0), false)?,
    })
}

pub fn check_s4_skola(courses: &Courses) -> Report {
    let mut report = Report::new();
    let c = &courses.school.course;
    report.check(
        "rozdíl 1000 / rozdíl 1475 (diglosie: psaný kód stojí)",
        c[0].0 / c[1].0,
        Cmp::Lt,
        1.0,
    );
    report.check(
        "rozdíl 2000 / (rozdíl 1475 / 3)",
        c[2].0 / (c[1].0 / 3.0),
        Cmp::Lt,
        1.0,
    );
    report.check(
        "rozdíl 2500 / (rozdíl 1475 / 3)",
        c[3].0 / (c[1].0 / 3.0),
        Cmp::Lt,
        1.0,
    );
    report
}

pub fn check_s4_bez_skoly(courses: &Courses) -> Report {
    let mut report = Report::new();
    let c = &courses.none.course;
    report.check("rozdíl 1000 / rozdíl 1475", c[0].0 / c[1].0, Cmp::Lt, 1.0);
    report.check("rozdíl 1475 / rozdíl 2000", c[1].0 / c[2].0, Cmp::Lt, 1.0);
    report.check("rozdíl 2000 / rozdíl 2500", c[2].0 / c[3].0, Cmp::Lt, 1.0);
    report
}

pub fn check_skola_sjednoti(courses: &Courses) -> Report {
    let mut report = Report::new();
    report.check(
        "nářečí 2500 se školou / (nářečí bez školy / 5)",
        courses.school.course[3].1 / (courses.none.course[3].1 / 5.0),
        Cmp::Lt,
        1.0,
    );
    report.check(
        "ustálení po 1750 se školou / (bez školy / 5)",
        courses.school.changes as f64 / (courses.none.changes as f64 / 5.0),
        Cmp::Gt,
        1.0,
    );
    report
}

pub fn check_skola_zmrazena(courses: &Courses) -> Report {
    let mut report = Report::new();
    report.check(
        "ustálení po 1750 bez tisku / (s tiskem / 3)",
        courses.frozen.changes as f64 / (courses.school.changes as f64 / 3.0),
        Cmp::Lt,
        1.0,
    );
    report
}

/// Kodifikace bez tisku: psaný kód po roce 100 stojí.
pub struct Codified {
    pub simulation: Simulation,
    pub written: String,
    pub before: Vec<(VariableId, Vec<VariantId>)>,
}

pub fn run_codification(seed: i64) -> Result<Codified, String> {
    let options = SeedOptions {
        syntax: true,
        semantics: true,
        ..SeedOptions::default()
    };
    let world = village_grid_default(3, 1, seed, &options)?;
    let names: Vec<String> = world
        .group_ids()
        .iter()
        .map(|&g| world.group_name(g).to_owned())
        .collect();
    let event: Box<dyn WorldEvent> = Box::new(PendingEvent::new(
        100.0,
        "codification",
        json!({"source": "v00-01", "readers": names}),
    ));
    let mut simulation = Simulation::new(world, SimulationConfig::default(), vec![event])?;
    simulation.run(100.0)?;
    let written = "written:v00-01".to_owned();
    let mut before = Vec::new();
    if let Some(group) = group_named(&simulation.world, &written) {
        for variable in 0..simulation.world.variables.len() {
            let id = VariableId::new(variable);
            if let Some(distribution) = simulation.world.distribution(group, id) {
                before.push((id, distribution.variants));
            }
        }
    }
    simulation.run(800.0)?;
    Ok(Codified {
        simulation,
        written,
        before,
    })
}

pub fn check_psany_kod_bez_tisku_stoji(run: &Codified) -> Report {
    let mut report = Report::new();
    let world = &run.simulation.world;
    let Some(group) = group_named(world, &run.written) else {
        report.missing(&format!("skupina {}", run.written));
        return report;
    };
    report.check(
        "počet proměnných psaného kódu po kodifikaci",
        run.before.len() as f64,
        Cmp::Gt,
        0.0,
    );
    let changed = run
        .before
        .iter()
        .filter(|(variable, variants)| {
            world
                .distribution(group, *variable)
                .is_none_or(|d| d.variants != *variants)
        })
        .count();
    report.check(
        "proměnné psaného kódu, které se změnily",
        changed as f64,
        Cmp::Eq,
        0.0,
    );
    // Počet mluvených skupin snímku je součet velikostí jeho nářečí.
    let snapshots = &run.simulation.history.snapshots;
    let wrong = snapshots
        .iter()
        .filter(|s| s.dialects.iter().map(Vec::len).sum::<usize>() != 3)
        .count();
    report.check(
        "snímky s jiným počtem mluvených skupin než 3",
        wrong as f64,
        Cmp::Eq,
        0.0,
    );
    report
}

/// Otisk historie téhož běhu (zkouška determinismu s písmem).
pub fn determinism_digest() -> Result<String, String> {
    let (world, events) = diglossia(3, 200.0, Some(500.0), true, 0.05, false)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    simulation.run(800.0)?;
    Ok(simulation.history.digest())
}

pub fn batches() -> Vec<Batch> {
    fn diglossia_batch(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let courses = run_diglossia_courses(seed)?;
        Ok(vec![
            ("m6a::s4_skola", check_s4_skola(&courses)),
            ("m6a::s4_bez_skoly", check_s4_bez_skoly(&courses)),
            ("m6a::skola_sjednoti", check_skola_sjednoti(&courses)),
            ("m6a::skola_zmrazena", check_skola_zmrazena(&courses)),
        ])
    }
    fn codification(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        Ok(vec![(
            "m6a::psany_kod_stoji",
            check_psany_kod_bez_tisku_stoji(&run_codification(seed)?),
        )])
    }
    vec![
        Batch {
            id: "m6a_diglossia",
            gates: &[
                "m6a::s4_skola",
                "m6a::s4_bez_skoly",
                "m6a::skola_sjednoti",
                "m6a::skola_zmrazena",
            ],
            run: Runner::Single(diglossia_batch),
        },
        Batch {
            id: "m6a_codification",
            gates: &["m6a::psany_kod_stoji"],
            run: Runner::Single(codification),
        },
    ]
}
