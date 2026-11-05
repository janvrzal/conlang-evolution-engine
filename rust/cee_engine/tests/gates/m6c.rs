//! M6c: strom jazyků. Rozpad se známou historií: v roce 300 se oddělí C, v roce 1800 A a B.

use crate::common::assert_statistical;

/// Všechny brány milníku proti zamčeným cílovým pásmům (dokument 21), semínka od 201.
#[test]
#[ignore = "statistické brány milníku (4 000 let, 20 semínek)"]
fn statisticke_brany() {
    assert_statistical("m6c");
}
