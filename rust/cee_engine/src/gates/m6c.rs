//! Brána M6c (`test_v2_m6c_gate.py`): strom jazyků. Rozpad se známou historií: řada devíti
//! vesnic, v roce 300 se oddělí C, v roce 1800 A a B. Pozorovaný strom má vyjít ((A, B), C),
//! bez kmitání.

use std::collections::BTreeSet;

use serde_json::Value;

use super::{Batch, Cmp, Report, Runner};
use crate::export::lineages;
use crate::scenarios::known_tree;
use crate::{Simulation, SimulationConfig};

pub fn run_known_tree(seed: i64) -> Result<Simulation, String> {
    let (world, events) = known_tree(seed, 300.0, 1800.0)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    simulation.run(4000.0)?;
    Ok(simulation)
}

/// První písmena jmen skupin (vesnice téhož shluku A, B, C mají stejné písmeno).
fn cluster<'a>(groups: impl Iterator<Item = &'a str>) -> BTreeSet<char> {
    groups.filter_map(|g| g.chars().next()).collect()
}

fn event_groups(event: &serde_json::Map<String, Value>) -> BTreeSet<char> {
    cluster(
        event
            .get("groups")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_str),
    )
}

pub fn check_strom_odpovida(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let history = &simulation.history;
    let splits: Vec<_> = history.of_kind("language_split").collect();
    let clusters: Vec<BTreeSet<char>> = splits.iter().map(|e| event_groups(e)).collect();
    let single = |c: char| BTreeSet::from([c]);
    report.flag(
        "rozštěpení: nejdřív C, potom B nebo A",
        clusters == [single('c'), single('b')] || clusters == [single('c'), single('a')],
    );
    let (Some(first), Some(second)) = (splits.first(), splits.get(1)) else {
        report.missing("dvě rozštěpení jazyka");
        return report;
    };
    let year = |e: &serde_json::Map<String, Value>| {
        e.get("year").and_then(Value::as_f64).unwrap_or(f64::NAN)
    };
    report.check("rok prvního rozštěpení", year(first), Cmp::Gt, 300.0);
    report.check("rok druhého rozštěpení", year(second), Cmp::Gt, 1800.0);
    let tree = lineages(simulation);
    let root = first.get("parent").and_then(Value::as_str);
    let root_item = tree
        .iter()
        .find(|item| item.get("id").and_then(Value::as_str) == root);
    report.flag(
        "kořen stromu nemá rodiče",
        root_item.is_some_and(|item| item.get("parent").is_some_and(Value::is_null)),
    );
    report.flag(
        "druhé rozštěpení vychází z téže linie",
        root.is_some() && second.get("parent").and_then(Value::as_str) == root,
    );
    let mut final_languages: Vec<String> = history
        .snapshots
        .last()
        .map(|s| {
            s.languages
                .values()
                .map(|groups| {
                    cluster(groups.iter().map(String::as_str))
                        .into_iter()
                        .collect()
                })
                .collect()
        })
        .unwrap_or_default();
    final_languages.sort();
    report.flag(
        "na konci jsou jazyky a, b a c",
        final_languages == ["a", "b", "c"],
    );
    report
}

pub fn check_strom_stabilni(simulation: &Simulation) -> Report {
    let mut report = Report::new();
    let history = &simulation.history;
    report.check(
        "počet rozštěpení",
        history.of_kind("language_split").count() as f64,
        Cmp::Eq,
        2.0,
    );
    report.check(
        "zaniklé jazyky",
        history.of_kind("language_ended").count() as f64,
        Cmp::Eq,
        0.0,
    );
    report.check(
        "vzniklé jazyky",
        history.of_kind("language_emerged").count() as f64,
        Cmp::Eq,
        1.0,
    );
    report
}

pub fn batches() -> Vec<Batch> {
    fn tree(seed: i64) -> Result<Vec<(&'static str, Report)>, String> {
        let simulation = run_known_tree(seed)?;
        Ok(vec![
            ("m6c::strom_odpovida", check_strom_odpovida(&simulation)),
            ("m6c::strom_stabilni", check_strom_stabilni(&simulation)),
        ])
    }
    vec![Batch {
        id: "m6c_known_tree",
        gates: &["m6c::strom_odpovida", "m6c::strom_stabilni"],
        run: Runner::Single(tree),
    }]
}
