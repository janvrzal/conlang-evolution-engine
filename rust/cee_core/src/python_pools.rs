//! Vazba na Python (PyO3) pro živé fondy a přenos: `NativeCells` (stav bloku fondů),
//! `NativeStep` (vstupy kroku sdílené bloky) a bezstavové funkce `hear`, `settle`,
//! `normalized` pro zlatá data a zkoušky.
//!
//! Stav bloku žije v Rustu (`pools::Cells`) po celý běh; Python drží jen rukojeť
//! a posílá změny. Hustý pohled a výsledky přenosu leží v polích `Slab`, na která
//! se Python dívá jako na pole `numpy` **bez kopie**. Pole se přepíše jen tehdy, když
//! na něj nikdo jiný neodkazuje (počet odkazů 1); jinak Rust založí nové, takže
//! pohled nikdy nezačne ukazovat na změněná data ani na uvolněnou paměť.
//! Přenos bloku je jediné volání (`NativeCells.transmit`), v něm Rust zavolá
//! Python jen pro tlaky (`fitness`), dokud nepřejdou do Rustu.

use numpy::ndarray::ArrayView3;
use numpy::{
    PyArray1, PyArray2, PyArray3, PyArrayMethods, PyReadonlyArray1, PyReadonlyArray2,
    PyReadonlyArray3, PyUntypedArrayMethods,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::pools::{Cells, Row};
use crate::transmission::{
    self, Channel, Cohorts, Component, Flow, HearScratch, Links, Network, Shape, State,
};

fn failure(message: impl Into<String>) -> PyErr {
    PyValueError::new_err(message.into())
}

fn slice<'a, T: numpy::Element>(array: &'a PyReadonlyArray1<'_, T>) -> PyResult<&'a [T]> {
    array
        .as_slice()
        .map_err(|_| failure("pole musí být souvislé"))
}

fn slice2<'a, T: numpy::Element>(array: &'a PyReadonlyArray2<'_, T>) -> PyResult<&'a [T]> {
    array
        .as_slice()
        .map_err(|_| failure("pole musí být souvislé"))
}

fn slice3<'a, T: numpy::Element>(array: &'a PyReadonlyArray3<'_, T>) -> PyResult<&'a [T]> {
    array
        .as_slice()
        .map_err(|_| failure("pole musí být souvislé"))
}

fn indices(values: &[i64]) -> PyResult<Vec<usize>> {
    values
        .iter()
        .map(|&value| usize::try_from(value).map_err(|_| failure("záporné číslo skupiny")))
        .collect()
}

// --- pole sdílená s numpy bez kopie ---------------------------------------------------

/// Pole čísel, jehož paměť patří Rustu a Python se na ni dívá jako na pole `numpy`.
#[pyclass(module = "cee_core")]
pub struct Slab {
    data: Vec<f64>,
}

/// Pole z `slot`, které nikdo jiný nedrží (počet odkazů 1), nebo nové; velikost `len`.
/// Obsah starého pole zůstává (kdo ho potřebuje vynulované, žádá `zero`).
fn acquire<'py>(
    py: Python<'py>,
    slot: &mut Option<Py<Slab>>,
    len: usize,
    zero: bool,
) -> PyResult<Bound<'py, Slab>> {
    if let Some(existing) = slot {
        // SAFETY: ukazatel patří živému objektu, který drží `existing`.
        if unsafe { pyo3::ffi::Py_REFCNT(existing.as_ptr()) } == 1 {
            let bound = existing.bind(py).clone();
            {
                let mut guard = bound.borrow_mut();
                if zero {
                    guard.data.clear();
                }
                guard.data.resize(len, 0.0);
            }
            return Ok(bound);
        }
    }
    let bound = Bound::new(
        py,
        Slab {
            data: vec![0.0; len],
        },
    )?;
    *slot = Some(bound.clone().unbind());
    Ok(bound)
}

/// Pohled `numpy` jen pro čtení na úsek pole `slab` s tvarem `shape` od prvku `offset`.
fn view<'py>(
    py: Python<'py>,
    slab: &Bound<'py, Slab>,
    offset: usize,
    shape: [usize; 3],
) -> PyResult<Bound<'py, PyArray3<f64>>> {
    let len = shape[0] * shape[1] * shape[2];
    let guard = slab.borrow();
    let part = guard
        .data
        .get(offset..offset + len)
        .ok_or_else(|| failure("pohled mimo pole"))?;
    let array = ArrayView3::from_shape(shape, part).map_err(|error| failure(error.to_string()))?;
    // SAFETY: paměť drží `slab`, který pohled drží jako základ, a Rust ji přepisuje,
    // jen když na pole nikdo jiný neodkazuje (viz `acquire`).
    let out = unsafe { PyArray3::borrow_from_array(&array, slab.clone().into_any()) };
    drop(guard);
    let flags = PyDict::new(py);
    flags.set_item("write", false)?;
    out.call_method("setflags", (), Some(&flags))?;
    Ok(out)
}

// --- vstupy kroku ---------------------------------------------------------------------

fn components_from(
    members: &[Vec<usize>],
    blocks: &[PyReadonlyArray2<'_, f64>],
) -> PyResult<Vec<Component>> {
    if members.len() != blocks.len() {
        return Err(failure("komponenty a bloky mají různý počet"));
    }
    members
        .iter()
        .zip(blocks)
        .map(|(group, block)| {
            let size = group.len();
            if block.shape() != [size, size] {
                return Err(failure("blok matice nemá tvar komponenty"));
            }
            Ok(Component {
                members: group.clone(),
                links: Links::from_dense(slice2(block)?, size),
            })
        })
        .collect()
}

/// Vstupy kroku sdílené všemi bloky: sít skupin po komponentách, vazby mezi jazyky
/// po kanálech, kanály mimo síť a čísla skupin (kohorty a klíče driftu).
#[pyclass(module = "cee_core")]
pub struct NativeStep {
    groups: usize,
    components: Vec<Component>,
    alone: Vec<usize>,
    alone_weight: Vec<f64>,
    flows: Vec<Vec<Component>>,
    channels: Vec<(Vec<usize>, Vec<usize>, Vec<f64>)>,
    renewal: Vec<f64>,
    drift_scale: Vec<f64>,
    loss_floor: Vec<f64>,
    row_keys: Vec<u64>,
}

type RawChannel<'py> = (
    PyReadonlyArray1<'py, i64>,
    PyReadonlyArray1<'py, i64>,
    PyReadonlyArray1<'py, f64>,
);

#[pymethods]
impl NativeStep {
    /// `members` a `blocks` jsou komponenty sítě (čísla skupin a matice vazeb), `cross`
    /// bloky vazeb mezi jazyky po kanálech (ve stejném pořadí komponent), `channels`
    /// trojice (učící se skupiny, zdroje, váhy).
    #[new]
    #[allow(clippy::too_many_arguments)]
    fn new(
        members: Vec<PyReadonlyArray1<'_, i64>>,
        blocks: Vec<PyReadonlyArray2<'_, f64>>,
        alone: PyReadonlyArray1<'_, i64>,
        alone_weight: PyReadonlyArray1<'_, f64>,
        cross: Vec<Vec<PyReadonlyArray2<'_, f64>>>,
        channels: Vec<RawChannel<'_>>,
        renewal: PyReadonlyArray1<'_, f64>,
        drift_scale: PyReadonlyArray1<'_, f64>,
        loss_floor: PyReadonlyArray1<'_, f64>,
        row_keys: PyReadonlyArray1<'_, u64>,
    ) -> PyResult<Self> {
        let groups = slice(&renewal)?.len();
        let members = members
            .iter()
            .map(|group| indices(slice(group)?))
            .collect::<PyResult<Vec<_>>>()?;
        let flows = cross
            .iter()
            .map(|flow| components_from(&members, flow))
            .collect::<PyResult<Vec<_>>>()?;
        let channels = channels
            .iter()
            .map(|(learners, sources, weights)| {
                Ok((
                    indices(slice(learners)?)?,
                    indices(slice(sources)?)?,
                    slice(weights)?.to_vec(),
                ))
            })
            .collect::<PyResult<Vec<_>>>()?;
        let step = NativeStep {
            groups,
            components: components_from(&members, &blocks)?,
            alone: indices(slice(&alone)?)?,
            alone_weight: slice(&alone_weight)?.to_vec(),
            flows,
            channels,
            renewal: slice(&renewal)?.to_vec(),
            drift_scale: slice(&drift_scale)?.to_vec(),
            loss_floor: slice(&loss_floor)?.to_vec(),
            row_keys: slice(&row_keys)?.to_vec(),
        };
        let sizes = [
            step.drift_scale.len(),
            step.loss_floor.len(),
            step.row_keys.len(),
        ];
        if sizes.iter().any(|&size| size != groups) || step.alone.len() != step.alone_weight.len() {
            return Err(failure("pole skupin kroku mají různou délku"));
        }
        if step
            .channels
            .iter()
            .any(|(a, b, c)| a.len() != b.len() || a.len() != c.len())
        {
            return Err(failure("kanál má pole různé délky"));
        }
        Ok(step)
    }

    fn groups(&self) -> usize {
        self.groups
    }
}

impl NativeStep {
    fn network(&self) -> Network<'_> {
        Network {
            components: &self.components,
            alone: &self.alone,
            alone_weight: &self.alone_weight,
        }
    }
}

// --- stav bloku -----------------------------------------------------------------------

/// Stav jednoho bloku živých fondů (proměnné se stejnou kapacitou slotů).
#[pyclass(module = "cee_core")]
pub struct NativeCells {
    cells: Cells,
    threads: usize,
    /// Hustý pohled (podíly a základny); platí jen když `dense_valid`.
    dense: [Option<Py<Slab>>; 2],
    dense_valid: bool,
    /// Výsledek posledního přenosu (nové podíly a základny).
    out: [Option<Py<Slab>>; 2],
    heard: Option<Py<Slab>>,
    scratch: Vec<HearScratch>,
    /// Ukazatele polí předaných `stage`: shodují-li se s `out`, převezme je `commit` jako hustý pohled.
    staged_from_out: bool,
}

impl NativeCells {
    fn blank(cells: Cells) -> Self {
        NativeCells {
            cells,
            threads: 1,
            dense: [None, None],
            dense_valid: false,
            out: [None, None],
            heard: None,
            scratch: Vec::new(),
            staged_from_out: false,
        }
    }

    fn shape(&self) -> [usize; 3] {
        [
            self.cells.rows.len(),
            self.cells.groups,
            self.cells.capacity,
        ]
    }

    /// Sestaví hustý pohled z řídkého uložení, není-li platný.
    fn ensure_dense<'py>(
        &mut self,
        py: Python<'py>,
    ) -> PyResult<(Bound<'py, Slab>, Bound<'py, Slab>)> {
        if self.dense_valid {
            if let [Some(freqs), Some(previous)] = &self.dense {
                return Ok((freqs.bind(py).clone(), previous.bind(py).clone()));
            }
        }
        let len: usize = self.shape().iter().product();
        let freqs = acquire(py, &mut self.dense[0], len, true)?;
        let previous = acquire(py, &mut self.dense[1], len, true)?;
        {
            let (mut f, mut p) = (freqs.borrow_mut(), previous.borrow_mut());
            self.cells.dense(&mut f.data, &mut p.data);
        }
        self.dense_valid = true;
        Ok((freqs, previous))
    }

    fn invalidate(&mut self) {
        self.dense_valid = false;
    }
}

#[allow(clippy::type_complexity)]
fn pair_of<'py>(
    py: Python<'py>,
    freqs: &Bound<'py, Slab>,
    previous: &Bound<'py, Slab>,
    shape: [usize; 3],
) -> PyResult<(Bound<'py, PyArray3<f64>>, Bound<'py, PyArray3<f64>>)> {
    Ok((view(py, freqs, 0, shape)?, view(py, previous, 0, shape)?))
}

#[pymethods]
impl NativeCells {
    #[new]
    #[pyo3(signature = (groups, capacity, threads=1))]
    fn new(groups: usize, capacity: usize, threads: usize) -> Self {
        let mut block = NativeCells::blank(Cells::new(groups, capacity));
        block.threads = threads.max(1);
        block
    }

    /// Stav uložený `flat`: ukazatele řádků, sloty, skupiny, podíly a základny.
    #[staticmethod]
    #[pyo3(signature = (groups, capacity, pointer, slot, group, freq, prev, threads=1))]
    #[allow(clippy::too_many_arguments)]
    fn from_flat(
        groups: usize,
        capacity: usize,
        pointer: PyReadonlyArray1<'_, i64>,
        slot: PyReadonlyArray1<'_, i16>,
        group: PyReadonlyArray1<'_, i32>,
        freq: PyReadonlyArray1<'_, f64>,
        prev: PyReadonlyArray1<'_, f64>,
        threads: usize,
    ) -> PyResult<Self> {
        let pointer = slice(&pointer)?;
        let total = slice(&slot)?.len();
        let consistent = pointer.first() == Some(&0)
            && pointer.windows(2).all(|pair| pair[0] <= pair[1])
            && pointer.last().copied() == Some(total as i64)
            && [
                slice(&group)?.len(),
                slice(&freq)?.len(),
                slice(&prev)?.len(),
            ]
            .iter()
            .all(|&size| size == total);
        if !consistent {
            return Err(failure("uložený stav fondu je nesourodý"));
        }
        let mut block = NativeCells::blank(Cells::from_flat(
            groups,
            capacity,
            pointer,
            slice(&slot)?,
            slice(&group)?,
            slice(&freq)?,
            slice(&prev)?,
        ));
        block.threads = threads.max(1);
        Ok(block)
    }

    /// Uložený stav: ukazatele řádků, sloty, skupiny, podíly a základny.
    #[allow(clippy::type_complexity)]
    fn flat<'py>(
        &self,
        py: Python<'py>,
    ) -> (
        Bound<'py, PyArray1<i64>>,
        Bound<'py, PyArray1<i16>>,
        Bound<'py, PyArray1<i32>>,
        Bound<'py, PyArray1<f64>>,
        Bound<'py, PyArray1<f64>>,
    ) {
        let (pointer, slot, group, freq, prev) = self.cells.to_flat();
        (
            PyArray1::from_vec(py, pointer),
            PyArray1::from_vec(py, slot),
            PyArray1::from_vec(py, group),
            PyArray1::from_vec(py, freq),
            PyArray1::from_vec(py, prev),
        )
    }

    fn set_threads(&mut self, threads: usize) {
        self.threads = threads.max(1);
    }

    fn __len__(&self) -> usize {
        self.cells.rows.len()
    }

    /// Počet uložených buněk (výskytů variant).
    fn entries(&self) -> usize {
        self.cells.entries()
    }

    /// Paměť řídkého uložení v bajtech.
    fn nbytes(&self) -> usize {
        self.cells.nbytes()
    }

    /// Přidá řádek z hustých polí `skupiny × šířka` (šířka ≤ kapacita).
    fn append(
        &mut self,
        freqs: PyReadonlyArray2<'_, f64>,
        previous: PyReadonlyArray2<'_, f64>,
    ) -> PyResult<()> {
        let width = freqs.shape()[1];
        if freqs.shape()[0] != self.cells.groups
            || freqs.shape() != previous.shape()
            || width > self.cells.capacity
        {
            return Err(failure("řádek má špatný tvar"));
        }
        self.cells
            .append_dense(slice2(&freqs)?, slice2(&previous)?, width);
        self.invalidate();
        Ok(())
    }

    /// Hustý tvar jednoho řádku `skupiny × kapacita` (kopie).
    #[allow(clippy::type_complexity)]
    fn row_dense<'py>(
        &self,
        py: Python<'py>,
        row: usize,
    ) -> PyResult<(Bound<'py, PyArray2<f64>>, Bound<'py, PyArray2<f64>>)> {
        if row >= self.cells.rows.len() {
            return Err(failure("řádek mimo blok"));
        }
        let size = self.cells.groups * self.cells.capacity;
        let (mut freqs, mut previous) = (vec![0.0; size], vec![0.0; size]);
        self.cells.row_dense(row, &mut freqs, &mut previous);
        let shape = [self.cells.groups, self.cells.capacity];
        Ok((
            PyArray1::from_vec(py, freqs).reshape(shape)?,
            PyArray1::from_vec(py, previous).reshape(shape)?,
        ))
    }

    /// Odebere řádek; na jeho místo přijde poslední.
    fn swap_remove(&mut self, row: usize) -> PyResult<()> {
        if row >= self.cells.rows.len() {
            return Err(failure("řádek mimo blok"));
        }
        let _: Row = self.cells.swap_remove(row);
        self.invalidate();
        Ok(())
    }

    /// Hustý pohled `(podíly, základny)` jen pro čtení, bez kopie; platí do první změny bloku.
    #[allow(clippy::type_complexity)]
    fn dense<'py>(
        &mut self,
        py: Python<'py>,
    ) -> PyResult<(Bound<'py, PyArray3<f64>>, Bound<'py, PyArray3<f64>>)> {
        let shape = self.shape();
        let (freqs, previous) = self.ensure_dense(py)?;
        pair_of(py, &freqs, &previous, shape)
    }

    /// Zahodí hustý pohled i vyrovnávací pole (zůstane jen řídké uložení).
    fn drop_dense(&mut self) {
        self.dense = [None, None];
        self.out = [None, None];
        self.heard = None;
        self.dense_valid = false;
    }

    fn has_dense(&self) -> bool {
        self.dense_valid
    }

    /// Připraví nový stav celého bloku z hustých polí; zapíše ho až `commit`.
    fn stage(
        &mut self,
        py: Python<'_>,
        freqs: PyReadonlyArray3<'_, f64>,
        previous: PyReadonlyArray3<'_, f64>,
    ) -> PyResult<()> {
        if freqs.shape() != self.shape() || previous.shape() != freqs.shape() {
            return Err(failure(
                "Pole musí mít tvar (proměnné, skupiny, sloty) bloku.",
            ));
        }
        let (f, p) = (slice3(&freqs)?, slice3(&previous)?);
        self.staged_from_out = match &self.out {
            [Some(first), Some(second)] => {
                first.bind(py).borrow().data.as_ptr() == f.as_ptr()
                    && second.bind(py).borrow().data.as_ptr() == p.as_ptr()
            }
            _ => false,
        };
        self.cells.stage(f, p, self.threads);
        Ok(())
    }

    /// Zapíše stav připravený `stage`. S `keep_dense` si blok nechá předaná pole jako hustý
    /// pohled, pokud jsou to výsledky jeho přenosu; bez něj zahodí hustá pole.
    fn commit(&mut self, keep_dense: bool) -> PyResult<()> {
        self.cells.commit().map_err(failure)?;
        if keep_dense && self.staged_from_out {
            self.dense.swap_with_slice(&mut self.out);
            self.dense_valid = true;
        } else {
            self.dense_valid = false;
            if !keep_dense {
                self.dense = [None, None];
                self.out = [None, None];
                self.heard = None;
            }
        }
        self.staged_from_out = false;
        Ok(())
    }

    /// Nová varianta ve slotu u jedné skupiny (`PoolBlock.add_share`).
    fn add_share(&mut self, row: usize, column: usize, slot: usize, share: f64) -> PyResult<()> {
        let capacity = self.cells.capacity;
        if row >= self.cells.rows.len() || column >= self.cells.groups || slot >= capacity {
            return Err(failure("buňka mimo blok"));
        }
        self.cells.rows[row].add_share(column, slot, share, capacity);
        self.invalidate();
        Ok(())
    }

    /// Uvolní sloty bez výskytu v řádku.
    fn free_slots(&mut self, row: usize, slots: Vec<usize>) -> PyResult<()> {
        let capacity = self.cells.capacity;
        if row >= self.cells.rows.len() {
            return Err(failure("řádek mimo blok"));
        }
        self.cells.rows[row].free_slots(&slots, capacity);
        self.invalidate();
        Ok(())
    }

    /// Sloty s kladným podílem u jedné skupiny: (sloty vzestupně, podíly, základny).
    #[allow(clippy::type_complexity)]
    fn cell<'py>(
        &self,
        py: Python<'py>,
        row: usize,
        column: usize,
    ) -> PyResult<(
        Bound<'py, PyArray1<i64>>,
        Bound<'py, PyArray1<f64>>,
        Bound<'py, PyArray1<f64>>,
    )> {
        let row = self
            .cells
            .rows
            .get(row)
            .ok_or_else(|| failure("řádek mimo blok"))?;
        let found = row.cell(column);
        Ok((
            PyArray1::from_vec(py, found.iter().map(|cell| cell.0 as i64).collect()),
            PyArray1::from_vec(py, found.iter().map(|cell| cell.1).collect()),
            PyArray1::from_vec(py, found.iter().map(|cell| cell.2).collect()),
        ))
    }

    /// Podíl varianty ve slotu u jedné skupiny (0, když tam není).
    fn value(&self, row: usize, column: usize, slot: usize) -> PyResult<f64> {
        Ok(self
            .cells
            .rows
            .get(row)
            .ok_or_else(|| failure("řádek mimo blok"))?
            .value(column, slot))
    }

    /// Mapa rozšíření varianty: sloupce skupin a podíly.
    #[allow(clippy::type_complexity)]
    fn range_of<'py>(
        &self,
        py: Python<'py>,
        row: usize,
        slot: usize,
    ) -> PyResult<(Bound<'py, PyArray1<i64>>, Bound<'py, PyArray1<f64>>)> {
        let (groups, shares) = self
            .cells
            .rows
            .get(row)
            .ok_or_else(|| failure("řádek mimo blok"))?
            .range_of(slot);
        Ok((
            PyArray1::from_vec(py, groups),
            PyArray1::from_vec(py, shares),
        ))
    }

    /// Přenos bloku: míšení, tlaky (`fitness`) a výběr s driftem a ustálením.
    ///
    /// Blok se počítá po kusech `chunk_rows` proměnných (0 = celý). Pro každý kus Rust
    /// zavolá `fitness(od, do, podíly, slyšené)` a čeká pole tlaků tvaru kusu; bez
    /// `fitness` jsou tlaky nulové. Vrací nové podíly a základny jako pohledy bez kopie,
    /// platné do příštího přenosu bloku. `params` je (selection, kappa, adult_rate, establish_threshold).
    /// Vyžaduje `libm_matches` (viz `cee.v2.native`): `exp`, `ln` a `cos` knihovny systému.
    #[pyo3(signature = (step, flow_factors, channel_factors, present, slot_keys, params, fitness=None, chunk_rows=0))]
    #[allow(clippy::too_many_arguments, clippy::type_complexity)]
    fn transmit<'py>(
        slf: &Bound<'py, Self>,
        step: PyRef<'_, NativeStep>,
        flow_factors: Vec<PyReadonlyArray1<'py, f64>>,
        channel_factors: Vec<PyReadonlyArray1<'py, f64>>,
        present: PyReadonlyArray2<'py, bool>,
        slot_keys: PyReadonlyArray2<'py, u64>,
        params: (f64, f64, f64, f64),
        fitness: Option<Bound<'py, PyAny>>,
        chunk_rows: usize,
    ) -> PyResult<(Bound<'py, PyArray3<f64>>, Bound<'py, PyArray3<f64>>)> {
        let py = slf.py();
        let [rows, groups, capacity] = slf.borrow().shape();
        if groups != step.groups
            || present.shape() != [rows, groups]
            || slot_keys.shape() != [rows, capacity]
            || flow_factors.len() != step.flows.len()
            || channel_factors.len() != step.channels.len()
        {
            return Err(failure("vstupy přenosu nesedí na tvar bloku"));
        }
        let factors = flow_factors
            .iter()
            .chain(&channel_factors)
            .map(|factor| slice(factor))
            .collect::<PyResult<Vec<_>>>()?;
        if factors.iter().any(|factor| factor.len() != rows) {
            return Err(failure("faktor kanálu nemá délku bloku"));
        }
        let (flow_factors, channel_factors) = factors.split_at(step.flows.len());
        let (present, slot_keys) = (slice2(&present)?, slice2(&slot_keys)?);
        let (selection, kappa, adult_rate, establish_threshold) = params;
        let stride = groups * capacity;
        let step_chunk = if chunk_rows == 0 {
            rows.max(1)
        } else {
            chunk_rows
        };

        // Vlastnictví polí na dobu přenosu: žádné vypůjčení objektu nesmí trvat přes volání tlaků.
        let (
            dense_f,
            dense_p,
            mut updated_slot,
            mut baseline_slot,
            mut heard_slot,
            mut scratch,
            threads,
        ) = {
            let mut me = slf.borrow_mut();
            let (f, p) = me.ensure_dense(py)?;
            (
                f,
                p,
                me.out[0].take(),
                me.out[1].take(),
                me.heard.take(),
                std::mem::take(&mut me.scratch),
                me.threads,
            )
        };
        let updated = acquire(py, &mut updated_slot, rows * stride, false)?;
        let baseline = acquire(py, &mut baseline_slot, rows * stride, false)?;
        let result = (|| -> PyResult<()> {
            let current_all = dense_f.borrow();
            let previous_all = dense_p.borrow();
            let mut updated_all = updated.borrow_mut();
            let mut baseline_all = baseline.borrow_mut();
            let mut first = 0;
            while first < rows {
                let last = (first + step_chunk).min(rows);
                let count = last - first;
                let cells = first * stride..last * stride;
                let shape = Shape {
                    variables: count,
                    groups,
                    slots: capacity,
                };
                let heard = acquire(py, &mut heard_slot, count * stride, false)?;
                {
                    let flows: Vec<Flow<'_>> = step
                        .flows
                        .iter()
                        .zip(flow_factors)
                        .map(|(components, factor)| Flow {
                            factor: &factor[first..last],
                            components,
                        })
                        .collect();
                    let channels: Vec<Channel<'_>> = step
                        .channels
                        .iter()
                        .zip(channel_factors)
                        .map(|((learners, sources, weights), factor)| Channel {
                            factor: &factor[first..last],
                            learners,
                            sources,
                            weights,
                        })
                        .collect();
                    let mut heard_data = heard.borrow_mut();
                    transmission::hear(
                        shape,
                        &current_all.data[cells.clone()],
                        &present[first * groups..last * groups],
                        &step.network(),
                        &flows,
                        &channels,
                        &mut scratch,
                        threads,
                        &mut heard_data.data,
                    );
                }
                let pressures;
                let pressure_data: Option<&[f64]> = match &fitness {
                    Some(call) => {
                        let current_view =
                            view(py, &dense_f, first * stride, [count, groups, capacity])?;
                        let heard_view = view(py, &heard, 0, [count, groups, capacity])?;
                        let found = call.call1((first, last, current_view, heard_view))?;
                        pressures = found.extract::<PyReadonlyArray3<'_, f64>>()?;
                        if pressures.shape() != [count, groups, capacity] {
                            return Err(failure("tlaky mají špatný tvar"));
                        }
                        Some(slice3(&pressures)?)
                    }
                    None => None,
                };
                let heard_data = heard.borrow();
                transmission::settle(
                    shape,
                    &State {
                        current: &current_all.data[cells.clone()],
                        previous: &previous_all.data[cells.clone()],
                        present: &present[first * groups..last * groups],
                        heard: &heard_data.data,
                        fitness: pressure_data,
                        slot_keys: &slot_keys[first * capacity..last * capacity],
                    },
                    &Cohorts {
                        drift_scale: &step.drift_scale,
                        renewal: &step.renewal,
                        loss_floor: &step.loss_floor,
                        row_keys: &step.row_keys,
                        selection,
                        kappa,
                        adult_rate,
                        establish_threshold,
                    },
                    threads,
                    &mut updated_all.data[cells.clone()],
                    &mut baseline_all.data[cells],
                );
                first = last;
            }
            Ok(())
        })();
        {
            let mut me = slf.borrow_mut();
            me.out = [updated_slot, baseline_slot];
            me.heard = heard_slot;
            me.scratch = scratch;
        }
        result?;
        let shape = [rows, groups, capacity];
        Ok((
            view(py, &updated, 0, shape)?,
            view(py, &baseline, 0, shape)?,
        ))
    }
}

// --- bezstavové funkce (zlatá data a zkoušky) --------------------------------------------

fn shape3(array: &PyReadonlyArray3<'_, f64>) -> Shape {
    let dims = array.shape();
    Shape {
        variables: dims[0],
        groups: dims[1],
        slots: dims[2],
    }
}

fn array3<'py>(
    py: Python<'py>,
    data: Vec<f64>,
    shape: Shape,
) -> PyResult<Bound<'py, PyArray3<f64>>> {
    PyArray1::from_vec(py, data).reshape([shape.variables, shape.groups, shape.slots])
}

type RawFlow<'py> = (PyReadonlyArray1<'py, f64>, Vec<PyReadonlyArray2<'py, f64>>);
type RawChannelIn<'py> = (
    PyReadonlyArray1<'py, f64>,
    PyReadonlyArray1<'py, i64>,
    PyReadonlyArray1<'py, i64>,
    PyReadonlyArray1<'py, f64>,
);

/// Co skupiny slyší (`phases_transmission.hear`), stejné argumenty jako v Pythonu.
#[pyfunction]
#[pyo3(signature = (current, present, members, blocks, alone, alone_weight, flows, channels, threads=1))]
#[allow(clippy::too_many_arguments)]
pub fn hear<'py>(
    py: Python<'py>,
    current: PyReadonlyArray3<'py, f64>,
    present: PyReadonlyArray2<'py, bool>,
    members: Vec<PyReadonlyArray1<'py, i64>>,
    blocks: Vec<PyReadonlyArray2<'py, f64>>,
    alone: PyReadonlyArray1<'py, i64>,
    alone_weight: PyReadonlyArray1<'py, f64>,
    flows: Vec<RawFlow<'py>>,
    channels: Vec<RawChannelIn<'py>>,
    threads: usize,
) -> PyResult<Bound<'py, PyArray3<f64>>> {
    let shape = shape3(&current);
    if present.shape() != [shape.variables, shape.groups] {
        return Err(failure("present nemá tvar bloku"));
    }
    let member_lists = members
        .iter()
        .map(|group| indices(slice(group)?))
        .collect::<PyResult<Vec<_>>>()?;
    let components = components_from(&member_lists, &blocks)?;
    let alone = indices(slice(&alone)?)?;
    let alone_weight = slice(&alone_weight)?;
    if alone.len() != alone_weight.len() || alone.iter().any(|&group| group >= shape.groups) {
        return Err(failure("osamocené skupiny nesedí"));
    }
    let flow_components = flows
        .iter()
        .map(|(_, flow)| components_from(&member_lists, flow))
        .collect::<PyResult<Vec<_>>>()?;
    let mut flow_views = Vec::new();
    for ((factor, _), components) in flows.iter().zip(&flow_components) {
        let factor = slice(factor)?;
        if factor.len() != shape.variables {
            return Err(failure("faktor kanálu nemá délku bloku"));
        }
        flow_views.push(Flow { factor, components });
    }
    let channel_lists = channels
        .iter()
        .map(|(factor, learners, sources, weights)| {
            let factor = slice(factor)?;
            let (learners, sources) = (indices(slice(learners)?)?, indices(slice(sources)?)?);
            let weights = slice(weights)?;
            if factor.len() != shape.variables
                || learners.len() != sources.len()
                || learners.len() != weights.len()
                || learners
                    .iter()
                    .chain(&sources)
                    .any(|&group| group >= shape.groups)
            {
                return Err(failure("kanál nesedí na blok"));
            }
            Ok((factor, learners, sources, weights))
        })
        .collect::<PyResult<Vec<_>>>()?;
    let channel_views: Vec<Channel<'_>> = channel_lists
        .iter()
        .map(|(factor, learners, sources, weights)| Channel {
            factor,
            learners,
            sources,
            weights,
        })
        .collect();
    let mut heard = vec![0.0; shape.cells()];
    let mut scratch = Vec::new();
    transmission::hear(
        shape,
        slice3(&current)?,
        slice2(&present)?,
        &Network {
            components: &components,
            alone: &alone,
            alone_weight,
        },
        &flow_views,
        &channel_views,
        &mut scratch,
        threads.max(1),
        &mut heard,
    );
    array3(py, heard, shape)
}

/// Nové frekvence a základna bloku (`phases_transmission.settle`), stejné argumenty jako v Pythonu.
#[pyfunction]
#[pyo3(signature = (current, previous, present, heard, fitness, slot_keys, row_keys, drift_scale, renewal, loss_floor, selection, kappa, adult_rate, establish_threshold, threads=1))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn settle<'py>(
    py: Python<'py>,
    current: PyReadonlyArray3<'py, f64>,
    previous: PyReadonlyArray3<'py, f64>,
    present: PyReadonlyArray2<'py, bool>,
    heard: PyReadonlyArray3<'py, f64>,
    fitness: PyReadonlyArray3<'py, f64>,
    slot_keys: PyReadonlyArray2<'py, u64>,
    row_keys: PyReadonlyArray1<'py, u64>,
    drift_scale: PyReadonlyArray1<'py, f64>,
    renewal: PyReadonlyArray1<'py, f64>,
    loss_floor: PyReadonlyArray1<'py, f64>,
    selection: f64,
    kappa: f64,
    adult_rate: f64,
    establish_threshold: f64,
    threads: usize,
) -> PyResult<(Bound<'py, PyArray3<f64>>, Bound<'py, PyArray3<f64>>)> {
    let shape = shape3(&current);
    let same = |other: &PyReadonlyArray3<'py, f64>| other.shape() == current.shape();
    let group_sizes = [
        slice(&row_keys)?.len(),
        slice(&drift_scale)?.len(),
        slice(&renewal)?.len(),
        slice(&loss_floor)?.len(),
    ];
    if !(same(&previous) && same(&heard) && same(&fitness))
        || present.shape() != [shape.variables, shape.groups]
        || slot_keys.shape() != [shape.variables, shape.slots]
        || group_sizes.iter().any(|&size| size != shape.groups)
    {
        return Err(failure("vstupy settle mají různý tvar"));
    }
    let (mut updated, mut baseline) = (vec![0.0; shape.cells()], vec![0.0; shape.cells()]);
    transmission::settle(
        shape,
        &State {
            current: slice3(&current)?,
            previous: slice3(&previous)?,
            present: slice2(&present)?,
            heard: slice3(&heard)?,
            fitness: Some(slice3(&fitness)?),
            slot_keys: slice2(&slot_keys)?,
        },
        &Cohorts {
            drift_scale: slice(&drift_scale)?,
            renewal: slice(&renewal)?,
            loss_floor: slice(&loss_floor)?,
            row_keys: slice(&row_keys)?,
            selection,
            kappa,
            adult_rate,
            establish_threshold,
        },
        threads.max(1),
        &mut updated,
        &mut baseline,
    );
    Ok((array3(py, updated, shape)?, array3(py, baseline, shape)?))
}

/// Podíly slotů dělené součtem po buňkách poslední osy (`phases_transmission.normalized`).
#[pyfunction]
pub fn normalized<'py>(
    py: Python<'py>,
    array: PyReadonlyArray3<'py, f64>,
    fallback: PyReadonlyArray3<'py, f64>,
) -> PyResult<Bound<'py, PyArray3<f64>>> {
    if array.shape() != fallback.shape() || array.shape()[2] == 0 {
        return Err(failure("pole nemají stejný tvar"));
    }
    let shape = shape3(&array);
    let out = transmission::normalized(slice3(&array)?, slice3(&fallback)?, shape.slots);
    array3(py, out, shape)
}

/// `exp`, `ln` a `cos` knihovny systému a šum driftu (`rng.hash_normal`) po prvcích: pro
/// zkoušku, zda Rust dává bit po bitu totéž co `numpy` (`cee.v2.native.libm_matches`).
#[pyfunction]
pub fn libm_probe<'py>(
    py: Python<'py>,
    kind: &str,
    first: PyReadonlyArray1<'py, f64>,
    second: PyReadonlyArray1<'py, u64>,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
    let values = slice(&first)?;
    let found: Vec<f64> = match kind {
        "exp" => values.iter().map(|value| value.exp()).collect(),
        "ln" => values.iter().map(|value| value.ln()).collect(),
        "cos" => values.iter().map(|value| value.cos()).collect(),
        "hash_normal" => {
            let keys = slice(&second)?;
            if keys.len() != 2 * values.len() {
                return Err(failure("hash_normal čeká dva klíče na prvek"));
            }
            keys.chunks(2)
                .map(|pair| transmission::hash_normal(pair[0], pair[1]))
                .collect()
        }
        _ => return Err(failure("neznámá zkouška")),
    };
    Ok(PyArray1::from_vec(py, found))
}
