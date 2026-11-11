//! Brána M2 (`test_v2_m2_gate.py`): metriky 3 až 6 nad zvukem. Kontinuum deseti vesnic
//! s vygenerovaným protojazykem, 3 000 let, tři semínka.

use std::collections::{BTreeMap, BTreeSet};

use cee_core::candidates::FAMILIES;

use super::metrics::{
    established_per_group, established_processes, established_with_reflexes, hellinger,
    lexicon_profile, maximum, median, minimum, text, LexiconProfile, CONSONANT_BAND, VOWEL_BAND,
};
use super::{Batch, Cmp, Report, Runner};
use crate::changes::sound::PRIORS;
use crate::ids::VariableId;
use crate::scenarios::{village_grid_default, SeedOptions};
use crate::{Simulation, SimulationConfig};

/// Doména každé rodiny zvukových změn v pořadí `FAMILIES` (`SoundChange.domain` v Pythonu).
pub const DOMAINS: [&str; 34] = [
    "consonant",
    "consonant",
    "consonant",
    "consonant",
    "consonant",
    "consonant",
    "consonant",
    "consonant",
    "consonant",
    "consonant",
    "consonant",
    "vowel",
    "vowel",
    "vowel",
    "vowel",
    "vowel",
    "vowel",
    "structure",
    "structure",
    "structure",
    "consonant",
    "consonant",
    "consonant",
    "vowel",
    "vowel",
    "consonant",
    "consonant",
    "consonant",
    "vowel",
    "vowel",
    "vowel",
    "vowel",
    "vowel",
    "vowel",
];

/// Běh jednoho semínka: simulace a profily slovní zásoby po 1 000, 2 000 a 3 000 letech.
pub struct PhonologyRun {
    pub simulation: Simulation,
    pub profiles: Vec<Vec<LexiconProfile>>,
}

pub fn run_phonology(seed: i64) -> Result<PhonologyRun, String> {
    let options = SeedOptions {
        phonology: true,
        ..SeedOptions::default()
    };
    let world = village_grid_default(10, 1, seed, &options)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    let mut profiles = Vec::new();
    for year in [1000.0, 2000.0, 3000.0] {
        simulation.run(year)?;
        let world = &simulation.world;
        profiles.push(
            world
                .group_ids()
                .into_iter()
                .map(|group| lexicon_profile(world, group))
                .collect(),
        );
    }
    Ok(PhonologyRun {
        simulation,
        profiles,
    })
}

pub fn check_metrika_3(run: &PhonologyRun) -> Report {
    let mut report = Report::new();
    let lengths: Vec<f64> = run
        .profiles
        .iter()
        .flatten()
        .map(|p| p.mean_length)
        .collect();
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
    report
}

pub fn check_metrika_4(run: &PhonologyRun) -> Report {
    let mut report = Report::new();
    let last = run.profiles.last().map(Vec::as_slice).unwrap_or(&[]);
    let consonants: Vec<f64> = last.iter().map(|p| p.consonants as f64).collect();
    let vowels: Vec<f64> = last.iter().map(|p| p.vowels as f64).collect();
    report.check(
        "nejmíň souhlásek",
        minimum(&consonants),
        Cmp::Ge,
        CONSONANT_BAND.0,
    );
    report.check(
        "nejvíc souhlásek",
        maximum(&consonants),
        Cmp::Le,
        CONSONANT_BAND.1,
    );
    report.check("nejmíň samohlásek", minimum(&vowels), Cmp::Ge, VOWEL_BAND.0);
    report.check("nejvíc samohlásek", maximum(&vowels), Cmp::Le, VOWEL_BAND.1);
    report
}

pub fn check_metrika_5(run: &PhonologyRun) -> Report {
    let mut report = Report::new();
    let last = run.profiles.last().map(Vec::as_slice).unwrap_or(&[]);
    let homophony: Vec<f64> = last.iter().map(|p| p.homophony).collect();
    report.check("nejvyšší homofonie", maximum(&homophony), Cmp::Lt, 0.05);
    report
}

/// Rodina ustálené procesní proměnné (jméno z historie).
fn family_of(simulation: &Simulation, variable: &str) -> Option<usize> {
    let world = &simulation.world;
    let id = VariableId(world.registry.variables.get(variable)?);
    let process = world.variables.process.get(id.index())?;
    let family = &world.processes.get(process.index())?.as_ref()?.family;
    FAMILIES.iter().position(|name| name == family)
}

/// Ustálené změny odpovídají prioru a nejsou jednostranné (legacy jádro ustálilo jen samohlásky).
pub fn check_metrika_6(runs: &[&PhonologyRun]) -> Report {
    let mut report = Report::new();
    let mut domains: BTreeMap<String, f64> = BTreeMap::new();
    let mut families: BTreeSet<usize> = BTreeSet::new();
    for run in runs {
        for variable in established_with_reflexes(&run.simulation.history) {
            if let Some(family) = family_of(&run.simulation, &variable) {
                families.insert(family);
                *domains.entry(DOMAINS[family].to_owned()).or_insert(0.0) += 1.0;
            }
        }
    }
    let total: f64 = domains.values().sum();
    // Počet změn podél jedné linie (průměr na vesnici), podíly druhů ze všech změn běhu.
    let per_lineage: f64 = runs
        .iter()
        .map(|run| established_per_group(&run.simulation.history))
        .sum();
    report.check("počet ustálených změn", per_lineage, Cmp::Ge, 30.0);
    let share = |domain: &str| domains.get(domain).copied().unwrap_or(0.0) / total;
    report.check("podíl souhláskových změn", share("consonant"), Cmp::Ge, 0.2);
    report.check("podíl samohláskových změn", share("vowel"), Cmp::Ge, 0.2);
    report.check("počet rodin změn", families.len() as f64, Cmp::Ge, 6.0);
    let mut prior: BTreeMap<String, f64> = BTreeMap::new();
    for (domain, weight) in DOMAINS.iter().zip(PRIORS) {
        *prior.entry((*domain).to_owned()).or_insert(0.0) += weight;
    }
    report.check(
        "Hellingerova vzdálenost od priorů",
        hellinger(&domains, &prior),
        Cmp::Lt,
        0.25,
    );
    report
}

/// Bez náhodilosti spuštění by každý jazyk prošel stejnými změnami.
pub fn check_jazyky_se_lisi(runs: &[&PhonologyRun]) -> Report {
    let mut report = Report::new();
    let histories: Vec<BTreeSet<String>> = runs
        .iter()
        .map(|run| {
            let world = &run.simulation.world;
            established_processes(&run.simulation.history)
                .into_iter()
                .filter_map(|name| {
                    let id = world.registry.variables.get(&name)?;
                    world.variables.key.get(id as usize).cloned()
                })
                .collect()
        })
        .collect();
    let mut overlaps = Vec::new();
    for (index, first) in histories.iter().enumerate() {
        for second in &histories[index + 1..] {
            let union = first.union(second).count();
            overlaps.push(if union == 0 {
                f64::NAN
            } else {
                first.intersection(second).count() as f64 / union as f64
            });
        }
    }
    report.check(
        "největší překryv ustálených změn dvou jazyků",
        maximum(&overlaps),
        Cmp::Lt,
        0.6,
    );
    report
}

/// Změny se šíří areálně a mají malé výjimky (relikty).
pub fn check_zvukove_zmeny_se_siri(run: &PhonologyRun) -> Report {
    let mut report = Report::new();
    let history = &run.simulation.history;
    let mut per_change: BTreeMap<String, f64> = BTreeMap::new();
    for event in history.of_kind("established") {
        let variable = text(&event, "variable").to_owned();
        if variable.starts_with("process:") {
            *per_change.entry(variable).or_insert(0.0) += 1.0;
        }
    }
    let counts: Vec<f64> = per_change.values().copied().collect();
    report.check(
        "počet ustálených zvukových změn",
        counts.len() as f64,
        Cmp::Ge,
        1.0,
    );
    report.check(
        "medián počtu skupin na změnu",
        median(&counts),
        Cmp::Ge,
        2.0,
    );
    let (mut relics, mut rewritten) = (0.0, 0.0);
    // Relikty jsou výjimky z proběhlé změny; odumřelá změna (`faded`) slova nezasáhla.
    for event in history.of_kind("process_closed").filter(|event| {
        !event
            .get("faded")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
    }) {
        relics += event.get("relics").and_then(|v| v.as_f64()).unwrap_or(0.0);
        rewritten += event
            .get("restructured")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);
    }
    report.check("relikty + přepsaná slova", relics + rewritten, Cmp::Gt, 0.0);
    report.check(
        "podíl reliktů (dolní)",
        relics / (relics + rewritten),
        Cmp::Gt,
        0.01,
    );
    report.check(
        "podíl reliktů (horní)",
        relics / (relics + rewritten),
        Cmp::Lt,
        0.15,
    );
    report
}

pub fn batches() -> Vec<Batch> {
    fn phonology(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let run = run_phonology(seed)?;
        let mut sound = check_metrika_3(&run);
        sound.extend("", check_metrika_5(&run));
        Ok(vec![
            ("m2::zvukove_metriky", sound),
            ("m2::metrika_4", check_metrika_4(&run)),
            (
                "m2::zvukove_zmeny_se_siri",
                check_zvukove_zmeny_se_siri(&run),
            ),
        ])
    }
    fn triplet(seeds: [i64; 3]) -> Result<Vec<(&'static str, Report)>, String> {
        let runs = seeds
            .iter()
            .map(|&seed| run_phonology(seed))
            .collect::<Result<Vec<_>, _>>()?;
        let refs: Vec<&PhonologyRun> = runs.iter().collect();
        Ok(vec![
            ("m2::metrika_6", check_metrika_6(&refs)),
            ("m2::ruznost_seedu", check_jazyky_se_lisi(&refs)),
        ])
    }
    vec![
        Batch {
            id: "m2_phonology",
            gates: &[
                "m2::zvukove_metriky",
                "m2::metrika_4",
                "m2::zvukove_zmeny_se_siri",
            ],
            run: Runner::Single(phonology),
        },
        Batch {
            id: "m2_phonology_triplet",
            gates: &["m2::metrika_6", "m2::ruznost_seedu"],
            run: Runner::Triplet(triplet),
        },
    ]
}
