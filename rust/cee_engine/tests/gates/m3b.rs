//! M3b: lexikon a význam. Semínka 1 a 2, 3 000 let; kontrolované pokusy s erozí a tabu.

use std::collections::BTreeSet;
use std::sync::OnceLock;

use cee_engine::gates::m3b::{self, run_m3b};
use cee_engine::ids::VariableId;
use cee_engine::Simulation;

use crate::common::{assert_every, assert_k_of_n, assert_passed, cached, collect_runs, Runs};

fn runs() -> &'static [(i64, Simulation)] {
    static CELL: OnceLock<Result<Vec<(i64, Simulation)>, String>> = OnceLock::new();
    cached(&CELL, || collect_runs(1..=2, run_m3b))
}

#[test]
#[ignore = "brána milníku (3 000 let, 8 vesnic)"]
fn metrika_1_retence_zakladni_slovni_zasoby_v_pasmu() {
    assert_every(runs(), m3b::check_metrika_1);
}

#[test]
#[ignore = "brána milníku (3 000 let, 8 vesnic)"]
fn metrika_2_caste_pojmy_se_nahrazuji_pomaleji() {
    let refs: Vec<&Simulation> = runs().iter().map(|(_, run)| run).collect();
    assert_passed(&m3b::check_metrika_2(&refs));
}

#[test]
#[ignore = "brána milníku (3 000 let, 8 vesnic)"]
fn nova_slova_maji_doloditelny_puvod() {
    let refs: Vec<&Simulation> = runs().iter().map(|(_, run)| run).collect();
    assert_passed(&m3b::check_nova_slova(&refs));
}

#[test]
#[ignore = "brána milníku"]
fn erodovana_slova_se_nahrazuji_casteji() {
    let (simulation, eroded): (Simulation, BTreeSet<VariableId>) = m3b::run_eroded(7).expect("běh");
    assert_passed(&m3b::check_erodovana_slova(&simulation, &eroded));
}

/// Brána existence (otevřená otázka do M7). Audit 101..120: 11/20, N = 12, k = 1, negativní kontrola (bez tabu) 0/12.
#[test]
#[ignore = "brána milníku (2 500 let, 12 semínek, dva běhy na semínko)"]
fn tabu_vyvola_kolobeh_opisu() {
    static CELL: Runs<(BTreeSet<String>, BTreeSet<String>)> = OnceLock::new();
    let runs = cached(&CELL, || collect_runs(1..=12, m3b::run_taboo_pair));
    assert_k_of_n(runs, |pair| m3b::check_tabu(&pair.0, &pair.1), 1);
}

#[test]
#[ignore = "brána milníku (3 000 let, 8 vesnic)"]
fn zvukove_metriky_drzi_i_s_lexikalni_zmenou() {
    assert_every(runs(), m3b::check_zvukove_metriky);
}

#[test]
#[ignore = "brána milníku"]
fn determinismus_s_vyznamem() {
    assert_eq!(
        m3b::determinism_digest().expect("běh"),
        m3b::determinism_digest().expect("běh")
    );
}
