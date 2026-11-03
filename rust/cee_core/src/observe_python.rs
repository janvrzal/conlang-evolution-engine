//! Vazba pozorování (`observe`) na Python (PyO3): tenká vrstva, jen převody polí.
//!
//! Hlavní vstup je jedno volání `observe_step` za pozorování: pohledy na bloky živých fondů
//! (podíly a příznaky „kdo proměnnou má“ bez kopie), dominantní kořeny skupin jako pole čísel,
//! polohy a vazby skupin. Vrací shluky dialektů a jazyků a na přání matici vzdáleností kódů.
//! Ostatní funkce (`observe_linkage`, `observe_candidates`, `observe_edit_distances`, zkoušky
//! `observe_dot_probe` a `observe_hypot_probe`) jsou stavební kameny téhož kódu pro testy shody.

use numpy::{
    PyArray1, PyArray2, PyArrayMethods, PyReadonlyArray1, PyReadonlyArray2, PyReadonlyArray3,
    PyUntypedArrayMethods,
};
use pyo3::prelude::*;
use pyo3::types::PyTuple;

use crate::observe::{
    self, candidates, categories, cognate_totals, distance_totals, dot, embedded_features,
    form_distance, linkage, Costs, Dominant, Features, FormTable, Hysteresis, PoolView, Sparse,
    DISTANCE_CHUNK, FORM_WEIGHT,
};
use crate::python::{failure, slice};

/// Blok fondů: podíly `(řádky, skupiny, sloty)`, kdo proměnnou má, vybrané řádky, pořadí při výběru vzorku.
type PoolIn<'py> = (
    PyReadonlyArray3<'py, f64>,
    PyReadonlyArray2<'py, bool>,
    PyReadonlyArray1<'py, i64>,
    PyReadonlyArray1<'py, i64>,
);

/// Tvary skupin: ukazatele, pojmy, kořeny a tvary dominantních kořenů, tabulka tvarů (ukazatele a hlásky),
/// pořadí pojmů podle názvu, vektory rysů hlásek a dělitel ceny záměny.
type FormsIn<'py> = (
    PyReadonlyArray1<'py, i64>,
    PyReadonlyArray1<'py, i32>,
    PyReadonlyArray1<'py, i32>,
    PyReadonlyArray1<'py, i32>,
    PyReadonlyArray1<'py, i64>,
    PyReadonlyArray1<'py, i32>,
    PyReadonlyArray1<'py, i32>,
    PyReadonlyArray2<'py, i8>,
    f64,
);

/// Slovník v CSR: ukazatele, sloupce, hodnoty.
type CsrIn<'py> = (
    PyReadonlyArray1<'py, i64>,
    PyReadonlyArray1<'py, i64>,
    PyReadonlyArray1<'py, f64>,
);

type CsrOut<'py> = (
    Bound<'py, PyArray1<i64>>,
    Bound<'py, PyArray1<i64>>,
    Bound<'py, PyArray1<f64>>,
);

fn views<'a>(pools: &'a [PoolIn<'_>]) -> PyResult<Vec<PoolView<'a>>> {
    let mut found = Vec::with_capacity(pools.len());
    for (freqs, present, rows, ranks) in pools {
        let shape = freqs.shape();
        if present.shape() != [shape[0], shape[1]] {
            return Err(failure("podíly a příznaky bloku mají různý tvar".into()));
        }
        let rows = slice(rows)?;
        let ranks = slice(ranks)?;
        if rows.len() != ranks.len() || rows.iter().any(|&row| row < 0 || row as usize >= shape[0])
        {
            return Err(failure("vybrané řádky bloku neodpovídají tvaru".into()));
        }
        found.push(PoolView {
            freqs: slice(freqs)?,
            present: slice(present)?,
            groups: shape[1],
            capacity: shape[2],
            rows,
            ranks,
        });
    }
    Ok(found)
}

/// Ověřené vstupy tvarů: pole nesmí odkazovat mimo sebe a hlásky tvarů musí mít vektor rysů.
struct FormsRef<'a> {
    dominant: Dominant<'a>,
    table: FormTable<'a>,
    ranks: &'a [i32],
    vectors: &'a [i8],
    width: usize,
    scale: f64,
}

fn forms_ref<'a>(forms: &'a FormsIn<'_>, live: usize) -> PyResult<FormsRef<'a>> {
    let (ptr, concept, root, form, form_ptr, flat, ranks, vectors, scale) = forms;
    let dominant = Dominant {
        ptr: slice(ptr)?,
        concept: slice(concept)?,
        root: slice(root)?,
        form: slice(form)?,
    };
    let table = FormTable {
        ptr: slice(form_ptr)?,
        flat: slice(flat)?,
    };
    let ranks = slice(ranks)?;
    let width = vectors.shape()[1];
    let vectors = slice(vectors)?;
    let entries = dominant.concept.len();
    let segments = vectors.len().checked_div(width).unwrap_or(0);
    let counted = dominant.ptr.len() == live + 1
        && dominant.ptr.windows(2).all(|pair| pair[0] <= pair[1])
        && dominant.ptr.first() == Some(&0)
        && dominant.ptr.last().copied() == Some(entries as i64);
    let tables = dominant.root.len() == entries
        && dominant.form.len() == entries
        && table.ptr.first() == Some(&0)
        && table.ptr.last().copied() == Some(table.flat.len() as i64)
        && table.ptr.windows(2).all(|pair| pair[0] <= pair[1]);
    if !counted
        || !tables
        || dominant
            .form
            .iter()
            .any(|&f| f < 0 || f as usize >= table.count())
        || dominant
            .concept
            .iter()
            .any(|&c| c < 0 || c as usize >= ranks.len())
        || table.flat.iter().any(|&s| s < 0 || s as usize >= segments)
    {
        return Err(failure("tvary skupin neodpovídají svým tabulkám".into()));
    }
    Ok(FormsRef {
        dominant,
        table,
        ranks,
        vectors,
        width,
        scale: *scale,
    })
}

fn pairs_of(array: &PyReadonlyArray2<'_, i64>) -> PyResult<Vec<(u32, u32)>> {
    if array.shape()[1] != 2 {
        return Err(failure("dvojice musí mít dva sloupce".into()));
    }
    Ok(slice(array)?
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| (pair[0] as u32, pair[1] as u32))
        .collect())
}

fn pairs_out<'py>(py: Python<'py>, pairs: &[(u32, u32)]) -> PyResult<Bound<'py, PyArray2<i64>>> {
    let flat: Vec<i64> = pairs
        .iter()
        .flat_map(|&(a, b)| [i64::from(a), i64::from(b)])
        .collect();
    PyArray1::from_vec(py, flat).reshape([pairs.len(), 2])
}

fn csr_out<'py>(py: Python<'py>, items: &[Sparse]) -> CsrOut<'py> {
    let mut ptr = Vec::with_capacity(items.len() + 1);
    let (mut cols, mut vals) = (Vec::new(), Vec::new());
    ptr.push(0_i64);
    for item in items {
        cols.extend(item.cols().iter().map(|&col| i64::from(col)));
        vals.extend_from_slice(item.vals());
        ptr.push(cols.len() as i64);
    }
    (
        PyArray1::from_vec(py, ptr),
        PyArray1::from_vec(py, cols),
        PyArray1::from_vec(py, vals),
    )
}

fn csr_in(item: &CsrIn<'_>, groups: usize) -> PyResult<Vec<Sparse>> {
    let (ptr, cols, vals) = (slice(&item.0)?, slice(&item.1)?, slice(&item.2)?);
    if ptr.len() != groups + 1
        || cols.len() != vals.len()
        || ptr.last() != Some(&(cols.len() as i64))
    {
        return Err(failure("slovníky skupin mají špatný tvar".into()));
    }
    Ok(ptr
        .windows(2)
        .map(|pair| {
            let range = pair[0] as usize..pair[1] as usize;
            Sparse::from_entries(
                cols[range.clone()].iter().map(|&col| col as u32).collect(),
                vals[range].to_vec(),
            )
        })
        .collect())
}

fn spoken_of(spoken: &PyReadonlyArray1<'_, i64>, live: usize) -> PyResult<Vec<usize>> {
    slice(spoken)?
        .iter()
        .map(|&group| {
            usize::try_from(group)
                .ok()
                .filter(|&group| group < live)
                .ok_or_else(|| failure("skupina mimo živé skupiny".into()))
        })
        .collect()
}

/// Matice vzdáleností kódů mluvených skupin (`observe.code_distances` podmnožina): variační
/// vzdálenost slov a konstrukcí dělená počtem lexikálních proměnných, plus rozdíly tvarů příbuzných slov.
#[allow(clippy::too_many_arguments)]
fn code_distances(
    views: &[PoolView<'_>],
    live: usize,
    spoken: &[usize],
    forms: Option<&FormsRef<'_>>,
    lexical: usize,
    threads: usize,
) -> Vec<f64> {
    let count = lexical.max(1) as f64;
    let mut total = distance_totals(views, live, DISTANCE_CHUNK, threads);
    for value in &mut total {
        *value /= count;
    }
    if let Some(forms) = forms {
        let mut costs = Costs::new(forms.vectors, forms.width, forms.scale);
        let cognate = cognate_totals(&forms.dominant, live, forms.ranks, &forms.table, &mut costs);
        for (value, add) in total.iter_mut().zip(&cognate) {
            *value += FORM_WEIGHT * add / count;
        }
    }
    let mut out = Vec::with_capacity(spoken.len() * spoken.len());
    for &first in spoken {
        for &second in spoken {
            out.push(total[first * live + second]);
        }
    }
    out
}

/// Pozorování jedním voláním: dialekty a jazyky mluvených skupin (a na přání matice vzdáleností).
///
/// `pools`: bloky fondů (podíly, kdo proměnnou má, vybrané řádky, pořadí při výběru vzorku),
/// `live`: počet živých skupin, `spoken`: jejich čísla pro mluvené skupiny, `forms`: dominantní
/// kořeny a tvary (nebo `None`, má-li svět bez tabulky hlásek), `lexical`: počet lexikálních
/// proměnných, `links`: dvojice pozic mluvených skupin spojených vazbou, `places`: pozice skupin
/// s polohou a jejich souřadnice, `labels`: číslo dosavadní linie skupin (−1 žádná), `limits`:
/// práh dialektů, práh jazyků a rezerva hystereze. S `detail` vrátí i rysy a kandidáty (pro testy).
/// Vrací `(dialekty, jazyky, vzdálenosti, detail)`.
#[pyfunction]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn observe_step<'py>(
    py: Python<'py>,
    pools: Vec<PoolIn<'py>>,
    live: usize,
    spoken: PyReadonlyArray1<'py, i64>,
    forms: Option<FormsIn<'py>>,
    lexical: usize,
    links: (PyReadonlyArray1<'py, i64>, PyReadonlyArray1<'py, i64>),
    places: (
        PyReadonlyArray1<'py, i64>,
        PyReadonlyArray1<'py, f64>,
        PyReadonlyArray1<'py, f64>,
    ),
    labels: PyReadonlyArray1<'py, i64>,
    limits: (f64, f64, f64),
    distances: bool,
    threads: usize,
    detail: bool,
) -> PyResult<Bound<'py, PyTuple>> {
    let views = views(&pools)?;
    if views.iter().any(|view| view.groups != live) {
        return Err(failure("blok fondů má jiný počet skupin než svět".into()));
    }
    let cols = spoken_of(&spoken, live)?;
    let labels = slice(&labels)?;
    if labels.len() != cols.len() {
        return Err(failure("linie skupin nesedí na mluvené skupiny".into()));
    }
    let forms = forms
        .as_ref()
        .map(|item| forms_ref(item, live))
        .transpose()?;
    let mut features = embedded_features(&views, &cols, lexical, threads);
    if let Some(forms) = &forms {
        let mut costs = Costs::new(forms.vectors, forms.width, forms.scale);
        let found = categories(&forms.dominant, &cols, &forms.table, &mut costs);
        features.forms = found.forms;
        features.spread = found.spread;
    }
    let (source, target) = (slice(&links.0)?, slice(&links.1)?);
    let (slots, xs, ys) = (slice(&places.0)?, slice(&places.1)?, slice(&places.2)?);
    if source.len() != target.len()
        || slots.len() != xs.len()
        || xs.len() != ys.len()
        || source
            .iter()
            .chain(target)
            .chain(slots)
            .any(|&at| at < 0 || at as usize >= cols.len())
    {
        return Err(failure(
            "vazby či polohy odkazují mimo mluvené skupiny".into(),
        ));
    }
    let linked: Vec<(u32, u32)> = source
        .iter()
        .zip(target)
        .map(|(&a, &b)| (a as u32, b as u32))
        .collect();
    let slots: Vec<u32> = slots.iter().map(|&at| at as u32).collect();
    let pairs = candidates(&linked, &slots, xs, ys);
    let dialects = linkage(&features, &pairs, limits.0, None);
    let hysteresis = Hysteresis {
        labels,
        margin: limits.2,
    };
    let languages = linkage(&features, &pairs, limits.1, Some(&hysteresis));
    let matrix = if distances {
        let flat = code_distances(&views, live, &cols, forms.as_ref(), lexical, threads);
        Some(PyArray1::from_vec(py, flat).reshape([cols.len(), cols.len()])?)
    } else {
        None
    };
    let extra = if detail {
        let shares = PyArray1::from_vec(py, features.shares.clone())
            .reshape([features.groups, features.dim])?;
        let squares = PyArray1::from_vec(py, features.squares.clone());
        let pairs = pairs_out(py, &pairs)?;
        Some((
            shares,
            squares,
            csr_out(py, &features.forms),
            csr_out(py, &features.spread),
            pairs,
        ))
    } else {
        None
    };
    PyTuple::new(
        py,
        [
            dialects.into_pyobject(py)?.into_any(),
            languages.into_pyobject(py)?.into_any(),
            matrix.into_pyobject(py)?.into_any(),
            extra.into_pyobject(py)?.into_any(),
        ],
    )
}

/// Matice součtů vzdáleností kódů bez dělení (`observe.distance_matrix` před dělením), pro testy
/// shody s `numpy` na libovolném `chunk`.
#[pyfunction]
pub fn observe_distance_totals<'py>(
    py: Python<'py>,
    pools: Vec<PoolIn<'py>>,
    live: usize,
    chunk: usize,
    threads: usize,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let views = views(&pools)?;
    if views.iter().any(|view| view.groups != live) {
        return Err(failure("blok fondů má jiný počet skupin než svět".into()));
    }
    let flat = distance_totals(&views, live, chunk, threads);
    PyArray1::from_vec(py, flat).reshape([live, live])
}

/// Součty rozdílů tvarů příbuzných slov (`observe.cognate_matrix`) pro živé skupiny.
#[pyfunction]
pub fn observe_cognate_totals<'py>(
    py: Python<'py>,
    live: usize,
    forms: FormsIn<'py>,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let forms = forms_ref(&forms, live)?;
    let mut costs = Costs::new(forms.vectors, forms.width, forms.scale);
    let flat = cognate_totals(&forms.dominant, live, forms.ranks, &forms.table, &mut costs);
    PyArray1::from_vec(py, flat).reshape([live, live])
}

/// Průměrná vazba nad zadanými rysy (`observe.constrained_average_linkage`): `shares` a `squares`,
/// slovníky tvarů a rozptylu v CSR, kandidáti, práh a případná hystereze (`labels`, `margin`).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn observe_linkage(
    shares: PyReadonlyArray2<'_, f32>,
    squares: PyReadonlyArray1<'_, f64>,
    forms: CsrIn<'_>,
    spread: CsrIn<'_>,
    lexical: f64,
    pairs: PyReadonlyArray2<'_, i64>,
    threshold: f64,
    labels: Option<PyReadonlyArray1<'_, i64>>,
    margin: f64,
) -> PyResult<Vec<Vec<usize>>> {
    let groups = squares.shape()[0];
    if shares.shape()[0] != groups {
        return Err(failure("rysy mají jiný počet skupin".into()));
    }
    let pairs = pairs_of(&pairs)?;
    if pairs
        .iter()
        .any(|&(a, b)| a as usize >= groups || b as usize >= groups)
    {
        return Err(failure("kandidát mimo skupiny".into()));
    }
    let features = Features {
        groups,
        dim: shares.shape()[1],
        shares: slice(&shares)?.to_vec(),
        squares: slice(&squares)?.to_vec(),
        forms: csr_in(&forms, groups)?,
        spread: csr_in(&spread, groups)?,
        lexical,
    };
    let labels = labels.as_ref().map(|item| slice(item)).transpose()?;
    if labels.is_some_and(|labels| labels.len() != groups) {
        return Err(failure("linie nesedí na skupiny".into()));
    }
    let hysteresis = labels.map(|labels| Hysteresis { labels, margin });
    Ok(linkage(&features, &pairs, threshold, hysteresis.as_ref()))
}

/// Kandidáti sloučení z vazeb a poloh (`observe._candidates`).
#[pyfunction]
pub fn observe_candidates<'py>(
    py: Python<'py>,
    links: PyReadonlyArray2<'py, i64>,
    slots: PyReadonlyArray1<'py, i64>,
    xs: PyReadonlyArray1<'py, f64>,
    ys: PyReadonlyArray1<'py, f64>,
) -> PyResult<Bound<'py, PyArray2<i64>>> {
    let slots: Vec<u32> = slice(&slots)?.iter().map(|&at| at as u32).collect();
    if slots.len() != xs.shape()[0] || slots.len() != ys.shape()[0] {
        return Err(failure("polohy mají různou délku".into()));
    }
    let found = candidates(&pairs_of(&links)?, &slots, slice(&xs)?, slice(&ys)?);
    pairs_out(py, &found)
}

/// Editační vzdálenosti dvojic tvarů (`observe.form_distance`): `ptr` a `flat` jsou tvary, `pairs`
/// dvojice čísel tvarů, `vectors` rysy hlásek a `scale` dělitel ceny záměny.
#[pyfunction]
pub fn observe_edit_distances<'py>(
    py: Python<'py>,
    vectors: PyReadonlyArray2<'py, i8>,
    scale: f64,
    ptr: PyReadonlyArray1<'py, i64>,
    flat: PyReadonlyArray1<'py, i32>,
    pairs: PyReadonlyArray2<'py, i64>,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
    let table = FormTable {
        ptr: slice(&ptr)?,
        flat: slice(&flat)?,
    };
    let width = vectors.shape()[1];
    let vectors = slice(&vectors)?;
    let segments = vectors.len().checked_div(width).unwrap_or(0);
    if table.ptr.first() != Some(&0)
        || table.ptr.last().copied() != Some(table.flat.len() as i64)
        || table.ptr.windows(2).any(|pair| pair[0] > pair[1])
        || table.flat.iter().any(|&s| s < 0 || s as usize >= segments)
    {
        return Err(failure("tvary neodpovídají své tabulce".into()));
    }
    let pairs = pairs_of(&pairs)?;
    if pairs
        .iter()
        .any(|&(a, b)| a as usize >= table.count() || b as usize >= table.count())
    {
        return Err(failure("dvojice odkazuje mimo tvary".into()));
    }
    let mut costs = Costs::new(vectors, width, scale);
    let mut row = Vec::new();
    let found: Vec<f64> = pairs
        .iter()
        .map(|&(a, b)| {
            form_distance(
                &mut costs,
                table.get(a as usize),
                table.get(b as usize),
                &mut row,
            )
        })
        .collect();
    Ok(PyArray1::from_vec(py, found))
}

/// Skalární součin řádků `f32` jako `a @ b` v `numpy`: dvojice řádků matice. Zkouška, zda
/// `numpy` na tomto stroji sčítá tak jako Rust (`cee.v2.native.observe_matches`).
#[pyfunction]
pub fn observe_dot_probe<'py>(
    py: Python<'py>,
    matrix: PyReadonlyArray2<'py, f32>,
    first: PyReadonlyArray1<'py, i64>,
    second: PyReadonlyArray1<'py, i64>,
) -> PyResult<Bound<'py, PyArray1<f32>>> {
    let width = matrix.shape()[1];
    let (rows, flat) = (matrix.shape()[0], slice(&matrix)?);
    let (first, second) = (slice(&first)?, slice(&second)?);
    if first.len() != second.len()
        || first
            .iter()
            .chain(second)
            .any(|&at| at < 0 || at as usize >= rows)
    {
        return Err(failure("řádky mimo matici".into()));
    }
    let row = |at: i64| &flat[at as usize * width..(at as usize + 1) * width];
    let found: Vec<f32> = first
        .iter()
        .zip(second)
        .map(|(&a, &b)| dot(row(a), row(b)))
        .collect();
    Ok(PyArray1::from_vec(py, found))
}

/// `hypot` knihovny systému po prvcích (zkouška shody s `numpy.hypot`).
#[pyfunction]
pub fn observe_hypot_probe<'py>(
    py: Python<'py>,
    first: PyReadonlyArray1<'py, f64>,
    second: PyReadonlyArray1<'py, f64>,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
    let (first, second) = (slice(&first)?, slice(&second)?);
    if first.len() != second.len() {
        return Err(failure("různé délky".into()));
    }
    let found: Vec<f64> = first.iter().zip(second).map(|(a, b)| a.hypot(*b)).collect();
    Ok(PyArray1::from_vec(py, found))
}

/// Tvar `a // b` jako v Pythonu po prvcích (zkouška shody s `numpy.floor_divide`).
#[pyfunction]
pub fn observe_floor_divide_probe<'py>(
    py: Python<'py>,
    first: PyReadonlyArray1<'py, f64>,
    second: f64,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
    let found: Vec<f64> = slice(&first)?
        .iter()
        .map(|&a| observe::floor_divide(a, second))
        .collect();
    Ok(PyArray1::from_vec(py, found))
}

/// Má sestavba stejný skalární součin `f32` jako `numpy` na macOS (Accelerate)?
#[pyfunction]
pub fn observe_native_dot() -> bool {
    observe::NATIVE_DOT
}
