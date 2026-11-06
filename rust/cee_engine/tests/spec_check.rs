//! Ověření popisu světa (`spec::check`): chyby s cestou, česká zpráva, varování.

use cee_engine::spec::{self, Issue, WorldSpec};
use cee_engine::{Simulation, SimulationConfig};
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

/// Usazení a elita po regionech: v `small` mluví region `c` jazykem `a`, region `x` jazykem `b`.
fn settlement_and_elite(settlement: Value, elite: Value) -> Value {
    let mut first = json!({"kind": "settlement", "year": 50, "from": "x", "to": "c", "share": 0.25,
                           "settlements": 1});
    let mut second = json!({"kind": "elite", "year": 100, "from": "x", "seat": "c",
                            "subjects": ["c", "x"], "population": 120, "prestige": 2.0,
                            "strength": 0.6});
    for (key, value) in settlement.as_object().unwrap() {
        first[key] = value.clone();
    }
    for (key, value) in elite.as_object().unwrap() {
        second[key] = value.clone();
    }
    small(json!({"events": [first, second]}))
}

#[test]
fn usazeni_a_elita_projdou_overenim_i_behem() {
    let spec_json = settlement_and_elite(json!({}), json!({"language": "b"}));
    assert!(check(spec_json.clone()).is_empty());
    // Co ověření pustí, to se postaví a proběhne: vznikne migrace a dobytí.
    let world_spec = WorldSpec::from_json(&spec_json.to_string()).unwrap();
    let (world, events) = spec::build(&world_spec).unwrap();
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events).unwrap();
    simulation.run(120.0).unwrap();
    assert_eq!(simulation.history.of_kind("migration").count(), 1);
    assert_eq!(simulation.history.of_kind("conquest").count(), 1);
}

#[test]
fn poloostrov_s_usazenim_a_elitou_nema_chyby() {
    let text = include_str!("../../../desktop/static/projects/poloostrov.cee.json");
    let mut spec_json: Value = serde_json::from_str(text).unwrap();
    let events = spec_json["events"].as_array_mut().unwrap();
    events.insert(
        0,
        json!({"kind": "settlement", "year": 350, "from": "bal", "to": "lisk", "share": 0.25,
               "settlements": 1}),
    );
    events.insert(
        1,
        json!({"kind": "elite", "year": 525, "from": "pelna", "seat": "kaar",
               "subjects": ["kaar", "dorn"], "population": 120, "prestige": 2.0, "strength": 0.6}),
    );
    let issues = check(spec_json);
    assert!(issues.is_empty(), "{issues:?}");
}

#[test]
fn usazeni_a_elita_overi_pole() {
    let issues = check(settlement_and_elite(
        json!({"to": "nikde"}),
        json!({"language": "zz", "seat": "c"}),
    ));
    assert!(message(&issues, "events.0.to").contains("neznámý region 'nikde'"));
    assert!(message(&issues, "events.1.language").contains("neznámý jazyk elity 'zz'"));

    let issues = check(settlement_and_elite(
        json!({"from": "nikde", "share": 1.5}),
        json!({"seat": "nikde"}),
    ));
    assert!(message(&issues, "events.0.from").contains("nikde"));
    assert!(message(&issues, "events.1.seat").contains("nikde"));

    let issues = check(settlement_and_elite(
        json!({"share": 1.5}),
        json!({"subjects": ["c", "nikde"]}),
    ));
    assert!(message(&issues, "events.0.share").contains("mezi 0 a 1"));
    assert!(message(&issues, "events.1.subjects.1").contains("nikde"));

    let issues = check(settlement_and_elite(
        json!({"settlements": 0}),
        json!({"population": "hodně"}),
    ));
    assert!(message(&issues, "events.0.settlements").contains("alespoň 1"));
    assert!(message(&issues, "events.1.population").contains("číslo"));

    let issues = check(settlement_and_elite(json!({}), json!({"from": null})));
    assert!(message(&issues, "events.1.from").contains("chybí"));
    assert!(issues.iter().all(|i| i.severity == "error"));
    // Stavba běhu odmítne totéž se stejnou cestou.
    let spec_json = settlement_and_elite(json!({"to": "nikde"}), json!({}));
    let error = spec::build(&WorldSpec::from_json(&spec_json.to_string()).unwrap())
        .err()
        .unwrap();
    assert!(error.starts_with("events.0.to"), "{error}");
}

#[test]
fn elita_jazyka_ktery_v_regionu_chybi_je_varovani() {
    // Jazykem `a` v regionu `x` na začátku nikdo nemluví; může se tam dostat během běhu.
    let issues = check(settlement_and_elite(json!({}), json!({"language": "a"})));
    assert_eq!(issues.len(), 1, "{issues:?}");
    assert_eq!(issues[0].path, "events.1.language");
    assert_eq!(issues[0].severity, "warning");
}
