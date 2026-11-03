//! Vazba stavu fonologie kódu na Python (PyO3): `NativeCode` a dávková volání.
//!
//! Python posílá jen vstupy, které mu patří (tvary kódu, sloupce morfémů světa,
//! sklony slov podle procesu, četnosti pojmů) jako pole bez kopie; fronty,
//! příznaky a dominantní kořeny žijí v `NativeCode`. Jádro nic nezapisuje do
//! objektů Pythonu: vrací přepsané tvary a události a Python je zapíše ve stejném
//! pořadí jako dřív (viz `cee.v2.phonology`).

use pyo3::prelude::*;
use pyo3::types::PyTuple;

use crate::code_state::{CodeNeeds, CodeState, Ctx, Event, Proc, Round, RoundOut, UsageInputs};
use crate::phonology::{Params, Units};
use crate::python::{failure, Held, NativeBank};

type NeedsOut = (
    Vec<(usize, usize)>,
    Vec<usize>,
    Vec<usize>,
    Vec<(usize, Vec<i32>)>,
    Vec<usize>,
);

type Columns<'py> = (
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
);

type Store<'py> = (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>);

/// Sloupce četností užití: četnosti pojmů, statické frekvence a váhy buněk.
type Usage<'py> = (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>);

/// Jedna skupina v dávce `restructure_groups`.
type RoundIn<'py> = (
    Bound<'py, NativeCode>,
    u8,
    Store<'py>,
    Vec<Bound<'py, PyAny>>,
    Vec<f64>,
    Vec<bool>,
    i64,
    f64,
);

/// Neutrální podoba procesu: (číslo, živý, redukční, řádek nebo −1, čekající,
/// přepsané, logity, morfémy, `fixed_since`).
type ProcExport = (
    usize,
    bool,
    bool,
    i64,
    Vec<u8>,
    Vec<u8>,
    Vec<f64>,
    Vec<i32>,
    Option<i64>,
);

fn needs_out(needs: CodeNeeds) -> NeedsOut {
    (
        needs.bias,
        needs.freq,
        needs.forms,
        needs.maps,
        needs.tables,
    )
}

/// Sloupce světa a pole kódu držené po dobu jednoho volání.
struct Inputs {
    store: [Held<i32>; 3],
    defaults: [Held<i32>; 4],
    concept: Held<f64>,
    fixed: Held<f64>,
    weight: Held<f64>,
}

impl Inputs {
    fn new(store: &Store<'_>, defaults: &Columns<'_>, usage: &Usage<'_>) -> PyResult<Inputs> {
        Ok(Inputs {
            store: [
                Held::new(&store.0)?,
                Held::new(&store.1)?,
                Held::new(&store.2)?,
            ],
            defaults: [
                Held::new(&defaults.0)?,
                Held::new(&defaults.1)?,
                Held::new(&defaults.2)?,
                Held::new(&defaults.3)?,
            ],
            concept: Held::new(&usage.0)?,
            fixed: Held::new(&usage.1)?,
            weight: Held::new(&usage.2)?,
        })
    }

    fn ctx(&self, params: Params) -> Ctx<'_> {
        Ctx {
            params,
            units: Units {
                form: self.store[0].view(),
                cut: self.store[1].view(),
                exponent: self.store[2].view(),
                default_form: self.defaults[0].view(),
                default_cut: self.defaults[1].view(),
                default_exponent: self.defaults[2].view(),
                lexeme: self.defaults[3].view(),
            },
            usage: UsageInputs {
                concept: self.concept.view(),
                fixed: self.fixed.view(),
                weight: self.weight.view(),
                lexeme: self.defaults[3].view(),
            },
        }
    }
}

/// Stav fonologie jednoho kódu: fronty procesů, dominantní kořeny, četnosti užití.
#[pyclass(module = "cee_core")]
#[derive(Default)]
pub struct NativeCode {
    inner: CodeState,
}

#[pymethods]
impl NativeCode {
    #[new]
    fn new() -> Self {
        NativeCode::default()
    }

    /// Dominantní kořen pojmu se změnil (−1 = pojem kořen ztratil).
    fn set_root(&mut self, concept: usize, root: i32) {
        self.inner.usage.set_root(concept, root);
    }

    /// Změnily se četnosti pojmů světa: paměť četností užití neplatí.
    fn invalidate_usage(&mut self) {
        self.inner.usage.invalidate_all();
    }

    /// Dvojice (pojem, kořen) v pořadí vstupu do mapy dominantních kořenů.
    fn roots(&self) -> Vec<(usize, i32)> {
        self.inner.usage.roots_in_order()
    }

    /// Čísla živých procesů v pořadí, ve kterém kód zasáhly.
    fn live(&self) -> Vec<usize> {
        self.inner
            .live()
            .into_iter()
            .map(|index| self.inner.procs[index].number)
            .collect()
    }

    /// Čísla všech procesů kódu (živých i uzavřených) v pořadí vzniku.
    fn processes(&self) -> Vec<usize> {
        self.inner.procs.iter().map(|proc| proc.number).collect()
    }

    /// −1 = kód proces nezná, 0 = uzavřený, 1 = živý.
    fn status(&self, number: usize) -> i8 {
        match self.inner.find(number) {
            None => -1,
            Some(index) => i8::from(self.inner.procs[index].live),
        }
    }

    /// Fronta procesu: potřebné logity a čísla morfémů (seřazené).
    fn queue(&self, number: usize) -> Option<(Vec<f64>, Vec<i32>)> {
        let proc = &self.inner.procs[self.inner.find(number)?];
        Some((proc.needed.clone(), proc.morphemes.clone()))
    }

    /// Čísla morfémů, které ve frontě procesu čekají (vzestupně).
    fn queued(&self, number: usize) -> Vec<usize> {
        self.flagged(number, true)
    }

    /// Čísla morfémů, které si změnu procesu zapsaly (vzestupně).
    fn done(&self, number: usize) -> Vec<usize> {
        self.flagged(number, false)
    }

    fn fixed_since(&self, number: usize) -> Option<i64> {
        self.inner
            .find(number)
            .and_then(|index| self.inner.procs[index].fixed_since)
    }

    /// Řádky tabulek procesů v bance pro pravidlo přízvuku kódu, v pořadí živých
    /// procesů (−1 = tabulka s tímto pravidlem v bance není).
    fn set_rows(&mut self, rows: Vec<i64>) -> PyResult<()> {
        let live = self.inner.live();
        if rows.len() != live.len() {
            return Err(failure("řádků je jiný počet než živých procesů".into()));
        }
        for (index, row) in live.into_iter().zip(rows) {
            self.inner.procs[index].row = usize::try_from(row).ok();
        }
        Ok(())
    }

    /// Neutrální podoba celého stavu (kopie, checkpointy, pickle).
    fn export(&self) -> (Vec<ProcExport>, Vec<(usize, i32)>) {
        let procs = self
            .inner
            .procs
            .iter()
            .map(|proc| {
                (
                    proc.number,
                    proc.live,
                    proc.reductive,
                    proc.row.map_or(-1, |row| row as i64),
                    proc.queued.clone(),
                    proc.done.clone(),
                    proc.needed.clone(),
                    proc.morphemes.clone(),
                    proc.fixed_since,
                )
            })
            .collect();
        (procs, self.inner.usage.roots_in_order())
    }

    fn __reduce__<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let module = py.import("cee_core")?;
        (module.getattr("restore_code")?, (self.export(),)).into_pyobject(py)
    }

    /// `_queue` pro všechny živé procesy a každý z morfémů; vrací
    /// `(hotových, needs, první_nové_číslo, nové_hlásky, nové_délky)`.
    #[pyo3(signature = (bank, rule, base, lead_scale, store, defaults, usage, biases, morphemes))]
    #[allow(clippy::too_many_arguments, clippy::type_complexity)]
    fn queue_units<'py>(
        &mut self,
        py: Python<'py>,
        bank: &Bound<'py, NativeBank>,
        rule: u8,
        base: f64,
        lead_scale: f64,
        store: Store<'py>,
        defaults: Columns<'py>,
        usage: Usage<'py>,
        biases: Vec<Bound<'py, PyAny>>,
        morphemes: Vec<i32>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let inputs = Inputs::new(&store, &defaults, &usage)?;
        let held = Held::<f64>::all(&biases)?;
        let views: Vec<&[f64]> = held.iter().map(Held::view).collect();
        let params = Params {
            rule,
            base,
            lead_scale,
        };
        let mut guard = bank.borrow_mut();
        let (done, needs) = self
            .inner
            .queue_units(&mut guard.bank, &inputs.ctx(params), &views, &morphemes)
            .map_err(failure)?;
        let (first, flat, lengths) = guard.bank.take_created();
        (done, needs_out(needs), first, flat, lengths).into_pyobject(py)
    }

    /// `activate`: fronta procesu `number` ze slovní zásoby (příznaky `vocabulary`);
    /// vrací `(needs, první_nové_číslo, nové_hlásky, nové_délky)`. S neprázdným
    /// `needs` proces nevznikl.
    #[pyo3(signature = (bank, rule, base, lead_scale, store, defaults, usage, number, row, reductive, bias, vocabulary))]
    #[allow(clippy::too_many_arguments, clippy::type_complexity)]
    fn activate<'py>(
        &mut self,
        py: Python<'py>,
        bank: &Bound<'py, NativeBank>,
        rule: u8,
        base: f64,
        lead_scale: f64,
        store: Store<'py>,
        defaults: Columns<'py>,
        usage: Usage<'py>,
        number: usize,
        row: usize,
        reductive: bool,
        bias: Bound<'py, PyAny>,
        vocabulary: Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let inputs = Inputs::new(&store, &defaults, &usage)?;
        let bias = Held::<f64>::new(&bias)?;
        let words = Held::<u8>::new(&vocabulary)?;
        let params = Params {
            rule,
            base,
            lead_scale,
        };
        let mut guard = bank.borrow_mut();
        let needs = self
            .inner
            .activate(
                &mut guard.bank,
                &inputs.ctx(params),
                number,
                row,
                reductive,
                bias.view(),
                words.view(),
            )
            .map_err(failure)?;
        let (first, flat, lengths) = guard.bank.take_created();
        (needs_out(needs), first, flat, lengths).into_pyobject(py)
    }

    /// Četnosti užití morfémů (`World.usage_frequency`) z dominantních kořenů kódu.
    #[pyo3(signature = (morphemes, concept, fixed, weight, lexeme))]
    fn frequencies(
        &mut self,
        morphemes: Vec<usize>,
        concept: Bound<'_, PyAny>,
        fixed: Bound<'_, PyAny>,
        weight: Bound<'_, PyAny>,
        lexeme: Bound<'_, PyAny>,
    ) -> PyResult<Vec<f64>> {
        let (concept, fixed) = (Held::<f64>::new(&concept)?, Held::<f64>::new(&fixed)?);
        let (weight, lexeme) = (Held::<f64>::new(&weight)?, Held::<i32>::new(&lexeme)?);
        let inputs = UsageInputs {
            concept: concept.view(),
            fixed: fixed.view(),
            weight: weight.view(),
            lexeme: lexeme.view(),
        };
        morphemes
            .into_iter()
            .map(|morpheme| {
                self.inner
                    .usage
                    .frequency(morpheme, &inputs)
                    .ok_or_else(|| {
                        failure(format!("četnost užití morfému č. {morpheme} nejde určit"))
                    })
            })
            .collect()
    }
}

impl NativeCode {
    fn flagged(&self, number: usize, queued: bool) -> Vec<usize> {
        let Some(index) = self.inner.find(number) else {
            return Vec::new();
        };
        let proc = &self.inner.procs[index];
        let flags = if queued { &proc.queued } else { &proc.done };
        (0..flags.len()).filter(|&item| flags[item] == 1).collect()
    }
}

/// Obnoví stav kódu z neutrální podoby (`NativeCode.export`).
#[pyfunction]
pub fn restore_code(state: (Vec<ProcExport>, Vec<(usize, i32)>)) -> NativeCode {
    let mut code = NativeCode::default();
    for (number, live, reductive, row, queued, done, needed, morphemes, fixed_since) in state.0 {
        code.inner.procs.push(Proc {
            number,
            live,
            reductive,
            row: usize::try_from(row).ok(),
            queued,
            done,
            needed,
            morphemes,
            fixed_since,
        });
    }
    for (concept, root) in state.1 {
        code.inner.usage.set_root(concept, root);
    }
    code
}

/// Počet jmen morfémů, které banka zná.
#[pyfunction]
pub fn names_count(bank: &Bound<'_, NativeBank>) -> usize {
    bank.borrow().bank.names.len()
}

/// Doplní bance jména morfémů od čísla `start` (dosavadní počet).
#[pyfunction]
pub fn extend_names(
    bank: &Bound<'_, NativeBank>,
    start: usize,
    names: Vec<String>,
) -> PyResult<()> {
    bank.borrow_mut()
        .bank
        .extend_names(start, names)
        .map_err(failure)
}

/// Fonologizace všech skupin jedním voláním (`phonology.restructure` po
/// skupinách v daném pořadí). Vrací
/// `(zastavení, přepisy, události, první_nové_číslo, nové_hlásky, nové_délky)`:
///
/// - zastavení je `None`, nebo `(skupina, needs)`: skupině chybí údaj, Python ho
///   doplní a zavolá znovu od této skupiny (hotová práce zůstala ve stavu);
/// - přepis je `(skupina, morfém, tvar, hranice, koncovka)`;
/// - událost je `(skupina, proces, druh, a, b)`: druh 0 = fáze procesu skončila
///   (`a` přepsaných slov), 1 = proces se uzavřel (`a` přepsaných morfémů, `b`
///   reliktů), 2 = fáze se zastavila (`a` přepsaných slov do té doby).
#[pyfunction]
#[pyo3(signature = (bank, base, lead_scale, dt, defaults, usage, groups))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn restructure_groups<'py>(
    py: Python<'py>,
    bank: &Bound<'py, NativeBank>,
    base: f64,
    lead_scale: f64,
    dt: f64,
    defaults: Columns<'py>,
    usage: Usage<'py>,
    groups: Vec<RoundIn<'py>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let mut guard = bank.borrow_mut();
    let mut rewrites = Vec::new();
    let mut events = Vec::new();
    let mut halt: Option<(usize, NeedsOut)> = None;
    for (group, (code, rule, store, biases, levels, full, tick, threshold)) in
        groups.iter().enumerate()
    {
        let inputs = Inputs::new(store, &defaults, &usage)?;
        let held = Held::<f64>::all(biases)?;
        let round = Round {
            ctx: inputs.ctx(Params {
                rule: *rule,
                base,
                lead_scale,
            }),
            biases: held.iter().map(Held::view).collect(),
            levels: levels.clone(),
            full: full.clone(),
            tick: *tick,
            dt,
            threshold: *threshold,
        };
        let mut out = RoundOut::default();
        let mut state = code.borrow_mut();
        let result = state
            .inner
            .restructure(&mut guard.bank, &round, &mut out)
            .map_err(failure)?;
        rewrites.extend(
            out.rewrites
                .iter()
                .map(|item| (group, item.morpheme, item.form, item.cut, item.exponent)),
        );
        events.extend(out.events.iter().map(|event| match *event {
            Event::Finished { proc, words } => (group, proc, 0u8, words, 0),
            Event::Closed {
                proc,
                restructured,
                relics,
            } => (group, proc, 1u8, restructured, relics),
            Event::Partial { proc, words } => (group, proc, 2u8, words, 0),
        }));
        if let Some(needs) = result {
            halt = Some((group, needs_out(needs)));
            break;
        }
    }
    let (first, flat, lengths) = guard.bank.take_created();
    (halt, rewrites, events, first, flat, lengths).into_pyobject(py)
}
