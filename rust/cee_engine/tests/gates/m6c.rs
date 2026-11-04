//! M6c: strom jazyků. Rozpad se známou historií: v roce 300 se oddělí C, v roce 1800 A a B.

use std::sync::OnceLock;

use cee_engine::gates::m6c;
use cee_engine::Simulation;

use crate::common::{assert_every, cached, collect_runs};

fn runs() -> &'static [(i64, Simulation)] {
    static CELL: OnceLock<Result<Vec<(i64, Simulation)>, String>> = OnceLock::new();
    cached(&CELL, || collect_runs(1..=2, m6c::run_known_tree))
}

#[test]
#[ignore = "brána milníku (4 000 let, 9 vesnic)"]
fn strom_jazyku_odpovida_historii_rozpadu() {
    assert_every(runs(), m6c::check_strom_odpovida);
}

#[test]
#[ignore = "brána milníku (4 000 let, 9 vesnic)"]
fn strom_je_stabilni() {
    assert_every(runs(), m6c::check_strom_stabilni);
}
