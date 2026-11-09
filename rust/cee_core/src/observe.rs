//! Pozorování dialektů a jazyků: zrcadlo `cee.v2.observe` (vzdálenosti tvarů, rysy
//! skupin, kandidáti sloučení, průměrná vazba mezi sousedícími shluky, matice
//! vzdáleností kódů).
//!
//! Čisté jádro nad poli bez Pythonu; vazba je v `observe_python.rs`. Bitová shoda
//! s Pythonem stojí na stejném pořadí operací:
//!
//! - editační vzdálenost tvarů a cena záměny hlásky jsou jen součty, rozdíly,
//!   podíl a minimum (přesné operace), takže stačí stejný postup tabulky;
//! - vložení podílů (`_embedded`) se počítá v `f32` jako v `numpy` (rozdíl, podíl,
//!   oříznutí, součin), čtverce a součty čtverců po skupinách jsou párový
//!   součet jako `np.sum(axis=1)`;
//! - skalární součin dvou řádků `f32` (`shares[a] @ shares[b]`) počítá BLAS, jehož
//!   pořadí sčítání neznáme. Na macOS volá Rust tutéž funkci `cblas_sdot` z
//!   Accelerate jako `numpy` (`dot`); jinde ani na jiné knihovně BLAS shoda není
//!   zaručena, proto ji Python jednou ověří (`native.observe_matches`) a bez shody
//!   počítá celé pozorování sám;
//! - součty v průměrné vazbě (`sum(weight * large.get(...))`) jdou v pořadí
//!   vkládání do slovníku (`Sparse` drží pořadí vkládání a zvlášť seřazený index);
//! - počty příslušnosti k linii a počty tvarů jsou celá čísla uložená jako
//!   `f64`, takže jejich součty nezávisí na pořadí.
//!
//! Hašovací mapy tu nejsou: kategorie tvarů se číslují řazením, slovníky jsou
//! vektory v pořadí vkládání s binárním hledáním.

use std::cmp::{Ordering, Reverse};
use std::collections::BinaryHeap;

use crate::assess::pairwise_sum;

/// Hranice intervalů vložení podílů (`observe.EDGES`).
pub const EDGES: [f64; 14] = [
    0.0, 1e-3, 0.01, 0.03, 0.08, 0.2, 0.4, 0.6, 0.8, 0.92, 0.97, 0.99, 0.999, 1.0,
];
/// Počet intervalů vložení (rozměrů na jeden sloupec podílů).
pub const INTERVALS: usize = EDGES.len() - 1;
/// Nejvýš tolik proměnlivých sloupců vstupuje do shlukování (`observe.SAMPLED`).
pub const SAMPLED: usize = 2000;
/// Kolik zeměpisně nejbližších skupin je kandidátem na sloučení (`observe.NEAREST`).
pub const NEAREST: usize = 4;
/// Váha rozdílu tvarů příbuzných slov proti rozdílu slova samého (`observe.FORM_WEIGHT`).
pub const FORM_WEIGHT: f64 = 1.0;
/// Velikost bloku, po kterém se počítá matice vzdáleností (`observe.distance_matrix`).
pub const DISTANCE_CHUNK: usize = 4_000_000;

// --- skalární součin řádků f32 ----------------------------------------------------

#[cfg(target_os = "macos")]
#[link(name = "Accelerate", kind = "framework")]
extern "C" {
    fn cblas_sdot(n: i32, x: *const f32, incx: i32, y: *const f32, incy: i32) -> f32;
}

/// Má tato sestavba stejný skalární součin `f32` jako `numpy` na macOS (Accelerate)?
pub const NATIVE_DOT: bool = cfg!(target_os = "macos");

/// Skalární součin dvou souvislých polí `f32` jako `numpy` (`a @ b`): na macOS `cblas_sdot`
/// z Accelerate (tatáž funkce, kterou volá `numpy`), jinde postupný součet (shodu s `numpy` pak
/// Python neověří a pozorování nepočítá v Rustu).
pub fn dot(a: &[f32], b: &[f32]) -> f32 {
    assert_eq!(a.len(), b.len(), "skalární součin: různé délky");
    #[cfg(target_os = "macos")]
    {
        if let Ok(count) = i32::try_from(a.len()) {
            // SAFETY: oba ukazatele ukazují na `count` souvislých prvků `f32` po dobu volání.
            return unsafe { cblas_sdot(count, a.as_ptr(), 1, b.as_ptr(), 1) };
        }
    }
    let mut sum = 0.0_f32;
    for (x, y) in a.iter().zip(b) {
        sum += x * y;
    }
    sum
}

// --- slovník v pořadí vkládání ----------------------------------------------------

/// Slovník `číslo sloupce → hodnota`, který drží pořadí vkládání jako `dict` v Pythonu
/// (na něm stojí pořadí sčítání) a vedle něj seřazený index pro hledání.
#[derive(Clone, Debug, Default)]
pub struct Sparse {
    cols: Vec<u32>,
    vals: Vec<f64>,
    /// Dvojice (sloupec, pozice v pořadí vkládání) seřazené podle sloupce.
    sorted: Vec<(u32, u32)>,
}

impl Sparse {
    /// Slovník z položek v pořadí vkládání; sloupce musí být různé.
    pub fn from_entries(cols: Vec<u32>, vals: Vec<f64>) -> Self {
        debug_assert_eq!(cols.len(), vals.len());
        let mut item = Sparse {
            cols,
            vals,
            sorted: Vec::new(),
        };
        item.reindex();
        item
    }

    fn reindex(&mut self) {
        self.sorted.clear();
        self.sorted.extend(
            self.cols
                .iter()
                .enumerate()
                .map(|(at, &col)| (col, at as u32)),
        );
        self.sorted.sort_unstable();
    }

    pub fn len(&self) -> usize {
        self.cols.len()
    }

    pub fn is_empty(&self) -> bool {
        self.cols.is_empty()
    }

    pub fn cols(&self) -> &[u32] {
        &self.cols
    }

    pub fn vals(&self) -> &[f64] {
        &self.vals
    }

    fn position(&self, col: u32) -> Option<usize> {
        self.sorted
            .binary_search_by_key(&col, |entry| entry.0)
            .ok()
            .map(|at| self.sorted[at].1 as usize)
    }

    pub fn get(&self, col: u32) -> Option<f64> {
        self.position(col).map(|at| self.vals[at])
    }

    /// Součet hodnot v pořadí vkládání (`sum(d.values())`).
    pub fn total(&self) -> f64 {
        let mut sum = 0.0;
        for &value in &self.vals {
            sum += value;
        }
        sum
    }

    /// Přičte položky `other` v jejím pořadí: `merged[col] = merged.get(col, 0.0) + weight`.
    /// Nové sloupce se přidají na konec v tomtéž pořadí.
    pub fn merge(&mut self, other: &Sparse) {
        let before = self.cols.len();
        for (&col, &weight) in other.cols.iter().zip(&other.vals) {
            match self.position(col) {
                Some(at) => self.vals[at] += weight,
                None => {
                    self.cols.push(col);
                    self.vals.push(0.0 + weight);
                }
            }
        }
        if self.cols.len() != before {
            self.reindex();
        }
    }
}

// --- editační vzdálenost tvarů ---------------------------------------------------

/// Ceny záměny hlásek z vektorů rysů (`observe.segment_cost`): podíl odlišných rysů,
/// nejvýš 1. Cena se počítá při každém dotazu bez paměti: porovnání dvou řádků rysů
/// je levnější než hledání v husté matici všech dvojic, která by u úplné tabulky
/// (přes 23 000 hlásek) měla přes 4 GB.
#[derive(Clone, Copy)]
pub struct Costs<'a> {
    vectors: &'a [i8],
    width: usize,
    count: usize,
    scale: f64,
}

impl<'a> Costs<'a> {
    /// `vectors` jsou řádky rysů hlásek po `width` hodnotách, `scale` dělí počet odlišných rysů.
    pub fn new(vectors: &'a [i8], width: usize, scale: f64) -> Self {
        let count = vectors.len().checked_div(width).unwrap_or(0);
        Costs {
            vectors,
            width,
            count,
            scale,
        }
    }

    /// Počet hlásek v tabulce.
    pub fn segments(&self) -> usize {
        self.count
    }

    pub fn cost(&mut self, first: i32, second: i32) -> f64 {
        if first == second {
            return 0.0;
        }
        let row = |segment: i32| &self.vectors[segment as usize * self.width..][..self.width];
        let differing = row(first)
            .iter()
            .zip(row(second))
            .filter(|(a, b)| a != b)
            .count();
        (differing as f64 / self.scale).min(1.0)
    }
}

/// Normalizovaná editační vzdálenost dvou tvarů (0 shodné, 1 zcela jiné): `observe.form_distance`.
/// `row` je pracovní pole (dvě řady tabulky).
pub fn form_distance(
    costs: &mut Costs<'_>,
    first: &[i32],
    second: &[i32],
    row: &mut Vec<f64>,
) -> f64 {
    if first == second {
        return 0.0;
    }
    if first.is_empty() || second.is_empty() {
        return 1.0;
    }
    let columns = second.len() + 1;
    row.clear();
    row.resize(2 * columns, 0.0);
    let (mut previous, mut current) = row.split_at_mut(columns);
    for (index, value) in previous.iter_mut().enumerate() {
        *value = index as f64;
    }
    for (at, &a) in first.iter().enumerate() {
        current[0] = (at + 1) as f64;
        for (column, &b) in second.iter().enumerate() {
            let column = column + 1;
            let delete = previous[column] + 1.0;
            let insert = current[column - 1] + 1.0;
            let replace = previous[column - 1] + costs.cost(a, b);
            current[column] = delete.min(insert).min(replace);
        }
        std::mem::swap(&mut previous, &mut current);
    }
    (previous[second.len()] / first.len().max(second.len()) as f64).min(1.0)
}

/// Tvary po číslech: tvar `i` jsou hlásky `flat[ptr[i]..ptr[i + 1]]`.
#[derive(Clone, Copy)]
pub struct FormTable<'a> {
    pub ptr: &'a [i64],
    pub flat: &'a [i32],
}

impl<'a> FormTable<'a> {
    pub fn count(&self) -> usize {
        self.ptr.len().saturating_sub(1)
    }

    pub fn get(&self, form: usize) -> &'a [i32] {
        &self.flat[self.ptr[form] as usize..self.ptr[form + 1] as usize]
    }
}

/// Dominantní kořeny skupin ve vkládacím pořadí pojmů: pro skupinu `g` položky
/// `ptr[g]..ptr[g + 1]` (pojem, kořen, tvar jako číslo v `FormTable`).
#[derive(Clone, Copy)]
pub struct Dominant<'a> {
    pub ptr: &'a [i64],
    pub concept: &'a [i32],
    pub root: &'a [i32],
    pub form: &'a [i32],
}

impl Dominant<'_> {
    fn range(&self, group: usize) -> std::ops::Range<usize> {
        self.ptr[group] as usize..self.ptr[group + 1] as usize
    }
}

// --- kategorie tvarů (příbuzná slova) ----------------------------------------------

/// Pro každou skupinu `forms` (kategorie tvaru dominantního kořene pojmu, váha 1) a `spread`
/// (součet vzdáleností k ostatním tvarům téhož kořene pojmu), obojí v pořadí vkládání jako
/// slovníky v `observe._features`.
pub struct Categories {
    pub forms: Vec<Sparse>,
    pub spread: Vec<Sparse>,
}

/// Kategorie (pojem, kořen, tvar) skupin `groups` (čísla živých skupin) a vzdálenosti mezi tvary
/// téhož kořene pojmu. Číslo kategorie je pořadí prvního výskytu, jako v Pythonu.
pub fn categories(
    dominant: &Dominant<'_>,
    groups: &[usize],
    forms: &FormTable<'_>,
    costs: &mut Costs<'_>,
) -> Categories {
    let mut entries: Vec<usize> = Vec::new(); // pozice v dominantních polích, v pořadí výskytu
    let mut starts = Vec::with_capacity(groups.len() + 1);
    for &group in groups {
        starts.push(entries.len());
        entries.extend(dominant.range(group));
    }
    starts.push(entries.len());
    let key = |entry: usize| {
        (
            dominant.concept[entries[entry]],
            dominant.root[entries[entry]],
            dominant.form[entries[entry]],
        )
    };
    // Různé klíče a číslo kategorie podle prvního výskytu.
    let mut order: Vec<u32> = (0..entries.len() as u32).collect();
    order.sort_unstable_by_key(|&entry| (key(entry as usize), entry));
    let mut run_of = vec![0_u32; entries.len()];
    let mut first_seen: Vec<u32> = Vec::new();
    for (at, &entry) in order.iter().enumerate() {
        if at == 0 || key(entry as usize) != key(order[at - 1] as usize) {
            first_seen.push(entry);
        }
        run_of[entry as usize] = (first_seen.len() - 1) as u32;
    }
    let mut by_first: Vec<u32> = (0..first_seen.len() as u32).collect();
    by_first.sort_unstable_by_key(|&run| first_seen[run as usize]);
    let mut category_of_run = vec![0_u32; first_seen.len()];
    for (category, &run) in by_first.iter().enumerate() {
        category_of_run[run as usize] = category as u32;
    }
    let category_of: Vec<u32> = run_of
        .iter()
        .map(|&run| category_of_run[run as usize])
        .collect();
    // Klíč každé kategorie a členové téhož (pojem, kořen) v pořadí čísel kategorií.
    let category_key: Vec<(i32, i32, i32)> = by_first
        .iter()
        .map(|&run| key(first_seen[run as usize] as usize))
        .collect();
    let mut by_pair: Vec<u32> = (0..category_key.len() as u32).collect();
    by_pair.sort_unstable_by_key(|&category| {
        let (concept, root, _) = category_key[category as usize];
        (concept, root, category)
    });
    let pair_of = |category: u32| {
        let (concept, root, _) = category_key[category as usize];
        (concept, root)
    };
    let mut member_range = vec![(0_usize, 0_usize); category_key.len()];
    let mut begin = 0;
    while begin < by_pair.len() {
        let mut end = begin + 1;
        while end < by_pair.len() && pair_of(by_pair[end]) == pair_of(by_pair[begin]) {
            end += 1;
        }
        for &category in &by_pair[begin..end] {
            member_range[category as usize] = (begin, end);
        }
        begin = end;
    }
    // Vzdálenosti tvarů téhož (pojem, kořen) se počítají jednou na dvojici; je symetrická.
    // Dva průchody: nejdřív se v pořadí výskytu vypíšou dvojice tvarů, které je třeba spočítat
    // (a místa v mezipaměti); editační vzdálenosti (čisté funkce tvarů) se spočtou souběžně;
    // pak se výstup složí stejným průchodem jako dřív, už jen z hotových hodnot.
    let mut pair_cache: Vec<f64> = Vec::new();
    let mut cache_start = vec![usize::MAX; category_key.len()];
    let mut wanted: Vec<(usize, usize, u32, u32)> = Vec::new(); // (místo, zrcadlo, tvar a, tvar b)
    let mut listed: Vec<Vec<(usize, u32)>> = Vec::with_capacity(groups.len()); // (místo, kategorie)
    for group in 0..groups.len() {
        let mut visited: Vec<(usize, u32)> = Vec::new();
        for &category in &category_of[starts[group]..starts[group + 1]] {
            let (begin, end) = member_range[category as usize];
            if end - begin < 2 {
                continue;
            }
            let size = end - begin;
            let base = cache_start[by_pair[begin] as usize];
            let base = if base == usize::MAX {
                let at = pair_cache.len();
                pair_cache.resize(at + size * size, f64::NAN);
                for &member in &by_pair[begin..end] {
                    cache_start[member as usize] = at;
                }
                at
            } else {
                base
            };
            let own = by_pair[begin..end]
                .iter()
                .position(|&member| member == category)
                .expect("kategorie je mezi členy svého kořene");
            for (position, &other) in by_pair[begin..end].iter().enumerate() {
                if other == category {
                    continue;
                }
                let slot = base + own * size + position;
                if pair_cache[slot].is_nan() {
                    // Zatím neznámá hodnota: zadá se k výpočtu a místo se označí nulou, aby se
                    // dvojice nezadala dvakrát (pravá hodnota se doplní po souběžném výpočtu).
                    let mirror = base + position * size + own;
                    pair_cache[slot] = 0.0;
                    pair_cache[mirror] = 0.0;
                    wanted.push((
                        slot,
                        mirror,
                        category_key[category as usize].2 as u32,
                        category_key[other as usize].2 as u32,
                    ));
                }
                visited.push((slot, other));
            }
        }
        listed.push(visited);
    }
    let computed: Vec<f64> = {
        let costs: &Costs<'_> = &*costs;
        let distance = |&(_, _, first, second): &(usize, usize, u32, u32)| {
            let mut own = *costs;
            let mut scratch = Vec::new();
            form_distance(
                &mut own,
                forms.get(first as usize),
                forms.get(second as usize),
                &mut scratch,
            )
        };
        if wanted.len() >= 64 {
            use rayon::prelude::*;
            wanted.par_iter().map(distance).collect()
        } else {
            wanted.iter().map(distance).collect()
        }
    };
    for (&(slot, mirror, _, _), &value) in wanted.iter().zip(&computed) {
        pair_cache[slot] = value;
        pair_cache[mirror] = value;
    }
    let mut out = Categories {
        forms: Vec::with_capacity(groups.len()),
        spread: Vec::with_capacity(groups.len()),
    };
    for group in 0..groups.len() {
        let form_cols: Vec<u32> = category_of[starts[group]..starts[group + 1]].to_vec();
        let mut spread_cols = Vec::new();
        let mut spread_vals = Vec::new();
        for &(slot, other) in &listed[group] {
            spread_cols.push(other);
            spread_vals.push(pair_cache[slot]);
        }
        let ones = vec![1.0; form_cols.len()];
        out.forms.push(Sparse::from_entries(form_cols, ones));
        out.spread
            .push(Sparse::from_entries(spread_cols, spread_vals));
    }
    out
}

// --- rysy pozorování --------------------------------------------------------------

/// Pohled na jeden blok živých fondů: podíly `(řádky, skupiny, sloty)`, kdo proměnnou má
/// `(řádky, skupiny)`, vybrané řádky (proměnné slov a konstrukcí) a pořadí proměnných při výběru
/// vzorku (`ranks`: nižší číslo je dřív).
pub struct PoolView<'a> {
    pub freqs: &'a [f64],
    pub present: &'a [bool],
    pub groups: usize,
    pub capacity: usize,
    pub rows: &'a [i64],
    pub ranks: &'a [i64],
}

impl PoolView<'_> {
    /// Podíl varianty ve slotu, 0 u skupiny, která proměnnou nemá.
    #[inline]
    fn value(&self, row: usize, group: usize, slot: usize) -> f64 {
        let cell = row * self.groups + group;
        if self.present[cell] {
            self.freqs[cell * self.capacity + slot]
        } else {
            0.0
        }
    }
}

/// Rysy skupin: vložení podílů variant, součty čtverců a kategorie tvarů (`observe._Features`).
pub struct Features {
    pub groups: usize,
    pub dim: usize,
    /// `(skupiny, dim)` po řádcích.
    pub shares: Vec<f32>,
    pub squares: Vec<f64>,
    pub forms: Vec<Sparse>,
    pub spread: Vec<Sparse>,
    pub lexical: f64,
}

/// Rozdělí `0..total` na nejvýš `parts` souvislých úseků.
fn spans(total: usize, parts: usize) -> Vec<(usize, usize)> {
    let parts = parts.clamp(1, total.max(1));
    let (each, extra) = (total / parts, total % parts);
    let mut begin = 0;
    (0..parts)
        .map(|part| {
            let end = begin + each + usize::from(part < extra);
            let span = (begin, end);
            begin = end;
            span
        })
        .collect()
}

/// Vložení jednoho podílu do `INTERVALS` rozměrů (`observe._embedded`), v `f32` jako `numpy`.
struct Embedding {
    starts: [f32; INTERVALS],
    widths: [f32; INTERVALS],
    roots: [f32; INTERVALS],
}

impl Embedding {
    fn new(factor: f64) -> Self {
        let edges: Vec<f32> = EDGES.iter().map(|&edge| edge as f32).collect();
        let factor = factor as f32;
        let mut embedding = Embedding {
            starts: [0.0; INTERVALS],
            widths: [0.0; INTERVALS],
            roots: [0.0; INTERVALS],
        };
        for at in 0..INTERVALS {
            embedding.starts[at] = edges[at];
            embedding.widths[at] = edges[at + 1] - edges[at];
            embedding.roots[at] = embedding.widths[at].sqrt() * factor;
        }
        embedding
    }

    fn write(&self, share: f64, out: &mut [f32]) {
        let share = share as f32;
        for (at, slot) in out.iter_mut().enumerate().take(INTERVALS) {
            let fraction = (share - self.starts[at]) / self.widths[at];
            *slot = fraction.clamp(0.0, 1.0) * self.roots[at];
        }
    }
}

/// Rysy skupin `cols` (čísla živých skupin): vložení podílů proměnlivých sloupců (proměnná × slot)
/// vzorku proměnných a součty čtverců. Kategorie tvarů se přikládají zvlášť.
pub fn embedded_features(
    pools: &[PoolView<'_>],
    cols: &[usize],
    lexical: usize,
    threads: usize,
) -> Features {
    let groups = cols.len();
    // Sloupce (řádek výběru × slot), ve kterých se skupiny liší od první skupiny.
    let mut varying: Vec<Vec<bool>> = pools
        .iter()
        .map(|pool| vec![false; pool.rows.len() * pool.capacity])
        .collect();
    if groups > 1 {
        for (pool, flags) in pools.iter().zip(&mut varying) {
            let capacity = pool.capacity;
            let mut first = vec![0.0; capacity];
            for (at, &row) in pool.rows.iter().enumerate() {
                let row = row as usize;
                for (slot, value) in first.iter_mut().enumerate() {
                    *value = pool.value(row, cols[0], slot);
                }
                for &col in &cols[1..] {
                    for (slot, &base) in first.iter().enumerate() {
                        if pool.value(row, col, slot) != base {
                            flags[at * capacity + slot] = true;
                        }
                    }
                }
            }
        }
    }
    let total: usize = varying.iter().flatten().filter(|&&flag| flag).count();
    let mut scale = 1.0_f64;
    if total > SAMPLED {
        // Nestranný odhad z pevného výběru proměnných: berou se v pořadí `ranks`, dokud se
        // nevyčerpá rozpočet sloupců; první proměnná, která se nevejde, výběr ukončí.
        let mut rows: Vec<(i64, usize, usize, usize)> = Vec::new();
        for (index, (pool, flags)) in pools.iter().zip(&varying).enumerate() {
            for at in 0..pool.rows.len() {
                let width = flags[at * pool.capacity..(at + 1) * pool.capacity]
                    .iter()
                    .filter(|&&flag| flag)
                    .count();
                if width > 0 {
                    rows.push((pool.ranks[at], index, at, width));
                }
            }
        }
        rows.sort_unstable();
        let mut used = 0;
        let mut kept = vec![Vec::<bool>::new(); pools.len()];
        for (index, pool) in pools.iter().enumerate() {
            kept[index] = vec![false; pool.rows.len()];
        }
        for &(_, index, at, width) in &rows {
            if used + width > SAMPLED {
                break;
            }
            kept[index][at] = true;
            used += width;
        }
        for (index, pool) in pools.iter().enumerate() {
            for at in 0..pool.rows.len() {
                if !kept[index][at] {
                    varying[index][at * pool.capacity..(at + 1) * pool.capacity].fill(false);
                }
            }
        }
        scale = total as f64 / used.max(1) as f64;
    }
    // Zachované sloupce v pořadí bloků, řádků a slotů.
    let mut columns: Vec<(usize, usize, usize)> = Vec::new();
    for (index, (pool, flags)) in pools.iter().zip(&varying).enumerate() {
        for at in 0..pool.rows.len() {
            for slot in 0..pool.capacity {
                if flags[at * pool.capacity + slot] {
                    columns.push((index, pool.rows[at] as usize, slot));
                }
            }
        }
    }
    let dim = columns.len() * INTERVALS;
    let embedding = Embedding::new(scale.sqrt());
    let mut shares = vec![0.0_f32; groups * dim];
    let mut squares = vec![0.0_f64; groups];
    let work = |range: (usize, usize), shares: &mut [f32], squares: &mut [f64]| {
        let mut scratch = vec![0.0_f64; dim];
        for (local, group) in (range.0..range.1).enumerate() {
            let row = &mut shares[local * dim..(local + 1) * dim];
            for (at, &(index, source, slot)) in columns.iter().enumerate() {
                let value = pools[index].value(source, cols[group], slot);
                embedding.write(value, &mut row[at * INTERVALS..(at + 1) * INTERVALS]);
            }
            for (square, &value) in scratch.iter_mut().zip(row.iter()) {
                let wide = f64::from(value);
                *square = wide * wide;
            }
            squares[local] = pairwise_sum(&scratch);
        }
    };
    let parts = spans(groups, threads);
    if parts.len() <= 1 {
        work((0, groups), &mut shares, &mut squares);
    } else {
        std::thread::scope(|scope| {
            let mut rest_shares = shares.as_mut_slice();
            let mut rest_squares = squares.as_mut_slice();
            for &span in &parts {
                let (mine, tail) = rest_shares.split_at_mut((span.1 - span.0) * dim);
                rest_shares = tail;
                let (mine_squares, tail) = rest_squares.split_at_mut(span.1 - span.0);
                rest_squares = tail;
                let work = &work;
                scope.spawn(move || work(span, mine, mine_squares));
            }
        });
    }
    Features {
        groups,
        dim,
        shares,
        squares,
        forms: vec![Sparse::default(); groups],
        spread: vec![Sparse::default(); groups],
        lexical: lexical.max(1) as f64,
    }
}

// --- kandidáti sloučení -----------------------------------------------------------

/// Celočíselné dělení `a // b` jako `float.__floordiv__` v Pythonu a `numpy.floor_divide`
/// (včetně opravy zaokrouhlení podílu), pro `b > 0`.
pub fn floor_divide(a: f64, b: f64) -> f64 {
    let mut modulus = a % b;
    let mut quotient = (a - modulus) / b;
    if modulus != 0.0 && (b < 0.0) != (modulus < 0.0) {
        modulus += b;
        quotient -= 1.0;
    }
    let _ = modulus;
    if quotient != 0.0 {
        let floor = quotient.floor();
        if quotient - floor > 0.5 {
            floor + 1.0
        } else {
            floor
        }
    } else {
        0.0_f64.copysign(a / b)
    }
}

/// Dvojice pozic skupin, které se smějí přímo sloučit: vazby (`links`, dvojice pozic) a nejbližší
/// sousedé na mapě (`observe._candidates`). `slots` jsou pozice skupin s polohou a `xs`, `ys`
/// jejich souřadnice. Výsledek je seřazený a bez opakování.
pub fn candidates(links: &[(u32, u32)], slots: &[u32], xs: &[f64], ys: &[f64]) -> Vec<(u32, u32)> {
    let mut pairs: Vec<(u32, u32)> = links
        .iter()
        .filter(|(source, target)| source != target)
        .map(|&(source, target)| (source.min(target), source.max(target)))
        .collect();
    let count = slots.len();
    if count > 1 {
        let max = |values: &[f64]| values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        let min = |values: &[f64]| values.iter().copied().fold(f64::INFINITY, f64::min);
        let extent = (max(xs) - min(xs)).max(max(ys) - min(ys)).max(1e-9);
        let size = extent / (count as f64 / 2.0).sqrt().max(1.0);
        let cell_of = |x: f64, y: f64| (floor_divide(x, size) as i64, floor_divide(y, size) as i64);
        let mut cells: Vec<((i64, i64), u32)> = (0..count)
            .map(|slot| (cell_of(xs[slot], ys[slot]), slot as u32))
            .collect();
        cells.sort_unstable();
        let reach = (extent / size).ceil() as i64 + 1;
        let mut found: Vec<(f64, u32)> = Vec::new();
        for slot in 0..count {
            let (x, y) = (xs[slot], ys[slot]);
            let home = cell_of(x, y);
            found.clear();
            for radius in 0..=reach {
                for dx in -radius..=radius {
                    for dy in -radius..=radius {
                        if dx.abs().max(dy.abs()) != radius {
                            continue;
                        }
                        let cell = (home.0 + dx, home.1 + dy);
                        let begin = cells.partition_point(|entry| entry.0 < cell);
                        for entry in cells[begin..].iter().take_while(|entry| entry.0 == cell) {
                            let other = entry.1 as usize;
                            if other != slot {
                                found.push(((xs[other] - x).hypot(ys[other] - y), other as u32));
                            }
                        }
                    }
                }
                // Kruh o poloměru r pokrývá jistě vše do vzdálenosti (r − 1) · size.
                if found.len() >= NEAREST {
                    let mut ordered = found.clone();
                    ordered.sort_by(|a, b| a.partial_cmp(b).unwrap_or(Ordering::Equal));
                    if ordered[NEAREST - 1].0 <= radius as f64 * size {
                        break;
                    }
                }
            }
            found.sort_by(|a, b| a.partial_cmp(b).unwrap_or(Ordering::Equal));
            for &(_, other) in found.iter().take(NEAREST) {
                let (first, second) = (slots[slot], slots[other as usize]);
                pairs.push((first.min(second), first.max(second)));
            }
        }
    }
    pairs.sort_unstable();
    pairs.dedup();
    pairs
}

// --- průměrná vazba mezi sousedícími shluky --------------------------------------

#[derive(PartialEq)]
struct Entry {
    value: f64,
    first: u32,
    second: u32,
    first_version: u32,
    second_version: u32,
}

impl Eq for Entry {}

impl Ord for Entry {
    fn cmp(&self, other: &Self) -> Ordering {
        self.value
            .partial_cmp(&other.value)
            .unwrap_or(Ordering::Equal)
            .then(self.first.cmp(&other.first))
            .then(self.second.cmp(&other.second))
            .then(self.first_version.cmp(&other.first_version))
            .then(self.second_version.cmp(&other.second_version))
    }
}

impl PartialOrd for Entry {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Stav shluků při slučování: velikosti, součty vložení a čtverců, četnosti tvarů a linií.
struct Clusters {
    dim: usize,
    lexical: f64,
    margin: f64,
    form_gate: f64,
    size: Vec<f64>,
    shares: Vec<f32>,
    squares: Vec<f64>,
    forms: Vec<Sparse>,
    spread: Vec<Sparse>,
    labels: Vec<Sparse>,
}

impl Clusters {
    /// Vzdálenost shluků `a` a `b` (průměr přes dvojice členů) ze součtů za shluk.
    fn linkage(&self, a: usize, b: usize) -> f64 {
        let (na, nb) = (self.size[a], self.size[b]);
        let d = self.dim;
        let product = dot(
            &self.shares[a * d..(a + 1) * d],
            &self.shares[b * d..(b + 1) * d],
        );
        let words =
            0.5 * (self.squares[a] / na + self.squares[b] / nb) - f64::from(product) / (na * nb);
        let mut value = words;
        let (small, large) = if self.spread[a].len() <= self.forms[b].len() {
            (&self.spread[a], &self.forms[b])
        } else {
            (&self.forms[b], &self.spread[a])
        };
        let mut sum = 0.0;
        for (&col, &weight) in small.cols.iter().zip(&small.vals) {
            if let Some(other) = large.get(col) {
                sum += weight * other;
            }
        }
        let mut forms = FORM_WEIGHT * sum / (na * nb);
        if self.form_gate > 0.0 {
            forms *= (words.max(0.0) / self.lexical / self.form_gate).min(1.0);
        }
        value += forms;
        value /= self.lexical;
        if self.margin != 0.0 {
            let mut same = 0.0;
            for (&label, &weight) in self.labels[a].cols.iter().zip(&self.labels[a].vals) {
                if let Some(count) = self.labels[b].get(label) {
                    same += weight * count;
                }
            }
            let known = self.labels[a].total() * self.labels[b].total();
            value += self.margin * (known - 2.0 * same) / (na * nb);
        }
        if value > 0.0 {
            value
        } else {
            0.0
        }
    }

    fn absorb(&mut self, keep: usize, drop: usize) {
        self.size[keep] += self.size[drop];
        let d = self.dim;
        let from: Vec<f32> = self.shares[drop * d..(drop + 1) * d].to_vec();
        for (to, add) in self.shares[keep * d..(keep + 1) * d].iter_mut().zip(&from) {
            *to += *add;
        }
        self.squares[keep] += self.squares[drop];
        for map in [&mut self.forms, &mut self.spread, &mut self.labels] {
            let source = std::mem::take(&mut map[drop]);
            map[keep].merge(&source);
        }
    }
}

/// Dosavadní linie skupin a hystereze: `labels[i]` je číslo linie skupiny `i` (−1 žádná).
pub struct Hysteresis<'a> {
    pub labels: &'a [i64],
    pub margin: f64,
    /// Brána tvarů u jazyků: rozdíl výslovnosti příbuzných slov se započte jen z podílu
    /// `min(1, rozdíl slov a konstrukcí / form_gate)`; 0 = vždy celý. Varieta se stejným slovníkem
    /// a cizí výslovností (po přechodu jazyka, irská angličtina) je nářečím, ne jazykem.
    pub form_gate: f64,
}

/// Průměrná vazba mezi sousedícími shluky až do prahu (`observe.constrained_average_linkage`).
/// `pairs` jsou kandidáti sloučení z :func:`candidates`. Vrací shluky jako seřazené seznamy pozic
/// skupin, seřazené podle prvního člena.
pub fn linkage(
    features: &Features,
    pairs: &[(u32, u32)],
    threshold: f64,
    hysteresis: Option<&Hysteresis<'_>>,
) -> Vec<Vec<usize>> {
    let count = features.groups;
    let mut clusters: Vec<Vec<usize>> = (0..count).map(|index| vec![index]).collect();
    if count < 2 {
        return clusters;
    }
    let mut state = Clusters {
        dim: features.dim,
        lexical: features.lexical,
        margin: hysteresis.map_or(0.0, |item| item.margin),
        form_gate: hysteresis.map_or(0.0, |item| item.form_gate),
        size: vec![1.0; count],
        shares: features.shares.clone(),
        squares: features.squares.clone(),
        forms: features.forms.clone(),
        spread: features.spread.clone(),
        labels: (0..count)
            .map(|index| match hysteresis {
                Some(item) if item.labels[index] >= 0 => {
                    Sparse::from_entries(vec![item.labels[index] as u32], vec![1.0])
                }
                _ => Sparse::default(),
            })
            .collect(),
    };
    let mut neighbours: Vec<Vec<u32>> = vec![Vec::new(); count];
    for &(first, second) in pairs {
        neighbours[first as usize].push(second);
        neighbours[second as usize].push(first);
    }
    for list in &mut neighbours {
        list.sort_unstable();
        list.dedup();
    }
    let mut version = vec![0_u32; count];
    let mut heap: BinaryHeap<Reverse<Entry>> = BinaryHeap::new();
    for (a, list) in neighbours.iter().enumerate() {
        for &b in list {
            if a < b as usize {
                heap.push(Reverse(Entry {
                    value: state.linkage(a, b as usize),
                    first: a as u32,
                    second: b,
                    first_version: 0,
                    second_version: 0,
                }));
            }
        }
    }
    let mut alive = vec![true; count];
    while let Some(Reverse(entry)) = heap.pop() {
        let (a, b) = (entry.first as usize, entry.second as usize);
        if !(alive[a] && alive[b])
            || version[a] != entry.first_version
            || version[b] != entry.second_version
        {
            continue;
        }
        if entry.value > threshold {
            break;
        }
        let (keep, drop) = if a < b { (a, b) } else { (b, a) };
        state.absorb(keep, drop);
        let moved = std::mem::take(&mut clusters[drop]);
        clusters[keep].extend(moved);
        alive[drop] = false;
        version[keep] += 1;
        let dropped = std::mem::take(&mut neighbours[drop]);
        let mut merged: Vec<u32> = neighbours[keep]
            .iter()
            .chain(&dropped)
            .copied()
            .filter(|&other| other as usize != keep && other as usize != drop)
            .collect();
        merged.sort_unstable();
        merged.dedup();
        for &other in &dropped {
            let other = other as usize;
            if other == keep {
                continue;
            }
            let list = &mut neighbours[other];
            if let Ok(at) = list.binary_search(&(drop as u32)) {
                list.remove(at);
            }
            if let Err(at) = list.binary_search(&(keep as u32)) {
                list.insert(at, keep as u32);
            }
        }
        neighbours[keep] = merged;
        for &other in &neighbours[keep] {
            let other = other as usize;
            let (first, second) = if keep < other {
                (keep, other)
            } else {
                (other, keep)
            };
            heap.push(Reverse(Entry {
                value: state.linkage(first, second),
                first: first as u32,
                second: second as u32,
                first_version: version[first],
                second_version: version[second],
            }));
        }
    }
    let mut result: Vec<Vec<usize>> = clusters
        .into_iter()
        .filter(|cluster| !cluster.is_empty())
        .map(|mut cluster| {
            cluster.sort_unstable();
            cluster
        })
        .collect();
    result.sort_by_key(|cluster| cluster[0]);
    result
}

// --- matice vzdáleností kódů -----------------------------------------------------

/// Párový součet `f32` jako `numpy` (`np.add.reduce` nad souvislým polem `float32`).
pub fn pairwise_f32(values: &[f32]) -> f32 {
    const BLOCK: usize = 128;
    let n = values.len();
    if n < 8 {
        let mut result = 0.0_f32;
        for &value in values {
            result += value;
        }
        result
    } else if n <= BLOCK {
        let mut r = [0.0_f32; 8];
        r.copy_from_slice(&values[..8]);
        let mut i = 8;
        while i < n - (n % 8) {
            for (j, part) in r.iter_mut().enumerate() {
                *part += values[i + j];
            }
            i += 8;
        }
        let mut result = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            result += values[i];
            i += 1;
        }
        result
    } else {
        let mut half = n / 2;
        half -= half % 8;
        pairwise_f32(&values[..half]) + pairwise_f32(&values[half..])
    }
}

/// Matice `(živé skupiny)²` průměrné variační vzdálenosti hlavních kódů přes proměnné slov a
/// konstrukcí, bez dělení počtem lexikálních proměnných (`observe.distance_matrix` před
/// závěrečným dělením). Součty jsou po blocích proměnných jako v Pythonu: v každém bloku po
/// `DISTANCE_CHUNK / (skupiny² · sloty)` řádcích součet `f32` přes řádky a sloty (jako
/// `np.sum(axis=(0, 3))`: po řádcích párový součet přes sloty), pak `0.5 ·` a přičtení k `f64`.
/// Počítá se horní trojúhelník (matice je symetrická, rozdíl je podle absolutní hodnoty) po
/// souvislých úsecích řádků na `threads` vláknech a spodní se zrcadlí.
pub fn distance_totals(
    pools: &[PoolView<'_>],
    groups: usize,
    chunk: usize,
    threads: usize,
) -> Vec<f64> {
    let mut total = vec![0.0_f64; groups * groups];
    // Podíly jako f32 po blocích: (vybrané řádky, skupiny, sloty).
    let wide: Vec<Vec<f32>> = pools
        .iter()
        .map(|pool| {
            let mut values = Vec::with_capacity(pool.rows.len() * groups * pool.capacity);
            for &row in pool.rows {
                for group in 0..groups {
                    for slot in 0..pool.capacity {
                        values.push(pool.value(row as usize, group, slot) as f32);
                    }
                }
            }
            values
        })
        .collect();
    let work = |range: (usize, usize), out: &mut [f64]| {
        let mut absolute: Vec<f32> = Vec::new();
        for (pool, values) in pools.iter().zip(&wide) {
            let capacity = pool.capacity;
            let rows = pool.rows.len();
            if rows == 0 {
                continue;
            }
            absolute.resize(capacity, 0.0);
            let step = (chunk / (groups * groups * capacity).max(1)).max(1);
            let mut start = 0;
            while start < rows {
                let end = (start + step).min(rows);
                for group in range.0..range.1 {
                    for other in group + 1..groups {
                        let mut sum = 0.0_f32;
                        for row in start..end {
                            let a = &values[(row * groups + group) * capacity..][..capacity];
                            let b = &values[(row * groups + other) * capacity..][..capacity];
                            for slot in 0..capacity {
                                absolute[slot] = (a[slot] - b[slot]).abs();
                            }
                            sum += pairwise_f32(&absolute);
                        }
                        out[(group - range.0) * groups + other] += f64::from(0.5 * sum);
                    }
                }
                start = end;
            }
        }
    };
    // Řádky horního trojúhelníku mají nestejnou práci; úseky se dělí podle ní.
    let parts = balanced(groups, threads);
    if parts.len() <= 1 {
        work((0, groups), &mut total);
    } else {
        std::thread::scope(|scope| {
            let mut rest = total.as_mut_slice();
            for &span in &parts {
                let (mine, tail) = rest.split_at_mut((span.1 - span.0) * groups);
                rest = tail;
                let work = &work;
                scope.spawn(move || work(span, mine));
            }
        });
    }
    for group in 0..groups {
        for other in group + 1..groups {
            total[other * groups + group] = total[group * groups + other];
        }
    }
    total
}

/// Úseky řádků horního trojúhelníku se zhruba stejným počtem dvojic.
fn balanced(groups: usize, threads: usize) -> Vec<(usize, usize)> {
    let parts = threads.clamp(1, groups.max(1));
    let total = groups * groups.saturating_sub(1) / 2;
    let mut spans = Vec::new();
    let (mut begin, mut done) = (0, 0);
    for part in 1..=parts {
        let goal = total * part / parts;
        let mut end = begin;
        while end < groups && done < goal {
            done += groups - end - 1;
            end += 1;
        }
        if part == parts {
            end = groups;
        }
        if end > begin {
            spans.push((begin, end));
        }
        begin = end;
    }
    spans
}

/// Součet rozdílů tvarů příbuzných slov přes pojmy (`observe.cognate_matrix`) pro živé skupiny:
/// pojem, kde mají dvě skupiny tentýž dominantní kořen v různých tvarech, přispěje vzdáleností
/// tvarů. Pojmy se berou v pořadí názvů (`concept_rank`), takže se do buňky sčítá v pořadí jako
/// v Pythonu (jedna buňka dostane nejvýš jeden příspěvek za pojem).
pub fn cognate_totals(
    dominant: &Dominant<'_>,
    groups: usize,
    concept_rank: &[i32],
    forms: &FormTable<'_>,
    costs: &mut Costs<'_>,
) -> Vec<f64> {
    let mut total = vec![0.0_f64; groups * groups];
    // (pořadí pojmu, kořen, tvar, skupina)
    let mut entries: Vec<(i32, i32, u32, u32)> = Vec::new();
    for group in 0..groups {
        for at in dominant.range(group) {
            entries.push((
                concept_rank[dominant.concept[at] as usize],
                dominant.root[at],
                dominant.form[at] as u32,
                group as u32,
            ));
        }
    }
    entries.sort_unstable_by(|a, b| {
        (a.0, a.1)
            .cmp(&(b.0, b.1))
            .then_with(|| forms.get(a.2 as usize).cmp(forms.get(b.2 as usize)))
            .then(a.3.cmp(&b.3))
    });
    let mut scratch = Vec::new();
    let mut begin = 0;
    while begin < entries.len() {
        let mut end = begin + 1;
        while end < entries.len()
            && (entries[end].0, entries[end].1) == (entries[begin].0, entries[begin].1)
        {
            end += 1;
        }
        // Skupiny téhož (pojem, kořen) podle tvaru, tvary seřazené podle obsahu.
        let mut shapes: Vec<(usize, usize)> = Vec::new();
        let mut at = begin;
        while at < end {
            let mut to = at + 1;
            while to < end && entries[to].2 == entries[at].2 {
                to += 1;
            }
            shapes.push((at, to));
            at = to;
        }
        for (position, &(a_from, a_to)) in shapes.iter().enumerate() {
            for &(b_from, b_to) in &shapes[position + 1..] {
                let value = form_distance(
                    costs,
                    forms.get(entries[a_from].2 as usize),
                    forms.get(entries[b_from].2 as usize),
                    &mut scratch,
                );
                for first in &entries[a_from..a_to] {
                    for second in &entries[b_from..b_to] {
                        let (a, b) = (first.3 as usize, second.3 as usize);
                        total[a * groups + b] += value;
                        total[b * groups + a] += value;
                    }
                }
            }
        }
        begin = end;
    }
    total
}

#[cfg(test)]
mod tests {
    use super::*;

    fn costs_for(vectors: &[i8], width: usize) -> Costs<'_> {
        Costs::new(vectors, width, 6.0)
    }

    #[test]
    fn editacni_vzdalenost_je_vazena_rysy_a_symetricka() {
        // Tři hlásky se čtyřmi rysy: 0 a 1 se liší jedním rysem, 0 a 2 třemi.
        let vectors: Vec<i8> = vec![0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0];
        let mut costs = costs_for(&vectors, 4);
        let mut row = Vec::new();
        assert_eq!(form_distance(&mut costs, &[0, 1], &[0, 1], &mut row), 0.0);
        assert_eq!(form_distance(&mut costs, &[0], &[], &mut row), 1.0);
        let near = form_distance(&mut costs, &[0, 0], &[0, 1], &mut row);
        assert_eq!(near, (1.0 / 6.0) / 2.0);
        let far = form_distance(&mut costs, &[0, 0], &[0, 2], &mut row);
        assert!(near < far && far <= 1.0);
        assert_eq!(
            form_distance(&mut costs, &[0, 1, 2], &[2, 1], &mut row).to_bits(),
            form_distance(&mut costs, &[2, 1], &[0, 1, 2], &mut row).to_bits()
        );
    }

    #[test]
    fn slovnik_drzi_poradi_vkladani_a_slucuje_jako_dict() {
        let mut a = Sparse::from_entries(vec![5, 2], vec![1.0, 2.0]);
        let b = Sparse::from_entries(vec![9, 2, 1], vec![0.5, 0.25, 4.0]);
        a.merge(&b);
        assert_eq!(a.cols(), &[5, 2, 9, 1]);
        assert_eq!(a.vals(), &[1.0, 2.25, 0.5, 4.0]);
        assert_eq!(a.get(9), Some(0.5));
        assert_eq!(a.get(3), None);
    }

    #[test]
    fn deleni_se_zaokrouhlenim_jako_python() {
        assert_eq!(floor_divide(7.5, 2.0), 3.0);
        assert_eq!(floor_divide(-0.5, 2.0), -1.0);
        assert_eq!(floor_divide(0.0, 2.0), 0.0);
        assert_eq!(floor_divide(-6.0, 2.0), -3.0);
        assert_eq!(floor_divide(0.3, 0.1), 2.0);
    }

    #[test]
    fn parovy_soucet_f32_sedi_s_postupnym_pro_kratka_pole() {
        let values = [0.1_f32, 0.2, 0.3, 0.4, 0.5];
        let mut sequential = 0.0_f32;
        for value in values {
            sequential += value;
        }
        assert_eq!(pairwise_f32(&values), sequential);
        assert_eq!(pairwise_f32(&[]), 0.0);
    }

    #[test]
    fn kandidati_jsou_vazby_a_nejblizsi_sousedi() {
        // Pět bodů na přímce: každý sousedí s nejbližšími čtyřmi, tedy se všemi.
        let xs = [0.0, 1.0, 2.0, 3.0, 4.0];
        let ys = [0.0; 5];
        let slots: Vec<u32> = (0..5).collect();
        let found = candidates(&[(4, 4)], &slots, &xs, &ys);
        assert_eq!(found.len(), 10);
        assert_eq!(found[0], (0, 1));
        // Bez polohy zůstanou jen vazby.
        assert_eq!(candidates(&[(2, 1), (1, 2)], &[], &[], &[]), vec![(1, 2)]);
    }

    fn features_of(shares: Vec<f32>, dim: usize, squares: Vec<f64>) -> Features {
        let groups = squares.len();
        Features {
            groups,
            dim,
            shares,
            squares,
            forms: vec![Sparse::default(); groups],
            spread: vec![Sparse::default(); groups],
            lexical: 1.0,
        }
    }

    #[test]
    fn vazba_slouci_blizke_skupiny_do_prahu() {
        // Tři skupiny ve dvou rozměrech: 0 a 1 jsou blízko, 2 daleko.
        let rows = [[0.0_f32, 0.0], [0.1, 0.0], [3.0, 4.0]];
        let squares: Vec<f64> = rows
            .iter()
            .map(|row| row.iter().map(|&v| f64::from(v) * f64::from(v)).sum())
            .collect();
        let features = features_of(rows.iter().flatten().copied().collect(), 2, squares);
        let pairs = [(0, 1), (1, 2)];
        assert_eq!(
            linkage(&features, &pairs, 0.0, None),
            vec![vec![0], vec![1], vec![2]]
        );
        assert_eq!(
            linkage(&features, &pairs, 0.1, None),
            vec![vec![0, 1], vec![2]]
        );
        assert_eq!(linkage(&features, &pairs, 100.0, None), vec![vec![0, 1, 2]]);
    }

    #[test]
    fn hystereze_drzi_spojene_a_oddelene_skupiny() {
        let rows = [[0.0_f32, 0.0], [1.0, 0.0]];
        let squares = vec![0.0, 1.0];
        let features = features_of(rows.iter().flatten().copied().collect(), 2, squares);
        let pairs = [(0, 1)];
        // Vzdálenost je 0,5 · (0 + 1) − 0 = 0,5.
        let same = Hysteresis {
            labels: &[7, 7],
            margin: 0.02,
            form_gate: 0.0,
        };
        let apart = Hysteresis {
            labels: &[7, 8],
            margin: 0.02,
            form_gate: 0.0,
        };
        assert_eq!(
            linkage(&features, &pairs, 0.49, Some(&same)),
            vec![vec![0, 1]]
        );
        assert_eq!(
            linkage(&features, &pairs, 0.51, Some(&apart)),
            vec![vec![0], vec![1]]
        );
    }

    #[test]
    fn kategorie_tvaru_cisluji_podle_prvniho_vyskytu() {
        // Dvě skupiny, pojem 0 má kořen 5: skupina 0 tvar 0, skupina 1 tvar 1; pojem 1 kořen 6 shodný.
        let ptr = [0_i64, 2, 4];
        let concept = [0, 1, 0, 1];
        let root = [5, 6, 5, 6];
        let form = [0, 0, 1, 0];
        let dominant = Dominant {
            ptr: &ptr,
            concept: &concept,
            root: &root,
            form: &form,
        };
        let table = FormTable {
            ptr: &[0, 1, 2],
            flat: &[0, 1],
        };
        let vectors: Vec<i8> = vec![0, 1];
        let mut costs = Costs::new(&vectors, 1, 6.0);
        let found = categories(&dominant, &[0, 1], &table, &mut costs);
        // Kategorie: (0,5,0)=0, (1,6,0)=1, (0,5,1)=2.
        assert_eq!(found.forms[0].cols(), &[0, 1]);
        assert_eq!(found.forms[1].cols(), &[2, 1]);
        assert_eq!(found.spread[0].cols(), &[2]);
        assert_eq!(found.spread[1].cols(), &[0]);
        assert_eq!(found.spread[0].vals(), found.spread[1].vals());
        assert!(found.spread[0].vals()[0] > 0.0);
    }

    #[test]
    fn vlozeni_je_nula_pod_prahem_a_cela_hodnota_nad_nim() {
        let embedding = Embedding::new(1.0);
        let mut out = [0.0_f32; INTERVALS];
        embedding.write(0.0, &mut out);
        assert!(out.iter().all(|&value| value == 0.0));
        embedding.write(1.0, &mut out);
        assert!(out.iter().zip(&embedding.roots).all(|(a, b)| a == b));
    }

    #[test]
    fn sdot_pocita_skalarni_soucin() {
        let a = [1.0_f32, 2.0, 3.0];
        let b = [4.0_f32, 5.0, 6.0];
        assert_eq!(dot(&a, &b), 32.0);
        assert_eq!(dot(&[], &[]), 0.0);
    }

    #[test]
    fn matice_vzdalenosti_je_symetricka_a_nezavisla_na_poctu_vlaken() {
        // Jeden blok, 3 řádky, 5 skupin, 4 sloty.
        let (rows, groups, capacity) = (3, 5, 4);
        let freqs: Vec<f64> = (0..rows * groups * capacity)
            .map(|index| ((index * 37 + 11) % 100) as f64 / 100.0)
            .collect();
        let present = vec![true; rows * groups];
        let selected = [0_i64, 1, 2];
        let ranks = [0_i64, 1, 2];
        let pool = PoolView {
            freqs: &freqs,
            present: &present,
            groups,
            capacity,
            rows: &selected,
            ranks: &ranks,
        };
        let one = distance_totals(std::slice::from_ref(&pool), groups, DISTANCE_CHUNK, 1);
        let three = distance_totals(std::slice::from_ref(&pool), groups, DISTANCE_CHUNK, 3);
        assert_eq!(
            one.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
            three.iter().map(|v| v.to_bits()).collect::<Vec<_>>()
        );
        for a in 0..groups {
            assert_eq!(one[a * groups + a], 0.0);
            for b in 0..groups {
                assert_eq!(one[a * groups + b].to_bits(), one[b * groups + a].to_bits());
            }
        }
        assert!(one[1] > 0.0);
        // Po blocích po jednom řádku vyjde jiné pořadí sčítání, ale stejná velikost.
        let small = distance_totals(std::slice::from_ref(&pool), groups, 1, 1);
        assert!((small[1] - one[1]).abs() < 1e-5);
    }

    #[test]
    fn rysy_vybiraji_jen_promenlive_sloupce() {
        // Jeden řádek, dva sloty, tři skupiny; slot 0 se liší, slot 1 je všude stejný.
        let freqs = [0.2, 0.5, 0.4, 0.5, 0.9, 0.5];
        let present = [true; 3];
        let rows = [0_i64];
        let ranks = [0_i64];
        let pool = PoolView {
            freqs: &freqs,
            present: &present,
            groups: 3,
            capacity: 2,
            rows: &rows,
            ranks: &ranks,
        };
        let features = embedded_features(std::slice::from_ref(&pool), &[0, 1, 2], 4, 1);
        assert_eq!(features.dim, INTERVALS);
        assert_eq!(features.shares.len(), 3 * INTERVALS);
        assert_eq!(features.lexical, 4.0);
        assert!(features.squares.iter().all(|&square| square > 0.0));
        // Jedna skupina: žádný sloupec nevaruje.
        assert_eq!(
            embedded_features(std::slice::from_ref(&pool), &[1], 1, 1).dim,
            0
        );
    }
}
