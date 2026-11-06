//! Ověření popisu světa (`spec::check`): chyby s cestou, česká zpráva, varování.

use cee_engine::spec::{self, Issue, WorldSpec};
use serde_json::{json, Value};

fn small(extra: Value) -> Value {
    let mut spec = json!({
        "end_year": 200,
        "languages": [{"id": "a"}, {"id": "b", "grammar": "substrate"}],
        "regions": [
            {"id": "c", "position": [0, 0], "density": 2, "neighbours": ["x"], "language": "a", "villages": 3},
            {"id": "x", "position": [60, 0], "neighbours": ["c"], "language": "b", "villages": 3,
             "terrain": "hills", "identity": "distinct"},
        ],
        "events": [{"kind": "state", "year": 0, "id": "k", "regions": ["c", "x"], "capital": "c"}],
        "semantics": false,
    });
    for (key, value) in extra.as_object().unwrap() {
        spec[key] = value.clone();
    }
    spec
}

fn check(spec: Value) -> Vec<Issue> {
    spec::check(&WorldSpec::from_json(&spec.to_string()).unwrap())
}

fn message<'a>(issues: &'a [Issue], path: &str) -> &'a str {
    &issues
        .iter()
        .find(|i| i.path == path)
        .unwrap_or_else(|| panic!("chybí {path}: {issues:?}"))
        .message
}

#[test]
fn platny_popis_nema_chyby() {
    assert!(check(small(json!({}))).is_empty());
    let example = include_str!("../../../src/cee/data/v2_example_world.json");
    assert!(spec::check(&WorldSpec::from_json(example).unwrap()).is_empty());
}

#[test]
fn chyby_udalosti_maji_cestu_a_ceskou_zpravu() {
    let issues = check(small(json!({"events": [
        {"kind": "state", "year": 0, "id": "k", "regions": ["c", "x"], "capital": "c", "policy": "brutal"},
        {"kind": "collapse", "year": 50, "state": "nikdo"},
        {"kind": "standard", "year": 900, "of": "k"},
    ]})));
    assert!(message(&issues, "events.0").contains("jazyková politika"));
    assert!(message(&issues, "events.1").contains("neexistuje"));
    assert!(message(&issues, "events.2.year").contains("mimo"));
    assert!(issues.iter().all(|i| i.severity == "error"));
}

#[test]
fn udalosti_se_zkousi_v_poradi_roku() {
    let late = json!({"events": [
        {"kind": "collapse", "year": 100, "state": "k"},
        {"kind": "state", "year": 50, "id": "k", "regions": ["c", "x"], "capital": "c"},
    ]});
    assert!(check(small(late)).is_empty());
}

#[test]
fn vlastni_slova_se_overi() {
    let issues = check(small(json!({"languages": [
        {"id": "a", "words": {"xyz": "ka", "fire": "ʬ", "hand": " ", "eye": "kʷá", "ear": "ɐɾʡ"}},
        {"id": "b"},
    ]})));
    assert!(message(&issues, "languages.0.words.xyz").contains("neznámý pojem"));
    assert!(message(&issues, "languages.0.words.fire").contains("hlásku"));
    assert!(message(&issues, "languages.0.words.hand").contains("prázdné"));
    assert!(issues.iter().all(|i| i.path != "languages.0.words.eye"));
    assert!(issues.iter().all(|i| i.path != "languages.0.words.ear"));
}

#[test]
fn slabicna_stavba_se_overi() {
    let ok = check(small(json!({"languages": [
        {"id": "a", "syllables": "complex"}, {"id": "b", "syllables": "simple"},
    ]})));
    assert!(ok.is_empty(), "{ok:?}");
    let issues = check(small(json!({"languages": [
        {"id": "a", "syllables": "CVC"}, {"id": "b"},
    ]})));
    assert!(message(&issues, "languages.0.syllables").contains("slabičná stavba"));
}

#[test]
fn parametry_slovnik_a_varovani() {
    let issues = check(small(json!({"parameters": {"nic": 1}})));
    assert_eq!(issues[0].path, "parameters.nic");
    let issues = check(small(json!({"vocabulary": 200, "background": "zzz"})));
    assert_eq!(issues[0].path, "background");
    let warning = issues.iter().find(|i| i.path == "vocabulary").unwrap();
    assert_eq!(warning.severity, "warning");
    let issues = check(small(json!({"concepts": [{"id": "hand"}]})));
    assert_eq!(issues[0].path, "concepts.0.id");
    let issues = check(small(
        json!({"concepts": [{"id": "novy", "related": [{"concept": "hand"}]}], "semantics": true}),
    ));
    assert!(!issues.iter().any(|i| i.path == "semantics"));
    let issues = check(small(
        json!({"concepts": [{"id": "novy", "related": [{"concept": "hand"}]}], "semantics": false}),
    ));
    assert!(issues
        .iter()
        .any(|i| i.path == "semantics" && i.severity == "warning"));
}

#[test]
fn neznamy_region_a_protojazyk() {
    let issues = check(small(
        json!({"regions": [{"id": "c", "position": [0, 0], "language": "q"}]}),
    ));
    assert_eq!(issues[0].path, "regions");
    let issues = check(small(json!({"events": [
        {"kind": "state", "year": 0, "id": "k", "regions": ["c", "zz"], "capital": "c"}]})));
    assert!(message(&issues, "events.0").contains("zz"));
}
