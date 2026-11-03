//! Vazba indexu hodnocení (`assess_index`) a tlaků (`pressures`) na Python (PyO3): tenká vrstva.
//!
//! `AssessIndex` drží vzorky a uložená hodnocení kódů; `PressureStep` drží vstupy jednoho kroku
//! sdílené bloky (skupiny, sloupce variant, plán tlaků, stav kroku). `NativeCells.transmit`
//! pak tlaky počítá voláním `fitness_chunk` mezi míšením a výběrem, bez zpětného volání
//! do Pythonu pro tlaky. Co Rust nezná (viz `assess_index::Needs`), zjistí Python jednou za
//! průchod přes `supplier` a kus se spočítá znovu; v ustáleném stavu se Python nevolá vůbec.

use numpy::{PyArray1, PyReadonlyArray1, PyReadonlyArray2, PyUntypedArrayMethods};
use pyo3::prelude::*;
use pyo3::types::PyTuple;

use crate::assess_index::{self, FormEntry, Inputs, Needs, ProcessInfo};
use crate::pressures::{
    self, Chunk, Gathered, Overlay, Params, Plan, Rows, Scorer, StepConst, StepState,
};
use crate::python::{failure, slice, Held, NativeBank};
use crate::transmission::ranges;

fn fail(message: &str) -> PyErr {
    failure(message.to_string())
}

/// Nejvíc průchodů jednoho kusu (každý dodá, co chybělo): víc je chyba, ne běžný stav.
const MAX_PASSES: usize = 64;

/// Index hodnocení všech kódů světa v Rustu; zrcadlo `cee.v2.language.assessment_index`.
#[pyclass(module = "cee_core")]
pub struct AssessIndex {
    pub(crate) inner: assess_index::AssessIndex,
}

type NeedsOut = (
    Vec<usize>,
    Vec<(usize, u32)>,
    Vec<(usize, Vec<i32>)>,
    Vec<(usize, u32)>,
    Vec<usize>,
    Vec<usize>,
    Vec<(usize, u32)>,
);

fn needs_out(needs: Needs) -> NeedsOut {
    (
        needs.samples.into_iter().collect(),
        needs.defaults.into_iter().collect(),
        needs
            .maps
            .into_iter()
            .map(|(row, segments)| (row, segments.into_iter().collect()))
            .collect(),
        needs.redundant.into_iter().collect(),
        needs.coda.into_iter().collect(),
        needs.form_sync.into_iter().collect(),
        needs.form_value.into_iter().collect(),
    )
}

#[pymethods]
impl AssessIndex {
    #[new]
    fn new() -> Self {
        AssessIndex {
            inner: assess_index::AssessIndex::new(),
        }
    }

    /// Souřadnice samohlásek (tvar „hlásky × 3“: výška, zadnost, zaokrouhlení).
    fn set_coordinates(&mut self, coords: PyReadonlyArray2<'_, f64>) -> PyResult<()> {
        let data = coords
            .as_slice()
            .map_err(|_| fail("pole musí být souvislé"))?;
        self.inner.set_coordinates(data.as_chunks::<3>().0.to_vec());
        Ok(())
    }

    /// Zaregistruje proces (číslo proměnné z registru): zda tvaruje vokály, výstupní hláska a maska cílů.
    fn register_process(
        &mut self,
        variable: u32,
        shapes: bool,
        output: i32,
        target: PyReadonlyArray1<'_, bool>,
    ) -> PyResult<()> {
        self.inner.register_process(
            variable,
            ProcessInfo {
                shapes,
                output,
                target: slice(&target)?.to_vec(),
            },
        );
        Ok(())
    }

    fn has_process(&self, variable: u32) -> bool {
        self.inner.has_process(variable)
    }

    /// Vzorek kódu (čísla morfémů v pořadí jmen, váhy a jejich součet) přepočítaný při verzi `version`.
    fn set_sample(
        &mut self,
        token: i64,
        version: i64,
        morphemes: PyReadonlyArray1<'_, i32>,
        weights: PyReadonlyArray1<'_, f64>,
        total: f64,
    ) -> PyResult<()> {
        let numbers = slice(&morphemes)?.iter().map(|&n| n as u32).collect();
        self.inner
            .set_sample(token, version, numbers, slice(&weights)?.to_vec(), total)
            .map_err(failure)
    }

    /// Uložená hodnocení kódu: čísla proměnných, verze, ticky a pět hodnot po řádcích.
    #[allow(clippy::type_complexity)]
    fn export<'py>(
        &self,
        py: Python<'py>,
        token: i64,
    ) -> (
        Bound<'py, PyArray1<i64>>,
        Bound<'py, PyArray1<i64>>,
        Bound<'py, PyArray1<i64>>,
        Bound<'py, PyArray1<f64>>,
    ) {
        let entries = self.inner.export(token);
        (
            PyArray1::from_vec(py, entries.iter().map(|e| i64::from(e.0)).collect()),
            PyArray1::from_vec(py, entries.iter().map(|e| e.1).collect()),
            PyArray1::from_vec(py, entries.iter().map(|e| e.2).collect()),
            PyArray1::from_vec(py, entries.iter().flat_map(|e| e.3).collect()),
        )
    }

    fn import_cache(
        &mut self,
        token: i64,
        variables: PyReadonlyArray1<'_, i64>,
        versions: PyReadonlyArray1<'_, i64>,
        ticks: PyReadonlyArray1<'_, i64>,
        values: PyReadonlyArray1<'_, f64>,
    ) -> PyResult<()> {
        let (variables, versions, ticks, values) = (
            slice(&variables)?,
            slice(&versions)?,
            slice(&ticks)?,
            slice(&values)?,
        );
        if versions.len() != variables.len()
            || ticks.len() != variables.len()
            || values.len() != 5 * variables.len()
        {
            return Err(fail("uložená hodnocení mají špatný tvar"));
        }
        let entries = (0..variables.len())
            .map(|at| {
                let v = &values[5 * at..5 * at + 5];
                (
                    variables[at] as u32,
                    versions[at],
                    ticks[at],
                    [v[0], v[1], v[2], v[3], v[4]],
                )
            })
            .collect();
        self.inner.import(token, entries);
        Ok(())
    }

    fn forget(&mut self, token: i64) {
        self.inner.forget(token);
    }

    /// Zrcadlo hodnocení tvarů: uloží hodnotu, zruší ji, vyprázdní kód, označí ho za dorovnaný.
    #[allow(clippy::too_many_arguments)]
    fn form_set(
        &mut self,
        token: i64,
        variable: u32,
        present: bool,
        gain: f64,
        frequency: f64,
        before: bool,
        after: bool,
    ) {
        self.inner.form_set(
            token,
            variable,
            FormEntry {
                present,
                gain,
                frequency,
                before,
                after,
            },
        );
    }

    fn form_invalidate(&mut self, token: i64, variable: u32) {
        self.inner.form_invalidate(token, variable);
    }

    fn form_clear(&mut self, token: i64) {
        self.inner.form_clear(token);
    }

    fn form_synced(&mut self, token: i64, version: i64) {
        self.inner.form_synced(token, version);
    }

    /// Hodnocení procesu `variable` pro skupiny `groups` (pozice v polích kroku). Vrací
    /// `(needs, hodnoty)`: `hodnoty` jsou pole „skupiny × 5“ s NaN u položek, kterým něco chybí;
    /// `needs` je neprázdné, když Python má něco dodat a zavolat znovu. `known` jsou už zjištěné
    /// odpovědi na `redundant` (skupina, morfém, ano/ne).
    #[allow(clippy::too_many_arguments, clippy::type_complexity)]
    fn assess<'py>(
        &mut self,
        py: Python<'py>,
        bank: &Bound<'py, NativeBank>,
        tokens: Vec<i64>,
        versions: Vec<i64>,
        rules: Vec<u8>,
        forms: Vec<Bound<'py, PyAny>>,
        defaults: Bound<'py, PyAny>,
        lexeme: Bound<'py, PyAny>,
        cell: Bound<'py, PyAny>,
        weights: (f64, f64),
        known: Vec<(usize, u32, bool)>,
        variable: u32,
        proc_row: usize,
        groups: Vec<usize>,
        tick: i64,
    ) -> PyResult<(NeedsOut, Bound<'py, PyArray1<f64>>)> {
        let held_forms = Held::<i32>::all(&forms)?;
        let (defaults, lexeme, cell) = (
            Held::<i32>::new(&defaults)?,
            Held::<i32>::new(&lexeme)?,
            Held::<i32>::new(&cell)?,
        );
        if versions.len() != tokens.len()
            || rules.len() != tokens.len()
            || held_forms.len() != tokens.len()
            || groups.iter().any(|&g| g >= tokens.len())
        {
            return Err(fail("vstupy hodnocení mají špatný tvar"));
        }
        let inp = Inputs {
            tokens: &tokens,
            versions: &versions,
            rules: &rules,
            forms: held_forms.iter().map(|held| held.view()).collect(),
            defaults: defaults.view(),
            lexeme: lexeme.view(),
            cell: cell.view(),
            paradigm_weight: weights.0,
            redundant_weight: weights.1,
        };
        let mut memo = assess_index::Memo::default();
        for (g, morpheme, value) in known {
            memo.redundant.insert((g, morpheme), value);
        }
        let mut needs = Needs::default();
        let mut bank = bank.borrow_mut();
        let found = self
            .inner
            .assess(
                &mut bank.bank,
                &inp,
                &mut memo,
                variable,
                proc_row,
                &groups,
                tick,
                &mut needs,
            )
            .map_err(failure)?;
        let mut flat = Vec::with_capacity(5 * found.len());
        for value in found {
            match value {
                Some(v) => flat.extend([v.coverage, v.merge, v.short, v.marked, v.dispersion]),
                None => flat.extend([f64::NAN; 5]),
            }
        }
        Ok((needs_out(needs), PyArray1::from_vec(py, flat)))
    }
}

/// Tvary, které Rust vytvořil při hodnocení (výsledky procesů), a které si má Python převzít:
/// (číslo prvního, hlásky, délky). Prázdné, když nic nevzniklo.
#[pyfunction]
pub fn take_created<'py>(
    py: Python<'py>,
    bank: &Bound<'py, NativeBank>,
) -> (usize, Bound<'py, PyArray1<i32>>, Bound<'py, PyArray1<i64>>) {
    let (first, flat, lengths) = bank.borrow_mut().bank.take_created();
    (
        first,
        PyArray1::from_vec(py, flat),
        PyArray1::from_vec(py, lengths),
    )
}

/// Pole z Pythonu, která tlaky čtou; drží se po dobu jednoho přenosu bloku (ne po každém průchodu).
pub(crate) struct HeldSet {
    forms: Vec<Held<i32>>,
    roots: Vec<Held<i32>>,
    defaults: Held<i32>,
    lexeme: Held<i32>,
    cell: Held<i32>,
    change: Held<i32>,
    morpheme: Held<i32>,
    origin: Held<i32>,
    appeal: Held<f64>,
    keys: Held<u64>,
}

impl HeldSet {
    fn new(
        py: Python<'_>,
        forms: &[Py<PyAny>],
        roots: &[Py<PyAny>],
        columns: &[Py<PyAny>],
    ) -> PyResult<HeldSet> {
        let objects = |list: &[Py<PyAny>]| -> Vec<Bound<'_, PyAny>> {
            list.iter().map(|item| item.bind(py).clone()).collect()
        };
        let column = |at: usize| columns[at].bind(py).clone();
        Ok(HeldSet {
            forms: Held::<i32>::all(&objects(forms))?,
            roots: Held::<i32>::all(&objects(roots))?,
            defaults: Held::<i32>::new(&column(0))?,
            lexeme: Held::<i32>::new(&column(1))?,
            cell: Held::<i32>::new(&column(2))?,
            change: Held::<i32>::new(&column(3))?,
            morpheme: Held::<i32>::new(&column(4))?,
            origin: Held::<i32>::new(&column(5))?,
            appeal: Held::<f64>::new(&column(6))?,
            keys: Held::<u64>::new(&column(7))?,
        })
    }
}

/// Vstupy jednoho kroku pro tlaky, sdílené bloky.
#[pyclass(module = "cee_core")]
pub struct PressureStep {
    /// Držená pole; zruší se před dotazem na Python a po přenosu, aby Python směl pole měnit.
    pub(crate) held: Option<HeldSet>,
    bank: Py<NativeBank>,
    index: Py<AssessIndex>,
    supplier: Py<PyAny>,
    plan: Plan,
    params: Params,
    weights: (f64, f64),
    tokens: Vec<i64>,
    versions: Vec<i64>,
    rules: Vec<u8>,
    strong: Vec<bool>,
    l2: Vec<f64>,
    actuation_keys: Vec<u64>,
    related: Vec<i64>,
    origin_weights: Vec<f64>,
    forms: Vec<Py<PyAny>>,
    roots: Vec<Py<PyAny>>,
    /// Výchozí tvary, lexémy a buňky morfémů a sloupce tabulky variant (změna, morfém, původ, přitažlivost, klíče).
    columns: Vec<Py<PyAny>>,
    state: StepState,
}

type PlanIn = Vec<Vec<(u8, f64)>>;

#[pymethods]
impl PressureStep {
    /// `plan` je pro každý druh proměnných seznam (číslo tlaku, váha) v pořadí sčítání;
    /// `scalars` je (tick, má tabulku, clarity_short_factor, functional_load_scale, dispersion_factor,
    /// coda_tolerance_scale, stress_strength_multiplier, paradigm_merge_weight, redundant_merge_weight).
    #[new]
    #[allow(clippy::too_many_arguments, clippy::type_complexity)]
    fn new(
        bank: Py<NativeBank>,
        index: Py<AssessIndex>,
        supplier: Py<PyAny>,
        plan: PlanIn,
        scalars: (i64, bool, f64, f64, f64, f64, f64, f64, f64),
        groups: (
            PyReadonlyArray1<'_, i64>,
            PyReadonlyArray1<'_, i64>,
            PyReadonlyArray1<'_, u8>,
            PyReadonlyArray1<'_, bool>,
            PyReadonlyArray1<'_, f64>,
            PyReadonlyArray1<'_, u64>,
        ),
        forms: Vec<Py<PyAny>>,
        roots: Vec<Py<PyAny>>,
        related: PyReadonlyArray1<'_, i64>,
        origin_weights: PyReadonlyArray1<'_, f64>,
        columns: Vec<Py<PyAny>>,
    ) -> PyResult<Self> {
        let tokens = slice(&groups.0)?.to_vec();
        let versions = slice(&groups.1)?.to_vec();
        let rules = slice(&groups.2)?.to_vec();
        let strong = slice(&groups.3)?.to_vec();
        let l2 = slice(&groups.4)?.to_vec();
        let actuation_keys = slice(&groups.5)?.to_vec();
        let related = slice(&related)?.to_vec();
        let origin_weights = slice(&origin_weights)?.to_vec();
        let count = tokens.len();
        if [
            versions.len(),
            rules.len(),
            strong.len(),
            l2.len(),
            actuation_keys.len(),
            forms.len(),
            roots.len(),
        ]
        .iter()
        .any(|&size| size != count)
            || plan.len() != pressures::KINDS
            || columns.len() != 8
        {
            return Err(fail("vstupy kroku pro tlaky mají špatný tvar"));
        }
        let mut kinds: [Vec<(u8, f64)>; pressures::KINDS] = Default::default();
        for (slot, entries) in kinds.iter_mut().zip(plan) {
            *slot = entries;
        }
        Ok(PressureStep {
            bank,
            index,
            supplier,
            plan: Plan { kinds },
            params: Params {
                tick: scalars.0,
                has_table: scalars.1,
                clarity_short_factor: scalars.2,
                functional_load_scale: scalars.3,
                dispersion_factor: scalars.4,
                coda_tolerance_scale: scalars.5,
                stress_strength_multiplier: scalars.6,
            },
            weights: (scalars.7, scalars.8),
            tokens,
            versions,
            rules,
            strong,
            l2,
            actuation_keys,
            related,
            origin_weights,
            forms,
            roots,
            columns,
            state: StepState::default(),
            held: None,
        })
    }
}

/// Popis řádků bloku z Pythonu (pole, která drží volající po dobu přenosu).
pub struct RowsArgs<'py> {
    kind: PyReadonlyArray1<'py, u8>,
    concept: PyReadonlyArray1<'py, i64>,
    variable: PyReadonlyArray1<'py, i64>,
    changed: PyReadonlyArray1<'py, i32>,
    proc_row: PyReadonlyArray1<'py, i32>,
    ease: PyReadonlyArray1<'py, f64>,
    clarity: PyReadonlyArray1<'py, f64>,
    flags: PyReadonlyArray1<'py, u8>,
    protection: PyReadonlyArray1<'py, f64>,
    variants: Held<i32>,
    overlay_pressure: PyReadonlyArray1<'py, u8>,
    overlay_cell: PyReadonlyArray1<'py, i64>,
    overlay_value: PyReadonlyArray1<'py, f64>,
    rows: usize,
}

impl<'py> RowsArgs<'py> {
    /// `items`: druh, pojem, proměnná, slot změny, řádek změny, úspora, zřetelnost, příznaky,
    /// ochrana, čísla variant ve slotech (řádky × sloty), řídké položky (tlak, buňka, hodnota).
    pub fn extract(items: &Bound<'py, PyTuple>) -> PyResult<RowsArgs<'py>> {
        if items.len() != 13 {
            return Err(fail("popis řádků tlaků má špatný počet polí"));
        }
        let rows = items.get_item(0)?.extract::<PyReadonlyArray1<'py, u8>>()?;
        let count = rows.len();
        let found = RowsArgs {
            rows: count,
            kind: rows,
            concept: items.get_item(1)?.extract()?,
            variable: items.get_item(2)?.extract()?,
            changed: items.get_item(3)?.extract()?,
            proc_row: items.get_item(4)?.extract()?,
            ease: items.get_item(5)?.extract()?,
            clarity: items.get_item(6)?.extract()?,
            flags: items.get_item(7)?.extract()?,
            protection: items.get_item(8)?.extract()?,
            variants: Held::new(&items.get_item(9)?)?,
            overlay_pressure: items.get_item(10)?.extract()?,
            overlay_cell: items.get_item(11)?.extract()?,
            overlay_value: items.get_item(12)?.extract()?,
        };
        for size in [
            found.concept.len(),
            found.variable.len(),
            found.changed.len(),
            found.proc_row.len(),
            found.ease.len(),
            found.clarity.len(),
            found.flags.len(),
            found.protection.len(),
        ] {
            if size != count {
                return Err(fail("pole popisu řádků mají různou délku"));
            }
        }
        Ok(found)
    }
}

/// Jeden průchod kusu: podklady a (když nic nechybí) skóre. `Some(needs)`, když něco chybí.
#[allow(clippy::too_many_arguments)]
fn pass(
    py: Python<'_>,
    step: &Bound<'_, PressureStep>,
    rows: &RowsArgs<'_>,
    chunk: &Chunk<'_>,
    threads: usize,
    gathered: &mut Gathered,
    out: &mut [f64],
) -> PyResult<Option<Needs>> {
    let mut guard = step.borrow_mut();
    let me = &mut *guard;
    let mut bank_guard = me.bank.bind(py).borrow_mut();
    let mut index_guard = me.index.bind(py).borrow_mut();
    if me.held.is_none() {
        me.held = Some(HeldSet::new(py, &me.forms, &me.roots, &me.columns)?);
    }
    let held = me.held.as_ref().expect("pole jsou držena");
    let (held_forms, held_roots) = (&held.forms, &held.roots);
    let (defaults, lexeme, cell) = (&held.defaults, &held.lexeme, &held.cell);
    let (change, morpheme, origin) = (&held.change, &held.morpheme, &held.origin);
    let (appeal, keys) = (&held.appeal, &held.keys);
    let inp = Inputs {
        tokens: &me.tokens,
        versions: &me.versions,
        rules: &me.rules,
        forms: held_forms.iter().map(|held| held.view()).collect(),
        defaults: defaults.view(),
        lexeme: lexeme.view(),
        cell: cell.view(),
        paradigm_weight: me.weights.0,
        redundant_weight: me.weights.1,
    };
    let step_const = StepConst {
        params: me.params,
        strong: &me.strong,
        l2: &me.l2,
        actuation_keys: &me.actuation_keys,
        roots: held_roots.iter().map(|held| held.view()).collect(),
        related: &me.related,
        variant_change: change.view(),
        variant_morpheme: morpheme.view(),
        variant_origin: origin.view(),
        variant_appeal: appeal.view(),
        variant_keys: keys.view(),
        origin_weights: &me.origin_weights,
    };
    let variable: Vec<u32> = slice(&rows.variable)?.iter().map(|&v| v as u32).collect();
    let desc = Rows {
        kind: slice(&rows.kind)?,
        concept: slice(&rows.concept)?,
        variable: &variable,
        changed: slice(&rows.changed)?,
        proc_row: slice(&rows.proc_row)?,
        ease: slice(&rows.ease)?,
        clarity: slice(&rows.clarity)?,
        flags: slice(&rows.flags)?,
        protection: slice(&rows.protection)?,
        variants: rows.variants.view(),
        overlay: Overlay {
            pressure: slice(&rows.overlay_pressure)?,
            cell: slice(&rows.overlay_cell)?,
            value: slice(&rows.overlay_value)?,
        },
    };
    if desc.variants.len() < rows.rows * chunk.slots {
        return Err(fail("čísla variant ve slotech nesedí na blok"));
    }
    let mut needs = Needs::default();
    pressures::gather(
        &mut index_guard.inner,
        &mut bank_guard.bank,
        &inp,
        &mut me.state,
        &step_const,
        &desc,
        &me.plan,
        chunk,
        gathered,
        &mut needs,
    )
    .map_err(failure)?;
    if !needs.is_empty() {
        return Ok(Some(needs));
    }
    let stride = chunk.groups * chunk.slots;
    let scorer = Scorer {
        bank: &bank_guard.bank,
        inp: &inp,
        state: &me.state,
        step: &step_const,
        rows: &desc,
        plan: &me.plan,
        chunk,
        gathered,
    };
    if threads <= 1 || chunk.count < 2 {
        for local in 0..chunk.count {
            scorer.row(local, &mut out[local * stride..(local + 1) * stride]);
        }
    } else {
        std::thread::scope(|scope| {
            let mut rest: &mut [f64] = out;
            for (start, stop) in ranges(chunk.count, threads) {
                let (mine, tail) = rest.split_at_mut((stop - start) * stride);
                rest = tail;
                let scorer = &scorer;
                scope.spawn(move || {
                    for local in start..stop {
                        let at = (local - start) * stride;
                        scorer.row(local, &mut mine[at..at + stride]);
                    }
                });
            }
        });
    }
    Ok(None)
}

/// Dodá, co chybělo: zavolá metody dodavatele (Python) a uloží odpovědi, které patří kroku.
fn supply(py: Python<'_>, step: &Bound<'_, PressureStep>, needs: Needs) -> PyResult<()> {
    // Python smí při dodávce měnit pole, která tlaky čtou: držená pole se uvolní.
    let supplier = {
        let mut me = step.borrow_mut();
        me.held = None;
        me.supplier.clone_ref(py)
    };
    let supplier = supplier.bind(py);
    let Needs {
        samples,
        defaults,
        maps,
        redundant,
        coda,
        form_sync,
        form_value,
    } = needs;
    if !samples.is_empty() {
        supplier.call_method1("samples", (samples.into_iter().collect::<Vec<_>>(),))?;
    }
    if !defaults.is_empty() {
        supplier.call_method1("defaults", (defaults.into_iter().collect::<Vec<_>>(),))?;
    }
    if !maps.is_empty() {
        let items: Vec<(usize, Vec<i32>)> = maps
            .into_iter()
            .map(|(row, segments)| (row, segments.into_iter().collect()))
            .collect();
        supplier.call_method1("maps", (items,))?;
    }
    if !redundant.is_empty() {
        let items: Vec<(usize, u32)> = redundant.into_iter().collect();
        let found: Vec<bool> = supplier
            .call_method1("redundant", (items.clone(),))?
            .extract()?;
        let mut me = step.borrow_mut();
        for (item, value) in items.into_iter().zip(found) {
            me.state.memo.redundant.insert(item, value);
        }
    }
    if !coda.is_empty() {
        let items: Vec<usize> = coda.into_iter().collect();
        let found: Vec<f64> = supplier.call_method1("coda", (items.clone(),))?.extract()?;
        let mut me = step.borrow_mut();
        for (group, value) in items.into_iter().zip(found) {
            me.state.coda[group] = value;
        }
    }
    if !form_sync.is_empty() {
        supplier.call_method1("form_sync", (form_sync.into_iter().collect::<Vec<_>>(),))?;
    }
    if !form_value.is_empty() {
        supplier.call_method1("form_value", (form_value.into_iter().collect::<Vec<_>>(),))?;
    }
    Ok(())
}

/// Tlaky jednoho kusu bloku: součet vážených tlaků každé buňky do `out` (délka řádky × skupiny × sloty).
#[allow(clippy::too_many_arguments)]
pub fn fitness_chunk(
    py: Python<'_>,
    step: &Bound<'_, PressureStep>,
    rows: &RowsArgs<'_>,
    first: usize,
    count: usize,
    groups: usize,
    slots: usize,
    current: &[f64],
    heard: &[f64],
    threads: usize,
    gathered: &mut Gathered,
    out: &mut Vec<f64>,
) -> PyResult<()> {
    out.clear();
    out.resize(count * groups * slots, 0.0);
    let chunk = Chunk {
        first,
        count,
        groups,
        slots,
        current,
        heard,
    };
    for _ in 0..MAX_PASSES {
        match pass(py, step, rows, &chunk, threads, gathered, out)? {
            None => return Ok(()),
            Some(needs) => supply(py, step, needs)?,
        }
    }
    Err(fail(
        "tlaky se nepodařilo dopočítat: Python nedodal, co chybí",
    ))
}

/// Zkušební vstup: tlaky jednoho kusu s vlastním `PressureStep` (zlatá data a zkoušky).
#[pyfunction]
#[pyo3(signature = (step, rows, current, heard, first=0, threads=1))]
pub fn pressure_scores<'py>(
    py: Python<'py>,
    step: &Bound<'py, PressureStep>,
    rows: &Bound<'py, PyTuple>,
    current: numpy::PyReadonlyArray3<'py, f64>,
    heard: numpy::PyReadonlyArray3<'py, f64>,
    first: usize,
    threads: usize,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
    let dims = current.shape();
    if heard.shape() != dims {
        return Err(fail("slyšené podíly mají jiný tvar než současné"));
    }
    let (count, groups, slots) = (dims[0], dims[1], dims[2]);
    let args = RowsArgs::extract(rows)?;
    let mut out = Vec::new();
    let mut gathered = Gathered::default();
    fitness_chunk(
        py,
        step,
        &args,
        first,
        count,
        groups,
        slots,
        current
            .as_slice()
            .map_err(|_| fail("pole musí být souvislé"))?,
        heard
            .as_slice()
            .map_err(|_| fail("pole musí být souvislé"))?,
        threads,
        &mut gathered,
        &mut out,
    )?;
    Ok(PyArray1::from_vec(py, out))
}
