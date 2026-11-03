//! Vazba `sites::SiteIndex` na Python (PyO3): tenká vrstva, jen převody polí.
//!
//! Pole stavu kódů (příznaky slovní zásoby, tvary, dominantní kořeny) a sloupce
//! světa jdou z Pythonu bez kopírování (`array.array`, `bytearray`); malé pomocné
//! tabulky (jména, výchozí tvary, vlastnosti kořenů, graf, katalog, konstrukce)
//! se posílají přírůstkově jen při změně.

use numpy::{PyArray1, PyReadonlyArray1};
use pyo3::prelude::*;

use crate::morphology_index::{CodeInput, Columns, Store};
use crate::python::{failure, slice, Held, NativeBank};
use crate::semantic_index::{self, Graph};
use crate::sites::{self, Borrowing, Catalog, Request};

/// Tři pole úložiště tvarů kódu: tvar, hranice, koncovka.
type Triple<'py> = (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>);

/// Výpůjčky: kanály, zda jsou odlišné, podíl vstupu (skupina × kanál), skupiny s dárci a filtr (kanál × pojem).
type BorrowingIn<'py> = (
    usize,
    bool,
    PyReadonlyArray1<'py, f64>,
    Vec<bool>,
    PyReadonlyArray1<'py, f64>,
);

/// Počty a součty dávky: součty (skupina × sloupec) a počty míst.
type TotalsOut<'py> = (Bound<'py, PyArray1<f64>>, Bound<'py, PyArray1<i64>>);

/// Míry všech druhů změn kromě zvukových a výpůjček v Rustu; zrcadlo
/// `cee.v2.language.site_index.SiteIndex` (Python reference).
#[pyclass(module = "cee_core")]
pub struct SiteIndex {
    inner: sites::SiteIndex,
}

#[pymethods]
impl SiteIndex {
    #[new]
    fn new() -> Self {
        SiteIndex {
            inner: sites::SiteIndex::new(),
        }
    }

    /// Připojí další jména morfémů a pojmů; `*_from` je počet jmen, které Rust už zná.
    fn set_names(
        &mut self,
        morphemes_from: usize,
        morphemes: Vec<String>,
        concepts_from: usize,
        concepts: Vec<String>,
    ) -> PyResult<()> {
        if morphemes_from != self.inner.morph.names.len()
            || concepts_from != self.inner.semantic.concepts.len()
        {
            return Err(failure("jména morfémů či pojmů na sebe nenavazují".into()));
        }
        self.inner.morph.names.extend(&morphemes);
        self.inner.semantic.concepts.extend(&concepts);
        Ok(())
    }

    /// Výchozí tvary morfémů (obsah hlásek), které index potřebuje a nemá.
    fn set_defaults(&mut self, numbers: Vec<u32>, forms: Vec<Vec<i32>>) -> PyResult<()> {
        if numbers.len() != forms.len() {
            return Err(failure("čísla a tvary mají různou délku".into()));
        }
        for (number, form) in numbers.iter().zip(&forms) {
            self.inner.morph.defaults.set(*number as usize, form);
        }
        Ok(())
    }

    /// Vlastnosti kořenů: pojem zdroje odvozeniny (−1 = není) a číslo základu (−1 = žádný).
    fn set_roots(&mut self, numbers: Vec<u32>, sources: Vec<i32>, bases: Vec<i32>) -> PyResult<()> {
        if numbers.len() != sources.len() || numbers.len() != bases.len() {
            return Err(failure("vlastnosti kořenů mají různou délku".into()));
        }
        self.inner.semantic.set_roots(&numbers, &sources, &bases);
        Ok(())
    }

    /// Graf pojmů: vztahy podle cíle (CSR), jejich váhy a příznaky, recepty složenin.
    #[allow(clippy::too_many_arguments)]
    fn set_graph(
        &mut self,
        concepts: usize,
        into_start: PyReadonlyArray1<'_, i64>,
        source: PyReadonlyArray1<'_, i64>,
        shift: PyReadonlyArray1<'_, f64>,
        conversion: PyReadonlyArray1<'_, f64>,
        derivation: PyReadonlyArray1<'_, f64>,
        flags: PyReadonlyArray1<'_, u8>,
        compound_start: PyReadonlyArray1<'_, i64>,
        left: PyReadonlyArray1<'_, i64>,
        right: PyReadonlyArray1<'_, i64>,
    ) -> PyResult<()> {
        let narrow = |values: &[i64]| -> Vec<u32> { values.iter().map(|&v| v as u32).collect() };
        let signed = |values: &[i64]| -> Vec<i32> { values.iter().map(|&v| v as i32).collect() };
        let graph = Graph::new(
            concepts,
            narrow(slice(&into_start)?),
            signed(slice(&source)?),
            slice(&shift)?.to_vec(),
            slice(&conversion)?.to_vec(),
            slice(&derivation)?.to_vec(),
            slice(&flags)?.to_vec(),
            narrow(slice(&compound_start)?),
            signed(slice(&left)?),
            signed(slice(&right)?),
        )
        .map_err(failure)?;
        self.inner.semantic.set_graph(graph);
        Ok(())
    }

    /// Katalog gramatických funkcí v pořadí jmen (viz `sites::Catalog`).
    #[allow(clippy::too_many_arguments)]
    fn set_catalog(
        &mut self,
        template: Vec<u8>,
        word_class: Vec<u8>,
        class: Vec<i32>,
        cell: Vec<i32>,
        has_cell: Vec<bool>,
        has_orders: Vec<bool>,
        coverage: Vec<f64>,
        source_start: Vec<u32>,
        sources: Vec<i32>,
        donor_start: Vec<u32>,
        donors: Vec<u32>,
        deputy_start: Vec<u32>,
        deputies: Vec<u32>,
    ) -> PyResult<()> {
        self.inner.catalog = Catalog::new(
            template,
            word_class,
            class,
            cell,
            has_cell,
            has_orders,
            coverage,
            source_start,
            sources,
            donor_start,
            donors,
            deputy_start,
            deputies,
        )
        .map_err(failure)?;
        Ok(())
    }

    /// Druh a stupeň konstrukcí podle čísla varianty.
    fn set_constructions(
        &mut self,
        variants: Vec<u32>,
        kinds: Vec<i8>,
        stages: Vec<i8>,
    ) -> PyResult<()> {
        if variants.len() != kinds.len() || variants.len() != stages.len() {
            return Err(failure("konstrukce mají různou délku".into()));
        }
        for ((variant, kind), stage) in variants.iter().zip(&kinds).zip(&stages) {
            self.inner
                .constructions
                .set(*variant as usize, *kind, *stage);
        }
        Ok(())
    }

    /// Dorovná morfologii kódů. Pole podle čísla morfému: příznaky slovní zásoby,
    /// tvary kódu (tvar, hranice, koncovka) a sloupce světa. Vrací čísla morfémů,
    /// jejichž výchozí tvar musí Python doplnit (`set_defaults`) a zavolat znovu.
    #[allow(clippy::too_many_arguments)]
    fn sync_morphology(
        &mut self,
        bank: PyRef<'_, NativeBank>,
        tokens: Vec<i64>,
        flags: Vec<Bound<'_, PyAny>>,
        store: Vec<Triple<'_>>,
        columns: Vec<Bound<'_, PyAny>>,
    ) -> PyResult<Vec<u32>> {
        if flags.len() != tokens.len() || store.len() != tokens.len() || columns.len() != 6 {
            return Err(failure("seznamy kódů či sloupců mají špatnou délku".into()));
        }
        let kind = Held::<i8>::new(&columns[0])?;
        let class = Held::<i32>::new(&columns[1])?;
        let cell = Held::<i32>::new(&columns[2])?;
        let lexeme = Held::<i32>::new(&columns[3])?;
        let exponent = Held::<i32>::new(&columns[4])?;
        let boundary = Held::<i32>::new(&columns[5])?;
        let cols = Columns {
            kind: kind.view(),
            class: class.view(),
            cell: cell.view(),
            lexeme: lexeme.view(),
            exponent: exponent.view(),
            boundary: boundary.view(),
        };
        let flags = Held::<u8>::all(&flags)?;
        let mut needs: Vec<u32> = Vec::new();
        for (at, token) in tokens.iter().enumerate() {
            let form = Held::<i32>::new(&store[at].0)?;
            let bounds = Held::<i32>::new(&store[at].1)?;
            let exps = Held::<i32>::new(&store[at].2)?;
            let input = CodeInput {
                token: *token,
                flags: flags[at].view(),
                store: Store {
                    form: form.view(),
                    boundary: bounds.view(),
                    exponent: exps.view(),
                },
            };
            needs.extend(
                self.inner
                    .morph
                    .sync(&bank.bank, &cols, &input)
                    .map_err(failure)?,
            );
        }
        needs.sort_unstable();
        needs.dedup();
        Ok(needs)
    }

    /// Dorovná sémantiku kódů: dominantní kořeny podle pojmu, pojmy lexikálních
    /// proměnných a tabu. Vrací čísla kořenů, jejichž vlastnosti Python doplní (`set_roots`).
    fn sync_semantic(
        &mut self,
        tokens: Vec<i64>,
        dominant: Vec<Bound<'_, PyAny>>,
        sites: Vec<Bound<'_, PyAny>>,
        taboo: Vec<Bound<'_, PyAny>>,
        suffix: Vec<bool>,
    ) -> PyResult<Vec<u32>> {
        let count = tokens.len();
        if [dominant.len(), sites.len(), taboo.len(), suffix.len()]
            .iter()
            .any(|&size| size != count)
        {
            return Err(failure("seznamy kódů mají různou délku".into()));
        }
        let dominant = Held::<i32>::all(&dominant)?;
        let sites = Held::<i32>::all(&sites)?;
        let taboo = Held::<i32>::all(&taboo)?;
        let mut needs: Vec<u32> = Vec::new();
        for (at, token) in tokens.iter().enumerate() {
            let input = semantic_index::Input {
                token: *token,
                dominant: dominant[at].view(),
                sites: sites[at].view(),
                taboo: taboo[at].view(),
                suffix: suffix[at],
            };
            needs.extend(self.inner.semantic.sync(&input).map_err(failure)?);
        }
        needs.sort_unstable();
        needs.dedup();
        Ok(needs)
    }

    /// Celkové míry a počty míst (skupina × sloupec, po řádcích za sebou).
    #[allow(clippy::too_many_arguments)]
    fn totals<'py>(
        &mut self,
        py: Python<'py>,
        tokens: Vec<i64>,
        variants: PyReadonlyArray1<'py, i32>,
        l2_share: PyReadonlyArray1<'py, f64>,
        lexical: PyReadonlyArray1<'py, i64>,
        morph_on: Vec<bool>,
        semantic_on: Vec<bool>,
        bases: PyReadonlyArray1<'py, f64>,
        scales: (f64, f64, f64),
        borrowing: Option<BorrowingIn<'py>>,
    ) -> PyResult<TotalsOut<'py>> {
        let groups = tokens.len();
        let functions = self.inner.catalog.count;
        let variants = slice(&variants)?;
        let l2_share = slice(&l2_share)?;
        let lexical = slice(&lexical)?;
        let bases = slice(&bases)?;
        if variants.len() != groups * functions
            || l2_share.len() != groups
            || lexical.len() != groups
            || morph_on.len() != groups
            || semantic_on.len() != groups
            || bases.len() != sites::COLUMNS
        {
            return Err(failure("vstup dávky má nesouhlasné rozměry".into()));
        }
        let request = Request {
            tokens: &tokens,
            variants,
            l2_share,
            lexical,
            morph_on: &morph_on,
            semantic_on: &semantic_on,
            bases,
            coinage_scale: scales.0,
            analogy_boost: scales.1,
            loss_boost: scales.2,
            borrowing: match &borrowing {
                Some((channels, distinct, exposure, donors, factors)) => {
                    let factors = slice(factors)?;
                    let concepts = factors.len() / (*channels).max(1);
                    Some(Borrowing {
                        channels: *channels,
                        distinct: *distinct,
                        exposure: slice(exposure)?,
                        donors,
                        factors,
                        concepts,
                    })
                }
                None => None,
            },
        };
        let (totals, counts) = self.inner.totals(&request);
        Ok((
            PyArray1::from_vec(py, totals),
            PyArray1::from_vec(py, counts),
        ))
    }

    /// Pojmy míst sémantické změny v pořadí jmen pojmů.
    fn semantic_sites<'py>(
        &self,
        py: Python<'py>,
        token: i64,
        kind: usize,
    ) -> Bound<'py, PyArray1<u32>> {
        PyArray1::from_vec(py, self.inner.semantic.sites(token, kind))
    }

    /// Míry míst sémantické změny při základní míře `base`.
    fn semantic_rates<'py>(
        &mut self,
        py: Python<'py>,
        token: i64,
        kind: usize,
        base: f64,
    ) -> Bound<'py, PyArray1<f64>> {
        PyArray1::from_vec(py, self.inner.semantic.rates(token, kind, base))
    }

    /// Dominantní kořeny, které sémantický index započítal.
    fn semantic_dominant<'py>(&self, py: Python<'py>, token: i64) -> Bound<'py, PyArray1<i32>> {
        PyArray1::from_vec(py, self.inner.semantic.dominant(token).to_vec())
    }

    /// Místa vyrovnání či rozšíření seřazená podle řetězcového ID: tvary a koncovky.
    fn morph_candidates<'py>(
        &self,
        py: Python<'py>,
        token: i64,
        extension: bool,
    ) -> (Bound<'py, PyArray1<u32>>, Bound<'py, PyArray1<i32>>) {
        let (units, exponents) = self.inner.morph.candidates(token, extension);
        (
            PyArray1::from_vec(py, units),
            PyArray1::from_vec(py, exponents),
        )
    }

    /// Počty koncovek (třída, buňka, koncovka, počet) a podoby koncovek (koncovka, hlásky, počet).
    #[allow(clippy::type_complexity)]
    fn morph_stats(&self, token: i64) -> (Vec<[i64; 4]>, Vec<(i32, Vec<i32>, u32)>) {
        self.inner.morph.stats(token)
    }

    /// Čísla členů slovní zásoby kódu (tvary slov) vzestupně.
    fn morph_members(&self, token: i64) -> Vec<u32> {
        self.inner.morph.members(token)
    }

    /// Slabost buňky (třída, buňka jako čísla číslování morfémů).
    fn morph_weakness(&self, token: i64, class: i32, cell: i32) -> f64 {
        self.inner.morph.weakness(token, class, cell)
    }

    /// Funkce (čísla v katalogu) a míry zániku kategorie, které jsou místy změny skupiny.
    fn syntax_sites<'py>(
        &self,
        py: Python<'py>,
        token: i64,
        kind: usize,
    ) -> (Bound<'py, PyArray1<u32>>, Bound<'py, PyArray1<f64>>) {
        let (found, rates) = self.inner.syntax_sites(token, kind);
        (PyArray1::from_vec(py, found), PyArray1::from_vec(py, rates))
    }
}

impl SiteIndex {
    /// Morfologický stav kódů (koncovky, jejich podoby a výchozí tvary), který čte hodnocení tvarů.
    pub(crate) fn morph(&self) -> &crate::morphology_index::MorphIndex {
        &self.inner.morph
    }
}
