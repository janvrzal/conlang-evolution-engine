//! M4: syntax a gramatikalizace. Kontrolované pokusy: oslabená koncovka nebo záporka.

use cee_engine::gates::m4;

use crate::common::assert_statistical;

#[test]
#[ignore = "brána milníku"]
fn determinismus_se_syntaxi() {
    assert_eq!(
        m4::determinism_digest().expect("běh"),
        m4::determinism_digest().expect("běh")
    );
}

/// Všechny brány milníku proti zamčeným cílovým pásmům (dokument 21), semínka od 201.
#[test]
#[ignore = "statistické brány milníku (1 500 až 3 000 let, 30 semínek)"]
fn statisticke_brany() {
    assert_statistical("m4");
}
