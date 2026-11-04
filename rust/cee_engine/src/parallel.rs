//! Vlákna: návrh a pomocníci pro `rayon` (MIT/Apache-2.0).
//!
//! **Zásady deterministického souběhu**
//!
//! 1. *Skupiny jsou nezávislé jen ve čtení.* Výpočty, které čtou stav na začátku kroku
//!    (míry inovací `Change::rate_sum`, místa `weighted_sites`, hodnocení tlaků), běží
//!    přes skupiny souběžně a vracejí výsledky **v pořadí vstupu** (`par_iter().map().collect()`).
//! 2. *Zápis je sekvenční* a v kanonickém pořadí (skupiny podle jmen, změny podle
//!    pořadí v seznamu). Souběh nikdy nezapisuje do sdíleného stavu.
//! 3. *Náhoda se tvoří z klíče*, ne ze sdíleného generátoru (`Stream::new`), takže tah
//!    nezávisí na tom, které vlákno ho losuje.
//! 4. *Součty s plovoucí desetinnou čárkou* se skládají po blocích pevné velikosti
//!    ([`ordered_sum`]), ne podle toho, jak se práce rozdělila na vlákna.
//!
//! Počet vláken je tak jen otázka rychlosti: výsledek je stejný pro 1 i 64 vláken
//! (test `tests/determinism.rs`). Počet vláken řídí obvyklá proměnná `RAYON_NUM_THREADS`
//! (nebo `cee --threads N`); bez nich [`default_threads`]. Co běží souběžně, popisuje
//! `docs/engine-v2/19-engine-v-rustu.md`, oddíl 5.

use std::sync::atomic::{AtomicUsize, Ordering};

use rayon::prelude::*;

/// Velikost bloku součtů; pevná, aby výsledek nezávisel na počtu vláken.
pub const SUM_BLOCK: usize = 256;

/// Součet přes bloky pevné velikosti: bloky se sečtou souběžně, jejich součty postupně.
pub fn ordered_sum(values: &[f64]) -> f64 {
    let partial: Vec<f64> = values
        .par_chunks(SUM_BLOCK)
        .map(|chunk| chunk.iter().sum())
        .collect();
    partial.iter().sum()
}

/// Nastaví počet vláken (jen jednou za proces; pozdější volání se ignoruje).
pub fn set_threads(threads: usize) {
    let _ = rayon::ThreadPoolBuilder::new()
        .num_threads(threads.max(1))
        .build_global();
}

/// Výchozí počet vláken: všechna dostupná jádra bez `reserve` jader (nejméně jedno vlákno).
///
/// CLI nechává `reserve = 0` (běh je jediná úloha stroje), server `reserve = 1`, aby zbylo
/// jádro pro UI, prohlížeč a samotný server, které by jinak soupeřily s vlákny enginu o čas.
/// Proměnná `RAYON_NUM_THREADS` má přednost (rozhoduje uživatel).
pub fn default_threads(reserve: usize) -> usize {
    if let Some(chosen) = std::env::var("RAYON_NUM_THREADS")
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|&value| value > 0)
    {
        return chosen;
    }
    let cores = std::thread::available_parallelism().map_or(1, usize::from);
    cores.saturating_sub(reserve).max(1)
}

/// Nastaví globální počet vláken na [`default_threads`] (jen jednou za proces).
pub fn init_default(reserve: usize) {
    set_threads(default_threads(reserve));
}

/// Nejmenší práce (buňky bloků v kroku), kterou se vyplatí rozdělit mezi vlákna; menší světy
/// (pod ~10 skupin) běží na jednom vlákně bez režie rozdělení.
pub const MIN_PARALLEL_CELLS: usize = 1 << 14;

static MIN_CELLS: AtomicUsize = AtomicUsize::new(MIN_PARALLEL_CELLS);

/// Změní práh rozdělení práce (jen pro testy: s nulou se dělí i malé světy, aby test
/// determinismu opravdu prověřil souběh). Výsledek běhu práh nemění.
pub fn set_min_parallel_cells(cells: usize) {
    MIN_CELLS.store(cells, Ordering::Relaxed);
}

/// Vyplatí se práce o `cells` buňkách rozdělit mezi vlákna? Rozhoduje jen o rychlosti:
/// kdo to používá, nesmí z odpovědi odvozovat výsledek.
pub fn worth_splitting(cells: usize) -> bool {
    rayon::current_num_threads() > 1 && cells >= MIN_CELLS.load(Ordering::Relaxed)
}
