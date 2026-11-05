//! M5: kontakt jazyků: S2 (ostrov a město), S3 (přechod na prestižní jazyk), výpůjčky, metrika 11.

use crate::common::assert_statistical;

/// Všechny brány milníku proti zamčeným cílovým pásmům (dokument 21), semínka od 201.
#[test]
#[ignore = "statistické brány milníku (2 000 až 3 000 let, 30 semínek)"]
fn statisticke_brany() {
    assert_statistical("m5");
}
