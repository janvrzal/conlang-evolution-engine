//! Brány milníků M1 až M6c (zrcadlo `tests/v2/test_v2_m*_gate.py`).
//!
//! Brány jsou stochastické a dlouhé (tisíce let, desítky skupin), proto jsou všechny označené
//! `#[ignore]`; spouštějí se po jednom milníku a vlákně:
//!
//! ```text
//! cargo test --release --test gates -- --ignored --test-threads=1 m3b::
//! ```
//!
//! Scénáře, semínka, prahy a metriky jsou v `cee_engine::gates` (sdílí je příkaz `cee gates`);
//! tady jsou semínka a pravidla k z N jednotlivých testů. Běh jednoho semínka se v souboru
//! milníku počítá jednou a sdílí ho všechny testy, které ho potřebují.

mod common;
mod m1;
mod m2;
mod m3;
mod m3b;
mod m4;
mod m4b;
mod m5;
mod m6a;
mod m6b;
mod m6c;

use cee_engine::gates::{batches, GATES};

/// Registr auditu je úplný: každá z 52 bran je v právě jedné dávce a žádná dávka nemá cizí bránu.
#[test]
fn registr_bran_je_uplny() {
    let all = batches();
    for gate in GATES {
        let owners = all.iter().filter(|b| b.gates.contains(&gate.id)).count();
        assert_eq!(owners, 1, "brána {} je v {owners} dávkách", gate.id);
    }
    for batch in &all {
        for gate in batch.gates {
            assert!(
                GATES.iter().any(|g| g.id == *gate),
                "dávka {} má neznámou bránu {gate}",
                batch.id
            );
        }
    }
    assert_eq!(GATES.len(), 52);
}
