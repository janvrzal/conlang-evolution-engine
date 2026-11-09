//! Data běhu pro UI (dok. 36): slovník po jazycích, protojazyk, zvukové změny a analogie,
//! studijní případy, kódy hlášek a „co kdyby“ z kontrolního bodu.

use cee_engine::checkpoint::Checkpoint;
use cee_engine::export;
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{Simulation, SimulationConfig};
use serde_json::{json, Value};

fn example() -> WorldSpec {
    let text = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../src/cee/data/v2_example_world.json"
    ))
    .unwrap();
    let mut world = WorldSpec::from_json(&text).unwrap();
    world.end_year = 400.0;
    world.events.retain(|e| e.year <= 400.0);
    world.events[0].study_case = Some("Vznik státu".into());
    world
}

/// Běh do konce s kontrolním bodem v roce `at`.
fn run_with_checkpoint(world: &WorldSpec, at: f64) -> (Simulation, Checkpoint) {
    let (w, events) = spec::build(world).unwrap();
    let mut simulation = Simulation::new(w, SimulationConfig::default(), events).unwrap();
    simulation.run(at).unwrap();
    let checkpoint = simulation.checkpoint();
    simulation.run(world.end_year).unwrap();
    (simulation, checkpoint)
}

#[test]
fn export_nese_slovnik_protojazyk_a_zmeny() {
    let world = example();
    let (simulation, _) = run_with_checkpoint(&world, 200.0);
    let out = export::export(&simulation, true);

    // protojazyk: tvary pojmů jazyků popisu na startu
    let proto = out["proto_lexicon"].as_object().unwrap();
    assert_eq!(proto.len(), world.languages.len());
    for item in proto.values() {
        assert!(item["forms"].as_object().unwrap().len() > 100);
        assert!(item["group"].is_string());
    }

    // dnešní slovník po pozorovaných jazycích
    let last = simulation.history.snapshots.last().unwrap();
    let lexicon = out["lexicon_by_language"].as_object().unwrap();
    let languages: Vec<&String> = last.languages.keys().collect();
    assert_eq!(lexicon.keys().collect::<Vec<_>>(), languages);
    let first = lexicon.values().next().unwrap();
    assert!(first["forms"]["WATER"].is_string() || first["forms"].as_object().unwrap().len() > 100);

    // zvukové změny po jazycích s vesnicemi a roky
    let history = out["change_history"].as_array().unwrap();
    let sounds: Vec<&Value> = history
        .iter()
        .flat_map(|l| l["changes"].as_array().unwrap())
        .filter(|c| c["kind"] == "sound")
        .collect();
    assert!(!sounds.is_empty(), "žádná zvuková změna");
    for change in &sounds {
        assert!(change["family"].is_string(), "{change}");
        let groups = change["groups"].as_array().unwrap();
        assert!(!groups.is_empty());
        let year = change["year"].as_f64().unwrap();
        assert!(groups.iter().all(|g| g["year"].as_f64().unwrap() >= year));
    }

    // studijní případ na časové ose
    let cases: Vec<&Value> = out["events"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|e| e["kind"] == "study_case")
        .collect();
    assert_eq!(cases.len(), 1);
    assert_eq!(cases[0]["label"], "Vznik státu");
    assert_eq!(cases[0]["event_kind"], world.events[0].kind.as_str());
}

#[test]
fn co_kdyby_z_kontrolniho_bodu() {
    let world = example();
    let (full, checkpoint) = run_with_checkpoint(&world, 200.0);
    // kontrolní bod přežije uložení do bajtů
    let checkpoint = Checkpoint::from_bytes(&checkpoint.to_bytes().unwrap()).unwrap();

    // beze změny: pokračování z bodu = celý běh
    let mut same = spec::resume(&world, checkpoint.clone(), SimulationConfig::default()).unwrap();
    same.run(world.end_year).unwrap();
    assert_eq!(same.history.digest(), full.history.digest());
    assert_eq!(same.history.proto, full.history.proto);

    // změna po bodu: rok větvení, pokračování z bodu = běh od začátku
    let mut changed = world.clone();
    let later = changed.events.iter().position(|e| e.year > 200.0).unwrap();
    changed.events[later].year += 50.0;
    let branch = spec::branch_year(&world, &changed).unwrap();
    assert_eq!(branch, world.events[later].year);
    assert!(checkpoint.year < branch);
    let mut resumed = spec::resume(&changed, checkpoint, SimulationConfig::default()).unwrap();
    resumed.run(changed.end_year).unwrap();
    let (fresh, _) = run_with_checkpoint(&changed, 200.0);
    assert_eq!(resumed.history.digest(), fresh.history.digest());
    assert_ne!(resumed.history.digest(), full.history.digest());

    // změna mimo události se musí počítat od začátku
    let mut other = world.clone();
    other.seed += 1;
    assert_eq!(spec::branch_year(&world, &other), None);
    assert_eq!(spec::branch_year(&world, &world), Some(f64::INFINITY));
}

#[test]
fn hlasky_maji_kod_a_hodnoty() {
    let mut world = example();
    world.languages[0].tones = vec!["x".into()];
    world
        .events
        .push(serde_json::from_value(json!({"year": 5000, "kind": "state"})).unwrap());
    let issues = spec::check(&world);
    let tone = issues
        .iter()
        .find(|i| i.code == "tone_unknown")
        .expect("{issues:?}");
    assert_eq!(tone.args["tone"], "x");
    assert!(issues.iter().all(|i| !i.code.is_empty()));
    world.languages[0].tones.clear();
    let issues = spec::check(&world);
    assert!(
        issues.iter().any(|i| i.code == "event_year_outside"),
        "{issues:?}"
    );
}
