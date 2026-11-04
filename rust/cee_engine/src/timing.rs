//! Volitelné měření času po fázích kroku.
//!
//! Zapíná se proměnnou prostředí `CEE_PHASE_TIMES=1` nebo přepínačem `cee --phase-times`;
//! v běžném běhu stojí jedno čtení atomického příznaku na fázi. Měří se jen v hlavním
//! vlákně na úrovni fází (ne uvnitř souběžných částí), takže součty jsou skutečný čas,
//! ne čas procesoru. Podfáze mají jméno s lomítkem (`transmission/blocks`) a řadí se
//! za nadřazenou fázi.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Instant;

static ENABLED: AtomicBool = AtomicBool::new(false);
static TABLE: Mutex<Vec<(&'static str, u128, u64)>> = Mutex::new(Vec::new());

/// Zapne měření (z příznaku CLI nebo z proměnné prostředí).
pub fn enable() {
    ENABLED.store(true, Ordering::Relaxed);
}

/// Zapne měření, je-li `CEE_PHASE_TIMES` nastavena na něco jiného než prázdné a `0`.
pub fn enable_from_env() {
    if let Ok(value) = std::env::var("CEE_PHASE_TIMES") {
        if !value.is_empty() && value != "0" {
            enable();
        }
    }
}

pub fn enabled() -> bool {
    ENABLED.load(Ordering::Relaxed)
}

/// Hlídač: při zániku přičte čas k fázi.
pub struct Scope(Option<(&'static str, Instant)>);

/// Začne měřit fázi `name`; při vypnutém měření nedělá nic.
pub fn scope(name: &'static str) -> Scope {
    Scope(enabled().then(|| (name, Instant::now())))
}

impl Drop for Scope {
    fn drop(&mut self) {
        if let Some((name, start)) = self.0.take() {
            let nanos = start.elapsed().as_nanos();
            let mut table = TABLE.lock().unwrap_or_else(|e| e.into_inner());
            match table.iter_mut().find(|row| row.0 == name) {
                Some(row) => {
                    row.1 += nanos;
                    row.2 += 1;
                }
                None => table.push((name, nanos, 1)),
            }
        }
    }
}

/// Tabulka časů po fázích (prázdný text, když se neměřilo). Podíl se počítá ze součtu fází
/// nejvyšší úrovně (jména bez lomítka).
pub fn report() -> String {
    let table = TABLE.lock().unwrap_or_else(|e| e.into_inner());
    if table.is_empty() {
        return String::new();
    }
    let total: u128 = table
        .iter()
        .filter(|row| !row.0.contains('/'))
        .map(|row| row.1)
        .sum();
    let mut order: Vec<&(&str, u128, u64)> = table.iter().collect();
    // Podfáze hned za nadřazenou fází, jinak pořadí prvního výskytu.
    let parent_at = |name: &str| {
        let top = name.split('/').next().unwrap_or(name);
        table.iter().position(|row| row.0 == top).unwrap_or(0)
    };
    order.sort_by_key(|row| (parent_at(row.0), row.0.contains('/')));
    let mut out = format!("{:<28}{:>10}{:>8}{:>8}\n", "fáze", "ms", "podíl", "volání");
    for (name, nanos, calls) in order {
        let share = if total > 0 {
            *nanos as f64 / total as f64 * 100.0
        } else {
            0.0
        };
        out.push_str(&format!(
            "{:<28}{:>10.1}{:>7.1}%{:>8}\n",
            name,
            *nanos as f64 / 1e6,
            share,
            calls
        ));
    }
    out.push_str(&format!(
        "{:<28}{:>10.1}\n",
        "celkem (fáze)",
        total as f64 / 1e6
    ));
    out
}
