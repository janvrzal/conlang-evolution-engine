//! Jedno dávkové volání hledání míst inovací za tik (krok B6d).
//!
//! Index prostředí zvukových změn (`SoundIndex`) a index míst ostatních změn (`SiteIndex`) se
//! dřív volaly zvlášť, každý s vlastním dorovnáním a případným doplněním dat z Pythonu. Tady se
//! v jednom volání dorovná zvukový index, morfologie a sémantika indexu míst a spočítá se matice
//! součtů míst pro všechny skupiny a druhy změn (sloupce indexu míst) i součty rodin zvukových
//! změn; oba indexy si data předávají v Rustu. Co Rust nemá (výchozí tvary morfémů, vlastnosti
//! kořenů), vrátí jako `needs`; Python to doplní a zavolá znovu (dorovnání je opakovatelné).

use numpy::{PyArray1, PyReadonlyArray1};
use pyo3::prelude::*;

use crate::index_python::{sound_sync, SoundIndex};
use crate::python::{slice, Held, NativeBank};
use crate::sites_python::{
    run_totals, sync_morphology, sync_semantic, BorrowingIn, SiteIndex, TotalsInput, Triple,
};

/// Zvukový index: tokeny kódů s hláskami, pravidla přízvuku, příznaky slovní zásoby a tvary kódů.
type SoundIn<'py> = (
    Vec<i64>,
    Vec<u8>,
    Vec<Bound<'py, PyAny>>,
    Vec<Bound<'py, PyAny>>,
);

/// Morfologie indexu míst: tokeny změněných kódů, příznaky, úložiště tvarů a sloupce světa.
type MorphIn<'py> = (
    Vec<i64>,
    Vec<Bound<'py, PyAny>>,
    Vec<Triple<'py>>,
    Vec<Bound<'py, PyAny>>,
);

/// Sémantika indexu míst: tokeny změněných kódů, dominantní kořeny, místa, tabu a přípona.
type SemanticIn<'py> = (
    Vec<i64>,
    Vec<Bound<'py, PyAny>>,
    Vec<Bound<'py, PyAny>>,
    Vec<Bound<'py, PyAny>>,
    Vec<bool>,
);

/// Vstup součtů míst: tokeny, dominantní konstrukce, podíl druhého jazyka, počty lexikálních
/// proměnných, příznaky morfologie a sémantiky, základní míry, násobky, výpůjčky, tvary kódů, prozodie.
type TotalsIn<'py> = (
    Vec<i64>,
    PyReadonlyArray1<'py, i32>,
    PyReadonlyArray1<'py, f64>,
    PyReadonlyArray1<'py, i64>,
    Vec<bool>,
    Vec<bool>,
    PyReadonlyArray1<'py, f64>,
    (f64, f64, f64),
    Option<BorrowingIn<'py>>,
    Vec<Bound<'py, PyAny>>,
    (bool, bool),
);

/// Co Rust vyžaduje od Pythonu: výchozí tvary pro zvukový index (pozice kódu, čísla morfémů),
/// výchozí tvary pro index míst a vlastnosti kořenů.
type NeedsOut = (Vec<(usize, Vec<u32>)>, Vec<u32>, Vec<u32>);

/// Výsledek: součty a počty míst (skupina × sloupec), součty rodin zvukových změn (kód s hláskami ×
/// rodina) a zda kód má rodiny (jinak počítá výchozí postup Pythonu).
type ResultsOut<'py> = (
    Bound<'py, PyArray1<f64>>,
    Bound<'py, PyArray1<i64>>,
    Bound<'py, PyArray1<f64>>,
    Vec<bool>,
);

/// Dorovná oba indexy a spočítá míry všech druhů změn jedním voláním.
///
/// Vrací co chybí (`needs`) a, když nic nechybí, výsledky. Zvukový index smí dostat prázdný
/// seznam kódů (svět bez hláskových tvarů), morfologie a sémantika se dorovnávají jen pro kódy,
/// které volající označil jako změněné.
#[pyfunction]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn innovation_totals<'py>(
    py: Python<'py>,
    bank: PyRef<'_, NativeBank>,
    mut sound: PyRefMut<'py, SoundIndex>,
    mut sites: PyRefMut<'py, SiteIndex>,
    sound_in: SoundIn<'py>,
    morph_in: Option<MorphIn<'py>>,
    semantic_in: Option<SemanticIn<'py>>,
    totals_in: TotalsIn<'py>,
) -> PyResult<(NeedsOut, Option<ResultsOut<'py>>)> {
    let mut sound_needs = Vec::new();
    if !sound_in.0.is_empty() {
        let needs = sound_sync(
            &mut sound.inner,
            &bank.bank,
            &sound_in.0,
            &sound_in.1,
            &sound_in.2,
            &sound_in.3,
        )?;
        sound_needs = needs.defaults;
    }
    let mut defaults = Vec::new();
    if let Some((tokens, flags, store, columns)) = &morph_in {
        defaults = sync_morphology(&mut sites.inner, &bank.bank, tokens, flags, store, columns)?;
    }
    let mut roots = Vec::new();
    if let Some((tokens, dominant, taboo_sites, taboo, suffix)) = &semantic_in {
        roots = sync_semantic(
            &mut sites.inner,
            tokens,
            dominant,
            taboo_sites,
            taboo,
            suffix,
        )?;
    }
    if !sound_needs.is_empty() || !defaults.is_empty() || !roots.is_empty() {
        return Ok(((sound_needs, defaults, roots), None));
    }
    let (
        tokens,
        variants,
        l2_share,
        lexical,
        morph_on,
        semantic_on,
        bases,
        scales,
        borrowing,
        forms,
        prosody,
    ) = totals_in;
    let held = Held::<i32>::all(&forms)?;
    let views: Vec<&[i32]> = held.iter().map(Held::view).collect();
    let ((totals, counts), more) = run_totals(
        &mut sites.inner,
        &bank.bank,
        &TotalsInput {
            tokens: &tokens,
            variants: slice(&variants)?,
            l2_share: slice(&l2_share)?,
            lexical: slice(&lexical)?,
            morph_on: &morph_on,
            semantic_on: &semantic_on,
            bases: slice(&bases)?,
            scales,
            borrowing: &borrowing,
            forms: &views,
            prosody: [prosody.0, prosody.1],
        },
    )?;
    if !more.is_empty() {
        return Ok(((Vec::new(), more, Vec::new()), None));
    }
    let families = sound.inner.family_count();
    let sound_totals = sound.inner.totals(&sound_in.0);
    let has: Vec<bool> = sound_in
        .0
        .iter()
        .map(|&token| sound.inner.has_families(token))
        .collect();
    debug_assert_eq!(sound_totals.len(), sound_in.0.len() * families);
    Ok((
        (Vec::new(), Vec::new(), Vec::new()),
        Some((
            PyArray1::from_vec(py, totals),
            PyArray1::from_vec(py, counts),
            PyArray1::from_vec(py, sound_totals),
            has,
        )),
    ))
}
