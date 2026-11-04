//! M4b: modulární gramatika: člen z ukazovacího zájmena, exaptace, jazyk bez kategorie.

use std::sync::OnceLock;

use cee_engine::gates::m4b::{self, ARTICLE_SEEDS};
use cee_engine::parameters::Parameters;
use cee_engine::Simulation;

use crate::common::{assert_k_of_n, assert_passed, cached, collect_runs, Runs};

/// Slovosled bez pádu se ověřuje na původních semínkách (robustní, 30/30).
const ORDER_SEEDS: usize = 3;

fn no_case() -> &'static [(i64, Simulation)] {
    static CELL: OnceLock<Result<Vec<(i64, Simulation)>, String>> = OnceLock::new();
    cached(&CELL, || {
        collect_runs(ARTICLE_SEEDS, |seed| m4b::run_no_case(seed, None))
    })
}

/// Člen není univerzála (WALS 37A): za 3 000 let bez kontaktu vznikne v některých jazycích,
/// ne ve všech. Invarianty (zdroj členu, buňka DEF) musí platit u každého semínka.
#[test]
#[ignore = "brána milníku (3 000 let, 50 semínek)"]
fn clen_vznikne_z_ukazovaciho_zajmena() {
    let mut with_article = 0;
    for (seed, simulation) in no_case() {
        let (report, article) = m4b::check_clen_invariants(simulation);
        assert!(report.passed(), "semínko {seed}:\n{}", report.failures());
        with_article += usize::from(article);
    }
    let total = no_case().len();
    assert!(
        (1..total).contains(&with_article),
        "člen ve {with_article} z {total} jazyků"
    );
}

/// Negativní kontrola: bez mechanismů vzniku (opis, exaptace) člen nevznikne.
#[test]
#[ignore = "brána milníku (3 000 let, 5 semínek)"]
fn bez_opisu_a_exaptace_clen_nevznikne() {
    let off = Parameters {
        change_rates: [
            ("periphrasis".to_owned(), 0.0),
            ("exaptation".to_owned(), 0.0),
        ]
        .into_iter()
        .collect(),
        ..Parameters::default()
    };
    for seed in 1..=5 {
        let simulation = m4b::run_no_case(seed, Some(off.clone())).expect("běh");
        let (report, article) = m4b::check_clen_invariants(&simulation);
        assert!(report.passed(), "semínko {seed}:\n{}", report.failures());
        assert!(!article, "semínko {seed}: člen vznikl bez opisu a exaptace");
    }
}

#[test]
#[ignore = "brána milníku (3 000 let, 50 semínek)"]
fn bez_padu_se_slovosled_ustali() {
    for (_, simulation) in &no_case()[..ORDER_SEEDS] {
        assert_passed(&m4b::check_bez_padu(simulation));
    }
}

/// Pád vedle pevného slovosledu nic nenese; jeho koncovka se stane členem. Audit 101..120: 15/20,
/// N = 10, k = 2, negativní kontrola (volný slovosled) 0/10.
#[test]
#[ignore = "brána milníku (1 500 let, 10 semínek, dva běhy na semínko)"]
fn exaptace_zbytkove_koncovky() {
    static CELL: Runs<(Simulation, Simulation)> = OnceLock::new();
    let runs = cached(&CELL, || collect_runs(1..=10, m4b::run_exaptation_pair));
    assert_k_of_n(runs, |pair| m4b::check_exaptace(&pair.0, &pair.1), 2);
}

#[test]
#[ignore = "brána milníku"]
fn jazyk_bez_kategorie_ji_nema_dokud_ji_nevyvine() {
    let (tenseless, zero) = m4b::run_tenseless_pair(3).expect("běh");
    assert_passed(&m4b::check_jazyk_bez_kategorie(&tenseless, &zero));
}

#[test]
#[ignore = "brána milníku"]
fn determinismus_s_profilem() {
    assert_eq!(
        m4b::determinism_digest().expect("běh"),
        m4b::determinism_digest().expect("běh")
    );
}
