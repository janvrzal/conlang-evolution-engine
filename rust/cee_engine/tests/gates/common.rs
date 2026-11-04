//! Společné pomůcky testů bran: sdílené běhy, kontrola reportů a k z N přes semínka.

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::OnceLock;

use cee_engine::gates::stats::{evaluate_seeds, Evaluation};
use cee_engine::gates::Report;

/// Sdílené běhy řady semínek.
pub type Runs<T> = OnceLock<Result<Vec<(i64, T)>, String>>;

/// Úspěch, nebo hláška s neúspěšnými metrikami.
pub fn assert_passed(report: &Report) {
    assert!(report.passed(), "Brána neprošla:\n{}", report.failures());
}

/// Hodnota spočtená jednou pro všechny testy souboru; chyba nebo pád enginu se zapamatuje, takže
/// se těžký běh při selhání neopakuje v každém testu.
pub fn cached<T: Send + Sync>(
    cell: &'static OnceLock<Result<T, String>>,
    init: impl FnOnce() -> Result<T, String>,
) -> &'static T {
    let result = cell.get_or_init(|| match catch_unwind(AssertUnwindSafe(init)) {
        Ok(result) => result,
        Err(payload) => Err(format!(
            "pád enginu: {}",
            payload
                .downcast_ref::<String>()
                .cloned()
                .or_else(|| payload.downcast_ref::<&str>().map(|s| (*s).to_owned()))
                .unwrap_or_default()
        )),
    });
    result.as_ref().unwrap_or_else(|error| panic!("{error}"))
}

/// Běhy pro řadu semínek: `(semínko, běh)`.
pub fn collect_runs<T>(
    seeds: impl IntoIterator<Item = i64>,
    run: impl Fn(i64) -> Result<T, String>,
) -> Result<Vec<(i64, T)>, String> {
    seeds
        .into_iter()
        .map(|seed| {
            run(seed)
                .map(|data| (seed, data))
                .map_err(|e| format!("semínko {seed}: {e}"))
        })
        .collect()
}

/// Brána prošla na každém semínku.
pub fn assert_every<T>(runs: &[(i64, T)], check: impl Fn(&T) -> Report) {
    let evaluation = evaluate_seeds(runs, check);
    assert!(
        evaluation.ok(runs.len()),
        "{}",
        evaluation.message(runs.len())
    );
}

/// Brána prošla aspoň na `k` semínkách (pravidlo k z N podle Wilsona).
pub fn assert_k_of_n<T>(runs: &[(i64, T)], check: impl Fn(&T) -> Report, k: usize) {
    let evaluation: Evaluation = evaluate_seeds(runs, check);
    assert!(evaluation.ok(k), "{}", evaluation.message(k));
}
