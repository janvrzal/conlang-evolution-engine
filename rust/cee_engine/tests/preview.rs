//! Náhled protojazyků bez běhu (`spec::preview`) a varianta generátoru (`LanguageSpec::variant`).

use cee_engine::spec::{self, WorldSpec};
use cee_engine::{Simulation, SimulationConfig};
use serde_json::{json, Value};

fn world(languages: Value) -> WorldSpec {
    let spec = json!({
        "end_year": 100,
        "languages": languages,
        "regions": [
            {"id": "c", "position": [0, 0], "neighbours": ["x"], "language": "a", "villages": 2},
            {"id": "x", "position": [60, 0], "neighbours": ["c"], "language": "b", "villages": 2},
        ],
        "semantics": false,
    });
    WorldSpec::from_json(&spec.to_string()).unwrap()
}

#[test]
fn nahled_je_jazyk_na_startu_behu() {
    let spec = world(
        json!([{"id": "a"}, {"id": "b", "consonants": ["p", "t", "k", "m", "n", "s"], "vowels": ["a", "i", "u"]}]),
    );
    let preview = spec::preview(&spec).unwrap();
    assert_eq!(preview.len(), 2);
    let (a, b) = (&preview[0], &preview[1]);
    assert!(a.generated_inventory && !b.generated_inventory);
    assert_eq!(b.consonants, ["p", "t", "k", "m", "n", "s"]);
    assert!(!a.consonants.is_empty() && !a.vowels.is_empty());
    assert!(["simple", "moderate", "complex"].contains(&a.syllables.as_str()));
    assert!(!a.suffixes.is_empty());
    // Tvary náhledu = tvary protojazyka v běhu.
    let (w, events) = spec::build(&spec).unwrap();
    let simulation = Simulation::new(w, SimulationConfig::default(), events).unwrap();
    assert_eq!(a.forms, simulation.history.proto["a"].forms);
    assert!(a.forms.len() > 100);
}

#[test]
fn varianta_zmeni_jen_svuj_jazyk() {
    let base = spec::preview(&world(json!([{"id": "a"}, {"id": "b"}]))).unwrap();
    let zero = spec::preview(&world(json!([{"id": "a", "variant": 0}, {"id": "b"}]))).unwrap();
    let other = spec::preview(&world(json!([{"id": "a", "variant": 1}, {"id": "b"}]))).unwrap();
    assert_eq!(
        base[0].forms, zero[0].forms,
        "varianta 0 je dosavadní jazyk"
    );
    assert_ne!(base[0].forms, other[0].forms);
    assert_ne!(base[0].consonants, other[0].consonants);
    assert_eq!(base[1].forms, other[1].forms, "druhý jazyk se nezmění");
}
