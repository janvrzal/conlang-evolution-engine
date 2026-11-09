//! Engine CEE v2 přímo v aplikaci: ověření zadání, schéma pro UI a běhy na pozadí.
//!
//! Nahrazuje Python server (`src/cee/api/v2.py`, `src/cee/v2/runner.py`): stejné tvary odpovědí,
//! jen se volají příkazy Tauri místo HTTP. Každý běh má vlastní vlákno; UI se ptá na stav a nové
//! snímky (`since`) a na konci si vezme export. Export nese jen události časové osy (dějiny,
//! jazyky, společnost); milníky zvukových změn (miliony) jsou sečtené po stoletích v `event_summary`.

use std::collections::BTreeMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use cee_engine::parameters::{parameter_file, LEVEL_TABLES};
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{export, Simulation, SimulationConfig};
use serde::Serialize;
use serde_json::{json, Map, Value};

/// Kolik dokončených běhů aplikace drží v paměti.
const KEEP_RUNS: usize = 8;
pub const API_REVISION: u32 = 10;

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct Issue {
    pub path: String,
    pub message: String,
    pub severity: &'static str,
}

/// Ověření popisu světa bez běhu: chyby před varováními (jako `/api/v2/validate`).
pub fn validate(spec: &Value) -> Vec<Issue> {
    // tvar zadání (pole, typy, meze) s cestou k poli; teprve pak engine
    let shape = crate::spec_schema::check_shape(spec);
    if !shape.is_empty() {
        return shape;
    }
    let text = spec.to_string();
    let world_spec = match WorldSpec::from_json(&text) {
        Ok(s) => s,
        Err(message) => return vec![Issue { path: "(svět)".into(), message, severity: "error" }],
    };
    let overrides = check_parameters(spec);
    if !overrides.is_empty() {
        return overrides;
    }
    let (errors, warnings): (Vec<_>, Vec<_>) = spec::check(&world_spec).into_iter().partition(|i| i.severity == "error");
    errors
        .into_iter()
        .chain(warnings)
        .map(|i| Issue { path: i.path, message: i.message, severity: if i.severity == "error" { "error" } else { "warning" } })
        .collect()
}

/// Přepisy parametrů podle `v2_parameters.json`: neznámé jméno, druh a meze.
fn check_parameters(spec: &Value) -> Vec<Issue> {
    let Some(overrides) = spec.get("parameters").and_then(Value::as_object) else { return Vec::new() };
    let file = parameter_file();
    overrides
        .iter()
        .filter_map(|(name, value)| match file.parameters.iter().find(|p| &p.name == name) {
            None => Some(Issue { path: format!("parameters.{name}"), message: "neznámý parametr".into(), severity: "error" }),
            Some(p) => p.check(value).err().map(|message| {
                // zpráva enginu začíná cestou „parameters.x.y: …“
                let (path, text) = message.split_once(": ").map(|(a, b)| (a.to_owned(), b.to_owned())).unwrap_or((format!("parameters.{name}"), message));
                Issue { path, message: text, severity: "error" }
            }),
        })
        .collect()
}

/// Schéma pro UI (jako `/api/v2/schema`): zadání, slovní úrovně, parametry podle rolí, druhy událostí, slovník.
pub fn schema() -> Value {
    let mut out = Map::new();
    out.insert("format".into(), json!(spec::FORMAT));
    out.insert("json_schema".into(), crate::spec_schema::json_schema());
    out.insert("event_kinds".into(), json!(crate::spec_schema::EVENT_KINDS));
    out.insert("vocabulary".into(), crate::spec_schema::vocabulary_options());
    let file: Value = serde_json::from_str(cee_engine::data::PARAMETERS_JSON).expect("v2_parameters.json");
    let items: Vec<Value> = file["parameters"]
        .as_array()
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .map(|mut item| {
            if matches!(item["kind"].as_str(), Some("level_table" | "level_table2")) {
                let mut levels: Vec<String> = item["default"].as_object().map(|o| o.keys().cloned().collect()).unwrap_or_default();
                levels.sort();
                item["levels"] = json!(levels);
            }
            item
        })
        .collect();
    let by_role = |role: &str| json!({ "groups": file["groups"], "items": items.iter().filter(|i| i["role"].as_str().unwrap_or("active") == role).cloned().collect::<Vec<_>>() });
    let levels: Map<String, Value> = LEVEL_TABLES
        .iter()
        .filter_map(|name| {
            let item = items.iter().find(|i| i["name"] == *name)?;
            let mut keys: Vec<String> = item["default"].as_object()?.keys().cloned().collect();
            keys.sort();
            Some((name.to_string(), json!(keys)))
        })
        .collect();
    out.insert("levels".into(), Value::Object(levels));
    out.insert("parameters".into(), json!({ "groups": file["groups"], "items": items }));
    out.insert("parameters_by_role".into(), json!({ "world": by_role("world"), "active": by_role("active"), "fixed": by_role("fixed") }));
    if let Some(v) = out.get_mut("vocabulary").and_then(Value::as_object_mut) {
        v.insert("max".into(), json!(cee_engine::vocabulary::max_size()));
    }
    Value::Object(out)
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum Status {
    Running,
    Done,
    Failed,
    Cancelled,
}

struct RunState {
    status: Status,
    year: f64,
    seconds: f64,
    error: Option<String>,
    frames: Vec<Value>,
    result: Option<Arc<Value>>,
}

pub struct Run {
    id: String,
    start_year: f64,
    end_year: f64,
    started: Instant,
    cancelled: AtomicBool,
    state: Mutex<RunState>,
}

impl Run {
    /// Stav pro UI; `since` = kolik snímků už klient má (jako `GET /api/v2/runs/{id}`).
    pub fn status(&self, since: usize) -> Value {
        let s = self.state.lock().expect("stav běhu");
        let span = (self.end_year - self.start_year).max(1e-9);
        json!({
            "id": self.id, "status": s.status, "year": s.year,
            "progress": ((s.year - self.start_year) / span).clamp(0.0, 1.0),
            "start_year": self.start_year, "end_year": self.end_year,
            "seconds": (s.seconds * 100.0).round() / 100.0, "error": s.error,
            "frame_count": s.frames.len(), "frames": s.frames.get(since..).unwrap_or(&[]),
        })
    }

    pub fn result(&self) -> Result<Arc<Value>, String> {
        let s = self.state.lock().expect("stav běhu");
        match (&s.result, s.status) {
            (Some(r), Status::Done) => Ok(r.clone()),
            (_, status) => Err(format!("Běh není dokončený (stav {status:?}).")),
        }
    }

    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::Relaxed);
    }

    fn execute(&self, mut simulation: Simulation) {
        let outcome = (|| -> Result<bool, String> {
            let mut observed = simulation.history.snapshots.len();
            loop {
                if self.cancelled.load(Ordering::Relaxed) {
                    return Ok(false);
                }
                let more = simulation.year() + simulation.config.dt <= self.end_year + 1e-9;
                if more {
                    simulation.step()?;
                } else {
                    // koncový snímek v end_year
                    simulation.observe_now()?;
                }
                let frame = (simulation.history.snapshots.len() != observed).then(|| export::frame(&simulation));
                observed = simulation.history.snapshots.len();
                let mut s = self.state.lock().expect("stav běhu");
                s.year = simulation.year();
                s.seconds = self.started.elapsed().as_secs_f64();
                if let Some(f) = frame {
                    s.frames.push(f);
                }
                if !more {
                    return Ok(true);
                }
            }
        })();
        let result = match outcome {
            Ok(true) => Some(result_of(&simulation)),
            _ => None,
        };
        let mut s = self.state.lock().expect("stav běhu");
        s.seconds = self.started.elapsed().as_secs_f64();
        match (outcome, result) {
            (Err(error), _) => {
                s.error = Some(error);
                s.status = Status::Failed;
            }
            (Ok(_), Some(r)) => {
                s.result = Some(Arc::new(r));
                s.status = Status::Done;
            }
            (Ok(_), None) => s.status = Status::Cancelled,
        }
    }
}

/// Export pro UI: události časové osy, souhrn všech událostí po stoletích a počty podle druhu.
pub fn result_of(simulation: &Simulation) -> Value {
    let mut out = export::export(simulation, true);
    let mut summary: BTreeMap<String, BTreeMap<String, u64>> = BTreeMap::new();
    let mut counts: BTreeMap<String, u64> = BTreeMap::new();
    for line in simulation.history.events.lines() {
        let (Some(kind), Some(year)) = (field_str(&line, "kind"), field_num(&line, "year")) else { continue };
        let century = ((year / 100.0).floor() * 100.0) as i64;
        *summary.entry(century.to_string()).or_default().entry(kind.to_owned()).or_default() += 1;
        *counts.entry(kind.to_owned()).or_default() += 1;
    }
    if let Some(o) = out.as_object_mut() {
        o.insert("event_summary".into(), json!(summary));
        o.insert("event_counts".into(), json!(counts));
        o.remove("links");
    }
    out
}

/// Rychlé čtení pole z řádku JSON bez úplného rozboru (miliony řádků logu).
fn field_str<'a>(line: &'a str, key: &str) -> Option<&'a str> {
    let start = line.find(&format!("\"{key}\":\""))? + key.len() + 4;
    let end = line[start..].find('"')? + start;
    Some(&line[start..end])
}
fn field_num(line: &str, key: &str) -> Option<f64> {
    let start = line.find(&format!("\"{key}\":"))? + key.len() + 3;
    let end = line[start..].find([',', '}']).map(|e| e + start)?;
    line[start..end].trim().parse().ok()
}

/// Běhy v paměti aplikace.
#[derive(Default)]
pub struct Runs {
    runs: Mutex<Vec<Arc<Run>>>,
    next: AtomicU64,
}

impl Runs {
    /// Spustí běh na pozadí; neplatný popis vrátí seznam chyb (jako 422 serveru).
    pub fn start(&self, spec: &Value) -> Result<Arc<Run>, Vec<Issue>> {
        let issues = validate(spec);
        if issues.iter().any(|i| i.severity == "error") {
            return Err(issues.into_iter().filter(|i| i.severity == "error").collect());
        }
        let error = |message: String| vec![Issue { path: "(svět)".into(), message, severity: "error" }];
        let world_spec = WorldSpec::from_json(&spec.to_string()).map_err(error)?;
        let (world, events) = spec::build(&world_spec).map_err(error)?;
        let simulation = Simulation::new(world, SimulationConfig::default(), events).map_err(error)?;
        let id = format!("run{}-{:x}", self.next.fetch_add(1, Ordering::Relaxed), std::process::id());
        let run = Arc::new(Run {
            id,
            start_year: world_spec.start_year,
            end_year: world_spec.end_year,
            started: Instant::now(),
            cancelled: AtomicBool::new(false),
            state: Mutex::new(RunState { status: Status::Running, year: world_spec.start_year, seconds: 0.0, error: None, frames: Vec::new(), result: None }),
        });
        {
            let mut runs = self.runs.lock().expect("seznam běhů");
            let finished: Vec<usize> = (0..runs.len()).filter(|&i| runs[i].state.lock().map(|s| s.status != Status::Running).unwrap_or(true)).collect();
            if finished.len() >= KEEP_RUNS {
                runs.remove(finished[0]);
            }
            runs.push(run.clone());
        }
        let worker = run.clone();
        std::thread::Builder::new()
            .name(format!("cee-{}", run.id))
            .stack_size(64 * 1024 * 1024)
            .spawn(move || worker.execute(simulation))
            .map_err(|e| error(e.to_string()))?;
        Ok(run)
    }

    pub fn get(&self, id: &str) -> Result<Arc<Run>, String> {
        self.runs
            .lock()
            .expect("seznam běhů")
            .iter()
            .find(|r| r.id == id)
            .cloned()
            .ok_or_else(|| "Běh nebyl nalezen (aplikace ho nedrží).".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn talvera() -> Value {
        serde_json::from_str(include_str!("../../static/projects/talvera.cee.json")).unwrap()
    }

    #[test]
    fn talvera_je_bez_chyb_a_preklep_hlasi_engine() {
        let world = talvera();
        assert!(validate(&world).iter().all(|i| i.severity != "error"));
        let mut broken = world.clone();
        broken["events"][28]["of"] = json!("selvaa");
        let issues = validate(&broken);
        assert_eq!(issues[0].path, "events.28");
        assert!(issues[0].message.contains("selvaa"));
        let mut param = world;
        param["parameters"]["neexistuje"] = json!(1);
        assert_eq!(validate(&param)[0].message, "neznámý parametr");
    }

    #[test]
    fn schema_ma_parametry_urovne_a_slovnik() {
        let s = schema();
        assert!(s["json_schema"].is_object());
        assert!(s["levels"]["policy_levels"].as_array().unwrap().iter().any(|v| v == "enforced"));
        assert!(!s["parameters_by_role"]["world"]["items"].as_array().unwrap().is_empty());
        assert!(s["vocabulary"]["max"].as_u64().unwrap() > 149);
        // druhy událostí popisu zadání = druhy, které engine umí
        let mut kinds: Vec<&str> = s["event_kinds"].as_array().unwrap().iter().filter_map(Value::as_str).collect();
        let mut engine_kinds = spec::EVENT_KINDS.to_vec();
        kinds.sort();
        engine_kinds.sort();
        assert_eq!(kinds, engine_kinds);
    }

    #[test]
    fn kratky_beh_ma_snimky_a_souhrn_udalosti() {
        let mut world = talvera();
        world["end_year"] = json!(-400);
        // pozdější události by zkrácený svět odmítl (leží mimo start_year až end_year)
        let events: Vec<Value> = world["events"].as_array().unwrap().iter().filter(|e| e["year"].as_f64().unwrap() <= -400.0).cloned().collect();
        world["events"] = json!(events);
        let runs = Runs::default();
        let run = runs.start(&world).expect("běh");
        let started = Instant::now();
        while run.status(0)["status"] == "running" {
            assert!(started.elapsed().as_secs() < 600, "běh trvá moc dlouho");
            std::thread::sleep(std::time::Duration::from_millis(100));
        }
        let status = run.status(0);
        assert_eq!(status["status"], "done", "{status}");
        assert!(status["frame_count"].as_u64().unwrap() >= 2);
        let result = run.result().unwrap();
        assert_eq!(result["format"], "cee-v2/1");
        assert!(result["event_summary"].as_object().is_some_and(|o| !o.is_empty()));
        assert!(result.get("links").is_none());
        assert_eq!(result["year"], -400.0);
    }
}

#[cfg(test)]
mod measure {
    use super::*;

    /// Celý běh Talvery: čas a velikost výsledku pro UI (`cargo test --lib -- --ignored --nocapture`).
    #[test]
    #[ignore]
    fn cela_talvera() {
        let world: Value = serde_json::from_str(include_str!("../../static/projects/talvera.cee.json")).unwrap();
        let runs = Runs::default();
        let run = runs.start(&world).expect("běh");
        let t = Instant::now();
        while run.status(0)["status"] == "running" {
            std::thread::sleep(std::time::Duration::from_millis(500));
        }
        let status = run.status(usize::MAX);
        let result = run.result().expect("výsledek");
        let text = result.to_string();
        let frames: usize = run.status(0)["frames"].to_string().len();
        println!(
            "Talvera: {:.0} s, {} snímků ({} MB), výsledek {} MB, {} událostí časové osy, jazyků {}",
            t.elapsed().as_secs_f64(),
            status["frame_count"],
            frames / 1_000_000,
            text.len() / 1_000_000,
            result["events"].as_array().map_or(0, Vec::len),
            result["lineages"].as_array().map_or(0, Vec::len)
        );
    }
}

#[cfg(test)]
mod tempo {
    use super::*;

    /// Čas kroku po stoletích proti velikosti světa (`cargo test --lib tempo -- --ignored --nocapture`).
    #[test]
    #[ignore]
    fn tempo_po_stoletich() {
        let world: Value = serde_json::from_str(include_str!("../../static/projects/talvera.cee.json")).unwrap();
        let ws = WorldSpec::from_json(&world.to_string()).unwrap();
        let (w, events) = spec::build(&ws).unwrap();
        let mut sim = Simulation::new(w, SimulationConfig::default(), events).unwrap();
        let mut t = Instant::now();
        let mut century = (sim.year() / 100.0).floor();
        let mut steps = 0;
        println!("století  s/krok  skupin  jazyků  událostí(log)");
        while sim.year() + sim.config.dt <= ws.end_year + 1e-9 {
            sim.step().unwrap();
            steps += 1;
            let c = (sim.year() / 100.0).floor();
            if c != century {
                let langs = sim.history.snapshots.last().map_or(0, |s| s.languages.len());
                println!("{:>6}  {:>6.2}  {:>6}  {:>6}  {:>10}", century * 100.0, t.elapsed().as_secs_f64() / steps as f64, sim.world.groups.len(), langs, sim.history.events.len());
                t = Instant::now();
                steps = 0;
                century = c;
            }
        }
    }
}
