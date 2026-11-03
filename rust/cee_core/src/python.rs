//! Vazba na Python (PyO3): tenká vrstva nad `bank::Bank`.
//!
//! Rozhraní je dávkové: tvary i výsledky putují jako pole `numpy`, ne po
//! jednom. Jednotlivé dotazy (`result`, `may_apply`) jsou jen pro horké cesty,
//! které volají Python po jednom tvaru.

use std::collections::BTreeMap;

use numpy::ndarray::Dimension;
use numpy::{PyArray1, PyReadonlyArray, PyReadonlyArray1, PyReadonlyArray2, PyUntypedArrayMethods};
use pyo3::buffer::{Element, PyBuffer, PyUntypedBuffer};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyTuple;

use crate::assess::{Assessed, Matrix};
use crate::bank::{Bank, Outcome};
use crate::phonology::{self, Needs, Params, Target, Units};
use crate::process::Proc;
use crate::support::{self, Contexts, Masks};

pub(crate) fn failure(message: String) -> PyErr {
    PyValueError::new_err(message)
}

pub(crate) fn slice<'a, T: numpy::Element, D: Dimension>(
    array: &'a PyReadonlyArray<'_, T, D>,
) -> PyResult<&'a [T]> {
    array
        .as_slice()
        .map_err(|_| failure("pole musí být souvislé".into()))
}

/// Pole z Pythonu (`array.array`, `bytearray`, numpy) držená po dobu jednoho
/// volání. Během něj Python nic nemění (drží se zámek GIL), po návratu se
/// zpřístupnění pole uvolní a Python smí pole zase měnit či zvětšovat.
pub(crate) struct Held<T: Element>(Option<PyBuffer<T>>);

impl<T: Element> Held<T> {
    pub(crate) fn new(object: &Bound<'_, PyAny>) -> PyResult<Self> {
        let buffer = PyUntypedBuffer::get(object)?;
        // Prázdné pole nemusí mít platnou ani zarovnanou adresu; nečte se.
        if buffer.item_count() == 0 {
            return Ok(Held(None));
        }
        let buffer = buffer.into_typed::<T>()?;
        if !buffer.is_c_contiguous() {
            return Err(failure("pole musí být souvislé".into()));
        }
        Ok(Held(Some(buffer)))
    }

    pub(crate) fn all(objects: &[Bound<'_, PyAny>]) -> PyResult<Vec<Self>> {
        objects.iter().map(Held::new).collect()
    }

    pub(crate) fn view(&self) -> &[T] {
        match self.0.as_ref().and_then(|buffer| buffer.as_slice_ptr()) {
            // SAFETY: pole je souvislé a po dobu volání (zámek GIL) ho nikdo
            // nemění ani nezmenšuje, drží ho `PyBuffer`; jádro ho jen čte.
            Some(pointer) => unsafe { &*pointer.as_ptr() },
            None => &[],
        }
    }
}

/// Čtyři seznamy a příznaky z Pythonu: fronty živých procesů kódu.
type RawTargets<'py> = (
    Vec<i64>,
    Vec<Bound<'py, PyAny>>,
    Vec<Bound<'py, PyAny>>,
    Vec<Bound<'py, PyAny>>,
    Vec<bool>,
);

/// Co jádro fonologizace čte: tvary kódu, sloupce světa a fronty procesů.
struct Inputs {
    store: [Held<i32>; 3],
    defaults: [Held<i32>; 4],
    queued: Vec<Held<u8>>,
    restructured: Vec<Held<u8>>,
    bias: Vec<Held<f64>>,
    rows: Vec<i64>,
    reductive: Vec<bool>,
}

impl Inputs {
    fn new(
        store: &(Bound<'_, PyAny>, Bound<'_, PyAny>, Bound<'_, PyAny>),
        defaults: &(
            Bound<'_, PyAny>,
            Bound<'_, PyAny>,
            Bound<'_, PyAny>,
            Bound<'_, PyAny>,
        ),
        targets: &RawTargets<'_>,
    ) -> PyResult<Inputs> {
        let (rows, queued, restructured, bias, reductive) = targets;
        if [
            queued.len(),
            restructured.len(),
            bias.len(),
            rows.len(),
            reductive.len(),
        ]
        .iter()
        .any(|&size| size != rows.len())
        {
            return Err(failure("seznamy front mají různou délku".into()));
        }
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
            queued: Held::all(queued)?,
            restructured: Held::all(restructured)?,
            bias: Held::all(bias)?,
            rows: rows.clone(),
            reductive: reductive.clone(),
        })
    }

    fn units(&self) -> Units<'_> {
        Units {
            form: self.store[0].view(),
            cut: self.store[1].view(),
            exponent: self.store[2].view(),
            default_form: self.defaults[0].view(),
            default_cut: self.defaults[1].view(),
            default_exponent: self.defaults[2].view(),
            lexeme: self.defaults[3].view(),
        }
    }

    fn targets(&self) -> Vec<Target<'_>> {
        (0..self.rows.len())
            .map(|index| Target {
                row: self.rows[index],
                queued: self.queued[index].view(),
                restructured: self.restructured[index].view(),
                bias: self.bias[index].view(),
                reductive: self.reductive[index],
            })
            .collect()
    }
}

type NeedsOut = (
    Vec<(usize, usize)>,
    Vec<usize>,
    Vec<usize>,
    Vec<(usize, Vec<i32>)>,
    Vec<usize>,
);

/// Co má Python doplnit: sklony (fronta, morfém), četnosti (lexém), výchozí
/// tvary (morfém), mapy hlásek (řádek změny, hlásky) a fronty, jejichž tabulka
/// procesu se má založit.
fn needs_out(needs: Needs) -> NeedsOut {
    (
        needs.bias.into_iter().collect(),
        needs.freq.into_iter().collect(),
        needs.forms.into_iter().collect(),
        needs
            .maps
            .into_iter()
            .map(|(row, segments)| (row, segments.into_iter().collect()))
            .collect(),
        needs.tables.into_iter().collect(),
    )
}

/// Zařazení do front jako tři pole: fronta, morfém, potřebný logit.
fn inserts_out(inserts: &[phonology::Insert]) -> (Vec<usize>, Vec<usize>, Vec<f64>) {
    (
        inserts.iter().map(|insert| insert.target).collect(),
        inserts.iter().map(|insert| insert.morpheme).collect(),
        inserts.iter().map(|insert| insert.needed).collect(),
    )
}

/// Banka tvarů a tabulky procesů v Rustu; zrcadlo `FormBank` z Pythonu.
#[pyclass(module = "cee_core")]
pub struct NativeBank {
    pub(crate) bank: Bank,
}

#[pymethods]
impl NativeBank {
    /// `boundary` je číslo hranice slova (počet hlásek), `vowel` maska
    /// samohlásek s hranicí na konci; `glide` je maska polosamohlásek (sonorita 3)
    /// stejné délky, bez ní se hodnocení příznakovosti slabik nepočítá správně.
    #[new]
    #[pyo3(signature = (boundary, vowel, glide=None))]
    fn new(
        boundary: i32,
        vowel: PyReadonlyArray1<'_, bool>,
        glide: Option<PyReadonlyArray1<'_, bool>>,
    ) -> PyResult<Self> {
        let mut bank = Bank::new(boundary, slice(&vowel)?.to_vec()).map_err(failure)?;
        if let Some(glide) = glide {
            bank.set_glide(slice(&glide)?.to_vec()).map_err(failure)?;
        }
        Ok(NativeBank { bank })
    }

    /// Počet tvarů, které banka zná.
    fn __len__(&self) -> usize {
        self.bank.len()
    }

    /// Počet zaregistrovaných změn.
    fn proc_count(&self) -> usize {
        self.bank.proc_count()
    }

    /// Nový tvar z Pythonu; vrací jeho číslo.
    fn push(&mut self, form: Vec<i32>) -> PyResult<u32> {
        self.bank.push(&form).map_err(failure)
    }

    /// Více tvarů naráz (obnova po kopii či načtení): hlásky za sebou a délky.
    fn push_many(
        &mut self,
        flat: PyReadonlyArray1<'_, i64>,
        lengths: PyReadonlyArray1<'_, i64>,
    ) -> PyResult<()> {
        let (flat, lengths) = (slice(&flat)?, slice(&lengths)?);
        let mut begin = 0usize;
        let mut form = Vec::new();
        for &length in lengths {
            let end = begin + length as usize;
            if end > flat.len() {
                return Err(failure("délky přesahují pole hlásek".into()));
            }
            form.clear();
            form.extend(flat[begin..end].iter().map(|&segment| segment as i32));
            self.bank.push(&form).map_err(failure)?;
            begin = end;
        }
        Ok(())
    }

    /// Zaregistruje změnu na řádku `row` (řádky jdou po řadě od nuly).
    ///
    /// `operation`, `stress` a čísla pravidel viz `cee.v2.native`; `segment`
    /// a `tone` jsou −1, když je změna nemá.
    #[pyo3(signature = (row, operation, stress, medial, segment, target, left, right, right2))]
    #[allow(clippy::too_many_arguments)]
    fn register_proc(
        &mut self,
        row: usize,
        operation: u8,
        stress: u8,
        medial: bool,
        segment: i32,
        target: PyReadonlyArray1<'_, bool>,
        left: PyReadonlyArray1<'_, bool>,
        right: PyReadonlyArray1<'_, bool>,
        right2: PyReadonlyArray1<'_, bool>,
    ) -> PyResult<()> {
        let size = slice(&target)?.len();
        let proc = Proc {
            operation,
            stress,
            medial,
            segment,
            target: slice(&target)?.to_vec(),
            left: slice(&left)?.to_vec(),
            right: slice(&right)?.to_vec(),
            right2: slice(&right2)?.to_vec(),
            map: vec![crate::process::MAP_UNRESOLVED; size.saturating_sub(1)],
        };
        self.bank.register_proc(row, proc).map_err(failure)
    }

    /// Doplní výstupy operací `change` a `tone` (−1 = hláska zůstane).
    fn set_map(
        &mut self,
        row: usize,
        segments: PyReadonlyArray1<'_, i64>,
        outputs: PyReadonlyArray1<'_, i64>,
    ) -> PyResult<()> {
        self.bank
            .set_map(row, slice(&segments)?, slice(&outputs)?)
            .map_err(failure)
    }

    /// Výsledek změny `row` s pravidlem přízvuku `rule` pro každý tvar z `form_ids`.
    ///
    /// Vrací `(needs, výsledky, první_nové_číslo, nové_hlásky, nové_délky)`.
    /// Když je `needs` neprázdné, nic se nespočítalo: Python má doplnit mapu
    /// pro tyto hlásky (`set_map`) a zeptat se znovu. Jinak jsou `výsledky`
    /// pole a nové tvary (vzniklé aplikací) si má Python převzít.
    fn results<'py>(
        &mut self,
        py: Python<'py>,
        row: usize,
        rule: u8,
        form_ids: PyReadonlyArray1<'py, i64>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let outcome = self
            .bank
            .results(row, rule, slice(&form_ids)?)
            .map_err(failure)?;
        let (first, flat, lengths) = self.bank.take_created();
        let (needs, found): (Vec<i32>, Option<Bound<'py, PyArray1<i64>>>) = match outcome {
            Outcome::Needs(needs) => (needs, None),
            Outcome::Done(found) => (Vec::new(), Some(PyArray1::from_vec(py, found))),
        };
        let found: Py<PyAny> = match found {
            Some(array) => array.into_any().unbind(),
            None => py.None(),
        };
        PyTuple::new(
            py,
            [
                needs.into_pyobject(py)?.into_any(),
                found.into_bound(py),
                first.into_pyobject(py)?.into_any(),
                PyArray1::from_vec(py, flat).into_any(),
                PyArray1::from_vec(py, lengths).into_any(),
            ],
        )
    }

    /// Výsledek pro jeden tvar: číslo tvaru, −1 (beze změny), −3 (Python má
    /// doplnit mapu) nebo −4 (vznikl nový tvar, převezme ho `results`).
    fn result(&mut self, row: usize, rule: u8, form_id: usize) -> PyResult<i64> {
        self.bank.result(row, rule, form_id).map_err(failure)
    }

    /// Hodnocení změny `row` (pravidlo přízvuku `rule`) nad maticí slovních zásob
    /// (`cee.v2.assessment._assess_batch`): `ids` a `weights` jsou řádky matice
    /// za sebou, `offsets` jejich meze (řádků + 1 čísel) a `width` šířka matice
    /// v Pythonu (nejdelší řádek); podle ní se sčítá jako `numpy`.
    ///
    /// Vrací `(needs, hmota, krátká hmota, příznakovost, počty dvojic, první,
    /// druhá, počty samohlásek před, samohlásky před, počty po, samohlásky po,
    /// první_nové_číslo, nové_hlásky, nové_délky)`. Je-li `needs` neprázdné,
    /// nic se nespočítalo: Python doplní mapy (`set_map`) a zeptá se znovu.
    #[pyo3(signature = (row, rule, ids, weights, offsets, width, want_vowels))]
    #[allow(clippy::too_many_arguments)]
    fn assess_rows<'py>(
        &mut self,
        py: Python<'py>,
        row: usize,
        rule: u8,
        ids: PyReadonlyArray1<'py, i64>,
        weights: PyReadonlyArray1<'py, f64>,
        offsets: PyReadonlyArray1<'py, i64>,
        width: usize,
        want_vowels: bool,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let matrix = Matrix {
            ids: slice(&ids)?,
            weights: slice(&weights)?,
            offsets: slice(&offsets)?,
            width,
        };
        let assessed = self
            .bank
            .assess_rows(row, rule, &matrix, want_vowels)
            .map_err(failure)?;
        let (first, flat, lengths) = self.bank.take_created();
        let (needs, rows) = match assessed {
            Assessed::Needs(needs) => (needs, Vec::new()),
            Assessed::Done(rows) => (Vec::new(), rows),
        };
        let floats = |pick: fn(&crate::assess::RowAssessment) -> f64| {
            PyArray1::from_vec(py, rows.iter().map(pick).collect::<Vec<f64>>())
        };
        let counts = |pick: fn(&crate::assess::RowAssessment) -> usize| {
            PyArray1::from_vec(
                py,
                rows.iter().map(|r| pick(r) as i64).collect::<Vec<i64>>(),
            )
        };
        let pairs: Vec<(u32, u32)> = rows.iter().flat_map(|r| r.pairs.iter().copied()).collect();
        let before: Vec<i64> = rows
            .iter()
            .flat_map(|r| r.before.iter().map(|&s| i64::from(s)))
            .collect();
        let after: Vec<i64> = rows
            .iter()
            .flat_map(|r| r.after.iter().map(|&s| i64::from(s)))
            .collect();
        PyTuple::new(
            py,
            [
                needs.into_pyobject(py)?.into_any(),
                floats(|r| r.mass).into_any(),
                floats(|r| r.short).into_any(),
                floats(|r| r.marked).into_any(),
                counts(|r| r.pairs.len()).into_any(),
                PyArray1::from_vec(
                    py,
                    pairs.iter().map(|p| i64::from(p.0)).collect::<Vec<i64>>(),
                )
                .into_any(),
                PyArray1::from_vec(
                    py,
                    pairs.iter().map(|p| i64::from(p.1)).collect::<Vec<i64>>(),
                )
                .into_any(),
                counts(|r| r.before.len()).into_any(),
                PyArray1::from_vec(py, before).into_any(),
                counts(|r| r.after.len()).into_any(),
                PyArray1::from_vec(py, after).into_any(),
                first.into_pyobject(py)?.into_any(),
                PyArray1::from_vec(py, flat).into_any(),
                PyArray1::from_vec(py, lengths).into_any(),
            ],
        )
    }

    /// Příznakovost slabičné stavby tvaru (`cee.v2.assessment.markedness`); pro testy.
    fn markedness(&mut self, form_id: usize) -> PyResult<f64> {
        self.bank.markedness_of(form_id).map_err(failure)
    }

    /// Předfiltr jednoho tvaru (`FormBank.screen`).
    fn screen(&mut self, form_id: usize) -> PyResult<()> {
        self.bank.screen(form_id).map_err(failure)
    }

    /// Může mít změna `row` v tvaru místo? (`FormBank.may_apply`)
    fn may_apply(&mut self, form_id: usize, row: usize) -> PyResult<bool> {
        self.bank.may_apply(form_id, row).map_err(failure)
    }

    /// Bity změn s možným místem v tvaru po 64bitových slovech od nejnižšího.
    fn rows_of(&mut self, form_id: usize) -> PyResult<Vec<u64>> {
        self.bank.rows_of(form_id).map_err(failure)
    }

    /// Cyklus fonologizace jednoho procesu (`phonology.restructure`): odebírá
    /// z čela fronty (`queue` = potřebné logity a čísla morfémů), dokud je
    /// logit pod `level`, přepisuje tvary a zařazuje přepsané morfémy do front
    /// ostatních procesů (`targets`, bez č. `skip`).
    ///
    /// Vrací `(needs, odebráno, morfémy, tvary, hranice, koncovky, fronty,
    /// zařazené morfémy, jejich logity, první_nové_číslo, nové_hlásky,
    /// nové_délky)`. Je-li `needs` neprázdné, krok se zastavil před dalším
    /// morfémem: Python má zapsat, co se do té doby stalo, doplnit chybějící
    /// údaje a zavolat znovu.
    #[pyo3(signature = (rule, base, lead_scale, store, defaults, targets, freq, row, queue, level, skip))]
    #[allow(clippy::too_many_arguments, clippy::type_complexity)]
    fn restructure_step<'py>(
        &mut self,
        py: Python<'py>,
        rule: u8,
        base: f64,
        lead_scale: f64,
        store: (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>),
        defaults: (
            Bound<'py, PyAny>,
            Bound<'py, PyAny>,
            Bound<'py, PyAny>,
            Bound<'py, PyAny>,
        ),
        targets: RawTargets<'py>,
        freq: BTreeMap<usize, f64>,
        row: usize,
        queue: (Bound<'py, PyAny>, Bound<'py, PyAny>),
        level: f64,
        skip: usize,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let inputs = Inputs::new(&store, &defaults, &targets)?;
        let (needed, morphemes) = (Held::<f64>::new(&queue.0)?, Held::<i32>::new(&queue.1)?);
        let params = Params {
            rule,
            base,
            lead_scale,
        };
        let out = phonology::step(
            &mut self.bank,
            &params,
            &inputs.units(),
            row,
            needed.view(),
            morphemes.view(),
            level,
            &inputs.targets(),
            skip,
            &freq,
        )
        .map_err(failure)?;
        let (first, flat, lengths) = self.bank.take_created();
        let (queues, inserted, logits) = inserts_out(&out.inserts);
        (
            needs_out(out.needs),
            out.popped,
            out.rewrites
                .iter()
                .map(|item| item.morpheme)
                .collect::<Vec<_>>(),
            out.rewrites
                .iter()
                .map(|item| item.form)
                .collect::<Vec<_>>(),
            out.rewrites.iter().map(|item| item.cut).collect::<Vec<_>>(),
            out.rewrites
                .iter()
                .map(|item| item.exponent)
                .collect::<Vec<_>>(),
            queues,
            inserted,
            logits,
            first,
            flat,
            lengths,
        )
            .into_pyobject(py)
    }

    /// Zařazení jednoho morfému do front živých procesů
    /// (`phonology.enter_vocabulary`, `requeue`).
    ///
    /// Vrací `(needs, fronty, morfémy, logity, první_nové_číslo, nové_hlásky,
    /// nové_délky)`; s neprázdným `needs` se nezařadilo nic.
    #[pyo3(signature = (rule, base, lead_scale, store, defaults, targets, freq, morpheme))]
    #[allow(clippy::too_many_arguments, clippy::type_complexity)]
    fn queue_morpheme<'py>(
        &mut self,
        py: Python<'py>,
        rule: u8,
        base: f64,
        lead_scale: f64,
        store: (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>),
        defaults: (
            Bound<'py, PyAny>,
            Bound<'py, PyAny>,
            Bound<'py, PyAny>,
            Bound<'py, PyAny>,
        ),
        targets: RawTargets<'py>,
        freq: BTreeMap<usize, f64>,
        morpheme: usize,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let inputs = Inputs::new(&store, &defaults, &targets)?;
        let params = Params {
            rule,
            base,
            lead_scale,
        };
        let (found, needs) = phonology::queue_morpheme(
            &mut self.bank,
            &params,
            &inputs.units(),
            &inputs.targets(),
            morpheme,
            &freq,
        )
        .map_err(failure)?;
        let (first, flat, lengths) = self.bank.take_created();
        let (queues, inserted, logits) = inserts_out(&found);
        (
            needs_out(needs),
            queues,
            inserted,
            logits,
            first,
            flat,
            lengths,
        )
            .into_pyobject(py)
    }

    /// Fronta procesu při aktivaci (`phonology.activate`) ze slovní zásoby
    /// (příznaky `vocabulary`); `targets` má právě jednu položku, proces sám.
    ///
    /// Vrací `(needs, morfémy, logity, první_nové_číslo, nové_hlásky,
    /// nové_délky)`; morfémy jsou seřazené podle (logit, číslo morfému).
    #[pyo3(signature = (rule, base, lead_scale, store, defaults, targets, freq, row, vocabulary))]
    #[allow(clippy::too_many_arguments, clippy::type_complexity)]
    fn activate<'py>(
        &mut self,
        py: Python<'py>,
        rule: u8,
        base: f64,
        lead_scale: f64,
        store: (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>),
        defaults: (
            Bound<'py, PyAny>,
            Bound<'py, PyAny>,
            Bound<'py, PyAny>,
            Bound<'py, PyAny>,
        ),
        targets: RawTargets<'py>,
        freq: BTreeMap<usize, f64>,
        row: usize,
        vocabulary: Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let inputs = Inputs::new(&store, &defaults, &targets)?;
        let words = Held::<u8>::new(&vocabulary)?;
        let params = Params {
            rule,
            base,
            lead_scale,
        };
        let all = inputs.targets();
        let [own] = all.as_slice() else {
            return Err(failure("aktivace čeká právě jednu frontu".into()));
        };
        let out = phonology::activate(
            &mut self.bank,
            &params,
            &inputs.units(),
            row,
            words.view(),
            own,
            &freq,
            None,
        )
        .map_err(failure)?;
        let (first, flat, lengths) = self.bank.take_created();
        (
            needs_out(out.needs),
            out.morphemes,
            out.needed,
            first,
            flat,
            lengths,
        )
            .into_pyobject(py)
    }

    /// Uložené výsledky tabulky jako pole (−2 = nezkoumáno); pro testy.
    fn stored_results<'py>(
        &self,
        py: Python<'py>,
        row: usize,
        rule: u8,
    ) -> Bound<'py, PyArray1<i64>> {
        PyArray1::from_vec(py, self.bank.stored_results(row, rule))
    }
}

/// Párový součet jako `np.sum` (viz `assess::pairwise_sum`); pro testy shody.
#[pyfunction]
fn pairwise_sum(values: PyReadonlyArray1<'_, f64>) -> PyResult<f64> {
    Ok(crate::assess::pairwise_sum(slice(&values)?))
}

/// Opora procesů zvukových změn (`support::supports`) nad počty prostředí.
///
/// `target`, `left`, `right` jsou masky „proces × sloupec hlásky“ (sloupce jsou
/// hlásky `columns`, seřazené), `right2` masky druhé následující hlásky jen
/// procesů v `right2_rows` (v pořadí řádků ve `right2`); `stressed_rows`
/// a `unstressed_rows` jsou procesy s podmínkou přízvuku. Prostředí mají čísla
/// hlásek, příznak přízvuku a počty; `vowel` je maska samohlásek podle čísla
/// hlásky. Vrací pole opor po procesech, nebo `None`, když některé prostředí
/// obsahuje hlásku mimo `columns`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn sound_supports<'py>(
    py: Python<'py>,
    columns: PyReadonlyArray1<'py, i64>,
    target: PyReadonlyArray2<'py, bool>,
    left: PyReadonlyArray2<'py, bool>,
    right: PyReadonlyArray2<'py, bool>,
    right2: PyReadonlyArray2<'py, bool>,
    right2_rows: PyReadonlyArray1<'py, i64>,
    stressed_rows: PyReadonlyArray1<'py, i64>,
    unstressed_rows: PyReadonlyArray1<'py, i64>,
    segment: PyReadonlyArray1<'py, i64>,
    previous: PyReadonlyArray1<'py, i64>,
    following: PyReadonlyArray1<'py, i64>,
    following2: PyReadonlyArray1<'py, i64>,
    stressed: PyReadonlyArray1<'py, bool>,
    vowel: PyReadonlyArray1<'py, bool>,
    count: PyReadonlyArray1<'py, i64>,
) -> PyResult<Option<Bound<'py, PyArray1<i64>>>> {
    let shape = |array: &PyReadonlyArray2<'py, bool>| (array.shape()[0], array.shape()[1]);
    let (processes, width) = shape(&target);
    if shape(&left) != (processes, width)
        || shape(&right) != (processes, width)
        || slice(&columns)?.len() != width
    {
        return Err(failure("masky procesů mají různý tvar".into()));
    }
    let (second_rows, second_width) = shape(&right2);
    if second_rows != slice(&right2_rows)?.len() || (second_rows > 0 && second_width != width) {
        return Err(failure(
            "masky druhé následující hlásky mají špatný tvar".into(),
        ));
    }
    let mut second_row = vec![-1_i64; processes];
    let mut stress = vec![support::STRESS_ANY; processes];
    for (position, &row) in slice(&right2_rows)?.iter().enumerate() {
        *second_row
            .get_mut(row as usize)
            .ok_or_else(|| failure("proces mimo masky".into()))? = position as i64;
    }
    for (rows, kind) in [
        (&stressed_rows, support::STRESS_STRESSED),
        (&unstressed_rows, support::STRESS_UNSTRESSED),
    ] {
        for &row in slice(rows)? {
            *stress
                .get_mut(row as usize)
                .ok_or_else(|| failure("proces mimo masky".into()))? = kind;
        }
    }
    let size = slice(&count)?.len();
    let positions = [
        slice(&segment)?,
        slice(&previous)?,
        slice(&following)?,
        slice(&following2)?,
    ];
    if positions.iter().any(|column| column.len() != size) || slice(&stressed)?.len() != size {
        return Err(failure("sloupce prostředí mají různou délku".into()));
    }
    // Maska samohlásek se čte podle čísla hlásky: musí pokrýt všechna čísla.
    let vowels = slice(&vowel)?;
    if positions[0]
        .iter()
        .any(|&number| number < 0 || number as usize >= vowels.len())
    {
        return Err(failure("hláska mimo masku samohlásek".into()));
    }
    let masks = Masks {
        width,
        target: slice(&target)?,
        left: slice(&left)?,
        right: slice(&right)?,
        right2: slice(&right2)?,
        right2_row: &second_row,
        stress: &stress,
    };
    let contexts = Contexts {
        columns: slice(&columns)?,
        segment: positions[0],
        previous: positions[1],
        following: positions[2],
        following2: positions[3],
        stressed: slice(&stressed)?,
        vowel: vowels,
        count: slice(&count)?,
    };
    Ok(support::supports(&masks, &contexts).map(|found| PyArray1::from_vec(py, found)))
}

#[pymodule]
mod cee_core {
    use pyo3::prelude::*;

    #[pymodule_export]
    use super::pairwise_sum;
    #[pymodule_export]
    use super::sound_supports;
    #[pymodule_export]
    use super::NativeBank;
    #[pymodule_export]
    use crate::code_state_python::{
        extend_names, names_count, restore_code, restructure_groups, NativeCode,
    };
    #[pymodule_export]
    use crate::index_python::clarity_scores;
    #[pymodule_export]
    use crate::index_python::SoundIndex;
    #[pymodule_export]
    use crate::pressures_python::{pressure_scores, take_created, AssessIndex, PressureStep};
    #[pymodule_export]
    use crate::python_pools::{
        hear, libm_probe, normalized, settle, NativeCells, NativeStep, Slab,
    };
    #[pymodule_export]
    use crate::sites_python::SiteIndex;

    #[pymodule_init]
    fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add("INTERFACE_VERSION", crate::INTERFACE_VERSION)
    }
}
