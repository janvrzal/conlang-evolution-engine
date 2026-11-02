//! Vazba na Python (PyO3): tenká vrstva nad `bank::Bank`.
//!
//! Rozhraní je dávkové: tvary i výsledky putují jako pole `numpy`, ne po
//! jednom. Jednotlivé dotazy (`result`, `may_apply`) jsou jen pro horké cesty,
//! které volají Python po jednom tvaru.

use numpy::{PyArray1, PyReadonlyArray1};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyTuple;

use crate::bank::{Bank, Outcome};
use crate::process::Proc;

fn failure(message: String) -> PyErr {
    PyValueError::new_err(message)
}

fn slice<'a, T: numpy::Element>(array: &'a PyReadonlyArray1<'_, T>) -> PyResult<&'a [T]> {
    array
        .as_slice()
        .map_err(|_| failure("pole musí být souvislé".into()))
}

/// Banka tvarů a tabulky procesů v Rustu; zrcadlo `FormBank` z Pythonu.
#[pyclass(module = "cee_core")]
pub struct NativeBank {
    bank: Bank,
}

#[pymethods]
impl NativeBank {
    /// `boundary` je číslo hranice slova (počet hlásek), `vowel` maska
    /// samohlásek s hranicí na konci.
    #[new]
    fn new(boundary: i32, vowel: PyReadonlyArray1<'_, bool>) -> PyResult<Self> {
        let bank = Bank::new(boundary, slice(&vowel)?.to_vec()).map_err(failure)?;
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

#[pymodule]
mod cee_core {
    use pyo3::prelude::*;

    #[pymodule_export]
    use super::NativeBank;

    #[pymodule_init]
    fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add("INTERFACE_VERSION", crate::INTERFACE_VERSION)
    }
}
