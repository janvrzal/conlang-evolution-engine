//! Brána M3 (`test_v2_m3_gate.py`): morfologie. Kontinuum osmi vesnic s podstatnými jmény
//! a slovesy, semínka 1 a 2 (a `1..10` pro hraniční brány), 3 000 let; pro Sturtevantův
//! paradox navíc tentýž běh bez vyrovnání.

use super::metrics::{lexicon_profile, maximum, mean, minimum, morphology_profile, text};
use super::{Batch, Cmp, Report, Runner};
use crate::changes::default_changes;
use crate::ids::{MorphemeId, VariableId};
use crate::model::lexicon::MorphemeKind;
use crate::scenarios::{village_grid_default, SeedOptions};
use crate::{Simulation, SimulationConfig};

/// Osm vesnic s fonologií a morfologií, 3 000 let; `leveling = false` vypne vyrovnání analogií.
pub fn run_m3(seed: i64, leveling: bool) -> Result<Simulation, String> {
    let options = SeedOptions {
        phonology: true,
        morphology: true,
        ..SeedOptions::default()
    };
    let world = village_grid_default(8, 1, seed, &options)?;
    let changes = default_changes()
        .into_iter()
        .filter(|change| leveling || change.kind() != "leveling")
        .collect();
    let mut simulation =
        Simulation::with_changes(world, SimulationConfig::default(), Vec::new(), changes)?;
    simulation.run(3000.0)?;
    Ok(simulation)
}

fn mean_profile(
    simulation: &Simulation,
    attribute: fn(&super::metrics::MorphologyProfile) -> f64,
) -> f64 {
    let world = &simulation.world;
    let values: Vec<f64> = world
        .group_ids()
        .into_iter()
        .map(|group| attribute(&morphology_profile(world, group)))
        .collect();
    mean(&values)
}

/// Zvuk tvoří alternace (`unleveled` je běh bez vyrovnání), analogie je opravuje.
pub fn check_sturtevantuv_paradox(simulation: &Simulation, unleveled: &Simulation) -> Report {
    let mut report = Report::new();
    let without = mean_profile(unleveled, |p| p.alternation);
    let with = mean_profile(simulation, |p| p.alternation);
    report.check("alternace bez vyrovnání", without, Cmp::Gt, 0.3);
    report.check(
        "alternace bez vyrovnání − s vyrovnáním",
        without - with,
        Cmp::Gt,
        0.1,
    );
    report
}

/// Plurál nesený jen kmenem: koncovka zanikla, alternace zůstala.
pub fn check_morfologizace(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    report.check(
        "podíl zmorfologizovaných buněk",
        mean_profile(simulation, |p| p.morphologized),
        Cmp::Gt,
        0.02,
    );
    report
}

/// Produktivní vzor se šíří a častá slova si drží nepravidelnost (přes všechny běhy dohromady).
pub fn check_produktivni_vzor(runs: &[&Simulation]) -> Report {
    let mut report = Report::new();
    let mut productive = Vec::new();
    let (mut frequent, mut rare) = (Vec::new(), Vec::new());
    for simulation in runs {
        productive.push(mean_profile(simulation, |p| p.productive_share));
        let world = &simulation.world;
        for group in world.group_ids() {
            let profile = morphology_profile(world, group);
            frequent.push(profile.irregular_frequent);
            rare.push(profile.irregular_rare);
        }
    }
    report.check(
        "nejnižší podíl produktivní koncovky",
        minimum(&productive),
        Cmp::Gt,
        0.8,
    );
    report.check(
        "nepravidelnost častých − vzácných slov",
        mean(&frequent) - mean(&rare),
        Cmp::Gt,
        0.0,
    );
    report
}

/// Analogie zasahuje spíš vzácná slova.
pub fn check_analogie(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let analogized: Vec<f64> = simulation
        .history
        .of_kind("analogy")
        .filter_map(|event| {
            let variable = VariableId(world.registry.variables.get(text(event, "variable"))?);
            let unit = world.form_changes.get(&variable)?.unit;
            Some(world.morphemes.frequency[world.morphemes.lexeme_id(unit).index()])
        })
        .collect();
    let vocabulary: Vec<f64> = (0..world.morphemes.len())
        .filter(|&m| {
            world.morphemes.present[m]
                && world.morphemes.kind[m] == MorphemeKind::Root
                && !world.morphemes.word_class[m].is_none()
        })
        .map(|m| world.morphemes.frequency[m])
        .collect();
    report.check("počet analogií", analogized.len() as f64, Cmp::Gt, 0.0);
    report.check(
        "průměrná frekvence slov s analogií / průměr slovní zásoby",
        mean(&analogized) / mean(&vocabulary),
        Cmp::Lt,
        1.0,
    );
    report
}

/// Délka slov a homofonie drží i s paradigmaty (`3 <= délka <= 8`, homofonie `< 0,05`).
pub fn check_zvukove_metriky(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
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

/// Otisk historie a tvary slovní zásoby první skupiny (zkouška determinismu s morfologií).
pub fn determinism_probe() -> Result<(String, std::collections::BTreeMap<String, Vec<i32>>), String>
{
    let options = SeedOptions {
        phonology: true,
        morphology: true,
        ..SeedOptions::default()
    };
    let world = village_grid_default(3, 1, 4, &options)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    simulation.run(1000.0)?;
    let world = &simulation.world;
    let first = world.group_ids()[0];
    let code = world.groups.main_code(first);
    let forms = code
        .phonology
        .vocabulary
        .iter()
        .map(|unit: MorphemeId| {
            (
                world.registry.morphemes.name(unit.0).to_owned(),
                world.form_of(first, unit).to_vec(),
            )
        })
        .collect();
    Ok((simulation.history.digest(), forms))
}

pub fn batches() -> Vec<Batch> {
    fn morphology(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let simulation = run_m3(seed, true)?;
        let unleveled = run_m3(seed, false)?;
        Ok(vec![
            (
                "m3::sturtevantuv_paradox",
                check_sturtevantuv_paradox(&simulation, &unleveled),
            ),
            ("m3::morfologizace", check_morfologizace(&simulation)),
            (
                "m3::produktivni_vzor",
                check_produktivni_vzor(&[&simulation]),
            ),
            ("m3::analogie", check_analogie(&simulation)),
            ("m3::zvukove_metriky", check_zvukove_metriky(&simulation)),
        ])
    }
    vec![Batch {
        id: "m3_morphology",
        gates: &[
            "m3::sturtevantuv_paradox",
            "m3::morfologizace",
            "m3::produktivni_vzor",
            "m3::analogie",
            "m3::zvukove_metriky",
        ],
        run: Runner::Single(morphology),
    }]
}
