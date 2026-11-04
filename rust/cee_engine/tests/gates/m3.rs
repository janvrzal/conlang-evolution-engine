//! M3: morfologie. Semínka 1 a 2 (a `1..10` pro hraniční brány), 3 000 let.

use std::sync::OnceLock;

use cee_engine::gates::m3;
use cee_engine::Simulation;

use crate::common::{assert_every, assert_k_of_n, assert_passed, cached, collect_runs};

/// Hraniční brány se vyhodnocují k z N na semínkách `1..10`.
fn runs_by_seed() -> &'static [(i64, Simulation)] {
    static CELL: OnceLock<Result<Vec<(i64, Simulation)>, String>> = OnceLock::new();
    cached(&CELL, || {
        collect_runs(1..=10, |seed| m3::run_m3(seed, true))
    })
}

/// Běhy semínek 1 a 2.
fn runs() -> &'static [(i64, Simulation)] {
    &runs_by_seed()[..2]
}

fn without_leveling() -> &'static [(i64, Simulation)] {
    static CELL: OnceLock<Result<Vec<(i64, Simulation)>, String>> = OnceLock::new();
    cached(&CELL, || {
        collect_runs(1..=2, |seed| m3::run_m3(seed, false))
    })
}

#[test]
#[ignore = "brána milníku (3 000 let, 8 vesnic)"]
fn sturtevantuv_paradox_zvuk_tvori_nepravidelnost_analogie_ji_opravuje() {
    for ((_, run), (_, unleveled)) in runs().iter().zip(without_leveling()) {
        assert_passed(&m3::check_sturtevantuv_paradox(run, unleveled));
    }
}

/// Audit 101..120: 19/20 (101..140: 35/40), N = 10, k = 4, negativní kontrola (bez `SoundChange`) 0/10.
#[test]
#[ignore = "brána milníku (3 000 let, 10 semínek)"]
fn morfologizace_vznikne_sama() {
    assert_k_of_n(runs_by_seed(), m3::check_morfologizace, 4);
}

#[test]
#[ignore = "brána milníku (3 000 let, 8 vesnic)"]
fn produktivni_vzor_se_siri_a_caste_slova_si_drzi_nepravidelnost() {
    let refs: Vec<&Simulation> = runs().iter().map(|(_, run)| run).collect();
    assert_passed(&m3::check_produktivni_vzor(&refs));
}

#[test]
#[ignore = "brána milníku (3 000 let, 8 vesnic)"]
fn analogie_zasahuje_spis_vzacna_slova() {
    assert_every(runs(), m3::check_analogie);
}

/// Audit 101..120: 20/20, N = 10, k = 5, negativní kontrola (bez `Clarity` a `FunctionalLoad`) 3/10.
#[test]
#[ignore = "brána milníku (3 000 let, 10 semínek)"]
fn zvukove_metriky_drzi_i_s_paradigmaty() {
    assert_k_of_n(runs_by_seed(), m3::check_zvukove_metriky, 5);
}

#[test]
#[ignore = "brána milníku"]
fn determinismus_s_morfologii() {
    assert_eq!(
        m3::determinism_probe().expect("běh"),
        m3::determinism_probe().expect("běh")
    );
}
