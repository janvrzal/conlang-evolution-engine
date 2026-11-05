//! M6a: instituce a diglosie: S4 (písmo v roce 500, škola a tisk v roce 1500).

use cee_engine::gates::m6a;

use crate::common::assert_statistical;

#[test]
#[ignore = "brána milníku"]
fn determinismus_s_pismem() {
    assert_eq!(
        m6a::determinism_digest().expect("běh"),
        m6a::determinism_digest().expect("běh")
    );
}

/// Všechny brány milníku proti zamčeným cílovým pásmům (dokument 21), semínka od 201.
#[test]
#[ignore = "statistické brány milníku (2 500 let, 30 semínek)"]
fn statisticke_brany() {
    assert_statistical("m6a");
}
