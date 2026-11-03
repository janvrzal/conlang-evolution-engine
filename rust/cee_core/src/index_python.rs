//! Vazba `index::SoundIndex` na Python (PyO3): tenká vrstva, jen převody polí.
//!
//! Pole tvarů, výchozích tvarů a příznaků slovní zásoby jdou z Pythonu bez
//! kopírování (`array.array`, `bytearray`); výstupy se vracejí jako pole.

use numpy::{PyArray1, PyReadonlyArray1, PyReadonlyArray2};
use pyo3::prelude::*;

use crate::index::{self, GroupInput};
use crate::python::{failure, slice, Held, NativeBank};

/// Co `sync` žádá od Pythonu: výchozí tvary k doplnění (pozice skupiny, čísla morfémů)
/// a inventáře, pro které chybí sada kandidátů.
type NeedsOut = (Vec<(usize, Vec<u32>)>, Vec<Vec<u32>>);

/// Index prostředí a opor zvukových změn všech kódů světa v Rustu;
/// zrcadlo `cee.v2.language.sound_index.SoundIndex`.
#[pyclass(module = "cee_core")]
pub struct SoundIndex {
    inner: index::SoundIndex,
}

#[pymethods]
impl SoundIndex {
    /// `scales`: míra každé rodiny na jednotku opory, v pořadí rodin.
    #[new]
    fn new(scales: Vec<f64>) -> Self {
        SoundIndex {
            inner: index::SoundIndex::new(scales),
        }
    }

    /// Dorovná kódy (`tokens`) na aktuální stav. Pole podle čísla morfému:
    /// příznaky slovní zásoby, tvary kódu a výchozí tvary světa. Vrací, co chybí.
    #[allow(clippy::too_many_arguments)]
    fn sync(
        &mut self,
        bank: PyRef<'_, NativeBank>,
        tokens: Vec<i64>,
        rules: Vec<u8>,
        flags: Vec<Bound<'_, PyAny>>,
        forms: Vec<Bound<'_, PyAny>>,
        defaults: Vec<Bound<'_, PyAny>>,
    ) -> PyResult<NeedsOut> {
        let count = tokens.len();
        if [rules.len(), flags.len(), forms.len(), defaults.len()]
            .iter()
            .any(|&size| size != count)
        {
            return Err(failure("seznamy kódů mají různou délku".into()));
        }
        let flags = Held::<u8>::all(&flags)?;
        let forms = Held::<i32>::all(&forms)?;
        let defaults = Held::<i32>::all(&defaults)?;
        let inputs: Vec<GroupInput<'_>> = (0..count)
            .map(|at| GroupInput {
                token: tokens[at],
                rule: rules[at],
                flags: flags[at].view(),
                forms: forms[at].view(),
                defaults: defaults[at].view(),
            })
            .collect();
        let needs = self.inner.sync(&bank.bank, &inputs).map_err(failure)?;
        Ok((needs.defaults, needs.sets))
    }

    /// Zaregistruje sadu kandidátů pro inventář (viz `_CombinedSoundCandidates`).
    #[allow(clippy::too_many_arguments)]
    fn register_set(
        &mut self,
        inventory: Vec<u32>,
        columns: PyReadonlyArray1<'_, i64>,
        target: PyReadonlyArray2<'_, bool>,
        left: PyReadonlyArray2<'_, bool>,
        right: PyReadonlyArray2<'_, bool>,
        right2: PyReadonlyArray2<'_, bool>,
        right2_rows: PyReadonlyArray1<'_, i64>,
        stressed_rows: PyReadonlyArray1<'_, i64>,
        unstressed_rows: PyReadonlyArray1<'_, i64>,
        family_ends: Vec<usize>,
    ) -> PyResult<()> {
        let columns: Vec<u32> = slice(&columns)?.iter().map(|&c| c as u32).collect();
        self.inner
            .register_set(
                inventory,
                columns,
                [slice(&target)?, slice(&left)?, slice(&right)?],
                slice(&right2)?,
                slice(&right2_rows)?,
                slice(&stressed_rows)?,
                slice(&unstressed_rows)?,
                family_ends,
            )
            .map_err(failure)
    }

    fn inventory(&self, token: i64) -> Vec<u32> {
        self.inner.inventory(token)
    }

    fn has_families(&self, token: i64) -> bool {
        self.inner.has_families(token)
    }

    /// Součty měr (kód × rodina), po řádcích za sebou.
    fn totals<'py>(&self, py: Python<'py>, tokens: Vec<i64>) -> Bound<'py, PyArray1<f64>> {
        PyArray1::from_vec(py, self.inner.totals(&tokens))
    }

    /// Místa (pořadí v rodině), míry a součet měr jedné rodiny.
    #[allow(clippy::type_complexity)]
    fn family<'py>(
        &self,
        py: Python<'py>,
        token: i64,
        family: usize,
    ) -> Option<(Bound<'py, PyArray1<i64>>, Bound<'py, PyArray1<f64>>, f64)> {
        self.inner.family(token, family).map(|state| {
            (
                PyArray1::from_vec(py, state.sites.iter().map(|&s| i64::from(s)).collect()),
                PyArray1::from_vec(py, state.rates.clone()),
                state.total,
            )
        })
    }

    fn supports<'py>(&self, py: Python<'py>, token: i64) -> Bound<'py, PyArray1<i64>> {
        PyArray1::from_vec(py, self.inner.supports(token))
    }

    /// Počty prostředí kódu: předchozí, hláska, další, přízvuk, druhá další, počet.
    #[allow(clippy::type_complexity)]
    fn context_counts<'py>(
        &mut self,
        py: Python<'py>,
        bank: PyRef<'_, NativeBank>,
        token: i64,
    ) -> (
        Bound<'py, PyArray1<i64>>,
        Bound<'py, PyArray1<i64>>,
        Bound<'py, PyArray1<i64>>,
        Bound<'py, PyArray1<bool>>,
        Bound<'py, PyArray1<i64>>,
        Bound<'py, PyArray1<i64>>,
    ) {
        let (previous, segment, following, stressed, following2, count) =
            self.inner.context_counts(&bank.bank, token);
        let wide =
            |values: Vec<u32>| PyArray1::from_vec(py, values.into_iter().map(i64::from).collect());
        (
            wide(previous),
            wide(segment),
            wide(following),
            PyArray1::from_vec(py, stressed),
            wide(following2),
            PyArray1::from_vec(py, count),
        )
    }

    /// Započítané tvary a pravidla (podle čísla morfému) pro uložení stavu.
    fn export<'py>(
        &self,
        py: Python<'py>,
        token: i64,
    ) -> (Bound<'py, PyArray1<i32>>, Bound<'py, PyArray1<u8>>) {
        let (forms, rules) = self.inner.export(token);
        (PyArray1::from_vec(py, forms), PyArray1::from_vec(py, rules))
    }

    /// Obnoví stav kódu z uložených polí (opory se přepočítají při příštím dorovnání).
    fn import_group(
        &mut self,
        bank: PyRef<'_, NativeBank>,
        token: i64,
        forms: PyReadonlyArray1<'_, i32>,
        rules: PyReadonlyArray1<'_, u8>,
    ) -> PyResult<()> {
        self.inner
            .import(
                &bank.bank,
                token,
                slice(&forms)?.to_vec(),
                slice(&rules)?.to_vec(),
            )
            .map_err(failure)
    }
}
