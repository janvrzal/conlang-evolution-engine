//! M6b: společnost: Séguyho zákon na mapě, superstrát, stabilní dvojjazyčnost, loajalita,
//! migrace, Fergusonova diglosie a náboženská změna.

use std::sync::OnceLock;

use cee_engine::gates::m6b::{self, Conquered, Converted, Ferguson, Loyalty};
use cee_engine::Simulation;

use crate::common::{assert_every, assert_k_of_n, assert_passed, cached, collect_runs};

const SEEDS: [i64; 2] = [1, 2];

#[test]
#[ignore = "brána milníku (2 500 let, 25 vesnic)"]
fn metrika_9_vzdalenost_roste_se_zemepisnou_zpomalene() {
    let runs = collect_runs([2, 3], m6b::run_metrika_9).expect("běh");
    assert_every(&runs, m6b::check_metrika_9);
}

fn conquered() -> &'static [(i64, Conquered)] {
    static CELL: OnceLock<Result<Vec<(i64, Conquered)>, String>> = OnceLock::new();
    cached(&CELL, || collect_runs(1..=10, m6b::run_conquered))
}

#[test]
#[ignore = "brána milníku (3 100 let, 10 semínek)"]
fn elita_v_mensine_prejde_na_jazyk_poddanych() {
    assert_every(&conquered()[..2], |run| {
        m6b::check_elita_prejde(&run.simulation)
    });
}

/// Audit 101..120: 16/20, N = 10, k = 2, negativní kontrola (bez dobytí) 0/10.
#[test]
#[ignore = "brána milníku (3 100 let, 10 semínek)"]
fn superstrat_je_hlavne_slovni() {
    assert_k_of_n(conquered(), m6b::check_superstrat, 2);
}

/// Audit 101..120: 16/20, N = 10, k = 2, negativní kontrola (`domain = "home"`) 0/10.
#[test]
#[ignore = "brána milníku (2 000 let, 10 semínek)"]
fn jazyk_trhu_jen_mimo_domov_je_stabilni_dvojjazycnost() {
    let runs: Vec<(i64, Simulation)> = collect_runs(1..=10, m6b::run_market_town).expect("běh");
    assert_k_of_n(&runs, m6b::check_jazyk_trhu, 2);
}

#[test]
#[ignore = "brána milníku (2 500 let, tři běhy)"]
fn loajalita_prechod_zpomali_nebo_zastavi() {
    let run: Loyalty = m6b::run_loyalty(1).expect("běh");
    assert_passed(&m6b::check_loajalita(&run));
}

/// Audit 101..120: 15/20, N = 10, k = 2, negativní kontrola (`migration = 0`) 0/10.
#[test]
#[ignore = "brána milníku (1 500 let, 10 semínek)"]
fn podil_l2_mluvcich_vyplyne_z_migrace_a_slozitost_klesa() {
    let runs: Vec<(i64, Simulation)> = collect_runs(1..=10, m6b::run_migration).expect("běh");
    assert_k_of_n(&runs, m6b::check_migrace, 2);
}

#[test]
#[ignore = "brána milníku (3 000 let)"]
fn fergusonova_diglosie_vysoka_varieta_stoji_lidova_rec_se_vzdaluje() {
    let runs: Vec<(i64, Ferguson)> = collect_runs(SEEDS, m6b::run_ferguson).expect("běh");
    assert_every(&runs, m6b::check_ferguson);
}

#[test]
#[ignore = "brána milníku (2 000 let, dva běhy na semínko)"]
fn nabozenstvi_prinese_ucena_slova_z_liturgickeho_jazyka() {
    let runs: Vec<(i64, Converted)> = collect_runs(SEEDS, m6b::run_conversion_pair).expect("běh");
    assert_every(&runs, m6b::check_nabozenstvi);
}
