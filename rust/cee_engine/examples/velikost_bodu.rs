//! Z čeho se skládá kontrolní bod: velikost částí světa a kódů skupin ve formátu postcard.
//! Části kódů se měří každá zvlášť (sdílené základy repertoárů se v nich počítají znovu).
//!
//! `cargo run --release --example velikost_bodu -- <spec.json> <rok>`

use cee_engine::spec::{self, WorldSpec};
use cee_engine::{Simulation, SimulationConfig};
fn sz<T: serde::Serialize + ?Sized>(v: &T) -> usize {
    postcard::to_stdvec(v).unwrap().len()
}
fn mb(n: usize) -> String {
    format!("{:>8.1} MB", n as f64 / 1e6)
}
fn main() {
    let text = std::fs::read_to_string(std::env::args().nth(1).unwrap()).unwrap();
    let until: f64 = std::env::args().nth(2).unwrap().parse().unwrap();
    let ws = WorldSpec::from_json(&text).unwrap();
    cee_engine::parallel::init_default(0);
    let (w, events) = spec::build(&ws).unwrap();
    let mut sim = Simulation::new(w, SimulationConfig::default(), events).unwrap();
    sim.run(until).unwrap();
    let w = &sim.world;
    let h = &sim.history;
    println!(
        "celkem bod {}",
        mb(sim.checkpoint_bytes_without_events().unwrap().len())
    );
    let mut rows: Vec<(usize, &str)> = vec![
        (sz(&w.registry), "registry"),
        (sz(&w.concepts), "concepts"),
        (sz(&w.territories), "territories"),
        (sz(&w.groups), "groups"),
        (sz(&w.links), "links"),
        (sz(&w.variables), "variables"),
        (sz(&w.variants), "variants"),
        (sz(&w.morphemes), "morphemes"),
        (sz(&w.processes), "processes"),
        (sz(&w.paradigms), "paradigms"),
        (sz(&w.form_changes), "form_changes"),
        (sz(&w.bank), "bank"),
        (sz(&w.live), "live"),
        (sz(&w.transfer), "transfer"),
        (sz(&w.sound), "sound"),
        (sz(&w.grammar), "grammar"),
        (sz(&w.society), "society"),
        (sz(&h.snapshots), "history.snapshots"),
        (sz(&h.trajectories), "history.trajectories"),
        (sz(&h.proto), "history.proto"),
    ];
    rows.sort();
    rows.reverse();
    for (n, name) in &rows {
        println!("{} {}", mb(*n), name);
    }
    // Uvnitř kódů skupin.
    let mut parts: std::collections::BTreeMap<&str, usize> = Default::default();
    for codes in &w.groups.codes {
        for c in codes {
            let p = &c.phonology;
            for (name, n) in [
                ("code.repertoire", sz(&c.repertoire)),
                ("code.acquisition", sz(&c.acquisition)),
                ("code.forms", sz(&c.forms)),
                ("forms.log", sz(&c.forms.log)),
                ("ph.vocabulary", sz(&p.vocabulary)),
                ("ph.dominant", sz(&p.dominant)),
                ("ph.uses", sz(&p.uses)),
                ("ph.dominant_log", sz(&p.dominant_log)),
                ("ph.usage_log", sz(&p.usage_log)),
                ("ph.vocabulary_log", sz(&p.vocabulary_log)),
                ("ph.grammar_log", sz(&p.grammar_log)),
                ("ph.grammar_applied_log", sz(&p.grammar_applied_log)),
                ("ph.sound", sz(&p.sound)),
                ("ph.grammar", sz(&p.grammar)),
                ("sound.lifecycle_log", sz(&p.sound.lifecycle_log)),
            ] {
                *parts.entry(name).or_default() += n;
            }
        }
    }
    let mut parts: Vec<(usize, &str)> = parts.into_iter().map(|(k, v)| (v, k)).collect();
    parts.sort();
    parts.reverse();
    println!("-- uvnitř kódů ({} skupin)", w.groups.codes.len());
    for (n, name) in parts.iter().take(16) {
        println!("{} {}", mb(*n), name);
    }
}
