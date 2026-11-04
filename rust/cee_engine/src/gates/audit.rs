//! Audit bran na řadě semínek (`cee gates`; v Pythonu `scripts/v2_gate_rates.py`).
//!
//! Pro každou dávku a semínko spustí scénář, vyhodnotí brány, které z něj plynou, a nakonec
//! vypíše tabulku míry průchodu s Wilsonovým intervalem, zařazením a prahy `k` z `N`
//! (`docs/engine-v2/09-zpevneni-bran.md`). Běh, který skončí chybou nebo pádem enginu, se
//! počítá jako neúspěch semínka (text chyby je v rozpisu).

use std::collections::BTreeMap;
use std::io::Write as _;
use std::panic::{catch_unwind, AssertUnwindSafe};

use serde_json::json;

use super::stats::{classify_rate, threshold_k, wilson_interval};
use super::{batches, Batch, Report, Runner, GATES};

pub struct AuditOptions {
    pub seeds: Vec<i64>,
    /// Milník (`m4b`), dávka (`m4b_no_case`) nebo brána (`m4b::exaptace`); prázdné = všechny.
    pub only: Vec<String>,
    /// Vypsat u každého semínka všechny metriky (hodnota, práh, výsledek).
    pub metrics: bool,
    /// Průběžný zápis výsledků po řádcích (JSONL).
    pub jsonl: Option<String>,
}

/// Brána patří do výběru, když ji vybere její milník, dávka nebo ona sama.
fn wanted(only: &[String], batch: &Batch, gate: &str) -> bool {
    only.is_empty()
        || only.iter().any(|item| {
            item == gate
                || item == batch.id
                || gate
                    .strip_prefix(item.as_str())
                    .is_some_and(|rest| rest.starts_with("::"))
        })
}

/// Seznam bran: jméno, semínka dnešního testu a dávka.
pub fn list() -> String {
    let mut text = String::from("| brána | semínek dnes | dávka |\n|---|---|---|\n");
    let all = batches();
    for gate in GATES {
        let batch = all.iter().find(|b| b.gates.contains(&gate.id));
        text.push_str(&format!(
            "| {} | {} | {} |\n",
            gate.id,
            gate.seeds_today,
            batch.map_or("-", |b| b.id)
        ));
    }
    text
}

#[derive(Default)]
struct Tally {
    passed: Vec<i64>,
    failed: Vec<(i64, String)>,
}

fn panic_text(payload: &(dyn std::any::Any + Send)) -> String {
    payload
        .downcast_ref::<String>()
        .cloned()
        .or_else(|| payload.downcast_ref::<&str>().map(|s| (*s).to_owned()))
        .unwrap_or_else(|| "pád enginu".to_owned())
}

/// Spustí dávku pro jedno semínko (nebo trojici); chybu a pád promění v text.
fn execute(runner: Runner, seeds: &[i64]) -> Result<Vec<(&'static str, Report)>, String> {
    let outcome = catch_unwind(AssertUnwindSafe(|| match runner {
        Runner::Single(run) => run(seeds[0]),
        Runner::Triplet(run) => run([seeds[0], seeds[1], seeds[2]]),
    }));
    match outcome {
        Ok(result) => result,
        Err(payload) => Err(format!("pád enginu: {}", panic_text(payload.as_ref()))),
    }
}

/// Provede audit a vrátí závěrečnou tabulku (Markdown).
pub fn run(options: &AuditOptions) -> Result<String, String> {
    let mut sink = match &options.jsonl {
        Some(path) => Some(std::fs::File::create(path).map_err(|e| format!("{path}: {e}"))?),
        None => None,
    };
    let mut tally: BTreeMap<&'static str, Tally> = BTreeMap::new();
    let mut metric_rows = String::new();
    for batch in batches() {
        let gates: Vec<&&str> = batch
            .gates
            .iter()
            .filter(|g| wanted(&options.only, &batch, g))
            .collect();
        if gates.is_empty() {
            continue;
        }
        let groups: Vec<Vec<i64>> = match batch.run {
            Runner::Single(_) => options.seeds.iter().map(|&s| vec![s]).collect(),
            Runner::Triplet(_) => options
                .seeds
                .as_chunks::<3>()
                .0
                .iter()
                .map(|c| c.to_vec())
                .collect(),
        };
        for seeds in groups {
            let label = format!("{seeds:?}");
            eprintln!("dávka {} semínko {label}", batch.id);
            let outcome = execute(batch.run, &seeds);
            let seed_key = seeds[0];
            for gate in &gates {
                let entry = tally.entry(gate).or_default();
                let found = outcome
                    .as_ref()
                    .ok()
                    .and_then(|reports| reports.iter().find(|(id, _)| id == *gate));
                let (passed, why, report) = match (&outcome, found) {
                    (Err(message), _) => (false, message.clone(), None),
                    (Ok(_), None) => (false, "dávka brány nevrátila".to_owned(), None),
                    (Ok(_), Some((_, report))) => {
                        (report.passed(), report.failures(), Some(report))
                    }
                };
                if passed {
                    entry.passed.push(seed_key);
                } else {
                    entry.failed.push((seed_key, why.clone()));
                }
                if let Some(report) = report.filter(|_| options.metrics) {
                    metric_rows.push_str(&report.table_rows(&format!("{gate} ({label})")));
                }
                if let Some(file) = sink.as_mut() {
                    let metrics: Vec<_> = report
                        .map(|r| {
                            r.metrics
                                .iter()
                                .map(|m| json!({"metric": m.name, "value": m.value, "threshold": m.threshold_text(), "passed": m.passed}))
                                .collect()
                        })
                        .unwrap_or_default();
                    let line = json!({"gate": gate, "seeds": seeds, "passed": passed, "failure": why, "metrics": metrics});
                    writeln!(file, "{line}").map_err(|e| e.to_string())?;
                }
            }
        }
    }
    let mut text = String::new();
    if options.metrics {
        text.push_str(
            "| brána (semínko) | metrika | hodnota | práh | výsledek |\n|---|---|---|---|---|\n",
        );
        text.push_str(&metric_rows);
        text.push('\n');
    }
    text.push_str(
        "| brána | semínek dnes | průchod | Wilson 95 % | zařazení | k (N=10) | k (N=5) |\n|---|---|---:|---|---|---:|---:|\n",
    );
    for gate in GATES {
        let Some(entry) = tally.get(gate.id) else {
            continue;
        };
        let total = (entry.passed.len() + entry.failed.len()) as u32;
        let passed = entry.passed.len() as u32;
        let (low, high) = wilson_interval(passed, total)?;
        text.push_str(&format!(
            "| {} | {} | {passed}/{total} | [{low:.3}, {high:.3}] | {} | {} | {} |\n",
            gate.id,
            gate.seeds_today,
            classify_rate(passed, total),
            threshold_k(10, low, 0.01),
            threshold_k(5, low, 0.01),
        ));
    }
    let mut failures = String::new();
    for gate in GATES {
        if let Some(entry) = tally.get(gate.id) {
            for (seed, why) in &entry.failed {
                failures.push_str(&format!("- {} (semínko {seed}):\n{why}\n", gate.id));
            }
        }
    }
    if !failures.is_empty() {
        text.push_str("\nNeúspěšná semínka a jejich metriky:\n");
        text.push_str(&failures);
    }
    Ok(text)
}
