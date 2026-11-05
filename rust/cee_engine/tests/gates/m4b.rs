//! M4b: modulární gramatika: člen z ukazovacího zájmena, exaptace, jazyk bez kategorie.

use cee_engine::gates::m4b;
use cee_engine::parameters::Parameters;

use crate::common::assert_statistical;

/// Negativní kontrola: bez mechanismů vzniku (opis, exaptace) člen nevznikne.
#[test]
#[ignore = "brána milníku (3 000 let, 5 semínek)"]
fn bez_opisu_a_exaptace_clen_nevznikne() {
    let off = Parameters {
        change_rates: [
            ("periphrasis".to_owned(), 0.0),
            ("exaptation".to_owned(), 0.0),
        ]
        .into_iter()
        .collect(),
        ..Parameters::default()
    };
    for seed in 1..=5 {
        let simulation = m4b::run_no_case(seed, Some(off.clone())).expect("běh");
        let (report, article) = m4b::check_clen_invariants(&simulation);
        assert!(report.passed(), "semínko {seed}:\n{}", report.failures());
        assert!(!article, "semínko {seed}: člen vznikl bez opisu a exaptace");
    }
}

#[test]
#[ignore = "brána milníku"]
fn determinismus_s_profilem() {
    assert_eq!(
        m4b::determinism_digest().expect("běh"),
        m4b::determinism_digest().expect("běh")
    );
}

/// Všechny brány milníku proti zamčeným cílovým pásmům (dokument 21), semínka od 201.
#[test]
#[ignore = "statistické brány milníku (3 000 let, až 50 semínek)"]
fn statisticke_brany() {
    assert_statistical("m4b");
}
