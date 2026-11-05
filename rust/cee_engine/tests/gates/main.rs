//! Brány milníků M1 až M6c (zrcadlo `tests/v2/test_v2_m*_gate.py`).
//!
//! Každý milník má test `statisticke_brany`: všechny jeho brány na N semínkách (od 201) proti
//! zamčeným cílovým pásmům (`src/cee/data/v2_gate_targets.json`, dokument 21), stejně jako
//! `cee gates`. Vedle nich zůstaly deterministické kontroly (stejné semínko, stejný výsledek;
//! přiblížení nemění nepropojenou oblast) a negativní kontrola členu. Testy jsou dlouhé, proto
//! jsou označené `#[ignore]`:
//!
//! ```text
//! cargo test --release --test gates -- --ignored m3b::
//! ```
//!
//! Scénáře, kontroly a vyhodnocení jsou v `cee_engine::gates`; celý běh všech bran trvá asi 10 minut.

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

/// Ve víc dávkách smí být jen tyto brány (vyhodnotí se zvlášť v každé).
const SHARED: [&str; 1] = ["m2::zvukove_metriky"];

/// Registr je úplný: každá ze 47 bran je v právě jedné dávce (sdílené aspoň ve dvou) a žádná
/// dávka nemá cizí bránu.
#[test]
fn registr_bran_je_uplny() {
    let all = batches();
    for gate in GATES {
        let owners = all.iter().filter(|b| b.gates.contains(&gate.id)).count();
        if SHARED.contains(&gate.id) {
            assert!(
                owners >= 2,
                "sdílená brána {} je v {owners} dávkách",
                gate.id
            );
        } else {
            assert_eq!(owners, 1, "brána {} je v {owners} dávkách", gate.id);
        }
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
    assert_eq!(GATES.len(), 47);
}
