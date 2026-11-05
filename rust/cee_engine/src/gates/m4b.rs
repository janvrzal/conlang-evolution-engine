//! Brána M4b (`test_v2_m4b_gate.py`): modulární gramatika. Funkce jsou řádky katalogu a jazyk
//! je má jen podle profilu protojazyka. Ověřuje se, že kategorie může vzniknout (člen
//! z ukazovacího zájmena), že zbytková koncovka může dostat novou funkci (exaptace) a že
//! jazyk bez kategorie ji nemá, dokud ji nevyvine.

use std::collections::BTreeSet;

use super::metrics::text;
use super::{Batch, Cmp, Report, Runner};
use crate::grammar::{profile, Catalog, Construction};
use crate::ids::{CellId, MorphemeId, WordClassId};
use crate::model::lexicon::MorphemeKind;
use crate::parameters::Parameters;
use crate::scenarios::{default_concepts, village_grid, SeedOptions};
use crate::syntax;
use crate::world::World;
use crate::{Simulation, SimulationConfig};

use super::m4::kind_count;

type Grammar = Vec<(&'static str, Construction)>;

/// Jazyk bez pádu a bez členu, který ho ale může vyvinout.
pub fn no_case() -> Grammar {
    let mut grammar: Grammar = profile::syntax()
        .into_iter()
        .filter(|(name, _)| *name != "OBJ")
        .collect();
    grammar.push(("DEFINITE", Construction::new("DEFINITE", "zero")));
    grammar
}

/// Člen vzniká jen v části jazyků (audit 6/30 na semínkách 101..130); pro „aspoň jednou“
/// s rizikem falešného selhání pod 1 % je třeba N >= 46.
pub const ARTICLE_SEEDS: std::ops::RangeInclusive<i64> = 1..=50;

fn grid(seed: i64, grammar: Grammar, params: Parameters) -> Result<World, String> {
    let options = SeedOptions {
        grammar: Some(grammar),
        semantics: true,
        ..SeedOptions::default()
    };
    village_grid(
        6,
        1,
        seed,
        &options,
        &default_concepts(),
        10.0,
        500,
        25.0,
        0.1,
        2.0,
        params,
    )
}

fn run_grid(world: World, until: f64) -> Result<Simulation, String> {
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    simulation.run(until)?;
    Ok(simulation)
}

pub fn run_no_case(seed: i64, params: Option<Parameters>) -> Result<Simulation, String> {
    run_grid(grid(seed, no_case(), params.unwrap_or_default())?, 3000.0)
}

/// Buňka je v paradigmatu třídy slova.
pub fn has_cell(world: &World, class: &str, cell: &str) -> bool {
    let (Some(class), Some(cell)) = (
        world.registry.word_classes.get(class),
        world.registry.cells.get(cell),
    ) else {
        return false;
    };
    world
        .paradigms
        .get(class as usize)
        .and_then(Option::as_ref)
        .is_some_and(|paradigm| paradigm.cells.contains(&CellId(cell)))
}

/// Tvary slov ve slovní zásobě skupiny, které funkci vyjadřují koncovkou (`syntax.cell_units`).
fn cell_units(world: &World, group: crate::ids::GroupId, function: &str) -> Vec<MorphemeId> {
    let Some(entry) = Catalog::shared().get(function) else {
        return Vec::new();
    };
    let class = entry
        .word_class()
        .and_then(|name| world.registry.word_classes.get(name))
        .map(WordClassId);
    let cell = entry
        .cell
        .as_deref()
        .and_then(|name| world.registry.cells.get(name))
        .map(CellId);
    let (Some(class), Some(cell)) = (class, cell) else {
        return Vec::new();
    };
    world
        .groups
        .main_code(group)
        .phonology
        .vocabulary
        .iter()
        .filter(|unit| {
            world.morphemes.kind[unit.index()] == MorphemeKind::Word
                && world.morphemes.word_class[unit.index()] == class
                && world.morphemes.cell[unit.index()] == cell
        })
        .collect()
}

/// Zdroj členu je z katalogu a srostlý člen dal jazyku buňku; vrací také, zda člen vznikl
/// (nejvýš dvě skupiny mají nulový člen).
pub fn check_clen_invariants(simulation: &Simulation) -> (Report, bool) {
    let mut report = Report::new();
    let world = &simulation.world;
    let sources = Catalog::shared()
        .get("DEFINITE")
        .map(|f| f.sources.clone())
        .unwrap_or_default();
    let foreign = world
        .group_ids()
        .into_iter()
        .filter_map(|group| syntax::dominant(world, group, "DEFINITE"))
        .filter(|c| c.source.as_ref().is_some_and(|s| !sources.contains(s)))
        .count();
    report.check("členy s cizím zdrojem", foreign as f64, Cmp::Eq, 0.0);
    let grammaticalized = simulation
        .history
        .of_kind("grammaticalized")
        .any(|event| text(&event, "function") == "DEFINITE");
    if grammaticalized {
        report.flag(
            "srostlý člen dal jazyku buňku DEF",
            has_cell(world, "noun", "DEF"),
        );
    }
    let zero = kind_count(world, "DEFINITE", "zero");
    (report, zero <= 2.0)
}

/// Brána „člen vznikne“ na jednom semínku: invarianty a vznik členu.
pub fn check_clen_jeden_seed(simulation: &Simulation) -> Report {
    let (mut report, article) = check_clen_invariants(simulation);
    report.flag("člen vznikl (nejvýš dvě skupiny s nulovým členem)", article);
    report
}

fn exaptation(order: Construction, seed: i64) -> Result<Simulation, String> {
    let mut grammar = profile::syntax();
    for entry in &mut grammar {
        if entry.0 == "ORDER" {
            entry.1 = order.clone();
        }
    }
    grammar.push(("DEFINITE", Construction::new("DEFINITE", "zero")));
    run_grid(grid(seed, grammar, Parameters::default())?, 1500.0)
}

/// Pád vedle pevného slovosledu a týž jazyk s volným slovosledem (kontrola).
pub fn run_exaptation_pair(seed: i64) -> Result<(Simulation, Simulation), String> {
    Ok((
        exaptation(Construction::new("ORDER", "fixed").with_order("SVO"), seed)?,
        exaptation(Construction::new("ORDER", "free"), seed)?,
    ))
}

/// Pád vedle pevného slovosledu nic nenese; jeho koncovka se stane členem.
pub fn check_exaptace(target: &Simulation, control: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &target.world;
    let events: Vec<_> = target.history.of_kind("exapted").collect();
    let groups: BTreeSet<&str> = events.iter().map(|e| text(e, "group")).collect();
    report.check("skupiny s exaptací", groups.len() as f64, Cmp::Ge, 4.0);
    let pairs: BTreeSet<(&str, &str)> = events
        .iter()
        .map(|e| (text(e, "function"), text(e, "donor")))
        .collect();
    report.flag(
        "exaptace jen DEFINITE z OBJ",
        pairs.len() == 1 && pairs.contains(&("DEFINITE", "OBJ")),
    );
    if let Some(first) = events.first() {
        match super::metrics::group_named(world, text(first, "group")) {
            Some(group) => {
                let definite = cell_units(world, group, "DEFINITE");
                report.check(
                    "tvary členu v první skupině",
                    definite.len() as f64,
                    Cmp::Gt,
                    0.0,
                );
                let vocabulary = &world.groups.main_code(group).phonology.vocabulary;
                let all = definite.iter().all(|unit| {
                    let lexeme = world.morphemes.lexeme_id(*unit);
                    let name = format!("{}#OBJ", world.registry.morphemes.name(lexeme.0));
                    world
                        .registry
                        .morphemes
                        .get(&name)
                        .is_some_and(|id| vocabulary.contains(MorphemeId(id)))
                });
                report.flag("každý člen má tvar s koncovkou OBJ ve slovní zásobě", all);
            }
            None => report.missing("skupina první exaptace"),
        }
    } else {
        report.flag("exaptace existuje", false);
    }
    report.check(
        "exaptace v kontrole se slovosledem volným",
        control.history.of_kind("exapted").count() as f64,
        Cmp::Eq,
        0.0,
    );
    report.flag(
        "kontrola nemá buňku DEF",
        !has_cell(&control.world, "noun", "DEF"),
    );
    report
}

/// Jazyk bez minulého času a týž jazyk s minulým časem jako prázdnou funkcí.
pub fn run_tenseless_pair(seed: i64) -> Result<(Simulation, Simulation), String> {
    let tenseless: Grammar = profile::syntax()
        .into_iter()
        .filter(|(name, _)| *name != "PAST")
        .collect();
    let first = run_grid(
        grid(seed, tenseless.clone(), Parameters::default())?,
        1000.0,
    )?;
    let mut zero = tenseless;
    zero.push(("PAST", Construction::new("PAST", "zero")));
    let second = run_grid(grid(seed, zero, Parameters::default())?, 2000.0)?;
    Ok((first, second))
}

pub fn check_jazyk_bez_kategorie(tenseless: &Simulation, zero: &Simulation) -> Report {
    let mut report = Report::new();
    let world = &tenseless.world;
    let verb_cells: Vec<&str> = world
        .registry
        .word_classes
        .get("verb")
        .and_then(|class| world.paradigms.get(class as usize))
        .and_then(Option::as_ref)
        .map(|p| {
            p.cells
                .iter()
                .map(|cell| world.registry.cells.name(cell.0))
                .collect()
        })
        .unwrap_or_default();
    report.flag("paradigma sloves má jen buňku PRES", verb_cells == ["PRES"]);
    report.flag(
        "proměnná minulého času neexistuje",
        syntax::variable_of(world, "PAST").is_none(),
    );
    let past = world.registry.cells.get("PAST").map(CellId);
    let units = world
        .group_ids()
        .into_iter()
        .map(|group| {
            world
                .groups
                .main_code(group)
                .phonology
                .vocabulary
                .iter()
                .filter(|unit| Some(world.morphemes.cell[unit.index()]) == past)
                .count()
        })
        .sum::<usize>();
    report.check(
        "tvary minulého času ve slovní zásobě",
        units as f64,
        Cmp::Eq,
        0.0,
    );
    let zero_world = &zero.world;
    report.check(
        "skupiny s nulovým minulým časem po vývoji",
        kind_count(zero_world, "PAST", "zero"),
        Cmp::Le,
        1.0,
    );
    let sources = Catalog::shared()
        .get("PAST")
        .map(|f| f.sources.clone())
        .unwrap_or_default();
    let foreign = zero_world
        .group_ids()
        .into_iter()
        .filter_map(|group| syntax::dominant(zero_world, group, "PAST"))
        // Jen vyjádřený minulý čas má zdroj; skupina, která ho (zatím) nevyvinula, nemá žádný.
        .filter(|c| c.kind != "zero")
        .filter(|c| !c.source.as_ref().is_some_and(|s| sources.contains(s)))
        .count();
    report.check(
        "zdroje minulého času mimo katalog",
        foreign as f64,
        Cmp::Eq,
        0.0,
    );
    if zero.history.of_kind("grammaticalized").next().is_some() {
        report.flag(
            "po gramatikalizaci má sloveso buňku PAST",
            has_cell(zero_world, "verb", "PAST"),
        );
    }
    report
}

/// Otisk historie téhož běhu (zkouška determinismu s profilem).
pub fn determinism_digest() -> Result<String, String> {
    let simulation = run_grid(grid(4, no_case(), Parameters::default())?, 1000.0)?;
    Ok(simulation.history.digest())
}

pub fn batches() -> Vec<Batch> {
    fn case(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let simulation = run_no_case(seed, None)?;
        Ok(vec![(
            "m4b::clen_vznikne",
            check_clen_jeden_seed(&simulation),
        )])
    }
    fn exaptation_batch(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let (target, control) = run_exaptation_pair(seed)?;
        Ok(vec![("m4b::exaptace", check_exaptace(&target, &control))])
    }
    fn tenseless(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let (first, second) = run_tenseless_pair(seed)?;
        Ok(vec![(
            "m4b::jazyk_bez_kategorie",
            check_jazyk_bez_kategorie(&first, &second),
        )])
    }
    vec![
        Batch {
            id: "m4b_no_case",
            gates: &["m4b::clen_vznikne"],
            run: Runner::Single(case),
        },
        Batch {
            id: "m4b_exaptation",
            gates: &["m4b::exaptace"],
            run: Runner::Single(exaptation_batch),
        },
        Batch {
            id: "m4b_tenseless",
            gates: &["m4b::jazyk_bez_kategorie"],
            run: Runner::Single(tenseless),
        },
    ]
}
