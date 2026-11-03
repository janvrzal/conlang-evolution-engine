//! Tlaky na varianty v Rustu: zrcadlo tříd z `cee.v2.pressures` (B3b).
//!
//! Vstupem kusu bloku (řádky = proměnné, skupiny, sloty) jsou současné podíly, slyšené podíly
//! a popisy řádků a kroku; výstupem je součet vážených tlaků každé buňky, v pořadí tlaků
//! daném plánem druhu proměnné (`pressures_by_kind`). Čísla jsou počítána stejnými výrazy
//! jako v Pythonu (bez sloučeného násobení se sčítáním, žádná nová transcendentní funkce
//! kromě `ln`, `cos` v `hash_normal`, na kterou se přechod ověřuje `libm_matches`), takže jsou
//! bit po bitu stejná.
//!
//! Výpočet má dvě fáze:
//!
//! 1. **Podklady** (`gather`, jedno vlákno, mění stav): hodnocení procesů a tvarů v dosažených
//!    buňkách, podíl koncových souhlásek a tabulky vlastníků tvarů pro lexikální jasnost. Co
//!    chybí, zapíše do `Needs`; volající dodá a kus spočítá znovu.
//! 2. **Skóre** (`score`, jen čtení): každý řádek samostatně do vlastní části výstupu, takže se
//!    dělí po souvislých úsecích řádků na vlákna beze změny výsledku.
//!
//! Tlaky, které čtou objekty světa (konstrukce, škola a tabu), dodává Python jako řídké položky
//! (`Overlay`) vypočtené ze stavu na začátku kroku; Rust je přičte na své místo v pořadí tlaků.

use crate::assess_index::{AssessIndex, Inputs, Needs};
use crate::bank::Bank;
use crate::form_assess::{FormCtx, FormInputs};
use crate::morphology_index::MorphIndex;
use crate::transmission::{hash_normal_mixed, splitmix64};

/// Čísla druhů proměnných (pořadí `cee.v2.tables.VARIABLE_KINDS`).
pub const PROCESS: u8 = 0;
pub const LEXICAL: u8 = 1;
pub const FORM: u8 = 2;
pub const CONSTRUCTION: u8 = 3;
pub const PROSODY: u8 = 4;
pub const KINDS: usize = 5;

/// Čísla tlaků (viz `cee.v2.pressures_native.PRESSURE_IDS`).
pub mod id {
    pub const ACTUATION: u8 = 0;
    pub const AMBIGUITY: u8 = 1;
    pub const APPEAL: u8 = 2;
    pub const ARTICULATION: u8 = 3;
    pub const CLARITY: u8 = 4;
    pub const CONFORMITY: u8 = 5;
    pub const CONSERVATION: u8 = 6;
    pub const DISPERSION: u8 = 7;
    pub const DISTINCTIVENESS: u8 = 8;
    pub const ECONOMY: u8 = 9;
    pub const ENTRENCHMENT: u8 = 10;
    pub const EXPRESSIVITY: u8 = 11;
    pub const FUNCTIONAL_LOAD: u8 = 12;
    pub const FUSION: u8 = 13;
    pub const LEXICAL_ACTUATION: u8 = 14;
    pub const LEXICAL_CLARITY: u8 = 15;
    pub const LEARNABILITY: u8 = 16;
    pub const MOTIVATION: u8 = 17;
    pub const NORM: u8 = 18;
    pub const PHONOTACTICS: u8 = 19;
    pub const TABOO: u8 = 20;
    pub const TEACHABILITY: u8 = 21;
    pub const UNIFORMITY: u8 = 22;
    /// Počet tlaků.
    pub const COUNT: usize = 23;
}

/// Příznaky řádku procesu a analogické změny.
pub const REDUCTIVE_UNSTRESSED: u8 = 1;
pub const APOCOPE: u8 = 2;
pub const LEVEL: u8 = 4;
pub const LEXEME_WIDE: u8 = 8;

/// Rozpětí náhodného ocenění změny (`Actuation.spread`).
const ACTUATION_SPREAD: f64 = 0.25;
/// Síla tlaku učitelnosti (`Teachability.strength`).
const TEACHABILITY: f64 = 1.0;

/// Tlaky každého druhu proměnných: (číslo tlaku, váha) v pořadí sčítání.
#[derive(Default, Clone)]
pub struct Plan {
    pub kinds: [Vec<(u8, f64)>; KINDS],
}

/// Konstanty kroku z `Parameters`.
#[derive(Clone, Copy, Default)]
pub struct Params {
    pub tick: i64,
    /// Má svět tabulku hlásek (jinak jsou lexikální tlaky nulové).
    pub has_table: bool,
    pub clarity_short_factor: f64,
    pub functional_load_scale: f64,
    pub dispersion_factor: f64,
    pub coda_tolerance_scale: f64,
    pub stress_strength_multiplier: f64,
}

/// Vlastník tvaru pro lexikální jasnost: (tvar, pojem, kořen).
pub type Owner = (i32, i64, i64);

/// Neměnné vstupy kroku (sdílené bloky).
pub struct StepConst<'a> {
    pub params: Params,
    /// Podle pozice skupiny: silný přízvuk, podíl L2 mluvčích a klíč ocenění změn v epoše.
    pub strong: &'a [bool],
    pub l2: &'a [f64],
    pub actuation_keys: &'a [u64],
    /// Dominantní kořeny podle čísla pojmu (−1 = žádný), podle pozice skupiny.
    pub roots: Vec<&'a [i32]>,
    /// Seřazené klíče příbuzných dvojic pojmů.
    pub related: &'a [i64],
    /// Sloupce tabulky variant podle čísla varianty a klíče ocenění variant.
    pub variant_change: &'a [i32],
    pub variant_morpheme: &'a [i32],
    pub variant_origin: &'a [i32],
    pub variant_appeal: &'a [f64],
    pub variant_keys: &'a [u64],
    /// Váha původu slova podle kódu původu; poslední prvek (0) platí pro chybějící původ.
    pub origin_weights: &'a [f64],
    /// Morfologický stav kódů (koncovky a jejich podoby) a pole pro hodnocení tvarů.
    pub morph: &'a MorphIndex,
    pub forms: FormInputs<'a>,
}

/// Měnitelný stav kroku sdílený bloky: paměť odpovědí, tabulky vlastníků, podíly koncových souhlásek.
#[derive(Default)]
pub struct StepState {
    pub memo: crate::assess_index::Memo,
    pub owners: Vec<Option<Vec<Owner>>>,
    /// Podíl slov s koncovou souhláskou podle pozice skupiny (NaN = ještě neznámý).
    pub coda: Vec<f64>,
}

/// Řídké položky tlaků, které počítá Python: (číslo tlaku, buňka v bloku, hodnota), vzestupně podle buňky.
#[derive(Default, Clone, Copy)]
pub struct Overlay<'a> {
    pub pressure: &'a [u8],
    pub cell: &'a [i64],
    pub value: &'a [f64],
}

/// Popis řádků bloku (druh, pojem, proces, příznaky) a čísla variant ve slotech.
pub struct Rows<'a> {
    pub kind: &'a [u8],
    pub concept: &'a [i64],
    pub variable: &'a [u32],
    /// Slot varianty „změna“ procesu či analogie (−1 = ve slotech není).
    pub changed: &'a [i32],
    pub proc_row: &'a [i32],
    pub ease: &'a [f64],
    pub clarity: &'a [f64],
    pub flags: &'a [u8],
    /// Ochrana zažitého slova podle řádku (jen lexikální řádky; počítá Python ze statistik pojmů).
    pub protection: &'a [f64],
    /// Čísla variant ve slotech, tvar (řádky, sloty); −1 = prázdný slot.
    pub variants: &'a [i32],
    pub overlay: Overlay<'a>,
}

/// Kus bloku: řádky `[first, first + count)`, tvar (řádek, skupina, slot).
pub struct Chunk<'a> {
    pub first: usize,
    pub count: usize,
    pub groups: usize,
    pub slots: usize,
    pub current: &'a [f64],
    pub heard: &'a [f64],
}

/// Podklady fáze 1 pro jeden kus: hodnocení v buňkách (řádek, skupina) a příznak, že existují.
#[derive(Default)]
pub struct Gathered {
    values: Vec<[f64; 5]>,
    present: Vec<bool>,
    /// Pracovní pole (dosažené skupiny řádku a nalezená hodnocení), aby se ve smyčce nealokovalo.
    columns: Vec<usize>,
    found: Vec<Option<crate::assess_index::Assessment>>,
}

impl Gathered {
    fn reset(&mut self, cells: usize) {
        self.values.clear();
        self.values.resize(cells, [0.0; 5]);
        self.present.clear();
        self.present.resize(cells, false);
    }
}

fn reached(chunk: &Chunk<'_>, row: usize, g: usize, slot: usize) -> bool {
    let at = ((row * chunk.groups) + g) * chunk.slots + slot;
    chunk.current[at] > 0.0 || chunk.heard[at] > 0.0
}

/// Fáze 1: podklady z indexů. Vrací `Ok(true)`, když je vše hotové, `Ok(false)`, když chybí
/// něco z `needs` (kus se pak po dodání spočítá znovu).
#[allow(clippy::too_many_arguments)]
pub fn gather(
    index: &mut AssessIndex,
    bank: &mut Bank,
    inp: &Inputs<'_>,
    state: &mut StepState,
    step: &StepConst<'_>,
    rows: &Rows<'_>,
    plan: &Plan,
    chunk: &Chunk<'_>,
    out: &mut Gathered,
    needs: &mut Needs,
) -> Result<(), String> {
    out.reset(chunk.count * chunk.groups);
    if state.coda.len() < chunk.groups {
        state.coda.resize(chunk.groups, f64::NAN);
    }
    if state.owners.len() < chunk.groups {
        state.owners.resize(chunk.groups, None);
    }
    let params = step.params;
    for local in 0..chunk.count {
        let row = chunk.first + local;
        let kind = rows.kind[row];
        let changed = rows.changed[row];
        if (kind == PROCESS || kind == FORM) && changed >= 0 {
            let slot = changed as usize;
            let mut columns = std::mem::take(&mut out.columns);
            columns.clear();
            columns.extend((0..chunk.groups).filter(|&g| reached(chunk, local, g, slot)));
            if columns.is_empty() {
                out.columns = columns;
                continue;
            }
            if kind == PROCESS {
                index.assess(
                    bank,
                    inp,
                    &mut state.memo,
                    rows.variable[row],
                    rows.proc_row[row] as usize,
                    &columns,
                    params.tick,
                    needs,
                    &mut out.found,
                )?;
                for (&g, value) in columns.iter().zip(&out.found) {
                    if let Some(value) = *value {
                        let at = local * chunk.groups + g;
                        out.values[at] = [
                            value.coverage,
                            value.merge,
                            value.short,
                            value.marked,
                            value.dispersion,
                        ];
                        out.present[at] = true;
                    }
                }
                if rows.flags[row] & APOCOPE != 0 && params.coda_tolerance_scale > 0.0 {
                    for &g in &columns {
                        if state.coda[g].is_nan() {
                            needs.coda.insert(g);
                        }
                    }
                }
            } else {
                let ctx = FormCtx {
                    bank: &*bank,
                    morph: step.morph,
                    inp,
                    fi: &step.forms,
                    roots: &step.roots,
                };
                for &g in &columns {
                    if let Some(entry) = index.form_lookup(&ctx, g, rows.variable[row], needs) {
                        let at = local * chunk.groups + g;
                        out.values[at] = [
                            entry.gain,
                            entry.frequency,
                            f64::from(u8::from(entry.before)),
                            f64::from(u8::from(entry.after)),
                            0.0,
                        ];
                        out.present[at] = entry.present;
                    }
                }
            }
            out.columns = columns;
        } else if kind == LEXICAL
            && params.has_table
            && plan.kinds[LEXICAL as usize]
                .iter()
                .any(|&(pressure, _)| pressure == id::LEXICAL_CLARITY)
        {
            for g in 0..chunk.groups {
                let mut any = false;
                for slot in 0..chunk.slots {
                    let number = rows.variants[row * chunk.slots + slot];
                    if number < 0 || !reached(chunk, local, g, slot) {
                        continue;
                    }
                    let morpheme = step.variant_morpheme[number as usize];
                    if morpheme < 0 {
                        continue;
                    }
                    any = true;
                    // Výchozí tvar dotazovaného morfému musí být v bance (pro délku výchozího tvaru).
                    if inp.defaults.get(morpheme as usize).copied().unwrap_or(-1) < 0 {
                        needs.defaults.insert((g, morpheme as u32));
                    }
                }
                if any && state.owners[g].is_none() {
                    build_owners(inp, step, state, g, needs);
                }
            }
        }
    }
    Ok(())
}

/// Tabulka vlastníků tvarů skupiny: (tvar, pojem, kořen) podle dominantních kořenů, seřazená.
fn build_owners(
    inp: &Inputs<'_>,
    step: &StepConst<'_>,
    state: &mut StepState,
    g: usize,
    needs: &mut Needs,
) {
    let mut list: Vec<Owner> = Vec::new();
    let mut missing = false;
    for (concept, &root) in step.roots[g].iter().enumerate() {
        if root < 0 {
            continue;
        }
        let form = effective(inp, g, root as u32);
        if form < 0 {
            needs.defaults.insert((g, root as u32));
            missing = true;
        } else {
            list.push((form, concept as i64, i64::from(root)));
        }
    }
    if !missing {
        list.sort_unstable();
        state.owners[g] = Some(list);
    }
}

/// Tvar morfému v kódu (uložený, jinak výchozí); −1, když výchozí tvar není v bance.
fn effective(inp: &Inputs<'_>, g: usize, morpheme: u32) -> i32 {
    match inp.forms[g].get(morpheme as usize) {
        Some(&form) if form >= 0 => form,
        _ => inp.defaults.get(morpheme as usize).copied().unwrap_or(-1),
    }
}

fn is_related(related: &[i64], first: i64, second: i64) -> bool {
    let key = (first.min(second) << 32) | first.max(second);
    related.binary_search(&key).is_ok()
}

/// Vše, co fáze 2 jen čte.
pub struct Scorer<'a> {
    pub bank: &'a Bank,
    pub inp: &'a Inputs<'a>,
    pub state: &'a StepState,
    pub step: &'a StepConst<'a>,
    pub rows: &'a Rows<'a>,
    pub plan: &'a Plan,
    pub chunk: &'a Chunk<'a>,
    pub gathered: &'a Gathered,
    /// Počítat tlak i ve slotech, které kohorta neslyší? Tam výběr tlak nečte (`slyšený × exp(…)` je nula),
    /// takže přenos je vynechává; zlatá data a zkoušky chtějí celé pole.
    pub exhaustive: bool,
}

/// Skóre lexikální jasnosti buňky (`cee.v2.language.lexical_index.clarity_scores`).
fn lexical_clarity(sc: &Scorer<'_>, g: usize, morpheme: u32, concept: i64) -> f64 {
    let form = effective(sc.inp, g, morpheme);
    let default = sc
        .inp
        .defaults
        .get(morpheme as usize)
        .copied()
        .unwrap_or(-1);
    let mut value = 0.0_f64;
    if form >= 0 && default >= 0 {
        let length = sc.bank.form(form as usize).len();
        if length <= 2 && length < sc.bank.form(default as usize).len() {
            value = -0.5;
        }
    }
    if let Some(owners) = &sc.state.owners[g] {
        let begin = owners.partition_point(|owner| owner.0 < form);
        for owner in &owners[begin..] {
            if owner.0 != form {
                break;
            }
            let (_, owner_concept, owner_root) = *owner;
            if owner_root != i64::from(morpheme)
                && owner_concept != concept
                && !is_related(sc.step.related, owner_concept, concept)
            {
                value += -0.4;
                break;
            }
        }
    }
    value
}

impl Scorer<'_> {
    /// Fitness jednoho řádku kusu (`local`) do `out` (délka skupiny × sloty, vynulovaná).
    pub fn row(&self, local: usize, out: &mut [f64]) {
        let (groups, slots) = (self.chunk.groups, self.chunk.slots);
        let row = self.chunk.first + local;
        let kind = self.rows.kind[row] as usize;
        let stride = groups * slots;
        let current = &self.chunk.current[local * stride..(local + 1) * stride];
        let params = self.step.params;
        let variants = &self.rows.variants[row * slots..(row + 1) * slots];
        let step = self.step;
        let changed = self.rows.changed[row];
        for &(pressure, weight) in &self.plan.kinds[kind] {
            match pressure {
                id::CONFORMITY => {
                    for (cell, &share) in out.iter_mut().zip(current) {
                        add(cell, weight * (2.0 * share - 1.0));
                    }
                }
                id::APPEAL => {
                    for (slot, &number) in variants.iter().enumerate() {
                        let appeal = if number < 0 {
                            0.0
                        } else {
                            let found = step
                                .variant_appeal
                                .get(number as usize)
                                .copied()
                                .unwrap_or(f64::NAN);
                            if found.is_nan() {
                                0.0
                            } else {
                                found
                            }
                        };
                        let term = weight * appeal.clamp(-1.0, 1.0);
                        for g in 0..groups {
                            add(&mut out[g * slots + slot], term);
                        }
                    }
                }
                id::ENTRENCHMENT if params.has_table => {
                    let protection = self.rows.protection[row];
                    for g in 0..groups {
                        for (slot, &number) in variants.iter().enumerate() {
                            let dominant = if current[g * slots + slot] >= 0.5 {
                                1.0
                            } else {
                                0.0
                            };
                            let has = if number >= 0 && step.variant_morpheme[number as usize] >= 0
                            {
                                1.0
                            } else {
                                0.0
                            };
                            add(
                                &mut out[g * slots + slot],
                                weight * (protection * dominant * has),
                            );
                        }
                    }
                }
                id::MOTIVATION if params.has_table => {
                    let last = step.origin_weights.len().saturating_sub(1);
                    for (slot, &number) in variants.iter().enumerate() {
                        let (origin, appeal) = if number < 0 {
                            (-1, 0.0)
                        } else {
                            let found = step
                                .variant_appeal
                                .get(number as usize)
                                .copied()
                                .unwrap_or(f64::NAN);
                            (
                                step.variant_origin[number as usize],
                                if found.is_nan() { 0.0 } else { found },
                            )
                        };
                        let origin_weight = if origin < 0 {
                            step.origin_weights[last]
                        } else {
                            step.origin_weights[origin as usize]
                        };
                        let term = weight * (origin_weight + appeal);
                        for g in 0..groups {
                            add(&mut out[g * slots + slot], term);
                        }
                    }
                }
                id::ACTUATION | id::LEXICAL_ACTUATION => {
                    let lexical = pressure == id::LEXICAL_ACTUATION;
                    for (slot, &number) in variants.iter().enumerate() {
                        if number < 0 {
                            continue;
                        }
                        let n = number as usize;
                        if step.variant_change[n] < 0 || (lexical && step.variant_morpheme[n] < 0) {
                            continue;
                        }
                        // Klíč varianty se promíchá jednou pro všechny skupiny.
                        let mixed = splitmix64(step.variant_keys[n]);
                        for g in 0..groups {
                            if !self.exhaustive
                                && self.chunk.heard[(local * groups + g) * slots + slot] <= 0.0
                            {
                                continue;
                            }
                            let noise = hash_normal_mixed(step.actuation_keys[g], mixed);
                            add(
                                &mut out[g * slots + slot],
                                weight * (ACTUATION_SPREAD * noise).clamp(-1.0, 1.0),
                            );
                        }
                    }
                }
                id::LEXICAL_CLARITY if params.has_table => {
                    let concept = self.rows.concept[row];
                    for g in 0..groups {
                        for (slot, &number) in variants.iter().enumerate() {
                            if number < 0 || step.variant_morpheme[number as usize] < 0 {
                                continue;
                            }
                            if !reached(self.chunk, local, g, slot) {
                                continue;
                            }
                            let morpheme = step.variant_morpheme[number as usize] as u32;
                            add(
                                &mut out[g * slots + slot],
                                weight * lexical_clarity(self, g, morpheme, concept),
                            );
                        }
                    }
                }
                id::ARTICULATION
                | id::CLARITY
                | id::DISPERSION
                | id::FUNCTIONAL_LOAD
                | id::PHONOTACTICS
                    if changed >= 0 =>
                {
                    self.process_pressure(pressure, weight, local, changed as usize, out);
                }
                id::UNIFORMITY | id::CONSERVATION | id::TEACHABILITY | id::DISTINCTIVENESS
                    if changed >= 0 =>
                {
                    self.form_pressure(pressure, weight, local, changed as usize, out);
                }
                id::AMBIGUITY
                | id::ECONOMY
                | id::EXPRESSIVITY
                | id::FUSION
                | id::LEARNABILITY
                | id::NORM
                | id::TABOO => self.overlay(pressure, weight, row, local, out),
                _ => {}
            }
        }
    }

    fn overlay(&self, pressure: u8, weight: f64, row: usize, local: usize, out: &mut [f64]) {
        let overlay = self.rows.overlay;
        let stride = (self.chunk.groups * self.chunk.slots) as i64;
        let (low, high) = (row as i64 * stride, (row as i64 + 1) * stride);
        let begin = overlay.cell.partition_point(|&cell| cell < low);
        let _ = local;
        for at in begin..overlay.cell.len() {
            if overlay.cell[at] >= high {
                break;
            }
            if overlay.pressure[at] == pressure {
                add(
                    &mut out[(overlay.cell[at] - low) as usize],
                    weight * overlay.value[at],
                );
            }
        }
    }

    fn process_pressure(
        &self,
        pressure: u8,
        weight: f64,
        local: usize,
        slot: usize,
        out: &mut [f64],
    ) {
        let (groups, slots) = (self.chunk.groups, self.chunk.slots);
        let row = self.chunk.first + local;
        let params = self.step.params;
        let (ease, clarity, flags) = (
            self.rows.ease[row],
            self.rows.clarity[row],
            self.rows.flags[row],
        );
        for g in 0..groups {
            let at = local * groups + g;
            if !reached(self.chunk, local, g, slot) || !self.gathered.present[at] {
                continue;
            }
            let [_, merge, short, marked, dispersion] = self.gathered.values[at];
            let score = match pressure {
                id::ARTICULATION => {
                    if flags & REDUCTIVE_UNSTRESSED != 0 {
                        ease * if self.step.strong[g] {
                            params.stress_strength_multiplier
                        } else {
                            1.0
                        }
                    } else {
                        ease
                    }
                }
                id::CLARITY => (clarity - params.clarity_short_factor * short).clamp(-1.0, 1.0),
                id::DISPERSION => (params.dispersion_factor * dispersion).clamp(-1.0, 1.0),
                id::FUNCTIONAL_LOAD => {
                    let scaled = params.functional_load_scale * merge;
                    -(if scaled < 1.0 { scaled } else { 1.0 })
                }
                _ => {
                    // Fonotaktika: příznakovost, u apokopy zmenšená podílem koncových souhlásek.
                    let mut delta = marked;
                    if flags & APOCOPE != 0 && params.coda_tolerance_scale > 0.0 {
                        let share = self.state.coda[g];
                        delta *= (1.0 - params.coda_tolerance_scale * share).clamp(0.0, 1.0);
                    }
                    -delta.clamp(-1.0, 1.0)
                }
            };
            add(&mut out[g * slots + slot], weight * score);
        }
    }

    fn form_pressure(&self, pressure: u8, weight: f64, local: usize, slot: usize, out: &mut [f64]) {
        let (groups, slots) = (self.chunk.groups, self.chunk.slots);
        let row = self.chunk.first + local;
        let flags = self.rows.flags[row];
        let any_l2 = self.step.l2.iter().any(|&share| share != 0.0);
        if pressure == id::TEACHABILITY && !any_l2 {
            return;
        }
        for g in 0..groups {
            let at = local * groups + g;
            if !reached(self.chunk, local, g, slot) || !self.gathered.present[at] {
                continue;
            }
            let [gain, frequency, before, after, _] = self.gathered.values[at];
            let score = match pressure {
                id::UNIFORMITY => {
                    if flags & LEVEL != 0 {
                        0.4
                    } else {
                        0.35 * gain
                    }
                }
                id::CONSERVATION => {
                    if flags & LEXEME_WIDE != 0 {
                        0.0
                    } else {
                        -0.6 * (2.0 * frequency - 1.0)
                    }
                }
                id::TEACHABILITY => {
                    let base = if flags & LEXEME_WIDE != 0 {
                        0.0
                    } else {
                        TEACHABILITY
                    };
                    base * self.step.l2[g]
                }
                _ => {
                    let (before, after) = (before != 0.0, after != 0.0);
                    if after && !before {
                        -0.8
                    } else if before && !after {
                        0.6
                    } else {
                        0.0
                    }
                }
            };
            add(&mut out[g * slots + slot], weight * score);
        }
    }
}

/// Přičte člen, pokud není nula (`x + 0` je `x`; fitness nikdy není −0, začíná +0).
#[inline]
fn add(cell: &mut f64, term: f64) {
    if term != 0.0 {
        *cell += term;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn bank() -> Bank {
        Bank::new(2, vec![true, false, false]).unwrap()
    }

    /// Jeden lexikální řádek, dvě skupiny a dva sloty: konformita a přitažlivost.
    #[test]
    fn konformita_a_pritazlivost_se_scitaji_v_poradi_planu() {
        let bank = bank();
        let morph = MorphIndex::new();
        let tokens = [1_i64, 2];
        let versions = [0_i64, 0];
        let rules = [0_u8, 0];
        let inp = Inputs {
            tokens: &tokens,
            versions: &versions,
            rules: &rules,
            forms: vec![&[], &[]],
            defaults: &[],
            lexeme: &[],
            cell: &[],
            paradigm_weight: 1.0,
            redundant_weight: 1.0,
        };
        let step = StepConst {
            params: Params {
                has_table: true,
                ..Params::default()
            },
            strong: &[false, false],
            l2: &[0.0, 0.0],
            actuation_keys: &[1, 2],
            roots: vec![&[], &[]],
            related: &[],
            variant_change: &[-1, -1],
            variant_morpheme: &[-1, -1],
            variant_origin: &[-1, -1],
            variant_appeal: &[0.5, f64::NAN],
            variant_keys: &[10, 11],
            origin_weights: &[0.0],
            morph: &morph,
            forms: FormInputs {
                boundary: vec![&[], &[]],
                exponent: vec![&[], &[]],
                order: vec![&[], &[]],
                stamps: &[0, 0],
                kind: &[],
                class: &[],
                unit_exponent: &[],
                unit_boundary: &[],
                frequency: &[],
                weights: &[],
                cells: 0,
                concept_frequency: &[],
            },
        };
        let rows = Rows {
            kind: &[LEXICAL],
            concept: &[0],
            variable: &[0],
            changed: &[-1],
            proc_row: &[-1],
            ease: &[0.0],
            clarity: &[0.0],
            flags: &[0],
            protection: &[0.0],
            variants: &[0, 1],
            overlay: Overlay::default(),
        };
        let mut plan = Plan::default();
        plan.kinds[LEXICAL as usize] = vec![(id::APPEAL, 1.0), (id::CONFORMITY, 0.1)];
        let current = [0.25, 0.75, 1.0, 0.0];
        let chunk = Chunk {
            first: 0,
            count: 1,
            groups: 2,
            slots: 2,
            current: &current,
            heard: &current,
        };
        let state = StepState::default();
        let gathered = Gathered::default();
        let scorer = Scorer {
            bank: &bank,
            inp: &inp,
            state: &state,
            step: &step,
            rows: &rows,
            plan: &plan,
            chunk: &chunk,
            gathered: &gathered,
            exhaustive: true,
        };
        let mut out = [0.0; 4];
        scorer.row(0, &mut out);
        let expected: [f64; 4] = [
            0.0 + 0.5 + 0.1 * (2.0 * 0.25 - 1.0),
            0.0 + 0.1 * (2.0 * 0.75 - 1.0),
            0.0 + 0.5 + 0.1 * (2.0 * 1.0 - 1.0),
            0.0 + 0.1 * (2.0 * 0.0 - 1.0),
        ];
        for (found, wanted) in out.iter().zip(expected) {
            assert_eq!(found.to_bits(), wanted.to_bits());
        }
    }

    #[test]
    fn jen_nenulove_cleny_se_pricitaji() {
        let mut cell = 0.0;
        add(&mut cell, 0.0);
        add(&mut cell, -0.0);
        assert_eq!(cell.to_bits(), 0.0_f64.to_bits());
        add(&mut cell, 0.25);
        assert_eq!(cell, 0.25);
    }
}

#[cfg(test)]
mod mixed_tests {
    use crate::transmission::{hash_normal, hash_normal_mixed, splitmix64};

    #[test]
    fn sum_s_promichanym_klicem_je_stejny_jako_hash_normal() {
        for (row, column) in [
            (0_u64, 0_u64),
            (1, 2),
            (u64::MAX, 12345),
            (987654321, u64::MAX),
        ] {
            assert_eq!(
                hash_normal(row, column).to_bits(),
                hash_normal_mixed(row, splitmix64(column)).to_bits()
            );
        }
    }
}
