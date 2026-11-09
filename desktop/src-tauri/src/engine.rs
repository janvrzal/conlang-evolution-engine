//! Engine CEE v2 přímo v aplikaci: ověření zadání, schéma pro UI a běhy na pozadí.
//!
//! Nahrazuje Python server (`src/cee/api/v2.py`, `src/cee/v2/runner.py`): stejné tvary odpovědí,
//! jen se volají příkazy Tauri místo HTTP. Každý běh má vlastní vlákno a zároveň se zapisuje do
//! své složky vedle projektu (`cee_store`: zadání, snímky, slovník v čase, kontrolní body, výsledek).
//! „Co kdyby“ pokračuje z kontrolního bodu rodiče před rokem větvení. Export nese jen události
//! časové osy; milníky zvukových změn (miliony) jsou sečtené po stoletích v `event_summary`.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use cee_engine::parameters::{parameter_file, LEVEL_TABLES};
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{export, Simulation, SimulationConfig};
use cee_store::recorder::{RecordOptions, Recorder};
use cee_store::{NewRun, RunWriter};
use serde::Serialize;
use serde_json::{json, Map, Value};

/// Kolik dokončených běhů aplikace drží v paměti.
const KEEP_RUNS: usize = 8;
pub const API_REVISION: u32 = 10;

/// Hláška ověření: cesta k poli, česká zpráva, závažnost, stálý kód pro překlad a dosazované hodnoty.
#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct Issue {
    pub path: String,
    pub message: String,
    pub severity: &'static str,
    pub code: String,
    pub args: BTreeMap<String, String>,
}

impl Issue {
    pub fn error(path: impl Into<String>, message: impl Into<String>, code: impl Into<String>) -> Issue {
        Issue { path: path.into(), message: message.into(), severity: "error", code: code.into(), args: BTreeMap::new() }
    }
    pub fn with(mut self, key: &str, value: impl ToString) -> Issue {
        self.args.insert(key.into(), value.to_string());
        self
    }
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
        Err(message) => return vec![Issue::error("(svět)", message, "world_invalid")],
    };
    let overrides = check_parameters(spec);
    if !overrides.is_empty() {
        return overrides;
    }
    let (errors, warnings): (Vec<_>, Vec<_>) = spec::check(&world_spec).into_iter().partition(|i| i.severity == "error");
    errors
        .into_iter()
        .chain(warnings)
        .map(|i| Issue {
            path: i.path,
            message: i.message,
            severity: if i.severity == "error" { "error" } else { "warning" },
            code: i.code.to_owned(),
            args: i.args.into_iter().map(|(k, v)| (k.to_owned(), v)).collect(),
        })
        .collect()
}

/// Přepisy parametrů podle `v2_parameters.json`: neznámé jméno, druh a meze.
fn check_parameters(spec: &Value) -> Vec<Issue> {
    let Some(overrides) = spec.get("parameters").and_then(Value::as_object) else { return Vec::new() };
    let file = parameter_file();
    overrides
        .iter()
        .filter_map(|(name, value)| match file.parameters.iter().find(|p| &p.name == name) {
            None => Some(Issue::error(format!("parameters.{name}"), "neznámý parametr", "parameter_unknown").with("name", name)),
            Some(p) => p.check(value).err().map(|message| {
                // zpráva enginu začíná cestou „parameters.x.y: …“
                let (path, text) = message.split_once(": ").map(|(a, b)| (a.to_owned(), b.to_owned())).unwrap_or((format!("parameters.{name}"), message));
                Issue::error(path, text, "parameter_invalid").with("name", name)
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

/// Stav běhu (jako `cee_store::Status`; `interrupted` jen u běhů přečtených z disku).
pub use cee_store::Status;

struct RunState {
    status: Status,
    year: f64,
    seconds: f64,
    error: Option<String>,
    frames: Vec<Value>,
    result: Option<Arc<Value>>,
}

/// Běh v paměti aplikace; zároveň se zapisuje do své složky (`cee_store`).
pub struct Run {
    /// Cesta ke složce běhu (je i jeho id pro UI).
    pub dir: PathBuf,
    start_year: f64,
    end_year: f64,
    started: Instant,
    cancelled: AtomicBool,
    state: Mutex<RunState>,
}

impl Run {
    pub fn id(&self) -> String {
        self.dir.to_string_lossy().to_string()
    }

    /// Stav pro UI; `since` = kolik snímků už klient má (jako `GET /api/v2/runs/{id}`).
    pub fn status(&self, since: usize) -> Value {
        let s = self.state.lock().expect("stav běhu");
        let span = (self.end_year - self.start_year).max(1e-9);
        json!({
            "id": self.id(), "status": s.status, "year": s.year,
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

    fn execute(&self, mut simulation: Simulation, mut writer: RunWriter, mut recorder: Recorder) {
        let outcome = (|| -> Result<bool, String> {
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
                let seconds = self.started.elapsed().as_secs_f64();
                let batch = recorder.collect(&simulation)?;
                let frame = batch.frame.clone();
                batch.write(&mut writer, seconds)?;
                let mut s = self.state.lock().expect("stav běhu");
                s.year = simulation.year();
                s.seconds = seconds;
                if let Some(f) = frame {
                    s.frames.push(f);
                }
                if !more {
                    return Ok(true);
                }
            }
        })();
        let seconds = self.started.elapsed().as_secs_f64();
        let (status, error, result) = match outcome {
            Ok(true) => (Status::Done, None, Some(Arc::new(result_of(&simulation)))),
            Ok(false) => (Status::Cancelled, None, None),
            Err(e) => (Status::Failed, Some(e), None),
        };
        // zápis do složky běhu; selhání zápisu se ukáže jako chyba běhu
        let saved = writer.finish(status, error.as_deref(), seconds, result.as_deref());
        let mut s = self.state.lock().expect("stav běhu");
        s.seconds = seconds;
        s.status = status;
        s.error = error.or(saved.err().map(|e| format!("Běh se nepodařilo uložit: {e}")));
        s.result = result;
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

/// Jak běh vznikne.
pub struct StartRun<'a> {
    pub spec: &'a Value,
    /// Složka běhů projektu (`svet.cee.behy`).
    pub dir: &'a Path,
    pub name: Option<&'a str>,
    /// „Co kdyby“: složka rodičovského běhu; počítá se od kontrolního bodu před rokem větvení.
    pub parent: Option<&'a Path>,
}

/// Běhy v paměti aplikace (zároveň zapisované na disk).
#[derive(Default)]
pub struct Runs {
    runs: Mutex<Vec<Arc<Run>>>,
}

fn issue(path: &str, message: String, code: &str) -> Vec<Issue> {
    vec![Issue::error(path, message, code)]
}

impl Runs {
    /// Spustí běh na pozadí; neplatný popis vrátí seznam chyb (jako 422 serveru).
    pub fn start(&self, new: StartRun<'_>) -> Result<Arc<Run>, Vec<Issue>> {
        let issues = validate(new.spec);
        if issues.iter().any(|i| i.severity == "error") {
            return Err(issues.into_iter().filter(|i| i.severity == "error").collect());
        }
        let world_spec = WorldSpec::from_json(&new.spec.to_string()).map_err(|e| issue("(svět)", e, "world_invalid"))?;
        let engine = format!("cee-desktop {}", env!("CARGO_PKG_VERSION"));
        // „co kdyby“: rok větvení proti rodiči a kontrolní bod před ním
        let resume = match new.parent {
            None => None,
            Some(parent) => {
                let parent_spec = cee_store::spec(parent).and_then(|v| WorldSpec::from_json(&v.to_string())).map_err(|e| issue("(svět)", e, "world_invalid"))?;
                match spec::branch_year(&parent_spec, &world_spec) {
                    None => None,
                    Some(year) => {
                        let at = if year.is_finite() { year } else { world_spec.end_year };
                        cee_store::checkpoint_before(parent, at).map_err(|e| issue("(svět)", e, "world_failed"))?.map(|point| (parent, year, point))
                    }
                }
            }
        };
        let parent_id = |p: &Path| p.file_name().map(|n| n.to_string_lossy().to_string());
        let (simulation, writer, recorder, start_year) = match resume {
            Some((parent, year, point)) => {
                let pid = parent_id(parent);
                let mut writer = RunWriter::create(
                    new.dir,
                    &NewRun { name: new.name, spec: Some(new.spec), parent: pid.as_deref(), branch_year: Some(year), engine: Some(&engine) },
                )
                .map_err(|e| issue("(svět)", e, "world_failed"))?;
                // snímky, slovník a záznam událostí rodiče do kontrolního bodu; bod může ležet i u prarodiče
                writer.branch_from(&point).map_err(|e| issue("(svět)", e, "world_failed"))?;
                let checkpoint = cee_store::load_checkpoint(&point).map_err(|e| issue("(svět)", e, "world_failed"))?;
                let simulation = spec::resume(&world_spec, checkpoint, SimulationConfig::default()).map_err(|e| issue("(svět)", e, "world_failed"))?;
                let recorder = Recorder::new(&simulation, RecordOptions::default());
                (simulation, writer, recorder, world_spec.start_year)
            }
            None => {
                let (world, events) = spec::build(&world_spec).map_err(|e| issue("(svět)", e, "world_failed"))?;
                let simulation = Simulation::new(world, SimulationConfig::default(), events).map_err(|e| issue("(svět)", e, "world_failed"))?;
                let parent_name = new.parent.and_then(parent_id);
                let mut writer = RunWriter::create(
                    new.dir,
                    &NewRun { name: new.name, spec: Some(new.spec), parent: parent_name.as_deref(), branch_year: None, engine: Some(&engine) },
                )
                .map_err(|e| issue("(svět)", e, "world_failed"))?;
                let recorder = Recorder::new(&simulation, RecordOptions::default());
                recorder.start(&simulation).write(&mut writer, 0.0).map_err(|e| issue("(svět)", e, "world_failed"))?;
                (simulation, writer, recorder, world_spec.start_year)
            }
        };
        // snímky převzaté od rodiče jsou hned k dispozici
        let frames = cee_store::frames(&writer.dir, 0).unwrap_or_default();
        let run = Arc::new(Run {
            dir: writer.dir.clone(),
            start_year,
            end_year: world_spec.end_year,
            started: Instant::now(),
            cancelled: AtomicBool::new(false),
            state: Mutex::new(RunState { status: Status::Running, year: simulation.year(), seconds: 0.0, error: None, frames, result: None }),
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
            .name("cee-run".into())
            .stack_size(64 * 1024 * 1024)
            .spawn(move || worker.execute(simulation, writer, recorder))
            .map_err(|e| issue("(svět)", e.to_string(), "world_failed"))?;
        Ok(run)
    }

    /// Běh v paměti podle id (cesty ke složce).
    pub fn get(&self, id: &str) -> Option<Arc<Run>> {
        self.runs.lock().expect("seznam běhů").iter().find(|r| r.id() == id).cloned()
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
        let dir = temp("kratky");
        let runs = Runs::default();
        let run = runs.start(StartRun { spec: &world, dir: &dir, name: Some("krátký"), parent: None }).expect("běh");
        wait(&run);
        let status = run.status(0);
        assert_eq!(status["status"], "done", "{status}");
        assert!(status["frame_count"].as_u64().unwrap() >= 2);
        let result = run.result().unwrap();
        assert_eq!(result["format"], "cee-v2/1");
        assert!(result["event_summary"].as_object().is_some_and(|o| !o.is_empty()));
        assert!(result.get("links").is_none());
        assert_eq!(result["year"], -400.0);
        // běh je na disku: info, snímky, slovník a výsledek
        let info = cee_store::info(&run.dir).unwrap();
        assert_eq!(info.status, Status::Done);
        assert!(info.has_result);
        assert_eq!(info.frames, status["frame_count"].as_u64().unwrap() as usize);
        assert!(!cee_store::lexicon_years(&run.dir).unwrap().is_empty());
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn co_kdyby_pokracuje_z_kontrolniho_bodu() {
        let mut world = talvera();
        world["end_year"] = json!(-200);
        let events: Vec<Value> = world["events"].as_array().unwrap().iter().filter(|e| e["year"].as_f64().unwrap() <= -200.0).cloned().collect();
        world["events"] = json!(events);
        let dir = temp("vetev");
        let runs = Runs::default();
        let parent = runs.start(StartRun { spec: &world, dir: &dir, name: None, parent: None }).expect("rodič");
        wait(&parent);
        // větev bez poslední události: počítá se od kontrolního bodu před jejím rokem
        let mut changed = world.clone();
        let last = changed["events"].as_array_mut().unwrap().pop().unwrap();
        let year = last["year"].as_f64().unwrap();
        let child = runs.start(StartRun { spec: &changed, dir: &dir, name: Some("bez poslední"), parent: Some(&parent.dir) }).expect("větev");
        wait(&child);
        assert_eq!(child.status(0)["status"], "done");
        let info = cee_store::info(&child.dir).unwrap();
        assert_eq!(info.parent.as_deref(), parent.dir.file_name().and_then(|n| n.to_str()));
        assert_eq!(info.branch_year, Some(year));
        // časová osa je celá: snímky převzaté od rodiče plus dopočítané
        assert_eq!(info.frames, cee_store::info(&parent.dir).unwrap().frames);
        let _ = std::fs::remove_dir_all(dir);
    }

    fn temp(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("cee-engine-test-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        d
    }

    fn wait(run: &Run) {
        let started = Instant::now();
        while run.status(0)["status"] == "running" {
            assert!(started.elapsed().as_secs() < 600, "běh trvá moc dlouho");
            std::thread::sleep(std::time::Duration::from_millis(100));
        }
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
        let dir = std::env::temp_dir().join("cee-mereni-talvera");
        let run = runs.start(StartRun { spec: &world, dir: &dir, name: None, parent: None }).expect("běh");
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

#[cfg(test)]
mod fixture {
    use super::*;

    /// Schéma enginu pro vývoj v prohlížeči (`static/fixtures/schema.json`).
    #[test]
    #[ignore]
    fn schema_vzorku() {
        let out = PathBuf::from(std::env::var("CEE_FIXTURES").expect("CEE_FIXTURES"));
        std::fs::write(out.join("schema.json"), schema().to_string()).unwrap();
    }

    /// Vzorek dat pro vývoj UI v prohlížeči ze skutečných běhů uložených přes `cee_store`:
    /// Talvera a větev „bez tvrdé politiky 1875“ z kontrolního bodu. Slovník v čase je rozbalený
    /// po rocích (`lexicon_years`), aby ho UI umělo i bez příkazů Tauri.
    /// `CEE_FIXTURES=~/Documents/CEE-worktrees/_fixtures cargo test --release --lib fixture -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn vzorek_talvery() {
        let out = PathBuf::from(std::env::var("CEE_FIXTURES").expect("CEE_FIXTURES"));
        let world: Value = serde_json::from_str(include_str!("../../static/projects/talvera.cee.json")).unwrap();
        let dir = std::env::temp_dir().join(format!("cee-vzorek-{}", std::process::id()));
        let runs = Runs::default();
        let wait = |run: &Run| {
            while run.status(0)["status"] == "running" {
                std::thread::sleep(std::time::Duration::from_millis(500));
            }
            assert_eq!(run.status(0)["status"], "done");
        };
        let t = Instant::now();
        let a = runs.start(StartRun { spec: &world, dir: &dir, name: Some("Talvera"), parent: None }).unwrap();
        wait(&a);
        println!("A {:.0} s", t.elapsed().as_secs_f64());
        let mut b_world = world.clone();
        b_world["events"] = json!(world["events"].as_array().unwrap().iter().filter(|e| !(e["kind"] == "language_policy" && e["policy"] == "enforced" && e["year"] == 1875.0)).cloned().collect::<Vec<_>>());
        let t = Instant::now();
        let b = runs.start(StartRun { spec: &b_world, dir: &dir, name: Some("bez tvrdé politiky 1875"), parent: Some(&a.dir) }).unwrap();
        wait(&b);
        println!("B (z kontrolního bodu) {:.0} s", t.elapsed().as_secs_f64());
        for (run, name) in [(&a, "talvera"), (&b, "talvera-bez-politiky")] {
            let years: Vec<Value> = cee_store::lexicon_years(&run.dir)
                .unwrap()
                .into_iter()
                .map(|(year, languages)| {
                    let langs: Map<String, Value> = languages
                        .iter()
                        .filter_map(|l| cee_store::lexicon(&run.dir, l, year).ok().flatten().map(|x| (l.clone(), json!({ "group": x.group, "forms": x.forms }))))
                        .collect();
                    json!({ "year": year, "languages": langs })
                })
                .collect();
            let data = json!({
                "world": cee_store::spec(&run.dir).unwrap(),
                "info": cee_store::info(&run.dir).unwrap(),
                "frames": cee_store::frames(&run.dir, 0).unwrap(),
                "result": *run.result().unwrap(),
                "lexicon_years": years,
            });
            std::fs::write(out.join(format!("{name}.json")), data.to_string()).unwrap();
            println!("{name}: {} MB", data.to_string().len() / 1_000_000);
        }
        let _ = std::fs::remove_dir_all(dir);
    }
}

#[cfg(test)]
mod rezie {
    use super::*;

    /// Kolik stojí zápis běhu, rozpad podle částí (sběr, slovník, záznam událostí, kontrolní body,
    /// snímky) a velikost složky: `cargo test --release --lib rezie -- --ignored --nocapture`.
    /// `CEE_REZIE_DO` = rok konce (výchozí 800).
    #[test]
    #[ignore]
    fn rezie_zapisu() {
        let until: f64 = std::env::var("CEE_REZIE_DO").ok().and_then(|v| v.parse().ok()).unwrap_or(800.0);
        let mut world: Value = serde_json::from_str(include_str!("../../static/projects/talvera.cee.json")).unwrap();
        world["end_year"] = json!(until);
        let events: Vec<Value> = world["events"].as_array().unwrap().iter().filter(|e| e["year"].as_f64().unwrap() <= until).cloned().collect();
        world["events"] = json!(events);
        let ws = WorldSpec::from_json(&world.to_string()).unwrap();
        for record in [false, true] {
            let (w, events) = spec::build(&ws).unwrap();
            let mut sim = Simulation::new(w, SimulationConfig::default(), events).unwrap();
            let dir = std::env::temp_dir().join(format!("cee-rezie-{}", std::process::id()));
            let _ = std::fs::remove_dir_all(&dir);
            let mut writer = RunWriter::create(&dir, &NewRun { spec: Some(&world), ..Default::default() }).unwrap();
            let mut recorder = Recorder::new(&sim, RecordOptions::default());
            if record {
                recorder.start(&sim).write(&mut writer, 0.0).unwrap();
            }
            let mut t = BTreeMap::<&str, f64>::new();
            let mut add = |k: &'static str, since: Instant| *t.entry(k).or_default() += since.elapsed().as_secs_f64();
            while sim.year() + sim.config.dt <= ws.end_year + 1e-9 {
                let at = Instant::now();
                sim.step().unwrap();
                add("krok", at);
                if !record {
                    continue;
                }
                let at = Instant::now();
                let batch = recorder.collect(&sim).unwrap();
                add("sběr (snímek, slovník, bod)", at);
                let at = Instant::now();
                if let Some((year, lexicons)) = &batch.lexicon {
                    writer.add_lexicon(*year, lexicons).unwrap();
                }
                add("zápis slovníku", at);
                let at = Instant::now();
                writer.add_events(&batch.events).unwrap();
                add("zápis událostí", at);
                let at = Instant::now();
                if let Some((tick, year, n, bytes)) = &batch.checkpoint {
                    writer.add_checkpoint(*tick, *year, *n, bytes).unwrap();
                }
                add("zápis bodů", at);
                let at = Instant::now();
                if let Some(frame) = &batch.frame {
                    writer.add_frame(frame, 0.0).unwrap();
                }
                add("zápis snímků", at);
            }
            if record {
                let at = Instant::now();
                writer.wait().unwrap();
                add("čekání na poslední bod", at);
            }
            let total: f64 = t.values().sum();
            println!("{} do roku {until}: celkem {total:.1} s", if record { "SE ZÁPISEM" } else { "BEZ ZÁPISU" });
            for (k, v) in &t {
                println!("  {k:28} {v:7.1} s");
            }
            if record {
                println!("  složka (bajty): {:?}", cee_store::size(&writer.dir));
            }
            let _ = std::fs::remove_dir_all(&dir);
        }
    }
}
