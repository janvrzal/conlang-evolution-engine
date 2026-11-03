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
//! (test `tests/determinism.rs`). Jedno použití na ukázku: fáze inovací
//! (`phases::innovation`), kde se míry počítají přes skupiny. Počet vláken řídí obvyklá
//! proměnná `RAYON_NUM_THREADS` (nebo `cee --threads N`).

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
