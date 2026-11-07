//! Vektory z Pythonu (`scripts/export_v2_rust_vectors.py`): náhoda, numpy generátor,
//! tabulka hlásek a parametry. Ověřují, že Rust dává stejná čísla jako referenční Python.
//! (Protojazyk už Python nezrcadlí: dok. 25, `tests/protoform.rs`.)

use cee_engine::legacy_numpy::Pcg64;
use cee_engine::parameters::Parameters;
use cee_engine::rng::{hash_poisson, stable_id, stable_int, Part, Stream};
use cee_engine::segments::SegmentTable;
use serde_json::Value;

fn fixture(name: &str) -> Value {
    let path = format!("{}/tests/fixtures/{name}.json", env!("CARGO_MANIFEST_DIR"));
    serde_json::from_str(&std::fs::read_to_string(path).expect("fixture")).expect("JSON")
}

fn parts_of(value: &Value) -> Vec<Part<'_>> {
    value
        .as_array()
        .expect("pole")
        .iter()
        .map(|item| match item {
            Value::String(text) => Part::Str(text),
            Value::Number(n) if n.is_f64() => Part::Float(n.as_f64().unwrap()),
            Value::Number(n) => Part::Int(n.as_i64().expect("celé číslo")),
            other => panic!("neznámá část {other}"),
        })
        .collect()
}

fn text_u64(value: &Value) -> u64 {
    value.as_str().expect("text").parse().expect("u64")
}

#[test]
fn stable_int_a_id() {
    let data = fixture("rng");
    for case in data["stable_int"].as_array().unwrap() {
        let parts = parts_of(&case["parts"]);
        assert_eq!(
            stable_int(&parts),
            text_u64(&case["value"]),
            "části {}",
            case["parts"]
        );
    }
    for case in data["stable_id"].as_array().unwrap() {
        let parts = parts_of(&case["parts"]);
        assert_eq!(
            stable_id(case["prefix"].as_str().unwrap(), &parts),
            case["value"].as_str().unwrap()
        );
    }
}

#[test]
fn proudy_nahody() {
    let data = fixture("rng");
    for case in data["streams"].as_array().unwrap() {
        let parts = parts_of(&case["parts"]);
        let mut stream = Stream::new(text_u64(&case["seed"]), &parts);
        assert_eq!(stream.state, text_u64(&case["key"]));
        for expected in case["u64"].as_array().unwrap() {
            assert_eq!(stream.next_u64(), text_u64(expected));
        }
        for expected in case["random"].as_array().unwrap() {
            assert_eq!(stream.random(), expected.as_f64().unwrap());
        }
        for (n, expected) in [1_u64, 2, 7, 1000, 1 << 40, 3, 5]
            .iter()
            .zip(case["integers"].as_array().unwrap())
        {
            assert_eq!(stream.integers(*n), expected.as_u64().unwrap());
        }
        let weights = [0.5, 0.0, 1.5, 3.0, 0.25];
        for expected in case["choice"].as_array().unwrap() {
            assert_eq!(
                stream.choice(&weights).unwrap() as u64,
                expected.as_u64().unwrap()
            );
        }
        for expected in case["normal"].as_array().unwrap() {
            let found = stream.normal(1.0, 2.0);
            assert!(
                (found - expected.as_f64().unwrap()).abs() < 1e-12,
                "{found} vs {expected}"
            );
        }
        for (lam, expected) in [0.3, 4.0, 29.0, 31.0, 120.5, 0.0]
            .iter()
            .zip(case["poisson"].as_array().unwrap())
        {
            assert_eq!(
                stream.poisson(*lam),
                expected.as_u64().unwrap(),
                "lambda {lam}"
            );
        }
        assert_eq!(stream.state, text_u64(&case["state"]));
    }
    for case in data["hash_poisson"].as_array().unwrap() {
        let found = hash_poisson(
            text_u64(&case["row"]),
            text_u64(&case["column"]),
            case["lambda"].as_f64().unwrap(),
        );
        assert_eq!(found, case["value"].as_u64().unwrap(), "{case}");
    }
}

#[test]
fn numpy_generator() {
    for case in fixture("numpy")["cases"].as_array().unwrap() {
        let seed = text_u64(&case["seed"]);
        let parts = parts_of(&case["parts"]);
        let mut rng = Pcg64::for_parts(seed, &parts);
        let mut weights = vec![1.0, 2.0, 3.0, 0.5, 0.25, 4.0, 1.0];
        let total: f64 = weights.iter().sum();
        weights.iter_mut().for_each(|w| *w /= total);
        for expected in case["integers"].as_array().unwrap() {
            assert_eq!(rng.integers(1, 4), expected.as_i64().unwrap());
        }
        for expected in case["random"].as_array().unwrap() {
            assert_eq!(rng.random(), expected.as_f64().unwrap());
        }
        for expected in case["choice"].as_array().unwrap() {
            assert_eq!(rng.choice(&weights) as u64, expected.as_u64().unwrap());
        }
        for expected in case["integers_wide"].as_array().unwrap() {
            assert_eq!(rng.integers(0, 100), expected.as_i64().unwrap());
        }
        for expected in case["uniform"].as_array().unwrap() {
            assert_eq!(rng.uniform(-3.0, -0.2), expected.as_f64().unwrap());
        }
        for expected in case["integers_after"].as_array().unwrap() {
            assert_eq!(rng.integers(1, 4), expected.as_i64().unwrap());
        }
    }
}

fn strings(value: &Value) -> Vec<String> {
    value
        .as_array()
        .unwrap()
        .iter()
        .map(|s| s.as_str().unwrap().to_owned())
        .collect()
}

#[test]
fn tabulka_hlasek() {
    let table = SegmentTable::default_table();
    let data = fixture("segments");
    assert_eq!(table.len() as u64, data["count"].as_u64().unwrap());
    for case in data["parse"].as_array().unwrap() {
        let ipa = case["ipa"].as_str().unwrap();
        match case["form"].as_array() {
            Some(form) => {
                let expected: Vec<i32> = form.iter().map(|v| v.as_i64().unwrap() as i32).collect();
                assert_eq!(table.parse(ipa).unwrap(), expected, "rozbor {ipa}");
                assert_eq!(table.render(&expected), case["render"].as_str().unwrap());
            }
            None => assert!(table.parse(ipa).is_err(), "{ipa} má být chyba"),
        }
    }
    let mut checked = 0;
    for case in data["changed"].as_array().unwrap() {
        let changes: Vec<(String, String)> = case["changes"]
            .as_array()
            .unwrap()
            .iter()
            .map(|c| {
                (
                    c[0].as_str().unwrap().to_owned(),
                    c[1].as_str().unwrap().to_owned(),
                )
            })
            .collect();
        let request: Vec<(&str, &str)> = changes
            .iter()
            .map(|(a, b)| (a.as_str(), b.as_str()))
            .collect();
        let allow: Vec<char> = strings(&case["allow"])
            .iter()
            .filter_map(|s| s.chars().next())
            .collect();
        let found = table
            .changed(case["segment"].as_i64().unwrap() as i32, &request, &allow)
            .unwrap();
        let expected = case["result"].as_i64().map(|v| v as i32);
        assert_eq!(found, expected, "změna {} {:?}", case["ipa"], changes);
        checked += 1;
    }
    assert!(checked > 100);
}

fn numeric_equal(left: &Value, right: &Value) -> bool {
    match (left, right) {
        (Value::Number(a), Value::Number(b)) => a.as_f64() == b.as_f64(),
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && a.iter()
                    .all(|(k, v)| b.get(k).is_some_and(|w| numeric_equal(v, w)))
        }
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(x, y)| numeric_equal(x, y))
        }
        _ => left == right,
    }
}

#[test]
fn vychozi_parametry() {
    let expected = fixture("parameters");
    let found = serde_json::to_value(Parameters::default()).unwrap();
    assert!(
        numeric_equal(&found, &expected),
        "výchozí parametry se liší od Pythonu"
    );
    let overrides =
        serde_json::json!({"village_openness": 0.2, "channel_domains": {"trade": {"power": 2.0}}});
    let params = Parameters::from_overrides(overrides.as_object().unwrap()).unwrap();
    assert_eq!(params.village_openness, 0.2);
    assert_eq!(params.channel_domains["trade"]["power"], 2.0);
    assert_eq!(params.channel_domains["trade"]["culture"], 3.0);
    assert!(
        Parameters::from_overrides(serde_json::json!({"nesmysl": 1}).as_object().unwrap()).is_err()
    );
}
