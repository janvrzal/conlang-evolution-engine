//! Přenos: míšení (`hear`) a výběr, drift a ustálení (`settle`) bloku živých proměnných.
//!
//! Zrcadlo funkcí `cee.v2.phases_transmission`. Pole mají tvar (proměnné ×
//! skupiny × sloty) po řádcích za sebou a stav bloku se nikde nemění: funkce
//! dostanou vstupy a vrátí nová pole.
//!
//! **Pořadí sčítání je součástí smlouvy** (bitová shoda s Pythonem):
//!
//! - míšení sčítá součiny `váha × podíl` pro každou cílovou skupinu striktně
//!   zleva doprava podle vzestupného čísla zdroje; zdroje s nulovou vahou se
//!   přeskočí (nulový součin součet nezmění). Součin se zaokrouhlí zvlášť a
//!   pak se přičte, Rust žádné sloučené násobení se sčítáním (FMA) nedělá;
//! - `normalized` sčítá podíly slotů zleva doprava po seřazení (od tří slotů);
//! - transcendentní funkce (`exp` výběru, `log` a `cos` šumu driftu) dává
//!   knihovna systému stejně jako `numpy` jen na strojích, kde to ověří zkouška
//!   (`cee.v2.native.libm_matches`); jinak `settle` v Rustu Python nepoužije.
//!   Odmocnina, dělení, součin a součet jsou přesné (IEEE), takže tam žádný rozdíl není;
//! - vlákna dělí jen proměnné (osa 0): každý úsek zapisuje do vlastního výstupu
//!   a nic se mezi vlákny nesčítá, výsledek je bitově stejný pro libovolný počet vláken.

// Indexované smyčky přes sloty jsou tu záměrně: pořadí operací je součástí smlouvy.
#![allow(clippy::needless_range_loop)]

/// Řídké vazby jedné komponenty sítě: pro každého cíle (řádek matice) jeho
/// nenulové zdroje vzestupně podle čísla zdroje.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Links {
    /// `start[i]..start[i + 1]` jsou buňky řádku `i` (délka `řádky + 1`).
    pub start: Vec<usize>,
    /// Číslo zdroje uvnitř komponenty.
    pub source: Vec<usize>,
    pub weight: Vec<f64>,
}

impl Links {
    /// Nenulové buňky husté čtvercové matice `size × size` (po řádcích).
    pub fn from_dense(matrix: &[f64], size: usize) -> Links {
        let mut links = Links {
            start: Vec::with_capacity(size + 1),
            ..Links::default()
        };
        links.start.push(0);
        for row in matrix.chunks_exact(size.max(1)).take(size) {
            for (source, &weight) in row.iter().enumerate() {
                if weight != 0.0 {
                    links.source.push(source);
                    links.weight.push(weight);
                }
            }
            links.start.push(links.source.len());
        }
        links
    }

    pub fn rows(&self) -> usize {
        self.start.len().saturating_sub(1)
    }

    pub fn is_empty(&self) -> bool {
        self.source.is_empty()
    }
}

/// Propojená komponenta: sloupce skupin v bloku a jejich vazby.
#[derive(Debug, Clone)]
pub struct Component {
    pub members: Vec<usize>,
    pub links: Links,
}

/// Tvar bloku: proměnné, skupiny a sloty (u pole bez slotů je `slots` 1).
#[derive(Debug, Clone, Copy)]
pub struct Shape {
    pub variables: usize,
    pub groups: usize,
    pub slots: usize,
}

impl Shape {
    pub fn cells(&self) -> usize {
        self.variables * self.groups * self.slots
    }
}

/// `out[v, člen i] += Σ_j váha(i, j) × values[v, člen j]` pro jednu komponentu,
/// sčítáno postupně přes zdroje podle vzestupného čísla (viz začátek modulu).
/// Pole `values` a `out` mají osy (proměnné, skupiny, `width`); `out` se přičítá.
fn mix_component(
    out: &mut [f64],
    values: &[f64],
    variables: usize,
    groups: usize,
    width: usize,
    component: &Component,
) {
    let Links {
        start,
        source,
        weight,
    } = &component.links;
    // Zdroj, který nemá v žádném slotu nic, do součtu nepřidá nic (`w × 0` je +0), takže se
    // přeskočí a ostatním se projdou jen sloty po poslední nenulový.
    let mut extent = vec![0usize; component.members.len()];
    for variable in 0..variables {
        let plane = variable * groups;
        for (index, &member) in component.members.iter().enumerate() {
            let from = (plane + member) * width;
            extent[index] = values[from..from + width]
                .iter()
                .rposition(|&value| value != 0.0)
                .map_or(0, |last| last + 1);
        }
        for (row, &target) in component.members.iter().enumerate() {
            let at = (plane + target) * width;
            let (first, last) = (start[row], start[row + 1]);
            for index in first..last {
                let size = extent[source[index]];
                if size == 0 {
                    continue;
                }
                let from = (plane + component.members[source[index]]) * width;
                let w = weight[index];
                for slot in 0..size {
                    out[at + slot] += w * values[from + slot];
                }
            }
        }
    }
}

/// Vazby uvnitř jazyka a osamocené skupiny: `blocks` jsou matice komponent
/// pro `members`, `alone` skupiny s vahou `alone_weight` se učí jen samy od sebe.
pub struct Network<'a> {
    pub components: &'a [Component],
    pub alone: &'a [usize],
    pub alone_weight: &'a [f64],
}

/// Vazby mezi jazyky jednoho kanálu: filtr přenositelnosti po proměnných bloku
/// a bloky matice po komponentách (ve stejném pořadí jako komponenty sítě).
pub struct Flow<'a> {
    pub factor: &'a [f64],
    pub components: &'a [Component],
}

/// Vstup mimo vazby sítě (interference, čtení, škola, liturgie): učící se skupina
/// `learners[i]` přebírá podíl `factor[v] × weights[i]` (nejvýš celý) od `sources[i]`.
pub struct Channel<'a> {
    pub factor: &'a [f64],
    pub learners: &'a [usize],
    pub sources: &'a [usize],
    pub weights: &'a [f64],
}

/// Rozdělí `variables` proměnných na nejvýš `threads` souvislých úseků `[od, do)`
/// (výsledek nezávisí na datech, jen na počtech).
pub fn ranges(variables: usize, threads: usize) -> Vec<(usize, usize)> {
    let parts = threads.clamp(1, variables.max(1));
    let (base, extra) = (variables / parts, variables % parts);
    let mut start = 0;
    (0..parts)
        .map(|part| {
            let stop = start + base + usize::from(part < extra);
            let range = (start, stop);
            start = stop;
            range
        })
        .collect()
}

/// Pracovní pole jednoho vlákna míšení (drží je objekt a znovu je používá).
#[derive(Default)]
pub struct HearScratch {
    mixed: Vec<f64>,
    mixed_weight: Vec<f64>,
    weight: Vec<f64>,
    present_weight: Vec<f64>,
}

/// Co skupiny slyší (`phases_transmission.hear`) pro proměnné `[first, last)`; `heard`
/// je jejich výstup (`(last − first) × skupiny × sloty`). Vstupy jsou celé bloky.
#[allow(clippy::too_many_arguments)]
pub fn hear_range(
    shape: Shape,
    range: (usize, usize),
    current: &[f64],
    present: &[bool],
    network: &Network<'_>,
    flows: &[Flow<'_>],
    channels: &[Channel<'_>],
    scratch: &mut HearScratch,
    heard: &mut [f64],
) {
    let Shape { groups, slots, .. } = shape;
    let (first, last) = range;
    let count = last - first;
    let current = &current[first * groups * slots..last * groups * slots];
    let present = &present[first * groups..last * groups];
    let HearScratch {
        mixed,
        mixed_weight,
        weight,
        present_weight,
    } = scratch;
    present_weight.clear();
    present_weight.extend(present.iter().map(|&flag| f64::from(flag)));
    weight.clear();
    weight.resize(count * groups, 0.0);
    heard.fill(0.0);
    // Osamocené skupiny se učí jen samy od sebe.
    for variable in 0..count {
        for (&group, &alone) in network.alone.iter().zip(network.alone_weight) {
            let at = (variable * groups + group) * slots;
            for slot in 0..slots {
                heard[at + slot] = alone * current[at + slot];
            }
            weight[variable * groups + group] = alone * present_weight[variable * groups + group];
        }
    }
    for component in network.components {
        mix_component(heard, current, count, groups, slots, component);
        mix_component(weight, present_weight, count, groups, 1, component);
    }
    for flow in flows {
        // Vazby mezi jazyky: jen tolik, kolik filtr přenositelnosti propustí.
        mixed.clear();
        mixed.resize(heard.len(), 0.0);
        mixed_weight.clear();
        mixed_weight.resize(weight.len(), 0.0);
        for component in flow.components {
            mix_component(mixed, current, count, groups, slots, component);
            mix_component(mixed_weight, present_weight, count, groups, 1, component);
        }
        for variable in 0..count {
            let factor = flow.factor[first + variable];
            let cells = variable * groups * slots..(variable + 1) * groups * slots;
            for (target, add) in heard[cells.clone()].iter_mut().zip(&mixed[cells]) {
                *target += factor * add;
            }
            let cells = variable * groups..(variable + 1) * groups;
            for (target, add) in weight[cells.clone()].iter_mut().zip(&mixed_weight[cells]) {
                *target += factor * add;
            }
        }
    }
    for (cell, &total) in weight.iter().enumerate() {
        let chunk = &mut heard[cell * slots..(cell + 1) * slots];
        if total > 0.0 {
            for value in chunk {
                *value /= total;
            }
        } else {
            chunk.fill(0.0);
        }
    }
    for channel in channels {
        // Váha domény nad 1 smí podíl zvýšit nejvýš na celý vstup.
        for variable in 0..count {
            let factor = channel.factor[first + variable];
            for ((&learner, &source), &weight) in channel
                .learners
                .iter()
                .zip(channel.sources)
                .zip(channel.weights)
            {
                let share = if present[variable * groups + source] {
                    (factor * weight).min(1.0)
                } else {
                    0.0
                };
                let at = (variable * groups + learner) * slots;
                let from = (variable * groups + source) * slots;
                for slot in 0..slots {
                    heard[at + slot] =
                        (1.0 - share) * heard[at + slot] + share * current[from + slot];
                }
            }
        }
    }
}

/// Míšení celého bloku na `threads` vláknech (po úsecích proměnných).
#[allow(clippy::too_many_arguments)]
pub fn hear(
    shape: Shape,
    current: &[f64],
    present: &[bool],
    network: &Network<'_>,
    flows: &[Flow<'_>],
    channels: &[Channel<'_>],
    scratch: &mut Vec<HearScratch>,
    threads: usize,
    heard: &mut [f64],
) {
    let parts = ranges(shape.variables, threads);
    if scratch.len() < parts.len() {
        scratch.resize_with(parts.len(), HearScratch::default);
    }
    let stride = shape.groups * shape.slots;
    if parts.len() == 1 {
        hear_range(
            shape,
            parts[0],
            current,
            present,
            network,
            flows,
            channels,
            &mut scratch[0],
            heard,
        );
        return;
    }
    std::thread::scope(|scope| {
        let mut rest = heard;
        for (&range, work) in parts.iter().zip(scratch.iter_mut()) {
            let (mine, tail) = rest.split_at_mut((range.1 - range.0) * stride);
            rest = tail;
            scope.spawn(move || {
                hear_range(
                    shape, range, current, present, network, flows, channels, work, mine,
                );
            });
        }
    });
}

/// Podíly slotů dělené součtem (`phases_transmission.normalized`) po buňkách
/// poslední osy délky `slots`; buňka s nekladným součtem dostane `fallback`.
///
/// Součet seřazených hodnot nezávisí na tom, ve kterých slotech varianty leží;
/// od tří slotů se řadí vzestupně a sčítá se striktně zleva doprava.
pub fn normalized(array: &[f64], fallback: &[f64], slots: usize) -> Vec<f64> {
    let mut out = vec![0.0; array.len()];
    let mut sorted = vec![0.0; slots];
    for (cell, chunk) in array.chunks_exact(slots.max(1)).enumerate() {
        let range = cell * slots..(cell + 1) * slots;
        normalize_cell(
            chunk,
            &fallback[range.clone()],
            &mut out[range],
            &mut sorted,
        );
    }
    out
}

/// Jedna buňka (podíly slotů) pro `normalized`; `sorted` je pracovní pole stejné délky.
fn normalize_cell(array: &[f64], fallback: &[f64], out: &mut [f64], sorted: &mut [f64]) {
    let mut total;
    if array.len() <= 2 {
        total = array[0] + 0.0;
        for &value in &array[1..] {
            total += value;
        }
    } else {
        // Nuly součet nemění, takže se řadí jen nenulové sloty (většina slotů je prázdná).
        let mut count = 0;
        for &value in array {
            if value != 0.0 {
                sorted[count] = value;
                count += 1;
            }
        }
        if count == 0 {
            total = 0.0;
        } else {
            let live = &mut sorted[..count];
            live.sort_by(|a, b| a.total_cmp(b));
            total = live[0] + 0.0;
            for &value in &live[1..] {
                total += value;
            }
        }
    }
    if total > 0.0 {
        for (target, &value) in out.iter_mut().zip(array) {
            *target = value / total;
        }
    } else {
        out.copy_from_slice(fallback);
    }
}

pub fn splitmix64(value: u64) -> u64 {
    let mut value = value.wrapping_add(0x9E37_79B9_7F4A_7C15);
    value = (value ^ (value >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    value = (value ^ (value >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    value ^ (value >> 31)
}

const FLOAT53: f64 = (1_u64 << 53) as f64;

/// Hodnota N(0, 1) závislá jen na páru klíčů (`rng.hash_normal` s `pairwise`):
/// Box–Muller z dvou čísel splitmixu. Používá `ln` a `cos` knihovny systému.
pub fn hash_normal(row_key: u64, column_key: u64) -> f64 {
    hash_normal_mixed(row_key, splitmix64(column_key))
}

/// Totéž co `hash_normal`, ale s už promíchaným klíčem sloupce (`splitmix64(klíč)`), aby se při
/// mnoha řádcích na jeden sloupec míchal jednou.
pub fn hash_normal_mixed(row_key: u64, mixed_column: u64) -> f64 {
    let first = splitmix64(row_key ^ mixed_column);
    let second = splitmix64(first);
    let uniform_a = ((first >> 11) as f64 + 0.5) / FLOAT53;
    let uniform_b = ((second >> 11) as f64 + 0.5) / FLOAT53;
    (-2.0 * uniform_a.ln()).sqrt() * (2.0 * std::f64::consts::PI * uniform_b).cos()
}

/// Čísla přenosu a osa skupin pro `settle`.
pub struct Cohorts<'a> {
    pub drift_scale: &'a [f64],
    pub renewal: &'a [f64],
    pub loss_floor: &'a [f64],
    pub row_keys: &'a [u64],
    pub selection: f64,
    pub kappa: f64,
    pub adult_rate: f64,
    pub establish_threshold: f64,
}

/// Stav bloku, který `settle` čte (celé bloky).
pub struct State<'a> {
    pub current: &'a [f64],
    pub previous: &'a [f64],
    pub present: &'a [bool],
    pub heard: &'a [f64],
    /// Tlaky na varianty; bez nich (`None`) jsou nulové.
    pub fitness: Option<&'a [f64]>,
    /// Klíče variant ve slotech, `proměnné × sloty`.
    pub slot_keys: &'a [u64],
}

/// Pracovní pole jedné buňky `settle` (délka = počet slotů).
#[derive(Default)]
struct CellScratch {
    selected: Vec<f64>,
    weighted: Vec<f64>,
    grown: Vec<f64>,
    children: Vec<f64>,
    tail: Vec<f64>,
    sorted: Vec<f64>,
    /// Sloty nosiče buňky (vzestupně) a kompaktní kopie hodnot nosiče.
    support: Vec<usize>,
    heard: Vec<f64>,
    current: Vec<f64>,
    result: Vec<f64>,
}

/// Nové frekvence a trendová základna proměnných `[first, last)` (`phases_transmission.settle`):
/// výběr `exp(selection × fitness)`, trend, Wright–Fisherův drift, děti a dospělí,
/// zánik pod prahem, ustálení. Výstupy `updated` a `baseline` jsou jen pro tyto proměnné.
pub fn settle_range(
    shape: Shape,
    range: (usize, usize),
    state: &State<'_>,
    cohorts: &Cohorts<'_>,
    updated: &mut [f64],
    baseline: &mut [f64],
) {
    let Shape { groups, slots, .. } = shape;
    let mut scratch = CellScratch::default();
    for field in [
        &mut scratch.selected,
        &mut scratch.weighted,
        &mut scratch.grown,
        &mut scratch.children,
        &mut scratch.tail,
        &mut scratch.sorted,
        &mut scratch.heard,
        &mut scratch.current,
        &mut scratch.result,
    ] {
        field.resize(slots, 0.0);
    }
    let offset = range.0 * groups * slots;
    for variable in range.0..range.1 {
        for group in 0..groups {
            let cell = variable * groups + group;
            let from = cell * slots;
            let to = from - offset;
            settle_cell(
                &CellIn {
                    current: &state.current[from..from + slots],
                    previous: &state.previous[from..from + slots],
                    heard: &state.heard[from..from + slots],
                    fitness: state.fitness.map(|fitness| &fitness[from..from + slots]),
                    slot_keys: &state.slot_keys[variable * slots..(variable + 1) * slots],
                    present: state.present[cell],
                    group,
                },
                cohorts,
                &mut scratch,
                &mut updated[to..to + slots],
                &mut baseline[to..to + slots],
            );
        }
    }
}

struct CellIn<'a> {
    current: &'a [f64],
    previous: &'a [f64],
    heard: &'a [f64],
    fitness: Option<&'a [f64]>,
    slot_keys: &'a [u64],
    present: bool,
    group: usize,
}

fn settle_cell(
    cell: &CellIn<'_>,
    cohorts: &Cohorts<'_>,
    scratch: &mut CellScratch,
    updated: &mut [f64],
    baseline: &mut [f64],
) {
    let slots = cell.current.len();
    let group = cell.group;
    updated.fill(0.0);
    baseline.fill(0.0);
    let CellScratch {
        selected,
        weighted,
        grown,
        children,
        tail,
        sorted,
        support,
        heard,
        current,
        result,
    } = scratch;
    // Počítá se jen s nosičem buňky: sloty, kde je něco z `current`, `previous` a `heard`.
    // Ostatní sloty dávají ve všech krocích přesně nulu a součet sloty s nulou nemění,
    // takže výsledky jsou stejné jako při výpočtu přes všechny sloty.
    support.clear();
    for slot in 0..slots {
        if cell.current[slot] != 0.0 || cell.previous[slot] != 0.0 || cell.heard[slot] != 0.0 {
            support.push(slot);
        }
    }
    let n = support.len();
    if n == 0 {
        return;
    }
    for (at, &slot) in support.iter().enumerate() {
        heard[at] = cell.heard[slot];
        current[at] = cell.current[slot];
        // Neslyšená varianta má váhu nulovou, ať je tlak jakýkoli (exp je konečné).
        weighted[at] = if heard[at] == 0.0 {
            0.0
        } else {
            let pressure = cell.fitness.map_or(0.0, |fitness| fitness[slot]);
            heard[at] * (cohorts.selection * pressure).exp()
        };
    }
    normalize_cell(&weighted[..n], &heard[..n], &mut selected[..n], sorted);
    for (at, &slot) in support.iter().enumerate() {
        let share = selected[at];
        let spread = share * (1.0 - share);
        // Varianta, kterou kohorta vůbec neslyší, nemůže driftem vzniknout; šum jen tam, kde soutěží varianty.
        let drift = if spread > 0.0 {
            hash_normal(cohorts.row_keys[group], cell.slot_keys[slot])
                * cohorts.drift_scale[group]
                * spread.sqrt()
        } else {
            0.0
        };
        let trend = cohorts.kappa * (cell.current[slot] - cell.previous[slot]);
        grown[at] = (share + trend + drift).max(0.0);
    }
    normalize_cell(&grown[..n], &selected[..n], &mut children[..n], sorted);
    let renewed = cohorts.renewal[group];
    let floor = cohorts.loss_floor[group];
    for at in 0..n {
        let adults = current[at] + cohorts.adult_rate * (heard[at] - current[at]);
        let mixed = (1.0 - renewed) * adults + renewed * children[at];
        tail[at] = if mixed < floor { 0.0 } else { mixed };
    }
    normalize_cell(&tail[..n], &current[..n], &mut result[..n], sorted);
    // Vedoucí varianta (první maximum); nad prahem a pod celou se ustálí a zbude sama.
    let mut leader = 0;
    for at in 1..n {
        if result[at] > result[leader] {
            leader = at;
        }
    }
    let top = result[leader];
    if top >= cohorts.establish_threshold && top < 1.0 {
        for (at, value) in result[..n].iter_mut().enumerate() {
            *value = if at == leader { 1.0 } else { 0.0 };
        }
    }
    if !cell.present {
        result[..n].fill(0.0);
    }
    let mut alive = 0;
    for (at, &slot) in support.iter().enumerate() {
        updated[slot] = result[at];
        baseline[slot] = if result[at] > 0.0 {
            alive += 1;
            cell.previous[slot] + renewed * (cell.current[slot] - cell.previous[slot])
        } else {
            0.0
        };
    }
    // Skupina s jedinou variantou nemá trend: základna je její podíl.
    if alive == 1 {
        baseline.copy_from_slice(updated);
    }
}

/// `settle` celého bloku na `threads` vláknech (po úsecích proměnných).
pub fn settle(
    shape: Shape,
    state: &State<'_>,
    cohorts: &Cohorts<'_>,
    threads: usize,
    updated: &mut [f64],
    baseline: &mut [f64],
) {
    let parts = ranges(shape.variables, threads);
    let stride = shape.groups * shape.slots;
    if parts.len() == 1 {
        settle_range(shape, parts[0], state, cohorts, updated, baseline);
        return;
    }
    std::thread::scope(|scope| {
        let (mut rest_updated, mut rest_baseline) = (updated, baseline);
        for &range in &parts {
            let size = (range.1 - range.0) * stride;
            let (mine_updated, tail_updated) = rest_updated.split_at_mut(size);
            let (mine_baseline, tail_baseline) = rest_baseline.split_at_mut(size);
            (rest_updated, rest_baseline) = (tail_updated, tail_baseline);
            scope.spawn(move || {
                settle_range(shape, range, state, cohorts, mine_updated, mine_baseline);
            });
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn soucet_je_zleva_doprava_a_nulove_vahy_se_preskoci() {
        // Tři skupiny v jedné komponentě; skupina 0 se učí z 0 a 2, váha na skupinu 1 je nulová.
        let matrix = [0.5, 0.0, 0.5, 0.25, 0.5, 0.25, 0.0, 0.0, 1.0];
        let links = Links::from_dense(&matrix, 3);
        assert_eq!(links.start, vec![0, 2, 5, 6]);
        assert_eq!(links.source, vec![0, 2, 0, 1, 2, 2]);
        let component = Component {
            members: vec![0, 1, 2],
            links,
        };
        let current = [0.1, 0.2, 0.3, 0.0, 0.0, 0.0];
        let present = [true; 3];
        let network = Network {
            components: &[component],
            alone: &[],
            alone_weight: &[],
        };
        let shape = Shape {
            variables: 1,
            groups: 3,
            slots: 2,
        };
        let mut heard = vec![0.0; 6];
        hear(
            shape,
            &current,
            &present,
            &network,
            &[],
            &[],
            &mut Vec::new(),
            1,
            &mut heard,
        );
        // Skupina 0 se učí ze skupin 0 a 2 (součet vah 1); skupina 2 nic nemá.
        assert_eq!(heard[0], 0.5 * 0.1 + 0.5 * 0.0);
        assert_eq!(heard[1], 0.5 * 0.2 + 0.5 * 0.0);
        assert_eq!(heard[2], 0.25 * 0.1 + 0.5 * 0.3 + 0.25 * 0.0);
    }

    #[test]
    fn vlakna_deli_jen_promenne_a_vysledek_je_stejny() {
        let (variables, groups, slots) = (7, 5, 3);
        let shape = Shape {
            variables,
            groups,
            slots,
        };
        let cells = shape.cells();
        let wave = |scale: f64| -> Vec<f64> {
            (0..cells)
                .map(|index| ((index * 37 % 11) as f64 + scale) / 20.0)
                .collect()
        };
        let current: Vec<f64> = wave(0.5);
        let previous = wave(0.25);
        let heard = wave(0.75);
        let fitness: Vec<f64> = wave(-0.4);
        let present = vec![true; variables * groups];
        let slot_keys: Vec<u64> = (0..variables * slots).map(|i| 1000 + i as u64).collect();
        let row_keys: Vec<u64> = (0..groups).map(|i| 77 + i as u64).collect();
        let (drift, renewal, floor) = (vec![0.05; groups], vec![0.4; groups], vec![0.01; groups]);
        let state = State {
            current: &current,
            previous: &previous,
            present: &present,
            heard: &heard,
            fitness: Some(&fitness),
            slot_keys: &slot_keys,
        };
        let cohorts = Cohorts {
            drift_scale: &drift,
            renewal: &renewal,
            loss_floor: &floor,
            row_keys: &row_keys,
            selection: 1.0,
            kappa: 0.3,
            adult_rate: 0.05,
            establish_threshold: 0.9,
        };
        let mut reference = (vec![0.0; cells], vec![0.0; cells]);
        settle(
            shape,
            &state,
            &cohorts,
            1,
            &mut reference.0,
            &mut reference.1,
        );
        for threads in [2, 3, 7, 20] {
            let mut found = (vec![0.0; cells], vec![0.0; cells]);
            settle(shape, &state, &cohorts, threads, &mut found.0, &mut found.1);
            assert_eq!(found, reference, "vlákna: {threads}");
        }
    }

    #[test]
    fn rozdeleni_na_useky_pokryje_vsechny_promenne() {
        assert_eq!(ranges(7, 3), vec![(0, 3), (3, 5), (5, 7)]);
        assert_eq!(ranges(2, 8), vec![(0, 1), (1, 2)]);
        assert_eq!(ranges(0, 4), vec![(0, 0)]);
    }

    #[test]
    fn normalizace_radi_od_tri_slotu_a_pri_nulovem_souctu_vrati_zalohu() {
        let out = normalized(
            &[0.1, 0.2, 0.7, 0.0, 0.0, 0.0],
            &[1.0, 0.0, 0.0, 0.5, 0.25, 0.25],
            3,
        );
        assert_eq!(out[..3], [0.1 / 1.0, 0.2 / 1.0, 0.7 / 1.0].map(|v: f64| v));
        assert_eq!(out[3..], [0.5, 0.25, 0.25]);
    }

    #[test]
    fn hash_normal_sedi_s_pythonem() {
        // numpy: hash_normal([1], [2], pairwise=True) = -0.470445890630542
        assert_eq!(
            hash_normal(1, 2).to_bits(),
            (-0.470445890630542_f64).to_bits()
        );
    }
}
