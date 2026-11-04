//! M5: kontakt jazyků: S2 (ostrov a město), S3 (přechod na prestižní jazyk), výpůjčky, metrika 11.

use std::sync::OnceLock;

use cee_engine::gates::m5::{self, Places, Shifted};
use cee_engine::Simulation;

use crate::common::{assert_every, assert_k_of_n, cached, collect_runs};

const SEEDS: [i64; 2] = [1, 2];

#[test]
#[ignore = "brána milníku (2 000 let)"]
fn s2_mesto_s_pristehovalci_zjednodusuje_ostrov_drzi() {
    let runs = collect_runs(SEEDS, m5::run_s2_city).expect("běh");
    assert_every(&runs, m5::check_s2_mesto);
}

#[test]
#[ignore = "brána milníku (2 000 let, dva běhy na semínko)"]
fn s2_zjednoduseni_pusobi_l2_mluvci() {
    let runs = collect_runs(SEEDS, m5::run_s2_l2_pair).expect("běh");
    assert_every(&runs, |pair| m5::check_s2_l2(&pair.0, &pair.1));
}

fn shifted() -> &'static [(i64, Shifted)] {
    static CELL: OnceLock<Result<Vec<(i64, Shifted)>, String>> = OnceLock::new();
    cached(&CELL, || collect_runs(1..=12, m5::run_shifted))
}

#[test]
#[ignore = "brána milníku (4 000 let, 12 semínek)"]
fn s3_region_prejde_na_prestizni_jazyk() {
    assert_every(&shifted()[..2], |run| m5::check_s3_prechod(&run.simulation));
}

/// Brána existence (otevřená otázka do M7). Audit 101..120: 11/20, N = 12, k = 1, negativní kontrola
/// (`INTERFERENCE_WEIGHT = 0`) 0/12.
#[test]
#[ignore = "brána milníku (4 000 let, 12 semínek)"]
fn s3_v_novem_jazyce_zustane_stavba_a_vyslovnost_ale_malo_slov() {
    assert_k_of_n(shifted(), m5::check_s3_substrat, 1);
}

fn borrowing() -> &'static [(i64, Simulation)] {
    static CELL: OnceLock<Result<Vec<(i64, Simulation)>, String>> = OnceLock::new();
    cached(&CELL, || collect_runs(SEEDS, m5::run_borrowing))
}

#[test]
#[ignore = "brána milníku (2 000 let)"]
fn vypujcky_jsou_vzacne_pojmy_adaptovane_hlaskami_prijemce() {
    assert_every(borrowing(), m5::check_vypujcky);
}

#[test]
#[ignore = "brána milníku (2 000 let)"]
fn bez_dvojjazycnosti_se_stavba_nepujcuje() {
    assert_every(borrowing(), m5::check_bez_dvojjazycnosti);
}

#[test]
#[ignore = "brána milníku (1 500 let, 20 míst)"]
fn metrika_11_slozitost_klesa_s_l2_mluvcimi_a_populaci() {
    let runs: Vec<(i64, (Simulation, Places))> =
        collect_runs(SEEDS, m5::run_metrika_11).expect("běh");
    assert_every(&runs, |run| m5::check_metrika_11(&run.0, &run.1));
}
