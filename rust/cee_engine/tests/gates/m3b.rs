//! M3b: lexikon a význam. Semínka 1 a 2, 3 000 let; kontrolované pokusy s erozí a tabu.

use cee_engine::gates::m3b;

use crate::common::assert_statistical;

#[test]
#[ignore = "brána milníku"]
fn determinismus_s_vyznamem() {
    assert_eq!(
        m3b::determinism_digest().expect("běh"),
        m3b::determinism_digest().expect("běh")
    );
}

/// Všechny brány milníku proti zamčeným cílovým pásmům (dokument 21), semínka od 201.
#[test]
#[ignore = "statistické brány milníku (3 000 let, 30 semínek)"]
fn statisticke_brany() {
    assert_statistical("m3b");
}
