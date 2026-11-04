//! Vazba PyO3 na engine CEE v2 pro server (`src/cee/v2/runner.py`).
//!
//! Tenká: `Run` postaví svět z popisu `WorldSpec` (JSON), krokuje ho a vrací lehké snímky
//! a úplný export `cee-v2/1` jako text JSON. Každý krok běží bez GIL (`detach`), takže server
//! mezitím obsluhuje dotazy UI. Zrušení je příznak mimo zámek běhu: `cancel()` nečeká na
//! rozpracovaný krok a `advance` se zastaví po jeho dokončení.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};

use cee_engine::export;
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{Simulation, SimulationConfig};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;

/// Celý svět z popisu; chyba je text se zprávou enginu.
fn simulation(spec_json: &str) -> Result<(Simulation, WorldSpec), String> {
    let world_spec = WorldSpec::from_json(spec_json)?;
    let (world, events) = spec::build(&world_spec)?;
    let simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    Ok((simulation, world_spec))
}

/// Jeden běh: simulace za zámkem, příznak zrušení vedle něj.
#[pyclass(module = "cee_engine_py")]
struct Run {
    inner: Mutex<Simulation>,
    cancelled: Arc<AtomicBool>,
    start_year: f64,
    end_year: f64,
}

impl Run {
    fn lock(&self) -> PyResult<MutexGuard<'_, Simulation>> {
        self.inner
            .lock()
            .map_err(|_| PyRuntimeError::new_err("běh enginu spadl (otrávený zámek)"))
    }
}

#[pymethods]
impl Run {
    /// Postaví svět z popisu `WorldSpec` (text JSON); neplatný popis vyhodí `ValueError`.
    #[new]
    fn new(py: Python<'_>, spec_json: &str) -> PyResult<Run> {
        let text = spec_json.to_owned();
        let (simulation, world_spec) = py
            .detach(move || simulation(&text))
            .map_err(PyValueError::new_err)?;
        Ok(Run {
            inner: Mutex::new(simulation),
            cancelled: Arc::new(AtomicBool::new(false)),
            start_year: world_spec.start_year,
            end_year: world_spec.end_year,
        })
    }

    #[getter]
    fn start_year(&self) -> f64 {
        self.start_year
    }

    #[getter]
    fn end_year(&self) -> f64 {
        self.end_year
    }

    /// Rok po posledním provedeném kroku.
    #[getter]
    fn year(&self, py: Python<'_>) -> PyResult<f64> {
        py.detach(|| self.lock().map(|s| s.year()))
    }

    #[getter]
    fn tick(&self, py: Python<'_>) -> PyResult<u32> {
        py.detach(|| self.lock().map(|s| s.tick))
    }

    /// Kolik pozorování (snímků dialektů a jazyků) už historie má.
    #[getter]
    fn snapshots(&self, py: Python<'_>) -> PyResult<usize> {
        py.detach(|| self.lock().map(|s| s.history.snapshots.len()))
    }

    /// Je běh zrušený?
    #[getter]
    fn cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Relaxed)
    }

    /// Je co krokovat (do `end_year` se vejde další krok)?
    #[getter]
    fn finished(&self, py: Python<'_>) -> PyResult<bool> {
        let end = self.end_year;
        py.detach(|| self.lock().map(|s| s.year() + s.config.dt > end + 1e-9))
    }

    /// Zruší běh: nečeká na rozpracovaný krok, `advance` se pak zastaví.
    fn cancel(&self) {
        self.cancelled.store(true, Ordering::Relaxed);
    }

    /// Provede nejvýš `steps` kroků bez GIL; po zrušení nebo po `end_year` skončí dřív.
    /// Vrátí, zda je ještě co krokovat. Chyba enginu vyhodí `RuntimeError`.
    #[pyo3(signature = (steps = 1))]
    fn advance(&self, py: Python<'_>, steps: u32) -> PyResult<bool> {
        let end = self.end_year;
        py.detach(|| {
            let mut simulation = self.lock()?;
            for _ in 0..steps {
                if self.cancelled.load(Ordering::Relaxed) {
                    return Ok(false);
                }
                if simulation.year() + simulation.config.dt > end + 1e-9 {
                    return Ok(false);
                }
                simulation.step().map_err(PyRuntimeError::new_err)?;
            }
            Ok(simulation.year() + simulation.config.dt <= end + 1e-9)
        })
    }

    /// Lehký snímek pro kreslení během běhu (`export.frame`) jako text JSON.
    fn frame(&self, py: Python<'_>) -> PyResult<String> {
        py.detach(|| {
            let simulation = self.lock()?;
            Ok(export::frame(&simulation).to_string())
        })
    }

    /// Úplný export `cee-v2/1` jako text JSON (`export.export`; `timeline` = jen události časové osy).
    #[pyo3(signature = (timeline = true))]
    fn export(&self, py: Python<'_>, timeline: bool) -> PyResult<String> {
        py.detach(|| {
            let simulation = self.lock()?;
            Ok(export::export(&simulation, timeline).to_string())
        })
    }
}

/// Zkušební stavba světa z popisu bez běhu: `None` = svět jde postavit, jinak zpráva o chybě.
#[pyfunction]
fn check_spec(py: Python<'_>, spec_json: &str) -> Option<String> {
    let text = spec_json.to_owned();
    py.detach(move || simulation(&text).err())
}

#[pymodule]
fn cee_engine_py(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Run>()?;
    module.add_function(wrap_pyfunction!(check_spec, module)?)?;
    Ok(())
}
