//! Brána M3b (`test_v2_m3b_gate.py`): lexikon a význam. Kontinuum osmi vesnic s fonologií,
//! paradigmaty a grafem pojmů, semínka 1 a 2, 3 000 let; k tomu pokusy s erozí a tabu.

use std::collections::BTreeSet;

use super::metrics::{concepts_by_frequency, lexical_variables, mean, retention, text};
use super::{Batch, Cmp, Report, Runner};
use crate::ids::MorphemeId;
use crate::ids::{ConceptId, VariableId};
use crate::model::forms::UnitForm;
use crate::model::repertoire::Payload;
use crate::scenarios::{village_grid_default, SeedOptions};
use crate::{Simulation, SimulationConfig};

/// Původy nových slov (`ORIGINS` v Pythonu; `clipping` od M11, dok. 30).
pub const ORIGINS: [&str; 12] = [
    "shift",
    "conversion",
    "derivation",
    "compound",
    "circumlocution",
    "contamination",
    "back_formation",
    "clipping",
    "renewal",
    "metathesis",
    "dissimilation",
    "coinage",
];

fn options() -> SeedOptions {
    SeedOptions {
        phonology: true,
        morphology: true,
        semantics: true,
        ..SeedOptions::default()
    }
}

pub fn run_m3b(seed: i64) -> Result<Simulation, String> {
    let world = village_grid_default(8, 1, seed, &options())?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    simulation.run(3000.0)?;
    Ok(simulation)
}

/// Je dominantní slovo proměnné ve skupině nové (nezděděné)?
fn replaced(
    simulation: &Simulation,
    group: crate::ids::GroupId,
    variable: VariableId,
) -> Option<bool> {
    let world = &simulation.world;
    let (variant, _) = world.dominant(group, variable)?;
    Some(world.variants.origin[variant.index()].change.is_some())
}

/// Kontrolovaný pokus: polovině pojmů se zděděné slovo zkrátí na dvě hlásky. Vrací běh
/// a zkrácené proměnné.
pub fn run_eroded(seed: i64) -> Result<(Simulation, BTreeSet<VariableId>), String> {
    let mut world = village_grid_default(6, 1, seed, &options())?;
    let first = world.group_ids()[0];
    let mut eroded = BTreeSet::new();
    for (index, (variable, _)) in lexical_variables(&world).into_iter().enumerate() {
        if index % 2 == 1 {
            continue;
        }
        let Some(root) = world.stored(first, variable) else {
            continue;
        };
        let Payload::Lexical { morpheme, .. } = world.variants.payload[root.variants[0].index()]
        else {
            continue;
        };
        let form = world
            .bank
            .form(world.morphemes.form[morpheme.index()])
            .to_vec();
        if form.len() < 4 {
            continue;
        }
        eroded.insert(variable);
        let short = world.bank.id_of(&form[..2]);
        for group in world.group_ids() {
            crate::views::set_form(
                &mut world,
                group,
                morpheme,
                UnitForm {
                    form: short,
                    boundary: -1,
                    exponent: MorphemeId::NONE,
                },
            );
            world.groups.main_code_mut(group).phonology.version += 1;
        }
    }
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    simulation.run(1500.0)?;
    Ok((simulation, eroded))
}

/// Varianty ustálené pro pojem `dog` (jména) po 2 500 letech, s tabu na `dog` nebo bez něj.
fn taboo_replacements(taboo: bool, seed: i64) -> Result<BTreeSet<String>, String> {
    let mut world = village_grid_default(4, 1, seed, &options())?;
    if taboo {
        let dog = world
            .registry
            .concepts
            .get("dog")
            .map(ConceptId)
            .ok_or("pojem dog ve světě není")?;
        for group in world.group_ids() {
            world.groups.taboo[group.index()] = vec![dog];
        }
    }
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    simulation.run(2500.0)?;
    Ok(simulation
        .history
        .of_kind("established")
        .filter(|event| text(event, "variable") == "lexical:dog")
        .map(|event| text(&event, "variant").to_owned())
        .collect())
}

/// Totéž s tabu a bez něj: (s tabu, bez tabu).
pub fn run_taboo_pair(seed: i64) -> Result<(BTreeSet<String>, BTreeSet<String>), String> {
    Ok((
        taboo_replacements(true, seed)?,
        taboo_replacements(false, seed)?,
    ))
}

pub fn check_metrika_1(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let values: Vec<f64> = world
        .group_ids()
        .into_iter()
        .map(|group| retention(world, group))
        .collect();
    report.between(
        "retence slovní zásoby za tisíciletí",
        mean(&values).powf(1.0 / 3.0),
        0.70,
        0.95,
    );
    report
}

/// Horních 30 % pojmů podle frekvence se nahrazuje pomaleji než ostatní (poměr rychlostí 0,85).
pub fn check_metrika_2(runs: &[&Simulation]) -> Report {
    let mut report = Report::new();
    let (mut frequent, mut rare) = (Vec::new(), Vec::new());
    for simulation in runs {
        let world = &simulation.world;
        let ordered = concepts_by_frequency(world);
        let top: BTreeSet<ConceptId> = ordered[(ordered.len() as f64 * 0.7) as usize..]
            .iter()
            .copied()
            .collect();
        for group in world.group_ids() {
            for (variable, concept) in lexical_variables(world) {
                if let Some(is_new) = replaced(simulation, group, variable) {
                    let value = f64::from(u8::from(is_new));
                    if top.contains(&concept) {
                        frequent.push(value);
                    } else {
                        rare.push(value);
                    }
                }
            }
        }
    }
    report.check(
        "podíl nahrazených častých / (0,85 × podíl nahrazených vzácných)",
        mean(&frequent) / (0.85 * mean(&rare)),
        Cmp::Lt,
        1.0,
    );
    report
}

/// Nová slova mají doložitelný původ, většinou motivovaný.
pub fn check_nova_slova(runs: &[&Simulation]) -> Report {
    let mut report = Report::new();
    let mut origins: Vec<String> = Vec::new();
    for simulation in runs {
        let world = &simulation.world;
        for group in world.group_ids() {
            for (variable, _) in lexical_variables(world) {
                let Some((variant, _)) = world.dominant(group, variable) else {
                    continue;
                };
                if world.variants.origin[variant.index()].change.is_none() {
                    continue;
                }
                if let Payload::Lexical { origin, .. } = &world.variants.payload[variant.index()] {
                    origins.push(origin.clone());
                }
            }
        }
    }
    let total = origins.len() as f64;
    let unknown = origins
        .iter()
        .filter(|o| !ORIGINS.contains(&o.as_str()))
        .count();
    let motivated = origins
        .iter()
        .filter(|o| {
            matches!(
                o.as_str(),
                "shift" | "conversion" | "derivation" | "compound"
            )
        })
        .count();
    let coinage = origins.iter().filter(|o| *o == "coinage").count();
    report.check("počet nových slov", total, Cmp::Gt, 0.0);
    report.check(
        "nová slova s neznámým původem",
        unknown as f64,
        Cmp::Eq,
        0.0,
    );
    report.check(
        "podíl motivovaných původů",
        motivated as f64 / total,
        Cmp::Ge,
        0.6,
    );
    report.check(
        "podíl vymyšlených slov",
        coinage as f64 / total,
        Cmp::Lt,
        0.3,
    );
    report
}

pub fn check_erodovana_slova(simulation: &Simulation, eroded: &BTreeSet<VariableId>) -> Report {
    let mut report = Report::new();
    let world = &simulation.world;
    let (mut hit, mut control) = (Vec::new(), Vec::new());
    for group in world.group_ids() {
        for (variable, _) in lexical_variables(world) {
            if let Some(is_new) = replaced(simulation, group, variable) {
                let value = f64::from(u8::from(is_new));
                if eroded.contains(&variable) {
                    hit.push(value);
                } else {
                    control.push(value);
                }
            }
        }
    }
    report.check(
        "podíl nahrazených zkrácených / (2 × podíl ostatních)",
        mean(&hit) / (2.0 * mean(&control)),
        Cmp::Gt,
        1.0,
    );
    report
}

/// Tabu vyvolá koloběh opisů: aspoň dvě ustálené náhrady s tabu, žádná bez něj.
pub fn check_tabu(with_taboo: &BTreeSet<String>, without_taboo: &BTreeSet<String>) -> Report {
    let mut report = Report::new();
    report.check(
        "počet ustálených náhrad s tabu",
        with_taboo.len() as f64,
        Cmp::Ge,
        2.0,
    );
    report.check(
        "počet ustálených náhrad bez tabu",
        without_taboo.len() as f64,
        Cmp::Eq,
        0.0,
    );
    report
}

pub fn check_zvukove_metriky(simulation: &Simulation) -> Report {
    super::m3::check_zvukove_metriky(simulation)
}

/// Otisk historie téhož běhu (zkouška determinismu s významem).
pub fn determinism_digest() -> Result<String, String> {
    let world = village_grid_default(3, 1, 4, &options())?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    simulation.run(1000.0)?;
    Ok(simulation.history.digest())
}

pub fn batches() -> Vec<Batch> {
    fn lexicon(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let simulation = run_m3b(seed)?;
        Ok(vec![
            ("m3b::metrika_1", check_metrika_1(&simulation)),
            ("m3b::metrika_2", check_metrika_2(&[&simulation])),
            ("m3b::nova_slova", check_nova_slova(&[&simulation])),
            ("m2::zvukove_metriky", check_zvukove_metriky(&simulation)),
        ])
    }
    fn eroded(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let (simulation, eroded) = run_eroded(seed)?;
        Ok(vec![(
            "m3b::erodovana_slova",
            check_erodovana_slova(&simulation, &eroded),
        )])
    }
    fn taboo(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let (with, without) = run_taboo_pair(seed)?;
        Ok(vec![("m3b::tabu", check_tabu(&with, &without))])
    }
    vec![
        Batch {
            id: "m3b_lexicon",
            gates: &[
                "m3b::metrika_1",
                "m3b::metrika_2",
                "m3b::nova_slova",
                "m2::zvukove_metriky",
            ],
            run: Runner::Single(lexicon),
        },
        Batch {
            id: "m3b_eroded",
            gates: &["m3b::erodovana_slova"],
            run: Runner::Single(eroded),
        },
        Batch {
            id: "m3b_taboo",
            gates: &["m3b::tabu"],
            run: Runner::Single(taboo),
        },
    ]
}
