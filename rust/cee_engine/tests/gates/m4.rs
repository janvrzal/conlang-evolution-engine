//! M4: syntax a gramatikalizace. Kontrolované pokusy: oslabená koncovka nebo záporka.

use std::sync::OnceLock;

use cee_engine::gates::m4::{self, BigCycle};
use cee_engine::Simulation;

use crate::common::{assert_k_of_n, assert_passed, cached, collect_runs};

fn control() -> &'static Simulation {
    static CELL: OnceLock<Result<Simulation, String>> = OnceLock::new();
    cached(&CELL, || m4::run_control(3))
}

#[test]
#[ignore = "brána milníku (1 500 let, 6 vesnic)"]
fn analytizace_po_erozi_padu_se_ustali_slovosled() {
    let eroded = m4::run_obj_eroded(3).expect("běh");
    assert_passed(&m4::check_analytizace(&eroded, control()));
}

/// Audit 101..120: 15/20, N = 10, k = 2, negativní kontrola (bez eroze `PAST`) 0/10.
#[test]
#[ignore = "brána milníku (2 500 let, 10 semínek)"]
fn velky_cyklus_eroze_opis_priklonka_nova_koncovka() {
    static CELL: OnceLock<Result<Vec<(i64, BigCycle)>, String>> = OnceLock::new();
    let runs = cached(&CELL, || collect_runs(1..=10, m4::run_velky_cyklus));
    assert_k_of_n(runs, m4::check_velky_cyklus, 2);
}

/// Audit 101..120: 8/20, N = 19, k = 1, negativní kontrola (bez oslabení záporky) 0/19. Poznámka do M7:
/// ověřit, zda má `embraced` dosáhnout `established` dřív, než ho `post` vytlačí.
#[test]
#[ignore = "brána milníku (3 000 let, 19 semínek)"]
fn jespersenuv_cyklus_ne_ne_pas_pas() {
    static CELL: OnceLock<Result<Vec<(i64, Simulation)>, String>> = OnceLock::new();
    let runs = cached(&CELL, || collect_runs(1..=19, m4::run_jespersen));
    assert_k_of_n(runs, m4::check_jespersenuv_cyklus, 1);
}

#[test]
#[ignore = "brána milníku (1 500 let, 6 vesnic)"]
fn bez_eroze_syntax_zustava_a_zvukove_metriky_drzi() {
    assert_passed(&m4::check_bez_eroze(control()));
}

#[test]
#[ignore = "brána milníku"]
fn determinismus_se_syntaxi() {
    assert_eq!(
        m4::determinism_digest().expect("běh"),
        m4::determinism_digest().expect("běh")
    );
}
