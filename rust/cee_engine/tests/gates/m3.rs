//! M3: morfologie. Semínka 1 a 2 (a `1..10` pro hraniční brány), 3 000 let.

use cee_engine::gates::m3;

use crate::common::assert_statistical;

#[test]
#[ignore = "brána milníku"]
fn determinismus_s_morfologii() {
    assert_eq!(
        m3::determinism_probe().expect("běh"),
        m3::determinism_probe().expect("běh")
    );
}

/// Všechny brány milníku proti zamčeným cílovým pásmům (dokument 21), semínka od 201.
#[test]
#[ignore = "statistické brány milníku (3 000 let, 30 semínek)"]
fn statisticke_brany() {
    assert_statistical("m3");
}
