//! M6a: instituce a diglosie: S4 (písmo v roce 500, škola a tisk v roce 1500).

use std::sync::OnceLock;

use cee_engine::gates::m6a::{self, Codified, Courses};

use crate::common::{assert_every, assert_passed, cached, collect_runs};

fn runs() -> &'static [(i64, Courses)] {
    static CELL: OnceLock<Result<Vec<(i64, Courses)>, String>> = OnceLock::new();
    cached(&CELL, || collect_runs(1..=2, m6a::run_diglossia_courses))
}

#[test]
#[ignore = "brána milníku (2 500 let, tři scénáře na semínko)"]
fn s4_rozdil_roste_do_skoly_pak_se_zmensuje() {
    assert_every(runs(), m6a::check_s4_skola);
}

#[test]
#[ignore = "brána milníku (2 500 let, tři scénáře na semínko)"]
fn s4_bez_skoly_rozdil_roste_dal() {
    assert_every(runs(), m6a::check_s4_bez_skoly);
}

#[test]
#[ignore = "brána milníku (2 500 let, tři scénáře na semínko)"]
fn skola_sjednoti_dialekty_ale_jazyk_se_meni_dal() {
    assert_every(runs(), m6a::check_skola_sjednoti);
}

/// Kontrafaktuál: masová škola bez tisku drží řeč u jazyka z doby kodifikace.
#[test]
#[ignore = "brána milníku (2 500 let, tři scénáře na semínko)"]
fn skola_se_zmrazenou_normou_zmenu_zastavi() {
    assert_every(runs(), m6a::check_skola_zmrazena);
}

#[test]
#[ignore = "brána milníku"]
fn psany_kod_bez_tisku_stoji() {
    let run: Codified = m6a::run_codification(4).expect("běh");
    assert_passed(&m6a::check_psany_kod_bez_tisku_stoji(&run));
}

#[test]
#[ignore = "brána milníku"]
fn determinismus_s_pismem() {
    assert_eq!(
        m6a::determinism_digest().expect("běh"),
        m6a::determinism_digest().expect("běh")
    );
}
