//! Společné pomůcky testů bran.

use cee_engine::gates::statistical::{render, run_rows, ReportOptions};

/// První semínko statistických bran (jako `cee gates`).
pub const START_SEED: i64 = 201;

/// Všechny brány s prefixem `milestone` (`m3` nebere `m3b`) projdou proti cílovým pásmům.
pub fn assert_statistical(milestone: &str) {
    let rows = run_rows(&ReportOptions {
        start: START_SEED,
        only: vec![milestone.to_owned()],
        jsonl: None,
    })
    .unwrap_or_else(|error| panic!("{error}"));
    assert!(!rows.is_empty(), "milník {milestone} nemá žádnou bránu");
    let failed: Vec<_> = rows.iter().filter(|row| !row.passed).cloned().collect();
    assert!(
        failed.is_empty(),
        "Neprošlo {} z {} veličin:\n{}",
        failed.len(),
        rows.len(),
        render(&failed)
    );
}
