//! Vazba `index::SoundIndex` na Python (PyO3): tenká vrstva, jen převody polí.
//!
//! Pole tvarů, výchozích tvarů a příznaků slovní zásoby jdou z Pythonu bez
//! kopírování (`array.array`, `bytearray`); výstupy se vracejí jako pole.

use numpy::{PyArray1, PyReadonlyArray1, PyReadonlyArray2};
use pyo3::prelude::*;

use crate::bank::Bank;
use crate::candidates::{self, Candidate, Pat, SegTable};
use crate::clarity::{self, GroupColumns};
use crate::index::{self, GroupInput};
use crate::python::{failure, slice, Held, NativeBank};

/// Co `sync` žádá od Pythonu: výchozí tvary k doplnění (pozice skupiny, čísla morfémů)
/// a inventáře, pro které chybí sada kandidátů.
type NeedsOut = (Vec<(usize, Vec<u32>)>, Vec<Vec<u32>>);

/// Index prostředí a opor zvukových změn všech kódů světa v Rustu;
/// zrcadlo `cee.v2.language.sound_index.SoundIndex`.
#[pyclass(module = "cee_core")]
pub struct SoundIndex {
    pub(crate) inner: index::SoundIndex,
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
    /// příznaky slovní zásoby a tvary kódu. Vrací, co chybí.
    #[allow(clippy::too_many_arguments)]
    fn sync(
        &mut self,
        bank: PyRef<'_, NativeBank>,
        tokens: Vec<i64>,
        rules: Vec<u8>,
        flags: Vec<Bound<'_, PyAny>>,
        forms: Vec<Bound<'_, PyAny>>,
    ) -> PyResult<NeedsOut> {
        let needs = sound_sync(&mut self.inner, &bank.bank, &tokens, &rules, &flags, &forms)?;
        Ok((needs.defaults, needs.sets))
    }

    /// Výchozí tvary morfémů (obsah hlásek), které index vyžádal; drží je mimo banku tvarů.
    fn set_defaults(&mut self, numbers: Vec<u32>, forms: Vec<Vec<i32>>) -> PyResult<()> {
        if numbers.len() != forms.len() {
            return Err(failure("čísla a tvary mají různou délku".into()));
        }
        self.inner.set_defaults(&numbers, &forms);
        Ok(())
    }

    /// Snímek tabulky hlásek (jména rysů, matice rysů, zápis IPA, samohlásky, kódy tónů, čísla
    /// symbolů v pořadí `candidate_symbols`, tónové značky): od té chvíle si Rust sady kandidátů
    /// zvukových změn staví sám.
    #[allow(clippy::too_many_arguments)]
    fn set_table(
        &mut self,
        names: Vec<String>,
        vectors: PyReadonlyArray2<'_, i8>,
        ipa: Vec<String>,
        vowel: PyReadonlyArray1<'_, bool>,
        tone: PyReadonlyArray1<'_, i32>,
        canon: PyReadonlyArray1<'_, i32>,
        symbols: Vec<i64>,
        tones: Vec<String>,
    ) -> PyResult<()> {
        let table = SegTable::new(
            names,
            slice(&vectors)?.to_vec(),
            ipa,
            slice(&vowel)?.to_vec(),
            slice(&tone)?.to_vec(),
            slice(&canon)?.to_vec(),
            &symbols,
            tones,
        )
        .map_err(failure)?;
        self.inner.set_table(table);
        Ok(())
    }

    fn has_table(&self) -> bool {
        self.inner.has_table()
    }

    /// Sada kandidátů pro inventář, jak ji Rust sestavuje (pro test proti Pythonu): ID proměnných,
    /// konce rodin, popisy kandidátů, sloupce hlásek a masky (cíl, vlevo, vpravo po řádcích kandidátů,
    /// druhý vpravo jen pro `right2_rows`) a řádky podmínky přízvuku.
    #[allow(clippy::type_complexity)]
    fn describe_set<'py>(
        &self,
        py: Python<'py>,
        inventory: Vec<u32>,
    ) -> PyResult<(
        Vec<String>,
        Vec<usize>,
        Vec<Spec>,
        Bound<'py, PyArray1<i64>>,
        [Bound<'py, PyArray1<bool>>; 4],
        [Vec<i64>; 3],
    )> {
        let table = self
            .inner
            .table()
            .ok_or_else(|| failure("chybí snímek tabulky hlásek".into()))?;
        let built = candidates::build(table, &inventory).map_err(failure)?;
        let masks = candidates::masks(table, &inventory, &built);
        let specs = built.candidates.iter().map(spec_out).collect();
        Ok((
            built.ids,
            built.family_ends,
            specs,
            PyArray1::from_vec(py, masks.columns.iter().map(|&c| i64::from(c)).collect()),
            [
                PyArray1::from_vec(py, masks.target),
                PyArray1::from_vec(py, masks.left),
                PyArray1::from_vec(py, masks.right),
                PyArray1::from_vec(py, masks.right2),
            ],
            [
                masks.right2_rows,
                masks.stressed_rows,
                masks.unstressed_rows,
            ],
        ))
    }

    /// ID proměnných míst jedné rodiny (v pořadí míst), když sadu sestavil Rust.
    fn family_names(&self, token: i64, family: usize) -> Option<Vec<String>> {
        self.inner
            .site_ids(token, family)
            .map(|ids| ids.into_iter().map(str::to_string).collect())
    }

    /// Opory míst jedné rodiny v pořadí míst.
    fn family_supports(&self, token: i64, family: usize) -> Option<Vec<i64>> {
        self.inner.site_supports(token, family)
    }

    /// Popis kandidáta místa rodiny (pole `Process`), ze kterého Python postaví proces.
    fn family_spec(&self, token: i64, family: usize, position: usize) -> Option<Spec> {
        self.inner
            .site_candidate(token, family, position)
            .map(|(candidate, _)| spec_out(candidate))
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

/// Dorovná kódy indexu prostředí (viz `SoundIndex::sync`).
pub(crate) fn sound_sync(
    inner: &mut index::SoundIndex,
    bank: &Bank,
    tokens: &[i64],
    rules: &[u8],
    flags: &[Bound<'_, PyAny>],
    forms: &[Bound<'_, PyAny>],
) -> PyResult<index::Needs> {
    let count = tokens.len();
    if [rules.len(), flags.len(), forms.len()]
        .iter()
        .any(|&size| size != count)
    {
        return Err(failure("seznamy kódů mají různou délku".into()));
    }
    let flags = Held::<u8>::all(flags)?;
    let forms = Held::<i32>::all(forms)?;
    let inputs: Vec<GroupInput<'_>> = (0..count)
        .map(|at| GroupInput {
            token: tokens[at],
            rule: rules[at],
            flags: flags[at].view(),
            forms: forms[at].view(),
        })
        .collect();
    inner.sync(bank, &inputs).map_err(failure)
}

/// Předpis vzoru: druh, dvojice (rys, hodnota) a zápis IPA hlásek výčtu.
type Recipe = (&'static str, Vec<(String, String)>, Vec<String>);

/// Popis kandidáta: (rodina, popis, operace, změny, výstupní hláska, přízvuk, jádro),
/// (úleva, úleva je celé číslo, zřetelnost, redukční, povolené značky, tón)
/// a vzory (cíl, vlevo, vpravo, druhý vpravo).
#[allow(clippy::type_complexity)]
type Spec = (
    (
        usize,
        String,
        &'static str,
        Vec<(String, String)>,
        Option<u32>,
        Option<&'static str>,
        bool,
    ),
    (f64, bool, f64, bool, Vec<String>, Option<i32>),
    (Recipe, Option<Recipe>, Option<Recipe>, Option<Recipe>),
);

fn recipe_out(pattern: &Pat) -> Recipe {
    pattern.recipe()
}

fn spec_out(candidate: &Candidate) -> Spec {
    (
        (
            candidate.family,
            candidate.label.clone(),
            candidate.operation.name(),
            candidate.changes.clone(),
            candidate.segment,
            candidate.stress.name(),
            candidate.medial,
        ),
        (
            candidate.ease,
            candidate.ease_int,
            candidate.clarity,
            candidate.reductive,
            candidate.allow.clone(),
            candidate.tone,
        ),
        (
            recipe_out(&candidate.target),
            candidate.left.as_ref().map(|p| recipe_out(p)),
            candidate.right.as_ref().map(|p| recipe_out(p)),
            candidate.right2.as_ref().map(|p| recipe_out(p)),
        ),
    )
}

/// Symboly, jejichž číslo v tabulce hlásek Rust potřebuje k sestavení kandidátů (pro `set_table`).
#[pyfunction]
pub fn candidate_symbols() -> Vec<String> {
    candidates::symbol_list()
}

/// Druhy rodin zvukových změn v pořadí `SOUND_CHANGES`.
#[pyfunction]
pub fn candidate_families() -> Vec<&'static str> {
    candidates::FAMILIES.to_vec()
}

/// Skóre lexikální jasnosti dávky dvojic (skupina, morfém, pojem).
///
/// Vrací pole skóre, nebo seznam čísel morfémů, jejichž výchozí tvar musí Python
/// nejdřív zařadit do banky (pak se volá znovu).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn clarity_scores<'py>(
    py: Python<'py>,
    bank: PyRef<'_, NativeBank>,
    roots: Vec<Bound<'py, PyAny>>,
    forms: Vec<Bound<'py, PyAny>>,
    defaults: Bound<'py, PyAny>,
    related: PyReadonlyArray1<'py, i64>,
    groups: PyReadonlyArray1<'py, i64>,
    morphemes: PyReadonlyArray1<'py, i64>,
    concepts: PyReadonlyArray1<'py, i64>,
) -> PyResult<Bound<'py, PyAny>> {
    if roots.len() != forms.len() {
        return Err(failure("seznamy skupin mají různou délku".into()));
    }
    let roots = Held::<i32>::all(&roots)?;
    let forms = Held::<i32>::all(&forms)?;
    let defaults = Held::<i32>::new(&defaults)?;
    let columns: Vec<GroupColumns<'_>> = roots
        .iter()
        .zip(&forms)
        .map(|(roots, forms)| GroupColumns {
            roots: roots.view(),
            forms: forms.view(),
        })
        .collect();
    let (groups, morphemes, concepts) = (slice(&groups)?, slice(&morphemes)?, slice(&concepts)?);
    if morphemes.len() != groups.len() || concepts.len() != groups.len() {
        return Err(failure("dotazy mají různou délku".into()));
    }
    let queries: Vec<(usize, i64, i64)> = (0..groups.len())
        .map(|at| (groups[at] as usize, morphemes[at], concepts[at]))
        .collect();
    let outcome = clarity::scores(
        &bank.bank,
        &columns,
        defaults.view(),
        slice(&related)?,
        &queries,
    )
    .map_err(failure)?;
    match outcome {
        clarity::Outcome::Scores(found) => Ok(PyArray1::from_vec(py, found).into_any()),
        clarity::Outcome::Needs(numbers) => Ok(numbers.into_pyobject(py)?.into_any()),
    }
}
